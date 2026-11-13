"""Registration and login: email + password, opaque bearer tokens, protection from bots and silly input.

Protection from silly input ("защита от дурака"): every field is normalised and checked, and every
mistake gets a clear Russian message saying what to fix (typos in popular mail domains get a hint).
Against bots, invisible to people:
- an empty honeypot field `website` (hidden in the app; bots fill every field);
- a real-looking email (not a throw-away mailbox), a non-trivial password, a sensible display name;
- at most 3 registrations per IP per hour and 10 per day.
Passwords: PBKDF2-SHA256, 310 000 iterations. Tokens: only their sha256 is stored.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import TOKEN_TTL_DAYS
from .db import get_db
from .models import AuthToken, User, utcnow
from .moderation import has_swearing
from .protection import client_ip

ITERATIONS = 310_000

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")
NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 .'\-]*$")
DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "10minutemail.com",
    "10minutemail.net", "temp-mail.org", "temp-mail.io", "tempmail.com", "tempmail.net", "tempmailo.com",
    "yopmail.com", "yopmail.net", "trashmail.com", "trashmail.de", "getnada.com", "nada.email",
    "dispostable.com", "maildrop.cc", "mailnesia.com", "mintemail.com", "throwawaymail.com", "fakeinbox.com",
    "emailondeck.com", "mohmal.com", "moakt.com", "tempail.com", "tempr.email", "discard.email",
    "spambog.com", "mailcatch.com", "inboxbear.com", "burnermail.io", "crazymailing.com", "dropmail.me",
    "emltmp.com", "1secmail.com", "1secmail.org", "1secmail.net", "minuteinbox.com", "tmpmail.org",
    "cryptogmail.com", "linshiyouxiang.net", "example.com", "example.org", "test.com", "mail.test",
}
COMMON_PASSWORDS = {
    "password", "password1", "password123", "qwerty123", "qwertyuiop", "qwerty12", "1q2w3e4r", "1q2w3e4r5t",
    "123qwe123", "zaq12wsx", "abc12345", "abcd1234", "admin123", "iloveyou1", "welcome1", "letmein1",
    "passw0rd", "p@ssw0rd", "monkey123", "dragon123", "football1", "baseball1", "sunshine1", "princess1",
    "йцукен123", "пароль123", "qwerty1234", "1qaz2wsx", "q1w2e3r4", "asdf1234", "zxcvbnm1", "11111111a",
}
RESERVED_NAMES = re.compile(r"admin|админ|moder|модер|мчс|mchs|поддержк|support|оператор|официальн|official|claude",
                            re.I)

# ---------- in-memory limits (per process) ----------
_login_fail_email: dict[str, deque] = defaultdict(deque)
_login_fail_ip: dict[str, deque] = defaultdict(deque)
_reg_ip: dict[str, deque] = defaultdict(deque)


def _count(q: deque, window_s: float) -> int:
    now = time.time()
    while q and now - q[0] > window_s:
        q.popleft()
    return len(q)


# ---------- passwords and tokens ----------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthToken(token_hash=_token_hash(token), user_id=user.id,
                     expires_at=utcnow() + timedelta(days=TOKEN_TTL_DAYS)))
    db.commit()
    return token


# ---------- input checks ----------
# typos in popular domains: suggest the right one instead of creating an account nobody can reach
DOMAIN_TYPOS = {
    "gmail.con": "gmail.com", "gmail.co": "gmail.com", "gmail.cm": "gmail.com", "gmial.com": "gmail.com",
    "gmai.com": "gmail.com", "gamil.com": "gmail.com", "gmail.ru": "gmail.com",
    "mail.ry": "mail.ru", "mail.ro": "mail.ru", "mial.ru": "mail.ru", "mali.ru": "mail.ru", "mail.r": "mail.ru",
    "yandex.ry": "yandex.ru", "yandex.ri": "yandex.ru", "yandx.ru": "yandex.ru", "yadex.ru": "yandex.ru",
    "yndex.ru": "yandex.ru", "ya.ry": "ya.ru", "bk.ry": "bk.ru", "inbox.ry": "inbox.ru", "list.ry": "list.ru",
    "rambler.ry": "rambler.ru", "ramler.ru": "rambler.ru", "outlook.con": "outlook.com",
}


def clean_email(raw: str) -> str:
    email = raw.strip().lower().replace(" ", "")
    if "@" not in email:
        raise HTTPException(422, "В email не хватает знака @. Пример: ivan@mail.ru")
    if re.search(r"[а-яё]", email):
        raise HTTPException(422, "Email пишется латиницей. Проверьте раскладку клавиатуры.")
    domain = email.rsplit("@", 1)[1]
    if domain in DOMAIN_TYPOS:
        raise HTTPException(422, f"Похоже на опечатку: вы имели в виду @{DOMAIN_TYPOS[domain]}?")
    if len(email) > 254 or ".." in email or not EMAIL_RE.match(email):
        raise HTTPException(422, "Проверьте email: например, ivan@mail.ru")
    if email.split("@", 1)[1] in DISPOSABLE:
        raise HTTPException(422, "Одноразовые почтовые ящики не подходят. Укажите постоянный email.")
    return email


def clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw.strip())
    letters = sum(ch.isalpha() for ch in name)
    if not (2 <= len(name) <= 40) or letters < 2 or not NAME_RE.match(name):
        raise HTTPException(422, "Имя: от 2 до 40 символов, буквы, цифры, пробел или дефис")
    if has_swearing(name):
        raise HTTPException(422, "В имени не должно быть нецензурных слов")
    if RESERVED_NAMES.search(name):
        raise HTTPException(422, "Такое имя нельзя: оно похоже на служебное или официальное")
    if re.search(r"(https?:|www\.|\.ru\b|\.com\b|@)", name, re.I):
        raise HTTPException(422, "В имени не должно быть ссылок и адресов")
    return name


def check_password(password: str, email: str, name: str) -> None:
    if not (8 <= len(password) <= 128):
        raise HTTPException(422, "Пароль: от 8 до 128 символов")
    if not re.search(r"[A-Za-zА-Яа-яЁё]", password) or not re.search(r"\d", password):
        raise HTTPException(422, "В пароле нужны и буквы, и цифры")
    low = password.lower()
    local = email.split("@")[0]
    if low in COMMON_PASSWORDS or re.search(r"(.)\1{3,}", password) or "12345678" in low or "qwertyui" in low:
        raise HTTPException(422, "Пароль слишком простой. Придумайте другой.")
    if (len(local) >= 4 and local in low) or name.lower().replace(" ", "") in low:
        raise HTTPException(422, "Пароль не должен содержать email или имя")


# ---------- dependencies ----------
def _user_from_header(authorization: str | None, db: Session) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    row = db.get(AuthToken, _token_hash(authorization[7:].strip()))
    if not row or row.expires_at < utcnow():
        return None
    return row.user


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    user = _user_from_header(authorization, db)
    if not user:
        raise HTTPException(401, "Войдите в аккаунт, чтобы продолжить")
    return user


def active_user(user: User = Depends(current_user)) -> User:
    """Logged in and not banned: required to publish, react, report and upload photos."""
    if user.banned_until and user.banned_until > utcnow():
        until = user.banned_until.strftime("%d.%m.%Y %H:%M")
        raise HTTPException(403, f"Аккаунт заблокирован до {until} UTC: {user.ban_reason or 'нарушение правил'}")
    return user


def is_moderator(user: User | None) -> bool:
    return bool(user and user.role in ("moderator", "admin"))


def moderator(user: User = Depends(current_user)) -> User:
    if not is_moderator(user):
        raise HTTPException(403, "Только для модераторов")
    return user


def optional_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User | None:
    return _user_from_header(authorization, db)


# ---------- schemas ----------
class RegisterIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)
    display_name: str = Field(max_length=80)
    website: str = Field(default="", max_length=200)  # honeypot: must stay empty


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    banned_until: str | None = None


class AuthOut(BaseModel):
    token: str
    user: UserOut


def user_out(u: User) -> UserOut:
    banned = u.banned_until.isoformat() + "Z" if u.banned_until and u.banned_until > utcnow() else None
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, role=u.role, banned_until=banned)


# ---------- routes ----------
@router.post("/register", response_model=AuthOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    if body.website:  # a bot filled the hidden field: a vague answer, tell it nothing
        raise HTTPException(422, "Не удалось зарегистрироваться. Попробуйте позже.")
    if _count(_reg_ip[ip], 3600) >= 3 or _count(_reg_ip[ip], 86400) >= 10:
        raise HTTPException(429, "С этого адреса уже зарегистрировано несколько аккаунтов. Попробуйте позже.")
    email = clean_email(body.email)
    name = clean_name(body.display_name)
    check_password(body.password, email, name)
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Этот email уже зарегистрирован. Войдите.")
    u = User(email=email, password_hash=hash_password(body.password), display_name=name)
    db.add(u)
    db.commit()
    db.refresh(u)
    _reg_ip[ip].append(time.time())
    return AuthOut(token=issue_token(db, u), user=user_out(u))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email, ip = body.email.strip().lower(), client_ip(request)
    if _count(_login_fail_email[email], 900) >= 10 or _count(_login_fail_ip[ip], 900) >= 30:
        raise HTTPException(429, "Слишком много попыток входа. Подождите 15 минут.")
    u = db.scalar(select(User).where(User.email == email))
    if not u or not verify_password(body.password, u.password_hash):
        _login_fail_email[email].append(time.time())
        _login_fail_ip[ip].append(time.time())
        raise HTTPException(401, "Неверный email или пароль")
    _login_fail_email.pop(email, None)
    db.execute(delete(AuthToken).where(AuthToken.user_id == u.id, AuthToken.expires_at < utcnow()))
    return AuthOut(token=issue_token(db, u), user=user_out(u))


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if authorization and authorization.lower().startswith("bearer "):
        db.execute(delete(AuthToken).where(AuthToken.token_hash == _token_hash(authorization[7:].strip())))
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


def reset_limits() -> None:
    """For tests."""
    for d in (_login_fail_email, _login_fail_ip, _reg_ip):
        d.clear()
