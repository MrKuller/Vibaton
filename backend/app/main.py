"""Крепкий лёд — API.

Run:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs: http://localhost:8000/docs

Identity for the MVP is an anonymous device id sent in the X-Device-Id header.
Phone verification is the next step (see README).
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import ai, geo, status as st
from .db import DATA_DIR, Base, engine, get_db, SessionLocal
from .models import Observation, Reaction, Zone
from .schemas import ObservationIn, ObservationOut, ReactionIn, StatusOut
from .weather import get_weather

UPLOADS = DATA_DIR / "uploads"
ONSITE_MAX_M = 300          # GPS must be within 300 m of the zone
ONSITE_MAX_ACCURACY_M = 50
CONFIRM_MAX_M = 2000        # confirming needs you to be nearby
NEAREST_ZONE_MAX_M = 3000
POSTS_PER_HOUR = 10
MAX_PHOTO_BYTES = 5 * 1024 * 1024

LEVEL_TEXT = {
    "danger": ("Опасно", "Не выходите на лёд на этом участке."),
    "risk": ("Есть риск", "Не уходите дальше 200 м от берега без крайней необходимости. Проверяйте лёд пешнёй."),
    "clear": ("Тревог нет", "Свежие сообщения без тревог. Это не значит, что лёд безопасен: проверяйте его сами."),
    "nodata": ("Нет свежих данных", "Свежих наблюдений нет. Обстановка неизвестна."),
}

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_zones(db)
    yield


app = FastAPI(title="Крепкий лёд API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
UPLOADS.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")


def sync_zones(db: Session) -> None:
    """Upsert zones from data/zones.geojson so the team edits zones in one file."""
    for f in geo.load_zones_geojson()["features"]:
        p = f["properties"]
        z = db.get(Zone, p["id"]) or Zone(id=p["id"])
        z.name, z.bay, z.geometry = p["name"], p["bay"], f["geometry"]
        z.offshore_from = p.get("offshore_from", [])
        z.ban, z.ban_text = bool(p.get("ban")), p.get("ban_text")
        db.add(z)
    db.commit()


def device(x_device_id: str | None = Header(default=None)) -> str:
    if not x_device_id or not (8 <= len(x_device_id) <= 64):
        raise HTTPException(400, "Нужен заголовок X-Device-Id (8–64 символа)")
    return x_device_id


def optional_device(x_device_id: str | None = Header(default=None)) -> str | None:
    return x_device_id


# ---------- helpers ----------
def now() -> datetime:
    return datetime.now(timezone.utc)


def zone_weather(z: Zone):
    lat, lon = geo.centroid(z.geometry)
    return get_weather(lat, lon)


def recent_obs(db: Session, zone_id: str | None = None, hours: int = 24) -> list[Observation]:
    q = (select(Observation).options(selectinload(Observation.reactions), selectinload(Observation.zone))
         .where(Observation.observed_at >= now() - timedelta(hours=hours))
         .order_by(Observation.observed_at.desc()))
    if zone_id:
        q = q.where(Observation.zone_id == zone_id)
    return list(db.scalars(q))


def status_out(s: st.ZoneStatus) -> StatusOut:
    label, advice = LEVEL_TEXT[s.level]
    return StatusOut(level=s.level, label=label, advice=advice, reasons=s.reasons, fresh_count=s.fresh_count,
                     fresh_window_h=s.fresh_window_h, last_observed_at=s.last_observed_at,
                     conflict=s.conflict, offshore_wind=s.offshore_wind)


def obs_out(o: Observation, dev: str | None) -> ObservationOut:
    age = now() - st.as_utc(o.observed_at)
    fresh = "fresh" if age < st.FRESH else "stale" if age < st.STALE else "old"
    lat, lon = o.lat, o.lon
    if lat is not None and lon is not None and o.hide_point and st.severity(o) == "clear":
        lat, lon = geo.coarsen(lat, lon)  # hazards stay exact, calm "thickness" posts are blurred
    my = next((r.kind for r in o.reactions if dev and r.device_id == dev), None)
    return ObservationOut(
        id=o.id, zone_id=o.zone_id, zone_name=o.zone.name, type=o.type, type_label=st.TYPES[o.type][0],
        severity=st.severity(o), thickness_cm=o.thickness_cm, method=o.method, ice_type=o.ice_type, text=o.text,
        lat=lat, lon=lon, onsite=o.onsite, gps_accuracy_m=o.gps_accuracy_m,
        author="Аноним" if o.anonymous or not o.author_name else o.author_name,
        photo_url=f"/uploads/{o.photo_path}" if o.photo_path else None,
        ai_hazard=o.ai_hazard, ai_tags=o.ai_tags or [], observed_at=st.as_utc(o.observed_at),
        age_min=int(age.total_seconds() // 60), freshness=fresh, counts=o.counts, my_reaction=my,
        mine=bool(dev and o.device_id == dev), excluded=st.is_wrong(o) or fresh == "old",
    )


def nearest_zone(db: Session, lat: float, lon: float) -> tuple[Zone | None, float]:
    best, best_d = None, float("inf")
    for z in db.scalars(select(Zone)):
        d = geo.distance_to_zone_m(lat, lon, z.geometry)
        if d < best_d:
            best, best_d = z, d
    return best, best_d


# ---------- routes ----------
@app.get("/health")
def health():
    return {"ok": True, "llm": "disabled" if ai._ollama_disabled() else ai.OLLAMA_MODEL}


@app.get("/zones")
def zones(db: Session = Depends(get_db)):
    """GeoJSON FeatureCollection; each feature carries its computed status."""
    obs = recent_obs(db)
    features = []
    for z in db.scalars(select(Zone).order_by(Zone.name)):
        s = st.compute(z, [o for o in obs if o.zone_id == z.id], zone_weather(z))
        lat, lon = geo.centroid(z.geometry)
        features.append({
            "type": "Feature", "id": z.id, "geometry": z.geometry,
            "properties": {"id": z.id, "name": z.name, "bay": z.bay, "ban": z.ban, "ban_text": z.ban_text,
                           "center": {"lat": lat, "lon": lon},
                           "status": status_out(s).model_dump(mode="json")},
        })
    return {"type": "FeatureCollection", "features": features}


@app.get("/zones/{zone_id}")
def zone_detail(zone_id: str, db: Session = Depends(get_db), dev: str | None = Depends(optional_device)):
    z = db.get(Zone, zone_id)
    if not z:
        raise HTTPException(404, "Участок не найден")
    obs = recent_obs(db, zone_id, hours=48)
    w = zone_weather(z)
    s = st.compute(z, obs, w)
    lat, lon = geo.centroid(z.geometry)
    return {
        "id": z.id, "name": z.name, "bay": z.bay, "ban": z.ban, "ban_text": z.ban_text,
        "center": {"lat": lat, "lon": lon}, "geometry": z.geometry,
        "status": status_out(s), "weather": w.to_dict(),
        "observations": [obs_out(o, dev) for o in obs],
    }


@app.get("/observations", response_model=list[ObservationOut])
def observations(
    db: Session = Depends(get_db), dev: str | None = Depends(optional_device),
    zone_id: str | None = None, lat: float | None = None, lon: float | None = None,
    radius_km: float | None = Query(default=None, gt=0, le=100),
    only_hazards: bool = False, fresh_only: bool = False, mine: bool = False,
    hours: int = Query(default=48, ge=1, le=24 * 30), limit: int = Query(default=100, le=500),
):
    obs = recent_obs(db, zone_id, hours=hours)
    out = []
    for o in obs:
        if mine and o.device_id != dev:
            continue
        if only_hazards and st.severity(o) == "clear":
            continue
        if fresh_only and now() - st.as_utc(o.observed_at) >= st.FRESH:
            continue
        if radius_km and lat is not None and lon is not None:
            zl, zn = geo.centroid(o.zone.geometry)
            if geo.haversine_m(lat, lon, zl, zn) > radius_km * 1000:
                continue
        out.append(obs_out(o, dev))
        if len(out) >= limit:
            break
    return out


@app.post("/observations", response_model=ObservationOut, status_code=201)
def create_observation(body: ObservationIn, db: Session = Depends(get_db), dev: str = Depends(device)):
    hour_ago = now() - timedelta(hours=1)
    recent = db.scalars(select(Observation).where(Observation.device_id == dev, Observation.created_at >= hour_ago)).all()
    if len(recent) >= POSTS_PER_HOUR:
        raise HTTPException(429, "Слишком много публикаций за час. Попробуйте позже.")

    zone = db.get(Zone, body.zone_id) if body.zone_id else None
    if body.zone_id and not zone:
        raise HTTPException(404, "Участок не найден")
    dist = None
    if body.lat is not None and body.lon is not None:
        if zone:
            dist = geo.distance_to_zone_m(body.lat, body.lon, zone.geometry)
        else:
            zone, dist = nearest_zone(db, body.lat, body.lon)
            if dist > NEAREST_ZONE_MAX_M:
                raise HTTPException(422, "Рядом нет участков. Выберите участок вручную.")
    if not zone:
        raise HTTPException(422, "Укажите участок или координаты")
    if body.type == "clear" and body.thickness_cm is not None and body.thickness_cm < 10:
        raise HTTPException(422, "При толщине меньше 10 см выберите «Тонкий лёд», а не «Без тревог».")

    onsite = (dist is not None and dist <= ONSITE_MAX_M and not body.mocked_location
              and (body.gps_accuracy_m or 999) <= ONSITE_MAX_ACCURACY_M)
    observed = body.observed_at or now()
    observed = min(st.as_utc(observed), now())
    if now() - observed > timedelta(hours=24):
        raise HTTPException(422, "Наблюдение старше суток: обстановка могла измениться.")
    cls = ai.classify(body.text)

    o = Observation(
        zone_id=zone.id, type=body.type, thickness_cm=body.thickness_cm,
        method=body.method if body.thickness_cm is not None else None, ice_type=body.ice_type, text=body.text,
        lat=body.lat, lon=body.lon, gps_accuracy_m=body.gps_accuracy_m, onsite=onsite, hide_point=body.hide_point,
        device_id=dev, author_name=(body.author_name or "").strip() or None, anonymous=body.anonymous,
        ai_hazard=cls["hazard"], ai_tags=cls["tags"], ai_source=cls["source"], observed_at=observed,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return obs_out(o, dev)


@app.delete("/observations/{obs_id}", status_code=204)
def delete_observation(obs_id: int, db: Session = Depends(get_db), dev: str = Depends(device)):
    o = db.get(Observation, obs_id)
    if not o:
        raise HTTPException(404, "Наблюдение не найдено")
    if o.device_id != dev:
        raise HTTPException(403, "Удалить можно только своё наблюдение")
    if o.photo_path:
        (UPLOADS / o.photo_path).unlink(missing_ok=True)
    db.delete(o)
    db.commit()


@app.post("/observations/{obs_id}/reactions", response_model=ObservationOut)
def react(obs_id: int, body: ReactionIn, db: Session = Depends(get_db), dev: str = Depends(device)):
    o = db.get(Observation, obs_id)
    if not o:
        raise HTTPException(404, "Наблюдение не найдено")
    if o.device_id == dev:
        raise HTTPException(403, "Нельзя оценивать своё наблюдение")
    if body.kind == "confirm":
        if body.lat is None or body.lon is None:
            raise HTTPException(403, "Подтвердить можно только рядом с участком: включите геолокацию")
        if geo.distance_to_zone_m(body.lat, body.lon, o.zone.geometry) > CONFIRM_MAX_M:
            raise HTTPException(403, "Подтвердить можно только рядом с участком (до 2 км)")
    existing = next((r for r in o.reactions if r.device_id == dev), None)
    if existing:
        o.reactions.remove(existing)
        db.flush()
    if body.kind:
        o.reactions.append(Reaction(device_id=dev, kind=body.kind))
    db.commit()
    db.refresh(o)
    return obs_out(o, dev)


@app.post("/observations/{obs_id}/photo", response_model=ObservationOut)
async def upload_photo(obs_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), dev: str = Depends(device)):
    o = db.get(Observation, obs_id)
    if not o or o.device_id != dev:
        raise HTTPException(404, "Наблюдение не найдено")
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(file.content_type or "")
    if not ext:
        raise HTTPException(415, "Нужно фото в формате JPEG, PNG или WebP")
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "Фото больше 5 МБ")
    name = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS / name).write_bytes(data)
    if o.photo_path:
        (UPLOADS / o.photo_path).unlink(missing_ok=True)
    o.photo_path = name
    db.commit()
    db.refresh(o)
    return obs_out(o, dev)


@app.get("/weather")
def weather(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180)):
    return get_weather(lat, lon).to_dict()


@app.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    """Bay-level AI warnings + official bans. Every warning lists its sources."""
    obs = recent_obs(db)
    zones_ = list(db.scalars(select(Zone)))
    out = [{"kind": "ban", "zone_id": z.id, "zone_name": z.name, "text": z.ban_text or "Запрет выхода на лёд",
            "critical": True} for z in zones_ if z.ban]
    for bay in sorted({z.bay for z in zones_}):
        bz = [z for z in zones_ if z.bay == bay]
        w = zone_weather(bz[0])
        offshore = any(geo.angle_in_ranges(w.wind_from_deg, z.offshore_from or []) for z in bz)
        hazards = [o for o in obs if o.zone.bay == bay and st.severity(o) != "clear" and not st.is_wrong(o)]
        warn = ai.bay_warning(bay, w, hazards, offshore)
        if warn:
            out.append({"kind": "ai", "critical": False, **warn})
    return out
