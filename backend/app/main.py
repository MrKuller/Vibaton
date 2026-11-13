"""Крепкий лёд — API.

Run:  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs

The map is a grid of water cells (data/grid.geojson). Reading needs no account;
publishing, reacting and uploading photos do.
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Annotated
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Path as PathParam, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, TimeoutError as PoolTimeout
from sqlalchemy.orm import Session, selectinload

from fastapi.exceptions import RequestValidationError

from . import ai, anonymizer, clusters, errors, geo, ice_vision, moderation, status as st, vision
from . import grid as gridmod
from .auth import active_user, current_user, is_moderator, moderator, optional_user, router as auth_router
from .config import UPLOADS_DIR
from .db import Base, SessionLocal, engine, get_db
from .models import ModerationAction, Observation, PhotoAnalysis, Reaction, Report, User, Zone, utcnow
from .protection import ProtectionMiddleware, photo_slots, read_cache
from .schemas import ModerationIn, ObservationIn, ObservationOut, PhotoInfo, ReactionIn, ReportIn, StatusOut
from .weather import get_weather

log = logging.getLogger("krepkiy")

ONSITE_MAX_M = 300          # GPS must be within 300 m of the cell
ONSITE_MAX_ACCURACY_M = 50
CONFIRM_MAX_M = 2000        # confirming needs you to be nearby
POSTS_PER_HOUR = 10
# anything outside the database integer range is a 422 with a message, not a crash
ObsId = Annotated[int, PathParam(ge=1, le=2_147_483_647, description="номер наблюдения")]
MAX_PHOTO_BYTES = 8 * 1024 * 1024
REJECT_NOT_ICE_CONFIDENCE = 0.7

LEVEL_TEXT = {
    "danger": ("Опасно", "Не выходите на лёд на этом участке."),
    "risk": ("Есть риск", "Не уходите дальше 200 м от берега без крайней необходимости. Проверяйте лёд пешнёй."),
    "clear": ("Тревог нет", "Свежие сообщения без тревог. Это не значит, что лёд безопасен: проверяйте его сами."),
    "nodata": ("Нет свежих данных", "Свежих наблюдений нет. Обстановка неизвестна."),
}


def grid() -> gridmod.Grid:
    return gridmod.load()


def sync_zones(db: Session) -> None:
    """Make sure every grid cell has a row (observations reference cells by foreign key).

    When the grid is rebuilt, observations on cells that no longer exist move to the new cell under
    their GPS point; old cells without observations are removed.
    """
    g = grid()
    have = set(db.scalars(select(Zone.id)))
    missing = [Zone(id=c.id, bay=c.bay[:80], place_id=c.place.id if c.place else None)
               for c in g.cells.values() if c.id not in have]
    if missing:
        db.add_all(missing)
        db.commit()
    stale = have - set(g.cells)
    if not stale:
        return
    moved = 0
    for o in db.scalars(select(Observation).where(Observation.zone_id.in_(stale))):
        if o.lat is not None and o.lon is not None:
            cell, dist = g.cell_for_point(o.lat, o.lon)
            if cell and dist <= gridmod.SNAP_MAX_M:
                o.zone_id = cell.id
                moved += 1
    db.commit()
    used = set(db.scalars(select(Observation.zone_id).where(Observation.zone_id.in_(stale))))
    for z in db.scalars(select(Zone).where(Zone.id.in_(stale - used))):
        db.delete(z)
    db.commit()
    log.info("grid changed: %d observations moved to new cells, %d left on old cells", moved, len(used))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_zones(db)
    yield


app = FastAPI(title="Крепкий лёд API", version="0.4.0", lifespan=lifespan)
app.add_middleware(ProtectionMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")  # only anonymized copies
app.include_router(auth_router)


app.add_exception_handler(RequestValidationError, errors.validation_error)
app.add_exception_handler(Exception, errors.unexpected_error)


@app.exception_handler(PoolTimeout)
@app.exception_handler(OperationalError)
async def db_overloaded(_: Request, exc: Exception):
    log.warning("database unavailable or overloaded: %s", exc)
    return JSONResponse({"detail": "Сервер перегружен. Повторите через минуту."}, status_code=503,
                        headers={"Retry-After": "30"})


# ---------- helpers ----------
def now() -> datetime:
    return datetime.now(timezone.utc)


def bay_weather(bay: str):
    lat, lon = grid().bay_centers[bay]
    return get_weather(lat, lon)


def cell_or_404(zone_id: str) -> gridmod.Cell:
    c = grid().resolve(zone_id)
    if not c:
        raise HTTPException(404, "Участок не найден")
    return c


def recent_obs(db: Session, zone_ids: list[str] | None = None, hours: int = 24, user_id: int | None = None,
               include_hidden: bool = False) -> list[Observation]:
    since = (now() - timedelta(hours=hours)).replace(tzinfo=None)
    q = (select(Observation)
         .options(selectinload(Observation.reactions), selectinload(Observation.user),
                  selectinload(Observation.photo_analysis), selectinload(Observation.reports))
         .where(Observation.observed_at >= since)
         .order_by(Observation.observed_at.desc())
         .limit(5000))  # a hard cap: no request may pull the whole table
    if zone_ids is not None:
        q = q.where(Observation.zone_id.in_(zone_ids))
    if user_id is not None:
        q = q.where(Observation.user_id == user_id)
    if not include_hidden:
        q = q.where(Observation.moderation_status != "hidden")
    return list(db.scalars(q))


def people(n: int) -> str:
    return f"{n} человека" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else f"{n} человек"


def cell_status(c: gridmod.Cell, obs: list[Observation], cl: list[clusters.Cluster]) -> st.ZoneStatus:
    s = st.compute(c, obs, bay_weather(c.bay))
    for k in cl:
        if k.zone_id == c.id:
            s.reasons.insert(1 if c.ban else 0,
                             f"{people(k.users)} независимо сообщили об опасности в радиусе {clusters.RADIUS_M} м")
    return s


def status_out(s: st.ZoneStatus) -> StatusOut:
    label, advice = LEVEL_TEXT[s.level]
    return StatusOut(level=s.level, label=label, advice=advice, reasons=s.reasons, fresh_count=s.fresh_count,
                     fresh_window_h=s.fresh_window_h, last_observed_at=s.last_observed_at,
                     conflict=s.conflict, offshore_wind=s.offshore_wind)


def photo_info(o: Observation) -> PhotoInfo | None:
    pa = o.photo_analysis
    if not pa:
        return None
    return PhotoInfo(
        faces_blurred=pa.face_count, plates_blurred=pa.plate_count, privacy_processed=pa.privacy_processed,
        privacy_detector=pa.privacy_detector, privacy_status=pa.privacy_status, looks_like_ice=pa.looks_like_ice,
        material=pa.material or {}, texture=pa.texture, crack_score=pa.crack_score, signs=pa.detected_signs or [],
        hazard=pa.hazard, source=pa.analysis_source, ai_checked="ollama" in (pa.analysis_source or ""),
    )


def obs_out(o: Observation, me: User | None) -> ObservationOut:
    age = now() - st.as_utc(o.observed_at)
    fresh = "fresh" if age < st.FRESH else "stale" if age < st.STALE else "old"
    lat, lon = o.lat, o.lon
    if lat is not None and lon is not None and o.hide_point and st.severity(o) == "clear":
        lat, lon = geo.coarsen(lat, lon)  # hazards stay exact, calm "thickness" posts are blurred
    my = next((r.kind for r in o.reactions if me and r.user_id == me.id), None)
    cell = grid().cells.get(o.zone_id)
    mine, mod = bool(me and o.user_id == me.id), is_moderator(me)
    text, photo_url, photo = o.text, (f"/uploads/{o.photo_path}" if o.photo_path else None), photo_info(o)
    note = None
    if o.moderation_status == "pending":
        if mine or mod:
            note = "На проверке у модератора: другие пока не видят текст и фото."
        else:
            text, photo_url, photo = "", None, None
            note = "Текст и фото на проверке у модератора. Сигнал об опасности уже учитывается на карте."
    elif o.moderation_status == "hidden":
        note = "Скрыто модератором" + (f": {o.moderation_reason}" if o.moderation_reason and (mine or mod) else "")
    return ObservationOut(
        id=o.id, zone_id=o.zone_id, zone_name=cell.name if cell else o.zone_id, type=o.type,
        type_label=st.TYPES[o.type][0], severity=st.severity(o), thickness_cm=o.thickness_cm, method=o.method,
        ice_type=o.ice_type, text=text, lat=lat, lon=lon, onsite=o.onsite, gps_accuracy_m=o.gps_accuracy_m,
        author="Аноним" if o.anonymous else o.user.display_name,
        photo_url=photo_url, photo=photo,
        ai_hazard=o.ai_hazard, ai_tags=o.ai_tags or [], observed_at=st.as_utc(o.observed_at),
        age_min=int(age.total_seconds() // 60), freshness=fresh, counts=o.counts, my_reaction=my,
        mine=mine, excluded=st.is_wrong(o) or fresh == "old" or not st.counts_for_status(o),
        moderation_status=o.moderation_status, moderation_note=note,
        reports_count=sum(not r.resolved for r in o.reports) if mod else 0,
        my_report=bool(me and any(r.user_id == me.id for r in o.reports)),
    )


def load_obs(db: Session, obs_id: int) -> Observation:
    o = db.scalar(select(Observation).where(Observation.id == obs_id)
                  .options(selectinload(Observation.reactions), selectinload(Observation.user),
                           selectinload(Observation.photo_analysis), selectinload(Observation.reports)))
    if not o:
        raise HTTPException(404, "Наблюдение не найдено")
    return o


# ---------- map ----------
@app.get("/health")
def health():
    return {"ok": True, "db": engine.dialect.name,
            "llm": "disabled" if ai._ollama_disabled() else ai.OLLAMA_MODEL,
            "privacy_model": anonymizer.detector_name(), "privacy_model_error": anonymizer.detector_error(),
            "ice_model": "cv+model" if ice_vision.ice_model() else "cv", "cells": len(grid().cells)}


@app.get("/grid")
def get_grid(request: Request):
    """All water cells: [h3 id, kind, bay, lat, lon]. The app draws hexagons from the H3 ids.
    Static: downloaded once and cached on the phone."""
    g = grid()
    headers = {"ETag": f'"{g.etag}"', "Cache-Control": "public, max-age=86400"}
    if request.headers.get("if-none-match") == f'"{g.etag}"':
        return Response(status_code=304, headers=headers)
    return Response(content=g.compact_bytes, media_type="application/json", headers=headers)


@app.get("/places")
def places():
    g = grid()
    return [{"id": p.id, "name": p.name, "bay": p.bay, "lat": p.lat, "lon": p.lon, "cell_id": p.cell_id,
             "ban": p.ban, "ban_text": p.ban_text} for p in g.places.values()]


def compute_status(db: Session) -> dict:
    g = grid()
    obs = recent_obs(db)
    cl = clusters.find_clusters(obs, now())
    by_cell: dict[str, list[Observation]] = {}
    for o in obs:
        by_cell.setdefault(o.zone_id, []).append(o)
    out: dict[str, dict] = {}
    for cid in set(by_cell) | {c.id for c in g.cells.values() if c.ban}:
        c = g.cells.get(cid)
        if not c:
            continue
        s = cell_status(c, by_cell.get(cid, []), cl)
        if s.level == "nodata" and not s.last_observed_at:
            continue
        out[cid] = {"level": s.level, "label": LEVEL_TEXT[s.level][0], "fresh_count": s.fresh_count,
                    "last_observed_at": s.last_observed_at.isoformat() if s.last_observed_at else None,
                    "reason": s.reasons[0] if s.reasons else LEVEL_TEXT[s.level][1]}
    return {"generated_at": now().isoformat(), "default": "nodata", "cells": out}


@app.get("/status")
def status(db: Session = Depends(get_db)):
    """Statuses of cells that are NOT grey. Every other cell is "нет данных". Cached for 20 s."""
    hit = read_cache.get("status")
    if hit is None:
        hit = compute_status(db)
        read_cache.put("status", hit)
    return hit


@app.get("/zones/{zone_id}")
def zone_detail(zone_id: str, db: Session = Depends(get_db), me: User | None = Depends(optional_user)):
    c = cell_or_404(zone_id)
    obs = recent_obs(db, [c.id], hours=48)
    s = cell_status(c, obs, clusters.find_clusters(recent_obs(db, hours=6), now()))
    return {
        "id": c.id, "name": c.name, "bay": c.bay, "kind": c.kind, "river": c.river, "ban": c.ban, "ban_text": c.ban_text,
        "place": {"id": c.place.id, "name": c.place.name} if c.place else None,
        "center": {"lat": c.lat, "lon": c.lon}, "geometry": c.geometry,
        "status": status_out(s), "weather": bay_weather(c.bay).to_dict(),
        "observations": [obs_out(o, me) for o in obs],
    }


@app.get("/clusters")
def get_clusters(db: Session = Depends(get_db)):
    """Places where several different people reported danger within 200 m in the last 6 h."""
    hit = read_cache.get("clusters")
    if hit is None:
        hit = [c.__dict__ for c in clusters.find_clusters(recent_obs(db, hours=6), now())]
        read_cache.put("clusters", hit)
    return hit


# ---------- observations ----------
@app.get("/observations", response_model=list[ObservationOut])
def observations(
    db: Session = Depends(get_db), me: User | None = Depends(optional_user),
    zone_id: str | None = None, lat: float | None = None, lon: float | None = None,
    radius_km: float | None = Query(default=None, gt=0, le=50),
    only_hazards: bool = False, fresh_only: bool = False, mine: bool = False,
    hours: int = Query(default=48, ge=1, le=24 * 30), limit: int = Query(default=100, ge=1, le=200),
):
    if mine and not me:
        raise HTTPException(401, "Войдите в аккаунт, чтобы увидеть свои наблюдения")
    zone_ids = [cell_or_404(zone_id).id] if zone_id else None
    obs = recent_obs(db, zone_ids, hours=hours, user_id=me.id if mine and me else None, include_hidden=mine)
    cells = grid().cells
    out = []
    for o in obs:
        if only_hazards and st.severity(o) == "clear":
            continue
        if fresh_only and now() - st.as_utc(o.observed_at) >= st.FRESH:
            continue
        if radius_km and lat is not None and lon is not None:
            c = cells.get(o.zone_id)
            if not c or geo.haversine_m(lat, lon, c.lat, c.lon) > radius_km * 1000:
                continue
        out.append(obs_out(o, me))
        if len(out) >= limit:
            break
    return out


@app.post("/observations", response_model=ObservationOut, status_code=201)
def create_observation(body: ObservationIn, db: Session = Depends(get_db), me: User = Depends(active_user)):
    hour_ago = (now() - timedelta(hours=1)).replace(tzinfo=None)
    recent = db.scalars(select(Observation.id).where(Observation.user_id == me.id, Observation.created_at >= hour_ago)).all()
    if len(recent) >= POSTS_PER_HOUR:
        raise HTTPException(429, "Слишком много публикаций за час. Попробуйте позже.")

    g = grid()
    cell, dist = None, None
    if body.lat is not None and body.lon is not None:
        cell, dist = g.cell_for_point(body.lat, body.lon)
        if dist > gridmod.SNAP_MAX_M:
            if not body.zone_id:
                raise HTTPException(422, "Вы далеко от льда заливов. Выберите участок вручную.")
            cell, dist = None, None
    if cell is None:
        if not body.zone_id:
            raise HTTPException(422, "Укажите участок или включите геолокацию")
        cell = g.resolve(body.zone_id)
        if not cell:
            raise HTTPException(404, "Участок не найден")
        if body.lat is not None and body.lon is not None:
            dist = geo.distance_to_zone_m(body.lat, body.lon, cell.geometry)
    if body.type == "clear" and body.thickness_cm is not None and body.thickness_cm < 10:
        raise HTTPException(422, "При толщине меньше 10 см выберите «Тонкий лёд», а не «Без тревог».")

    onsite = (dist is not None and dist <= ONSITE_MAX_M and not body.mocked_location
              and (body.gps_accuracy_m or 999) <= ONSITE_MAX_ACCURACY_M)
    observed = min(st.as_utc(body.observed_at or now()), now())
    if now() - observed > timedelta(hours=24):
        raise HTTPException(422, "Наблюдение старше суток: обстановка могла измениться.")
    verdict = moderation.check_text(body.text)
    if verdict.action == "reject":
        raise HTTPException(422, verdict.reason)
    cls = ai.classify(body.text)

    o = Observation(
        zone_id=cell.id, user_id=me.id, type=body.type, thickness_cm=body.thickness_cm,
        method=body.method if body.thickness_cm is not None else None, ice_type=body.ice_type, text=body.text,
        lat=body.lat, lon=body.lon, gps_accuracy_m=body.gps_accuracy_m, onsite=onsite, hide_point=body.hide_point,
        anonymous=body.anonymous, ai_hazard=cls["hazard"], ai_tags=cls["tags"], ai_source=cls["source"],
        observed_at=observed.replace(tzinfo=None),
        moderation_status="pending" if verdict.action == "review" else "ok",
        moderation_reason=verdict.reason or None,
    )
    db.add(o)
    db.flush()
    if verdict.action == "review":
        db.add(ModerationAction(observation_id=o.id, target_user_id=me.id, action="auto_review", note=verdict.reason[:300]))
    db.commit()
    read_cache.clear()
    return obs_out(load_obs(db, o.id), me)


@app.delete("/observations/{obs_id}", status_code=204)
def delete_observation(obs_id: ObsId, db: Session = Depends(get_db), me: User = Depends(current_user)):
    o = load_obs(db, obs_id)
    if o.user_id != me.id and me.role not in ("moderator", "admin"):
        raise HTTPException(403, "Удалить можно только своё наблюдение")
    if o.photo_path:
        (UPLOADS_DIR / o.photo_path).unlink(missing_ok=True)
    db.delete(o)
    db.commit()
    read_cache.clear()


@app.post("/observations/{obs_id}/reactions", response_model=ObservationOut)
def react(obs_id: ObsId, body: ReactionIn, db: Session = Depends(get_db), me: User = Depends(active_user)):
    o = load_obs(db, obs_id)
    if o.user_id == me.id:
        raise HTTPException(403, "Нельзя оценивать своё наблюдение")
    if body.kind == "confirm":
        if body.lat is None or body.lon is None:
            raise HTTPException(403, "Подтвердить можно только рядом с участком: включите геолокацию")
        if geo.distance_to_zone_m(body.lat, body.lon, cell_or_404(o.zone_id).geometry) > CONFIRM_MAX_M:
            raise HTTPException(403, "Подтвердить можно только рядом с участком (до 2 км)")
    existing = next((r for r in o.reactions if r.user_id == me.id), None)
    if existing:
        o.reactions.remove(existing)
        db.flush()
    if body.kind:
        o.reactions.append(Reaction(user_id=me.id, kind=body.kind))
    db.commit()
    read_cache.clear()
    return obs_out(load_obs(db, obs_id), me)


def process_photo(data: bytes):
    """CPU-heavy, runs in a worker thread: check → model 1 (privacy) → model 2 (ice) → optional VLM."""
    img = anonymizer.decode(data)
    vision.basic_check(img)
    phash = moderation.dhash(img)
    anon = anonymizer.anonymize(img)
    ice = ice_vision.analyze(anonymizer.decode(anon.jpeg))  # models only ever see the blurred copy
    vlm = vision.ai_check(anon.jpeg)
    return anon, ice, vlm, phash


@app.post("/observations/{obs_id}/photo", response_model=ObservationOut)
async def upload_photo(obs_id: ObsId, file: UploadFile = File(...), db: Session = Depends(get_db),
                       me: User = Depends(active_user)):
    o = load_obs(db, obs_id)
    if o.user_id != me.id:
        raise HTTPException(404, "Наблюдение не найдено")
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Фото больше 8 МБ")
    if photo_slots.locked():
        log.info("photo queue is full, waiting")
    async with photo_slots:  # at most PHOTO_WORKERS photos are processed at once
        try:
            anon, ice, vlm, phash = await run_in_threadpool(process_photo, data)
        except vision.PhotoRejected as e:
            raise HTTPException(422, str(e))
    since = (now() - timedelta(days=60)).replace(tzinfo=None)
    seen = db.execute(select(PhotoAnalysis.phash).where(PhotoAnalysis.phash.is_not(None),
                                                        PhotoAnalysis.observation_id != o.id,
                                                        PhotoAnalysis.created_at >= since).limit(50_000)).scalars()
    if any(moderation.hamming(phash, h) <= moderation.DUPLICATE_MAX_DISTANCE for h in seen):
        raise HTTPException(422, "Это фото уже публиковалось. Сделайте новый снимок на месте.")
    if vlm.looks_like_ice is False and (vlm.confidence or 0) >= REJECT_NOT_ICE_CONFIDENCE:
        raise HTTPException(422, "На фото не видно льда, снега или воды. Снимите участок, о котором сообщаете.")

    signs = sorted(set(ice.signs) | set(vlm.signs))
    order = {"none": 0, "risk": 1, "danger": 2}
    hazard = max(ice.hazard, vlm.hazard, key=order.__getitem__)
    source = ice.source + ("+ollama" if vlm.source == "ollama" else "")

    name = f"{uuid.uuid4().hex}.jpg"
    (UPLOADS_DIR / name).write_bytes(anon.jpeg)
    if o.photo_path:
        (UPLOADS_DIR / o.photo_path).unlink(missing_ok=True)
    o.photo_path = name
    o.photo_hazard = hazard
    pa = o.photo_analysis or PhotoAnalysis(observation_id=o.id)
    pa.face_count, pa.plate_count, pa.privacy_processed = anon.face_count, anon.plate_count, True
    pa.privacy_detector, pa.privacy_status = anon.detector, anon.status
    pa.privacy_detections = [{"kind": d.kind, "confidence": d.confidence} for d in anon.detections]
    pa.material, pa.texture, pa.crack_score = ice.material, ice.texture, ice.crack_score
    pa.looks_like_ice = vlm.looks_like_ice if vlm.looks_like_ice is not None else ice.looks_like_ice
    pa.detected_signs, pa.hazard = signs, hazard
    pa.confidence = max(ice.confidence, vlm.confidence or 0)
    pa.analysis_source, pa.analysis_status, pa.width, pa.height = source, vlm.status, anon.width, anon.height
    pa.phash = phash
    o.photo_analysis = pa
    db.commit()
    read_cache.clear()
    return obs_out(load_obs(db, obs_id), me)


# ---------- reports and moderation ----------
@app.post("/observations/{obs_id}/reports", status_code=201)
def report(obs_id: ObsId, body: ReportIn, db: Session = Depends(get_db), me: User = Depends(active_user)):
    """A complaint. After REPORTS_TO_REVIEW different people the post goes to the moderator queue:
    its text and photo are hidden; a danger signal still counts on the map."""
    o = load_obs(db, obs_id)
    if o.user_id == me.id:
        raise HTTPException(403, "Нельзя пожаловаться на своё наблюдение")
    if any(r.user_id == me.id for r in o.reports):
        raise HTTPException(409, "Вы уже пожаловались на это наблюдение")
    o.reports.append(Report(user_id=me.id, reason=body.reason, comment=body.comment))
    open_reports = [r for r in o.reports if not r.resolved]
    if o.moderation_status == "ok" and len({r.user_id for r in open_reports}) >= moderation.REPORTS_TO_REVIEW:
        o.moderation_status = "pending"
        o.moderation_reason = "Жалобы: " + ", ".join(sorted({moderation.REPORT_REASONS[r.reason] for r in open_reports}))
        db.add(ModerationAction(observation_id=o.id, target_user_id=o.user_id, action="auto_review", note=o.moderation_reason))
    db.commit()
    read_cache.clear()
    return {"ok": True, "message": "Спасибо, жалоба отправлена модераторам."}


@app.get("/moderation/queue")
def moderation_queue(db: Session = Depends(get_db), me: User = Depends(moderator)):
    """Posts on review and posts with open reports, newest first."""
    q = (select(Observation)
         .options(selectinload(Observation.reactions), selectinload(Observation.user),
                  selectinload(Observation.photo_analysis), selectinload(Observation.reports))
         .where((Observation.moderation_status == "pending")
                | Observation.id.in_(select(Report.observation_id).where(Report.resolved.is_(False))))
         .order_by(Observation.created_at.desc()).limit(200))
    out = []
    for o in db.scalars(q):
        item = obs_out(o, me).model_dump(mode="json")
        item["moderation_reason"] = o.moderation_reason
        item["author_id"] = o.user_id
        item["author_name"] = o.user.display_name
        item["author_banned_until"] = o.user.banned_until.isoformat() + "Z" if o.user.banned_until else None
        item["reports"] = [{"reason": moderation.REPORT_REASONS[r.reason], "comment": r.comment}
                           for r in o.reports if not r.resolved]
        out.append(item)
    return out


@app.post("/moderation/observations/{obs_id}")
def moderate(obs_id: ObsId, body: ModerationIn, db: Session = Depends(get_db), me: User = Depends(moderator)):
    o = load_obs(db, obs_id)
    note = body.note.strip()
    if body.action == "approve":
        o.moderation_status, o.moderation_reason = "ok", None
    elif body.action == "hide":
        o.moderation_status, o.moderation_reason = "hidden", note or "нарушение правил"
    for r in o.reports:
        r.resolved = True
    author = o.user
    db.add(ModerationAction(moderator_id=me.id, observation_id=o.id, target_user_id=author.id, action=body.action, note=note))
    if body.ban_days:
        if author.role in ("moderator", "admin"):
            raise HTTPException(403, "Модератора может заблокировать только администратор через консоль")
        author.banned_until = utcnow() + timedelta(days=body.ban_days)
        author.ban_reason = note or "нарушение правил"
        db.add(ModerationAction(moderator_id=me.id, observation_id=o.id, target_user_id=author.id, action="ban",
                                note=f"{body.ban_days} дн. {note}"[:300]))
    if body.action == "delete":
        if o.photo_path:
            (UPLOADS_DIR / o.photo_path).unlink(missing_ok=True)
        db.delete(o)
    db.commit()
    read_cache.clear()
    return {"ok": True}


# ---------- weather and alerts ----------
@app.get("/weather")
def weather(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    return get_weather(lat, lon).to_dict()


@app.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    """Official bans, clusters of independent danger reports and bay-level AI warnings, each with sources."""
    hit = read_cache.get("alerts")
    if hit is not None:
        return hit
    g = grid()
    obs = recent_obs(db)
    out: list[dict] = [{"kind": "ban", "zone_id": p.cell_id, "zone_name": p.name, "text": p.ban_text or "Запрет выхода на лёд",
                        "critical": True, "lat": p.lat, "lon": p.lon} for p in g.places.values() if p.ban]
    for c in clusters.find_clusters(obs, now()):
        cell = g.cells[c.zone_id]
        out.append({"kind": "cluster", "critical": c.level == "danger", "zone_id": c.zone_id, "zone_name": cell.name,
                    "text": f"{people(c.users)} независимо сообщили об опасности в радиусе {clusters.RADIUS_M} м. "
                            "Требуется проверка участка.",
                    "lat": c.lat, "lon": c.lon, "level": c.level, "observation_ids": c.observation_ids})
    defaults = {c.bay: c.offshore_from for c in g.cells.values() if not c.place}
    for bay in sorted(g.bay_centers):
        w = bay_weather(bay)
        offshore = geo.angle_in_ranges(w.wind_from_deg, defaults.get(bay, []))
        hazards = [o for o in obs if (c := g.cells.get(o.zone_id)) and c.bay == bay
                   and st.severity(o) != "clear" and not st.is_wrong(o)]
        warn = ai.bay_warning(bay, w, hazards, offshore)
        if warn:
            out.append({"kind": "ai", "critical": False, **warn})
    read_cache.put("alerts", out)
    return out
