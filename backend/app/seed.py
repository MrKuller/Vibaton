"""Fills the database with demo observations from demo users (they cannot log in).

python -m app.seed          # add demo data
python -m app.seed --reset  # wipe observations first
"""
import sys
from datetime import timedelta

from sqlalchemy import delete, select

from . import ai
from . import grid as gridmod
from .db import Base, SessionLocal, engine
from .main import now, sync_zones
from .models import Observation, PhotoAnalysis, Reaction, User

ROWS = [
    # zone, type, minutes ago, thickness, method, ice, text, onsite, confirms, author, offset (m north, m east)
    ("patrokl", "hole", 40, None, None, None, "Открытая вода метров 10, края тонкие. Обходите левее, ближе к берегу тоже вода.", True, 6, 1, (0, 0)),
    ("uglovoe", "floe", 70, None, None, None, "У кромки отломило кусок, унесло метров на 30. Народ ушёл к берегу.", True, 3, 2, (0, 0)),
    ("defriz", "crack", 100, 18, "Лунка", "Белый слоистый", "Вдоль берега трещина метров 50, сочится вода.", True, 4, 3, (0, 0)),
    ("defriz", "crack", 145, None, None, None, "Трещина у берега, обходили по льду правее.", True, 2, 4, (60, 80)),
    ("sedanka", "clear", 120, 32, "Бур", "Прозрачный", "Лёд 32 см, прозрачный, без воды. Людей много.", True, 1, 5, (0, 0)),
    ("tavayza", "water", 200, None, None, None, "У берега вода поверх льда, дальше сухо.", True, 2, 6, (0, 0)),
    ("defriz", "water", 255, None, None, None, "", False, 1, 7, (300, -200)),
    ("shamora", "clear", 26 * 60, 25, "Лунка", None, "Лёд 25 см у берега, дальше не ходил.", True, 0, 8, (0, 0)),
]


def demo_user(db, i: int) -> User:
    email = f"demo{i}@demo.local"
    u = db.scalar(select(User).where(User.email == email))
    if not u:
        u = User(email=email, password_hash="!", display_name=f"Рыбак {i}")  # "!" never matches: no login
        db.add(u)
        db.flush()
    return u


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_zones(db)
        if "--reset" in sys.argv:
            for t in (PhotoAnalysis, Reaction, Observation):
                db.execute(delete(t))
            db.commit()
        for zid, typ, mins, thick, method, ice, text, onsite, confirms, author, (dn, de) in ROWS:
            cell = gridmod.load().resolve(zid)  # place id -> its water cell
            lat, lon = cell.lat + dn / 111_320, cell.lon + de / 81_000
            cls = ai.classify_rules(text)
            o = Observation(zone_id=cell.id, user_id=demo_user(db, author).id, type=typ, thickness_cm=thick, method=method,
                            ice_type=ice, text=text, lat=lat, lon=lon, gps_accuracy_m=6 if onsite else None,
                            onsite=onsite, anonymous=author % 2 == 0, ai_hazard=cls["hazard"], ai_tags=cls["tags"],
                            observed_at=(now() - timedelta(minutes=mins)).replace(tzinfo=None))
            o.reactions = [Reaction(user_id=demo_user(db, 100 + i).id, kind="confirm") for i in range(confirms)]
            db.add(o)
        db.commit()
        print(f"added {len(ROWS)} demo observations")


if __name__ == "__main__":
    main()
