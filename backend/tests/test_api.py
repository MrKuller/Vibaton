import cv2
import numpy as np

from conftest import place_cell, register


# ---------- map ----------
def test_grid_covers_water_and_unknown_is_grey(client):
    r = client.get("/grid")
    assert r.status_code == 200
    g = r.json()
    assert len(g["cells"]) > 5000 and len(r.content) < 400_000  # ids + centres, not geometry
    kinds = {g["kinds"][c[1]] for c in g["cells"]}
    assert kinds == {"open", "coast", "river"} and "р. Раздольная" in g["bays"]
    etag = r.headers["etag"]
    assert client.get("/grid", headers={"If-None-Match": etag}).status_code == 304

    places = {p["id"]: p for p in client.get("/places").json()}
    assert {"sedanka", "defriz", "shamora", "patrokl"} <= set(places)
    s = client.get("/status").json()
    assert s["default"] == "nodata"
    assert s["cells"][places["patrokl"]["cell_id"]]["level"] == "danger"  # official ban
    assert len(s["cells"]) < 50  # everything else stays grey


def test_zone_detail_by_cell_or_place(client):
    z = client.get("/zones/sedanka").json()
    assert z["name"] == "Участок у Седанки" and z["status"]["level"] == "nodata"
    assert client.get(f"/zones/{z['id']}").json()["id"] == z["id"]
    assert client.get("/zones/nowhere").status_code == 404


# ---------- registration protection ----------
def reg(client, **kw):
    body = {"email": "ivan@mail.ru", "password": "лёд-крепкий-2026", "display_name": "Иван"}
    body.update(kw)
    return client.post("/auth/register", json=body)


def test_register_and_login(client):
    r = reg(client, email="Anna@Mail.ru", display_name="Анна")
    assert r.status_code == 201, r.text
    tok = r.json()["token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()["email"] == "anna@mail.ru"
    assert reg(client, email="anna@mail.ru", display_name="Анна Б").status_code == 409
    assert client.post("/auth/login", json={"email": "anna@mail.ru", "password": "wrong-pass1"}).status_code == 401
    t2 = client.post("/auth/login", json={"email": "ANNA@mail.ru", "password": "лёд-крепкий-2026"}).json()["token"]
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {t2}"}).status_code == 204
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 401


def test_register_rejects_bots_and_silly_input(client):
    assert reg(client, website="http://spam").status_code == 422                        # honeypot (bots)
    assert "@" in reg(client, email="ivan.mail.ru").json()["detail"]
    assert "латиницей" in reg(client, email="иван@почта.рф").json()["detail"]
    assert "gmail.com" in reg(client, email="ivan@gmail.con").json()["detail"]
    assert "mail.ru" in reg(client, email="ivan@mail.ry").json()["detail"]
    assert reg(client, email="  Ivan@Mail.RU ").status_code == 201                      # spaces and case are fixed
    assert reg(client, email="ivan@mail.ru", display_name="Иван Б").status_code == 409
    assert "Одноразовые" in reg(client, email="x@mailinator.com").json()["detail"]
    assert reg(client, email="not-an-email").status_code == 422
    assert reg(client, email="a..b@mail.ru").status_code == 422
    assert "буквы, и цифры" in reg(client, password="onlyletters").json()["detail"]
    assert "простой" in reg(client, password="password1").json()["detail"]
    assert "простой" in reg(client, password="aaaa1111b").json()["detail"]
    assert reg(client, password="ivan2026x", email="ivan2026x@mail.ru").status_code == 422  # contains email
    assert reg(client, password="short1").status_code == 422
    assert "служебное" in reg(client, display_name="Админ").json()["detail"]
    assert "служебное" in reg(client, display_name="МЧС Приморья").json()["detail"]
    assert reg(client, display_name="x").status_code == 422
    assert reg(client, display_name="12345").status_code == 422
    assert reg(client, display_name="www.casino.ru").status_code == 422



def test_validation_errors_are_readable(client):
    r = client.post("/auth/register", json={"email": "a@mail.ru"})
    assert r.status_code == 422 and r.json()["detail"] in ("Пароль: не заполнено", "Имя: не заполнено")
    assert set(r.json()["fields"]) == {"password", "display_name"}
    a = register(client)
    r = client.post("/observations", headers=a, json={"type": "hole", "zone_id": "defriz", "thickness_cm": "много"})
    assert r.json()["detail"] == "Толщина льда: нужно целое число"
    r = client.post("/observations", headers=a, json={"type": "сугроб", "zone_id": "defriz"})
    assert r.json()["detail"] == "Что вы видите: выберите вариант из списка"
    r = client.post("/observations", content=b"{oops", headers={**a, "Content-Type": "application/json"})
    assert r.status_code == 422 and "формат" in r.json()["detail"]
    assert client.get("/observations?hours=-5").json()["detail"] == "Период: должно быть не меньше 1"


def test_register_ip_limit(client):
    for i in range(3):
        assert reg(client, email=f"user{i}@mail.ru", display_name=f"Рыбак {i}").status_code == 201
    assert reg(client, email="user9@mail.ru", display_name="Рыбак девять").status_code == 429


# ---------- observations ----------
def test_publish_needs_login_and_maps_gps_to_cell(client):
    c = place_cell(client, "defriz")
    body = {"type": "hole", "lat": c["lat"], "lon": c["lon"], "gps_accuracy_m": 6, "text": "Промоина метров 5"}
    assert client.post("/observations", json=body).status_code == 401
    a = register(client, "Анна")
    r = client.post("/observations", headers=a, json=body)
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["zone_id"] == c["id"] and o["zone_name"] == "Участок у Де-Фриза" and o["onsite"] and o["ai_hazard"] == "danger"
    assert client.get("/status").json()["cells"][c["id"]]["level"] == "danger"
    # far from any water without a chosen zone -> rejected; with a chosen place -> accepted but not on site
    assert client.post("/observations", headers=a, json={"type": "crack", "lat": 55.75, "lon": 37.6}).status_code == 422
    r = client.post("/observations", headers=a, json={"type": "crack", "zone_id": "shamora", "lat": 55.75, "lon": 37.6})
    assert r.status_code == 201 and not r.json()["onsite"]


def test_validation(client):
    a = register(client)
    assert client.post("/observations", headers=a, json={"type": "hole", "zone_id": "defriz", "thickness_cm": 400}).status_code == 422
    assert client.post("/observations", headers=a, json={"type": "clear", "zone_id": "defriz", "thickness_cm": 5}).status_code == 422
    assert client.post("/observations", headers=a, json={"type": "hole"}).status_code == 422


def test_reactions_and_delete(client):
    c = place_cell(client, "defriz")
    a, b = register(client, "Анна"), register(client, "Борис")
    oid = client.post("/observations", headers=a, json={"type": "crack", "zone_id": "defriz"}).json()["id"]
    assert client.post(f"/observations/{oid}/reactions", headers=a, json={"kind": "confirm", "lat": c["lat"], "lon": c["lon"]}).status_code == 403
    assert client.post(f"/observations/{oid}/reactions", headers=b, json={"kind": "confirm"}).status_code == 403
    r = client.post(f"/observations/{oid}/reactions", headers=b, json={"kind": "confirm", "lat": c["lat"], "lon": c["lon"]})
    assert r.json()["counts"]["confirm"] == 1 and r.json()["my_reaction"] == "confirm"
    r = client.post(f"/observations/{oid}/reactions", headers=b, json={"kind": "wrong"})
    assert r.json()["counts"] == {"confirm": 0, "changed": 0, "wrong": 1}
    assert client.delete(f"/observations/{oid}", headers=b).status_code == 403
    assert client.delete(f"/observations/{oid}", headers=a).status_code == 204


def test_feed_filters_and_privacy(client):
    c = place_cell(client, "defriz")
    a = register(client)
    client.post("/observations", headers=a, json={"type": "clear", "thickness_cm": 30, "lat": c["lat"] + 0.0007, "lon": c["lon"]})
    client.post("/observations", headers=a, json={"type": "hole", "zone_id": "shamora"})
    assert len(client.get("/observations").json()) == 2
    assert [o["type"] for o in client.get("/observations?only_hazards=true").json()] == ["hole"]
    near = client.get(f"/observations?lat={c['lat']}&lon={c['lon']}&radius_km=3").json()
    assert [o["zone_id"] for o in near] == [c["id"]]
    assert near[0]["lat"] != round(c["lat"] + 0.0007, 6)  # calm posts are blurred to a grid


def test_clusters_need_two_different_people(client):
    c = place_cell(client, "defriz")
    a, b = register(client, "Анна"), register(client, "Борис")
    body = {"type": "crack", "lat": c["lat"], "lon": c["lon"]}
    for _ in range(3):
        client.post("/observations", headers=a, json=body)
    assert client.get("/clusters").json() == []
    client.post("/observations", headers=b, json={**body, "lat": c["lat"] + 0.001})
    cl = client.get("/clusters").json()
    assert len(cl) == 1 and cl[0]["users"] == 2 and len(cl[0]["observation_ids"]) == 4
    assert any(x["kind"] == "cluster" for x in client.get("/alerts").json())
    assert any("2 человека" in v["reason"] for v in client.get("/status").json()["cells"].values())


# ---------- photos: model 1 (privacy) and model 2 (ice) ----------
def snow_photo(crack=False, water=False) -> bytes:
    rng = np.random.default_rng(1)
    img = np.clip(np.full((600, 800, 3), 225) + rng.integers(-12, 12, (600, 800, 3)), 0, 255).astype(np.uint8)
    if crack:
        cv2.polylines(img, [np.array([[40, 350], [200, 380], [400, 360], [600, 400], [780, 390]])], False, (70, 70, 70), 3)
    if water:
        img[350:600, 0:400] = (60, 40, 20)
    return cv2.imencode(".jpg", img)[1].tobytes()


def upload(client, h, oid, data, ct="image/jpeg"):
    return client.post(f"/observations/{oid}/photo", headers=h, files={"file": ("p.jpg", data, ct)})


def test_photo_checks(client):
    a, b = register(client, "Анна"), register(client, "Борис")
    oid = client.post("/observations", headers=a, json={"type": "crack", "zone_id": "defriz"}).json()["id"]
    assert upload(client, b, oid, snow_photo()).status_code == 404
    assert upload(client, a, oid, b"not an image").status_code == 422
    black = cv2.imencode(".jpg", np.zeros((600, 800, 3), np.uint8))[1].tobytes()
    assert "тёмное" in upload(client, a, oid, black).json()["detail"]
    tiny = cv2.imencode(".jpg", np.full((100, 100, 3), 180, np.uint8))[1].tobytes()
    assert upload(client, a, oid, tiny).status_code == 422


def test_ice_model_finds_crack_and_raises_level(client):
    c = place_cell(client, "sedanka")
    a = register(client)
    oid = client.post("/observations", headers=a, json={"type": "clear", "zone_id": "sedanka"}).json()["id"]
    assert client.get("/status").json()["cells"][c["id"]]["level"] == "clear"
    r = upload(client, a, oid, snow_photo(crack=True))
    assert r.status_code == 200, r.text
    p = r.json()["photo"]
    assert "трещина" in p["signs"] and p["material"]["snow"] > 0.5 and p["source"] == "cv"
    assert p["privacy_detector"] == "haar" and p["privacy_status"] == "NO_DETECTIONS"
    assert r.json()["severity"] == "risk"  # a "calm" post with a crack on the photo counts as risk
    assert client.get("/status").json()["cells"][c["id"]]["level"] == "risk"
    stored = client.get(r.json()["photo_url"]).content
    assert stored[:2] == b"\xff\xd8" and b"Exif" not in stored[:200]


class _FakeBoxes(list):
    pass


class _Box:
    def __init__(self, cls, conf, xyxy):
        import types
        self.cls, self.conf = [cls], [conf]
        self.xyxy = [types.SimpleNamespace(tolist=lambda: list(xyxy))]


class FakeYolo:
    """Same interface as ultralytics.YOLO for the parts we use."""
    names = {0: "face", 1: "license_plate"}

    def predict(self, source, conf, iou, verbose):
        import types
        return [types.SimpleNamespace(boxes=_FakeBoxes([_Box(0, 0.91, (100, 100, 220, 260)), _Box(1, 0.8, (500, 400, 700, 450))]))]


def test_yolo_face_plate_model_blurs(client, monkeypatch):
    from app import anonymizer
    monkeypatch.setattr(anonymizer, "_yolo", FakeYolo())
    a = register(client)
    oid = client.post("/observations", headers=a, json={"type": "crack", "zone_id": "defriz"}).json()["id"]
    rng = np.random.default_rng(3)
    src = rng.integers(0, 255, (600, 800, 3), dtype=np.uint8)  # high-detail image: blur is easy to measure
    r = upload(client, a, oid, cv2.imencode(".png", src)[1].tobytes(), "image/png")
    assert r.status_code == 200, r.text
    p = r.json()["photo"]
    assert p["privacy_detector"] == "yolo" and p["faces_blurred"] == 1 and p["plates_blurred"] == 1
    assert p["privacy_status"] == "PROCESSED_REQUIRES_REVIEW"
    out = cv2.imdecode(np.frombuffer(client.get(r.json()["photo_url"]).content, np.uint8), cv2.IMREAD_COLOR)
    detail = lambda im: cv2.Laplacian(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()  # noqa: E731
    assert detail(out[130:230, 120:200]) < 0.05 * detail(src[130:230, 120:200])   # face centre blurred
    assert detail(out[410:440, 520:680]) < 0.05 * detail(src[410:440, 520:680])   # plate blurred
    assert detail(out[20:90, 600:780]) > 0.5 * detail(src[20:90, 600:780])        # elsewhere untouched


def test_yolo_crash_falls_back_to_haar(client, monkeypatch):
    from app import anonymizer

    class Broken:
        names = {}

        def predict(self, **kw):
            raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(anonymizer, "_yolo", Broken())
    a = register(client)
    oid = client.post("/observations", headers=a, json={"type": "crack", "zone_id": "defriz"}).json()["id"]
    r = upload(client, a, oid, snow_photo())
    assert r.status_code == 200 and r.json()["photo"]["privacy_detector"] == "haar"


# ---------- flood protection ----------
def test_rate_limit_and_cache(client, monkeypatch):
    from app import config, protection
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    login = lambda: client.post("/auth/login", json={"email": "x@mail.ru", "password": "whatever1"})  # noqa: E731
    codes = [login().status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[-1] == 429
    r = login()
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert client.get("/health").status_code == 200  # health is never limited
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)

    first = client.get("/status").json()["generated_at"]
    assert client.get("/status").json()["generated_at"] == first  # served from cache
    a = register(client)
    client.post("/observations", headers=a, json={"type": "hole", "zone_id": "defriz"})
    assert client.get("/status").json()["generated_at"] != first  # a write clears the cache
    assert protection.MAX_BODY_BYTES < 10 * 1024 * 1024


def test_big_body_rejected(client):
    r = client.post("/auth/login", content=b"x" * (10 * 1024 * 1024), headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_weather_and_alerts_offline(client):
    assert client.get("/weather?lat=43.2&lon=131.9").json()["source"] == "fallback"
    alerts = client.get("/alerts").json()
    assert any(a["kind"] == "ban" for a in alerts)
    for a in alerts:
        if a["kind"] == "ai":
            assert a["facts"] and "безопасн" not in a["text"].lower()


def test_seed_runs(client):
    from app import seed
    seed.main()
    assert len(client.get("/observations").json()) == 8
    levels = {v["level"] for v in client.get("/status").json()["cells"].values()}
    assert {"danger", "risk"} <= levels


def test_mysql_statement_timeout_is_set(client):
    from app.db import engine
    if engine.dialect.name != "mysql":
        return
    with engine.connect() as conn:
        version = conn.exec_driver_sql("SELECT VERSION()").scalar().lower()
        var = "max_statement_time" if "mariadb" in version else "max_execution_time"
        assert float(conn.exec_driver_sql(f"SELECT @@SESSION.{var}").scalar()) > 0


def test_cells_follow_the_coast_and_rivers(client):
    from app import geo, grid
    g = grid.load()
    sizes = {k: sorted({c.id[1] for c in g.cells.values() if c.kind == k}) for k in ("open", "coast", "river")}
    assert sizes == {"open": ["8"], "coast": ["9"], "river": ["a"]}  # H3 resolution digit: 8, 9, 10
    # every place is close to its cell: the coast is no longer cut off
    for p in g.places.values():
        c = g.cells[p.cell_id]
        assert geo.haversine_m(p.lat, p.lon, c.lat, c.lon) < 700, p.name
    # a point inside a coastal / river cell is found exactly
    coast = next(c for c in g.cells.values() if c.kind == "coast")
    river = next(c for c in g.cells.values() if c.kind == "river")
    assert g.cell_for_point(coast.lat, coast.lon) == (coast, 0.0)
    assert g.cell_for_point(river.lat, river.lon)[0].name.startswith("Река Раздольная")
    _, d = g.cell_for_point(43.115, 131.92)  # downtown Vladivostok is land
    assert d > 0


def test_grid_rebuild_moves_old_observations(client):
    from app.db import SessionLocal
    from app.main import sync_zones
    from app.models import Observation, User, Zone
    with SessionLocal() as db:
        u = User(email="old@mail.ru", password_hash="!", display_name="Старый")
        db.add_all([u, Zone(id="c021r025", bay="Амурский залив")])
        db.flush()
        db.add(Observation(zone_id="c021r025", user_id=u.id, type="crack", lat=43.262, lon=131.93, device_id=None)
               if hasattr(Observation, "device_id") else
               Observation(zone_id="c021r025", user_id=u.id, type="crack", lat=43.262, lon=131.93))
        db.commit()
        sync_zones(db)
        o = db.query(Observation).one()
        assert o.zone_id != "c021r025" and len(o.zone_id) == 15  # an H3 id now
        assert db.get(Zone, "c021r025") is None
