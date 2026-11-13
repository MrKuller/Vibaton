from conftest import DEV_A, DEV_B


def defriz_center(client):
    z = client.get("/zones/defriz").json()
    return z["center"]["lat"], z["center"]["lon"]


def test_zones_geojson(client):
    r = client.get("/zones")
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 6
    by_id = {f["id"]: f for f in fc["features"]}
    assert by_id["patrokl"]["properties"]["status"]["level"] == "danger"  # official ban
    assert by_id["shamora"]["geometry"]["type"] == "Polygon"


def test_publish_flow(client):
    lat, lon = defriz_center(client)
    r = client.post("/observations", headers=DEV_A, json={
        "type": "hole", "lat": lat, "lon": lon, "gps_accuracy_m": 6, "text": "Промоина метров 5"})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["zone_id"] == "defriz" and o["onsite"] and o["mine"] and o["ai_hazard"] == "danger"
    assert client.get("/zones/defriz").json()["status"]["level"] == "danger"

    # far away GPS → not on site
    r = client.post("/observations", headers=DEV_A, json={"type": "crack", "zone_id": "defriz", "lat": lat + 0.02, "lon": lon})
    assert r.status_code == 201 and not r.json()["onsite"]


def test_validation(client):
    assert client.post("/observations", json={"type": "hole", "zone_id": "defriz"}).status_code == 400
    assert client.post("/observations", headers=DEV_A, json={"type": "hole", "zone_id": "defriz", "thickness_cm": 400}).status_code == 422
    assert client.post("/observations", headers=DEV_A, json={"type": "clear", "zone_id": "defriz", "thickness_cm": 5}).status_code == 422
    assert client.post("/observations", headers=DEV_A, json={"type": "hole", "lat": 55.75, "lon": 37.6}).status_code == 422


def test_reactions_and_delete(client):
    lat, lon = defriz_center(client)
    oid = client.post("/observations", headers=DEV_A, json={"type": "crack", "zone_id": "defriz"}).json()["id"]
    assert client.post(f"/observations/{oid}/reactions", headers=DEV_A, json={"kind": "confirm", "lat": lat, "lon": lon}).status_code == 403
    assert client.post(f"/observations/{oid}/reactions", headers=DEV_B, json={"kind": "confirm"}).status_code == 403
    r = client.post(f"/observations/{oid}/reactions", headers=DEV_B, json={"kind": "confirm", "lat": lat, "lon": lon})
    assert r.json()["counts"]["confirm"] == 1 and r.json()["my_reaction"] == "confirm"
    r = client.post(f"/observations/{oid}/reactions", headers=DEV_B, json={"kind": "wrong"})
    assert r.json()["counts"] == {"confirm": 0, "changed": 0, "wrong": 1}
    assert client.delete(f"/observations/{oid}", headers=DEV_B).status_code == 403
    assert client.delete(f"/observations/{oid}", headers=DEV_A).status_code == 204


def test_feed_filters_and_privacy(client):
    lat, lon = defriz_center(client)
    client.post("/observations", headers=DEV_A, json={"type": "clear", "zone_id": "defriz", "thickness_cm": 30, "lat": lat + 0.0007, "lon": lon})
    client.post("/observations", headers=DEV_A, json={"type": "hole", "zone_id": "shamora"})
    assert len(client.get("/observations").json()) == 2
    assert [o["type"] for o in client.get("/observations?only_hazards=true").json()] == ["hole"]
    near = client.get(f"/observations?lat={lat}&lon={lon}&radius_km=3").json()
    assert [o["zone_id"] for o in near] == ["defriz"]
    calm = near[0]
    assert calm["lat"] != round(lat + 0.0007, 6)  # calm posts are blurred to a grid


def test_photo_upload(client):
    oid = client.post("/observations", headers=DEV_A, json={"type": "crack", "zone_id": "defriz"}).json()["id"]
    r = client.post(f"/observations/{oid}/photo", headers=DEV_A, files={"file": ("a.jpg", b"\xff\xd8\xff fake", "image/jpeg")})
    assert r.status_code == 200 and r.json()["photo_url"].startswith("/uploads/")
    assert client.get(r.json()["photo_url"]).status_code == 200
    assert client.post(f"/observations/{oid}/photo", headers=DEV_A, files={"file": ("a.txt", b"x", "text/plain")}).status_code == 415


def test_weather_and_alerts_offline(client):
    w = client.get("/weather?lat=43.2&lon=131.9").json()
    assert w["source"] == "fallback"
    alerts = client.get("/alerts").json()
    assert any(a["kind"] == "ban" for a in alerts)
    for a in alerts:
        if a["kind"] == "ai":
            assert a["facts"] and "безопасн" not in a["text"].lower()
