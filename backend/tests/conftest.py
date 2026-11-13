import os
import sys
from pathlib import Path

os.environ["KL_OFFLINE"] = "1"  # no Open-Meteo / Ollama calls in tests
_db = Path(__file__).resolve().parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from app.db import Base, engine
    from app.main import app
    Base.metadata.drop_all(engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(engine)


DEV_A = {"X-Device-Id": "device-aaaa-0001"}
DEV_B = {"X-Device-Id": "device-bbbb-0002"}
