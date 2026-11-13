"""Zone status rules. Pure functions, unit-tested in tests/test_status.py.

Scale has no "safe" level: danger > risk > clear ("тревог нет") > nodata.
- one fresh danger report beats any number of calm ones;
- reports are fresh for 6 h (3 h during thaw or strong wind) and stop counting after 24 h;
- weather and AI can only raise a level;
- an official ban always means danger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .geo import angle_in_ranges

TYPES = {
    "crack": ("Трещина", "risk"),
    "hole": ("Промоина", "danger"),
    "water": ("Вода на льду", "risk"),
    "thin": ("Тонкий лёд", "danger"),
    "floe": ("Отрыв льдины", "danger"),
    "clear": ("Без тревог", "clear"),
}
LEVELS = ("nodata", "clear", "risk", "danger")
FRESH = timedelta(hours=6)
FRESH_SHORT = timedelta(hours=3)
STALE = timedelta(hours=24)
STRONG_WIND_MS = 10
OFFSHORE_MIN_MS = 8


def rank(level: str) -> int:
    return LEVELS.index(level)


def raise_to(cur: str, new: str) -> str:
    return new if rank(new) > rank(cur) else cur


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_wrong(o) -> bool:
    c = o.counts
    return c["wrong"] >= 2 and c["wrong"] > c["confirm"]


def severity(o) -> str:
    sev = TYPES[o.type][1]
    # text hints only raise: a "clear" post that mentions a crack counts as risk
    if sev == "clear" and o.ai_hazard in ("risk", "danger"):
        return "risk"
    if sev == "risk" and o.ai_hazard == "danger":
        return "danger"
    return sev


@dataclass
class ZoneStatus:
    level: str
    reasons: list[str] = field(default_factory=list)
    fresh_count: int = 0
    last_observed_at: datetime | None = None
    conflict: bool = False
    fresh_window_h: int = 6
    offshore_wind: bool = False


def compute(zone, observations: list, weather, now: datetime | None = None) -> ZoneStatus:
    now = now or datetime.now(timezone.utc)
    thaw_or_wind = bool(weather and (weather.crosses_zero or weather.wind_ms >= STRONG_WIND_MS))
    fresh_win = FRESH_SHORT if thaw_or_wind else FRESH

    valid = sorted((o for o in observations if not is_wrong(o)), key=lambda o: as_utc(o.observed_at), reverse=True)
    fresh = [o for o in valid if now - as_utc(o.observed_at) < fresh_win]
    stale = [o for o in valid if fresh_win <= now - as_utc(o.observed_at) < STALE]

    level, reasons = "nodata", []
    for o in fresh:
        level = raise_to(level, severity(o))
        if severity(o) != "clear":
            reasons.append(f"{TYPES[o.type][0]}: свежее сообщение")
    if any(severity(o) != "clear" for o in stale):
        level = raise_to(level, "risk")
        if not reasons:
            reasons.append("Сигналы риска за сутки, свежих подтверждений нет")
    conflict = any(severity(o) == "clear" for o in fresh) and any(severity(o) != "clear" for o in fresh)

    offshore = bool(weather and weather.wind_ms >= OFFSHORE_MIN_MS
                    and angle_in_ranges(weather.wind_from_deg, zone.offshore_from or []))
    if offshore:
        level = raise_to(level, "risk")
        reasons.append(f"Отжимной ветер {weather.wind_ms:.0f} м/с")
    if weather and weather.crosses_zero:
        reasons.append("Оттепель: температура выше 0 °C")
    if zone.ban:
        level = "danger"
        reasons.insert(0, zone.ban_text or "Официальный запрет выхода на лёд")

    return ZoneStatus(
        level=level, reasons=list(dict.fromkeys(reasons)), fresh_count=len(fresh),
        last_observed_at=as_utc(valid[0].observed_at) if valid else None,
        conflict=conflict, fresh_window_h=int(fresh_win.total_seconds() // 3600), offshore_wind=offshore,
    )
