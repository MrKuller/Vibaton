from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config
from .config import DATA_DIR, DATABASE_URL

DATA_DIR.mkdir(parents=True, exist_ok=True)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Bounded pool: under a flood requests wait up to 5 s for a connection and then fail with 503,
    # instead of opening hundreds of connections and taking MySQL down for everyone.
    engine = create_engine(
        DATABASE_URL,
        pool_size=config.DB_POOL_SIZE,
        max_overflow=config.DB_MAX_OVERFLOW,
        pool_timeout=5,
        pool_pre_ping=True,   # MySQL closes idle connections after wait_timeout
        pool_recycle=1800,
        connect_args={"connect_timeout": 5, "read_timeout": 15, "write_timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def _limit_statement_time(dbapi_conn, _record):
        """No single query may run longer than DB_STATEMENT_TIMEOUT_MS (MySQL: SELECTs; MariaDB: all)."""
        cur = dbapi_conn.cursor()
        try:
            cur.execute("SELECT VERSION()")
            version = str(cur.fetchone()[0]).lower()
            ms = config.DB_STATEMENT_TIMEOUT_MS
            if "mariadb" in version:
                cur.execute(f"SET SESSION max_statement_time = {ms / 1000:.3f}")
            else:
                cur.execute(f"SET SESSION max_execution_time = {int(ms)}")
        finally:
            cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
