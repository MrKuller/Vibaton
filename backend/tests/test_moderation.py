import cv2
import numpy as np
import pytest

from conftest import place_cell, register


def make_mod(email):
    from app.admin import main
    assert main(["role", email, "moderator"]) == 0


def post(client, h, **kw):
    body = {"type": "crack", "zone_id": "defriz", **kw}
    return client.post("/observations", headers=h, json=body)


# ---------- text rules ----------
@pytest.mark.parametrize("text,why", [
    ("тут пиздец промоина", "нецензурные"),
    ("охуенный лёд", "нецензурные"),
    ("Продам бур недорого", "Реклама"),
    ("звоните +7 914 123-45-67", "телефоны"),
    ("подробности на www.ice-fish.ru", "Ссылки"),
    ("t.me/fishing_vl", "Ссылки"),
    ("ааааааааааааа", "случайный набор"),
])
def test_bad_text_is_rejected_with_reason(client, text, why):
    h = register(client)
    r = post(client, h, text=text)
    assert r.status_code == 422 and why in r.json()["detail"]


@pytest.mark.parametrize("text", [
    "Лёд 30 см, ребята, всё нормально", "Хулиган на снегоходе гоняет", "Колебания уровня, у берега вода",
    "Бляха-муха, опять промоина", "Хлеб для прикорма", "Небо ясное, лёд белый слоистый",
])
def test_normal_text_passes(client, text):
    assert post(client, register(client), text=text).status_code == 201


def test_swearing_in_display_name(client):
    r = client.post("/auth/register", json={"email": "a1@mail.ru", "password": "лёд-крепкий-2026", "display_name": "Пиздюк"})
    assert r.status_code == 422 and "нецензурных" in r.json()["detail"]


# ---------- LLM review keeps danger visible ----------
def test_llm_flag_sends_to_review_but_danger_still_counts(client, monkeypatch):
    from app import moderation
    monkeypatch.setattr(moderation, "check_llm", lambda t: moderation.Verdict("review", "ИИ: оскорбление", "ollama"))
    c = place_cell(client, "defriz")
    a, b = register(client, "Анна"), register(client, "Борис")
    o = post(client, a, type="hole", text="соседи тут все дураки, промоина").json()
    assert o["moderation_status"] == "pending" and o["mine"] and "На проверке" in o["moderation_note"]
    seen_by_b = client.get(f"/zones/{c['id']}", headers=b).json()["observations"][0]
    assert seen_by_b["text"] == "" and seen_by_b["photo_url"] is None and "учитывается" in seen_by_b["moderation_note"]
    assert client.get("/status").json()["cells"][c["id"]]["level"] == "danger"  # safety first


def test_calm_post_on_review_does_not_paint_the_map(client, monkeypatch):
    from app import moderation
    monkeypatch.setattr(moderation, "check_llm", lambda t: moderation.Verdict("review", "ИИ: спам", "ollama"))
    c = place_cell(client, "sedanka")
    post(client, register(client), type="clear", zone_id="sedanka", text="всё отлично заходите все")
    assert c["id"] not in client.get("/status").json()["cells"]


# ---------- reports and moderator ----------
def test_reports_queue_and_moderator_actions(client):
    a = register(client, "Автор", "author@mail.ru")
    oid = post(client, a, type="clear", zone_id="sedanka", thickness_cm=30, text="лёд отличный").json()["id"]
    reporters = [register(client, f"Рыбак {i}", f"r{i}@mail.ru") for i in range(3)]
    assert client.post(f"/observations/{oid}/reports", headers=a, json={"reason": "fake"}).status_code == 403
    for h in reporters[:2]:
        assert client.post(f"/observations/{oid}/reports", headers=h, json={"reason": "fake"}).status_code == 201
    assert client.post(f"/observations/{oid}/reports", headers=reporters[0], json={"reason": "spam"}).status_code == 409
    assert client.get("/observations").json()[0]["moderation_status"] == "ok"  # 2 reports: still visible
    client.post(f"/observations/{oid}/reports", headers=reporters[2], json={"reason": "fake", "comment": "там вода"})
    o = client.get("/observations", headers=reporters[0]).json()[0]
    assert o["moderation_status"] == "pending" and o["my_report"] and o["text"] == ""

    # regular users cannot see the queue
    assert client.get("/moderation/queue", headers=reporters[0]).status_code == 403
    m = register(client, "Иван Петров", "mod@mail.ru")
    make_mod("mod@mail.ru")
    q = client.get("/moderation/queue", headers=m).json()
    assert len(q) == 1 and q[0]["reports_count"] == 3 and q[0]["text"] == "лёд отличный"
    assert {r["reason"] for r in q[0]["reports"]} == {"Неправда или фейк"}

    # hide + ban 7 days
    r = client.post(f"/moderation/observations/{oid}", headers=m, json={"action": "hide", "note": "фейк", "ban_days": 7})
    assert r.status_code == 200
    assert client.get("/observations").json() == []                       # hidden from everyone
    mine = client.get("/observations?mine=true", headers=a).json()[0]
    assert mine["moderation_status"] == "hidden" and "фейк" in mine["moderation_note"]
    r = post(client, a, text="снова тут")
    assert r.status_code == 403 and "заблокирован" in r.json()["detail"]
    assert client.get("/moderation/queue", headers=m).json() == []        # reports resolved

    from app.admin import main
    assert main(["unban", "author@mail.ru"]) == 0
    assert post(client, a, text="я исправился").status_code == 201
    assert main(["log"]) == 0


def test_moderator_approve_and_delete(client, monkeypatch):
    from app import moderation
    monkeypatch.setattr(moderation, "check_llm", lambda t: moderation.Verdict("review", "ИИ: не по теме", "ollama"))
    a = register(client, "Автор", "author@mail.ru")
    m = register(client, "Ольга Смирнова", "mod@mail.ru")
    make_mod("mod@mail.ru")
    o1 = post(client, a, text="что-то про погоду").json()["id"]
    o2 = post(client, a, text="ещё что-то").json()["id"]
    assert client.post(f"/moderation/observations/{o1}", headers=m, json={"action": "approve"}).status_code == 200
    assert client.post(f"/moderation/observations/{o2}", headers=m, json={"action": "delete"}).status_code == 200
    obs = client.get("/observations").json()
    assert [o["id"] for o in obs] == [o1] and obs[0]["moderation_status"] == "ok" and obs[0]["text"]
    assert client.post(f"/moderation/observations/{o1}", headers=m, json={"action": "explode"}).json()["detail"] == \
        "Действие: выберите вариант из списка"


# ---------- duplicate photos ----------
def photo(seed: int, size=(480, 640)) -> np.ndarray:
    img = np.random.default_rng(seed).integers(0, 255, (*size, 3), dtype=np.uint8)
    img = cv2.GaussianBlur(img, (41, 41), 0)
    return cv2.normalize(img, None, 40, 230, cv2.NORM_MINMAX)


def upload(client, h, oid, img, ext=".jpg"):
    data = cv2.imencode(ext, img)[1].tobytes()
    return client.post(f"/observations/{oid}/photo", headers=h, files={"file": ("p" + ext, data, "image/jpeg")})


def test_duplicate_photo_rejected(client):
    a, b = register(client, "Анна"), register(client, "Борис")
    o1 = post(client, a).json()["id"]
    o2 = post(client, b).json()["id"]
    o3 = post(client, b).json()["id"]
    original = photo(1)
    assert upload(client, a, o1, original).status_code == 200
    copy = cv2.resize(original, (800, 600))  # another account uploads a resized copy
    r = upload(client, b, o2, copy)
    assert r.status_code == 422 and "уже публиковалось" in r.json()["detail"]
    assert upload(client, b, o3, photo(2)).status_code == 200  # a genuinely new photo is fine
