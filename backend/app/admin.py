"""Admin commands (run on the server, in backend/):

    python -m app.admin role ivan@mail.ru moderator     # user | moderator | admin
    python -m app.admin unban ivan@mail.ru
    python -m app.admin staff                           # list moderators and admins
    python -m app.admin log                             # last 30 moderator actions

Roles are not set through the API on purpose: nobody can make themselves a moderator from the app.
"""
import sys

from sqlalchemy import select

from .db import Base, SessionLocal, engine
from .models import ModerationAction, User

ROLES = ("user", "moderator", "admin")


def main(argv: list[str]) -> int:
    Base.metadata.create_all(engine)
    if not argv or argv[0] not in ("role", "unban", "staff", "log"):
        print(__doc__)
        return 1
    with SessionLocal() as db:
        cmd = argv[0]
        if cmd == "staff":
            for u in db.scalars(select(User).where(User.role != "user").order_by(User.role)):
                print(f"{u.role:10s} {u.email}  ({u.display_name})")
            return 0
        if cmd == "log":
            rows = db.scalars(select(ModerationAction).order_by(ModerationAction.id.desc()).limit(30))
            for a in rows:
                print(f"{a.created_at:%d.%m %H:%M}  {a.action:12s} obs={a.observation_id} user={a.target_user_id} "
                      f"by={a.moderator_id or 'авто'}  {a.note}")
            return 0
        if len(argv) < 2:
            print(__doc__)
            return 1
        u = db.scalar(select(User).where(User.email == argv[1].strip().lower()))
        if not u:
            print(f"Нет пользователя с email {argv[1]}")
            return 1
        if cmd == "role":
            if len(argv) < 3 or argv[2] not in ROLES:
                print(f"Роль: одна из {', '.join(ROLES)}")
                return 1
            u.role = argv[2]
            print(f"{u.email}: роль {u.role}")
        else:
            u.banned_until, u.ban_reason = None, None
            db.add(ModerationAction(target_user_id=u.id, action="unban", note="консоль"))
            print(f"{u.email}: блокировка снята")
        db.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
