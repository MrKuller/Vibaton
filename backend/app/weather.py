"""Open-Meteo client with a 30-minute cache and an explicit fallback.

Open-Meteo needs no API key. When it is unreachable we return the last good answer,
or demo values marked source="fallback" so the app never shows invented weather as real.
"""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field

import httpx

OPEN_METEO_URL = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
CACHE_TTL_S = 30 * 60
_cache: dict[tuple[float, float], tuple[float, "Weather"]] = {}


@dataclass
class Weather:
    temp_c: float
    wind_ms: float
    wind_gust_ms: float | None
    wind_from_deg: float
    days: list[dict] = field(default_factory=list)  # [{date, t_max, t_min}]
    source: str = "open-meteo"
    fetched_at: float = field(default_factory=time.time)

    @property
    def crosses_zero(self) -> bool:
        """Thaw signal: any day in the window rises above 0 °C."""
        return any(d.get("t_max") is not None and d["t_max"] > 0 for d in self.days)

    @property
    def warming_c(self) -> float:
        maxes = [d["t_max"] for d in self.days if d.get("t_max") is not None]
        return (maxes[-1] - maxes[0]) if len(maxes) >= 2 else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["wind_from"] = compass(self.wind_from_deg)
        d["crosses_zero"] = self.crosses_zero
        d["warming_c"] = round(self.warming_c, 1)
        return d


def compass(deg: float) -> str:
    names = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]
    return names[int((deg % 360) / 45 + 0.5) % 8]


def fallback() -> Weather:
    return Weather(
        temp_c=-8, wind_ms=12, wind_gust_ms=17, wind_from_deg=0,
        days=[{"date": d, "t_max": t, "t_min": t - 7} for d, t in
              [("d-2", -19), ("d-1", -15), ("d0", -11), ("d+1", -8), ("d+2", -2)]],
        source="fallback",
    )


def offline() -> bool:
    from .config import flag
    return flag("KL_OFFLINE")


def get_weather(lat: float, lon: float) -> Weather:
    key = (round(lat, 2), round(lon, 2))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        return hit[1]
    if offline():
        return hit[1] if hit else fallback()
    try:
        r = httpx.get(OPEN_METEO_URL, timeout=6, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m",
            "daily": "temperature_2m_max,temperature_2m_min",
            "wind_speed_unit": "ms", "timezone": "auto", "past_days": 2, "forecast_days": 3,
        })
        r.raise_for_status()
        j = r.json()
        cur, daily = j["current"], j["daily"]
        w = Weather(
            temp_c=cur["temperature_2m"], wind_ms=cur["wind_speed_10m"],
            wind_gust_ms=cur.get("wind_gusts_10m"), wind_from_deg=cur["wind_direction_10m"],
            days=[{"date": d, "t_max": mx, "t_min": mn} for d, mx, mn in
                  zip(daily["time"], daily["temperature_2m_max"], daily["temperature_2m_min"])],
        )
    except (httpx.HTTPError, KeyError, ValueError):
        return hit[1] if hit else fallback()
    _cache[key] = (time.time(), w)
    return w
