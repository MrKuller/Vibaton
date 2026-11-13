"""Tests run on SQLite by default. To run them on MySQL/MariaDB:
TEST_DATABASE_URL="mysql+pymysql://user:pass@localhost/krepkiy_led_test?charset=utf8mb4" pytest -q
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["KL_OFFLINE"] = "1"            # no Open-Meteo / Ollama calls in tests
os.environ["RATE_LIMIT_ENABLED"] = "0"    # switched on in the rate-limit test only
os.environ["FACE_LP_MODEL_PATH"] = "/nonexistent/face.pt"
os.environ["ICE_MODEL_PATH"] = "/nonexistent/ice.pt"
_db = Path(__file__).resolve().parent / "test.db"
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_db}"
os.environ["UPLOADS_DIR"] = tempfile.mkdtemp(prefix="kl-uploads-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from app import auth, protection
    from app.db import Base, engine
    from app.main import app
    Base.metadata.drop_all(engine)
    auth.reset_limits()
    protection.buckets.data.clear()
    protection.read_cache.clear()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


def register(client, name="Рыбак", email=None) -> dict:
    email = email or f"{abs(hash(name)) % 10**8}@mail.ru"
    r = client.post("/auth/register", json={"email": email, "password": "лёд-крепкий-2026", "display_name": name})
    assert r.status_code == 201, r.text
    from app import auth
    auth._reg_ip.clear()  # tests register many users from one address; the limit itself is tested separately
    return {"Authorization": f"Bearer {r.json()['token']}"}


def place_cell(client, place_id: str) -> dict:
    p = next(p for p in client.get("/places").json() if p["id"] == place_id)
    z = client.get(f"/zones/{p['cell_id']}").json()
    return {"id": z["id"], "lat": z["center"]["lat"], "lon": z["center"]["lon"]}
