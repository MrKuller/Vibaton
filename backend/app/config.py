"""Settings come from backend/.env (copy .env.example) or the environment."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", DATA_DIR / "uploads"))

# MySQL: mysql+pymysql://user:password@localhost:3306/krepkiy_led?charset=utf8mb4
# Without DATABASE_URL a local SQLite file is used (handy for tests and a quick demo).
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'app.db'}"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:3b")
OLLAMA_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S", "8"))
OLLAMA_VISION_TIMEOUT_S = float(os.getenv("OLLAMA_VISION_TIMEOUT_S", "40"))

TOKEN_TTL_DAYS = int(os.getenv("TOKEN_TTL_DAYS", "90"))


def flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in ("1", "true", "yes")

# ---------- models ----------
MODELS_DIR = BASE_DIR / "models"
# YOLO face + licence plate model (the team's yolo26m_face_lp.pt); missing file -> Haar cascades
FACE_LP_MODEL_PATH = Path(os.getenv("FACE_LP_MODEL_PATH", MODELS_DIR / "yolo26m_face_lp.pt"))
if not FACE_LP_MODEL_PATH.is_absolute():
    FACE_LP_MODEL_PATH = BASE_DIR / FACE_LP_MODEL_PATH
# optional trained ice model (YOLO classify/detect); missing file -> classic CV only
ICE_MODEL_PATH = Path(os.getenv("ICE_MODEL_PATH", MODELS_DIR / "ice.pt"))
if not ICE_MODEL_PATH.is_absolute():
    ICE_MODEL_PATH = BASE_DIR / ICE_MODEL_PATH

# ---------- protection ----------
# set to 1 only when the API sits behind your own proxy (nginx, cloudflared): then X-Forwarded-For is trusted
TRUSTED_PROXY = os.getenv("TRUSTED_PROXY", "0").strip().lower() in ("1", "true", "yes")
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1").strip().lower() in ("1", "true", "yes")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))
DB_STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "3000"))
PHOTO_WORKERS = int(os.getenv("PHOTO_WORKERS", "2"))          # photos processed at the same time


def _secret() -> str:
    """Server secret: SECRET_KEY from .env, else generated once into data/secret.key."""
    if os.getenv("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    f = DATA_DIR / "secret.key"
    if not f.exists():
        import secrets
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


SECRET_KEY = _secret()
