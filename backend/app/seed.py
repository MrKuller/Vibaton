"""Fills the database with demo observations (marked by device id 'demo-seed-device').

python -m app.seed          # add demo data
python -m app.seed --reset  # wipe observations first
"""
import sys
from datetime import timedelta

from sqlalchemy import delete

from . import ai, geo
from .db import Base, SessionLocal, engine
from .main import now, sync_zones
from .models import Observation, Reaction, Zone

DEMO = "demo-seed-device"

ROWS = [
    # zone, type, minutes ago, thickness, method, ice, text, onsite, confirms
    ("patrokl", "hole", 40, None, None, None, "Открытая вода метров 10, края тонкие. Обходите левее, ближе к берегу тоже вода.", True, 6),
    ("uglovoe", "floe", 70, None, None, None, "У кромки отломило кусок, унесло метров на 30. Народ ушёл к берегу.", True, 3),
    ("defriz", "crack", 100, 18, "Лунка", "Белый слоистый", "Вдоль берега трещина метров 50, сочится вода.", True, 4),
    ("sedanka", "clear", 120, 32, "Бур", "Прозрачный", "Лёд 32 см, прозрачный, без воды. Людей много.", True, 1),
    ("defriz", "crack", 145, None, None, None, "Трещина у берега, обходили по льду правее.", True, 2),
    ("sukhodol", "water", 200, None, None, None, "У берега вода поверх льда, дальше сухо.", True, 2),
    ("defriz", "water", 255, None, None, None, "", False, 1),
    ("shamora", "clear", 26 * 60, 25, "Лунка", None, "Лёд 25 см у берега, дальше не ходил.", True, 0),
]


def main() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_zones(db)
        if "--reset" in sys.argv:
            db.execute(delete(Reaction))
            db.execute(delete(Observation))
            db.commit()
        for zid, typ, mins, thick, method, ice, text, onsite, confirms in ROWS:
            z = db.get(Zone, zid)
            lat, lon = geo.centroid(z.geometry)
            cls = ai.classify_rules(text)
            o = Observation(zone_id=zid, type=typ, thickness_cm=thick, method=method, ice_type=ice, text=text,
                            lat=lat, lon=lon, gps_accuracy_m=6 if onsite else None, onsite=onsite,
                            device_id=DEMO, anonymous=True, ai_hazard=cls["hazard"], ai_tags=cls["tags"],
                            observed_at=now() - timedelta(minutes=mins))
            o.reactions = [Reaction(device_id=f"demo-confirmer-{i:02d}", kind="confirm") for i in range(confirms)]
            db.add(o)
        db.commit()
        print(f"added {len(ROWS)} demo observations")


if __name__ == "__main__":
    main()
