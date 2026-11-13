"""Monkey testing: random and broken input must never crash the server (no HTTP 500).

- dumb monkey: knows nothing about the API; sends random paths, query strings, headers and bodies
  to every route;
- smart monkey: knows the shape of the requests; takes valid payloads and breaks them one field at a time
  (wrong types, empty, huge, negative, SQL and HTML injections, path traversal, emoji, zero bytes);
- photo monkey: random bytes, truncated and odd images to the photo upload.

The random generator is seeded, so a failure can be repeated: the seed is printed in the assertion message.
    MONKEY_SEED=123 MONKEY_N=2000 pytest tests/test_monkey.py -q
"""
import json
import os
import random
from urllib.parse import quote

import cv2
import numpy as np
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from conftest import register

SEED = int(os.getenv("MONKEY_SEED", "20261113"))
N = int(os.getenv("MONKEY_N", "300"))

NASTY_STRINGS = [
    "", " ", "\x00", "\n\r\t", "a" * 10_000, "😀🧊🎣" * 50, "' OR '1'='1' --", "\"; DROP TABLE users; --",
    "<script>alert(1)</script>", "../../../../etc/passwd", "..\\..\\windows\\win.ini", "%00", "${jndi:ldap://x}",
    "{{7*7}}", "null", "undefined", "NaN", "-1", "0", "1e309", "9" * 400, "Ｆｕｌｌｗｉｄｔｈ", "‮RTL", "ДРОП",
    "c000r000", "defriz", "patrokl/../sedanka", "     defriz     ",
]
NASTY_VALUES = [None, True, False, 0, -1, 1, 2**31, -(2**63), 2**64, 1e308, -1e308, 0.5, float("nan"), float("inf"),
                [], {}, [1, 2, 3], {"$gt": ""}, {"a": {"b": {"c": [None]}}}]


@pytest.fixture()
def raw_client(client):
    """Same app, but server exceptions come back as HTTP 500 instead of raising inside the test."""
    from app.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def rand_value(rng: random.Random):
    return rng.choice(NASTY_STRINGS) if rng.random() < 0.6 else rng.choice(NASTY_VALUES)


def rand_json_body(rng: random.Random) -> bytes:
    kind = rng.random()
    if kind < 0.15:
        return bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 300)))  # not JSON at all
    if kind < 0.25:
        return b'{"email": "a@b.ru", "password": '  # truncated JSON
    obj = {rng.choice(["email", "password", "display_name", "type", "zone_id", "thickness_cm", "text", "lat", "lon",
                       "kind", "anonymous", "observed_at", "x", ""]): rand_value(rng) for _ in range(rng.randint(0, 6))}
    if rng.random() < 0.1:
        obj = rand_value(rng)  # a list, number or string instead of an object
    return json.dumps(obj, allow_nan=True, ensure_ascii=rng.random() < 0.5).encode()


def routes():
    from app.main import app
    out = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in r.methods:
                out.append((m, r.path))
    return out


def fill_path(path: str, rng: random.Random) -> str:
    while "{" in path:
        a, b = path.index("{"), path.index("}")
        val = str(rng.choice(NASTY_STRINGS + ["1", "999999", "-5", "defriz", "0"]))
        path = path[:a] + quote(val, safe="") + path[b + 1:]
    return path


def assert_no_500(r, what: str):
    assert r.status_code < 500 or r.status_code == 503, (
        f"{what} -> {r.status_code}: {r.text[:300]}  (MONKEY_SEED={SEED})")


def test_dumb_monkey_random_requests_to_every_route(raw_client):
    rng = random.Random(SEED)
    token_headers = register(raw_client, "Обезьяна")
    all_routes = routes()
    assert len(all_routes) >= 10
    for i in range(N):
        method, path = rng.choice(all_routes)
        url = fill_path(path, rng)
        if rng.random() < 0.5:
            url += "?" + "&".join(f"{rng.choice(['lat', 'lon', 'hours', 'limit', 'radius_km', 'zone_id', 'mine', 'x'])}="
                                  f"{quote(str(rand_value(rng))[:50], safe='')}" for _ in range(rng.randint(1, 4)))
        headers = {"Content-Type": rng.choice(["application/json", "text/plain", "multipart/form-data", ""])}
        roll = rng.random()
        if roll < 0.4:
            headers.update(token_headers)
        elif roll < 0.6:
            headers["Authorization"] = rng.choice(["Bearer ", "Bearer x", "Basic abc", "bearer " + "z" * 500,
                                                  b"Bearer \xff\xfe\x01"])  # raw non-ASCII bytes
        body = rand_json_body(rng) if method in ("POST", "PUT", "PATCH", "DELETE") else None
        r = raw_client.request(method, url, content=body, headers={k: v for k, v in headers.items() if v})
        assert_no_500(r, f"#{i} {method} {url[:120]}")
    # after the storm the API still works
    assert raw_client.get("/status").status_code == 200
    assert raw_client.get("/auth/me", headers=token_headers).status_code == 200


def mutate(valid: dict, rng: random.Random) -> dict:
    body = dict(valid)
    for _ in range(rng.randint(1, 3)):
        key = rng.choice(list(valid) + ["unexpected_field"])
        if rng.random() < 0.2:
            body.pop(key, None)
        else:
            body[key] = rand_value(rng)
    return body


def test_smart_monkey_breaks_valid_payloads(raw_client):
    rng = random.Random(SEED + 1)
    h = register(raw_client, "Умная обезьяна")
    valid_register = {"email": "monkey@mail.ru", "password": "лёд-крепкий-2026", "display_name": "Рыбак"}
    valid_obs = {"type": "crack", "zone_id": "defriz", "thickness_cm": 20, "method": "Лунка", "ice_type": "Прозрачный",
                 "text": "трещина", "lat": 43.26, "lon": 131.93, "gps_accuracy_m": 5, "anonymous": True,
                 "hide_point": True, "observed_at": "2026-01-01T10:00:00Z"}
    created = 0
    for i in range(N):
        target = rng.random()
        if target < 0.3:
            body = mutate(valid_register, rng)
            r = raw_client.post("/auth/register", content=json.dumps(body, allow_nan=True),
                                headers={"Content-Type": "application/json"})
            what = "register"
        elif target < 0.45:
            body = mutate({"email": "monkey@mail.ru", "password": "x"}, rng)
            r = raw_client.post("/auth/login", content=json.dumps(body, allow_nan=True),
                                headers={"Content-Type": "application/json"})
            what = "login"
        elif target < 0.85:
            body = mutate(valid_obs, rng)
            r = raw_client.post("/observations", content=json.dumps(body, allow_nan=True),
                                headers={**h, "Content-Type": "application/json"})
            created += r.status_code == 201
            what = "observation"
        else:
            body = mutate({"kind": "confirm", "lat": 43.26, "lon": 131.93}, rng)
            r = raw_client.post(f"/observations/{rng.choice([1, 2, 999999, -1])}/reactions",
                                content=json.dumps(body, allow_nan=True), headers={**h, "Content-Type": "application/json"})
            what = "reaction"
        assert_no_500(r, f"#{i} {what} {json.dumps(body, allow_nan=True, ensure_ascii=False)[:200]}")
        if r.status_code == 422:
            assert isinstance(r.json().get("detail"), str) and r.json()["detail"], "422 must explain the problem"
    assert raw_client.get("/status").status_code == 200
    assert created < N  # most broken payloads must be rejected


def test_photo_monkey(raw_client):
    rng = random.Random(SEED + 2)
    h = register(raw_client)
    oid = raw_client.post("/observations", headers=h, json={"type": "crack", "zone_id": "defriz"}).json()["id"]
    good = cv2.imencode(".jpg", np.full((480, 640, 3), 200, np.uint8))[1].tobytes()
    samples = [
        b"", b"\xff\xd8\xff", good[: len(good) // 3], good[:-50], b"GIF89a" + b"\x00" * 50,
        cv2.imencode(".png", np.zeros((1, 1, 3), np.uint8))[1].tobytes(),
        cv2.imencode(".png", np.zeros((400, 5000, 3), np.uint8) + 128)[1].tobytes(),   # very wide
        cv2.imencode(".png", np.zeros((480, 640), np.uint8) + 200)[1].tobytes(),      # greyscale
        cv2.imencode(".png", np.zeros((480, 640, 4), np.uint8) + 200)[1].tobytes(),   # with alpha
        b"%PDF-1.4 not a photo", b"<svg xmlns='http://www.w3.org/2000/svg'/>",
    ] + [bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 5000))) for _ in range(15)]
    for i, data in enumerate(samples):
        ct = rng.choice(["image/jpeg", "image/png", "application/octet-stream", "text/plain", ""])
        r = raw_client.post(f"/observations/{oid}/photo", headers=h, files={"file": ("x", data, ct or "image/jpeg")})
        assert_no_500(r, f"photo sample #{i} ({len(data)} bytes, {ct})")
    # wrong form field name and no file at all
    assert_no_500(raw_client.post(f"/observations/{oid}/photo", headers=h, files={"photo": ("x", good, "image/jpeg")}), "no file")
    assert_no_500(raw_client.post(f"/observations/{oid}/photo", headers=h), "empty body")
