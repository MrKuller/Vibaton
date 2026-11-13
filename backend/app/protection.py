"""Protection of the API and the MySQL server behind it against floods and accidental overload.

What the application can do (this module):
- per-IP rate limits by route group (token bucket), 429 with Retry-After when exceeded;
- a short cache for heavy read endpoints, so 1000 map refreshes cost one database query;
- a request body size limit;
- a cap on photos processed at once (image models are the heaviest work);
- connection pool and statement time limits are in db.py.

What it cannot do: stop a volumetric DDoS that fills the network link. That needs a proxy or provider
in front of the server (Cloudflare, DDoS-Guard, the hosting's own filter) — see README.
Limits live in this process's memory: with several uvicorn workers each has its own counters.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from . import config

MAX_BODY_BYTES = 9 * 1024 * 1024  # an 8 MB photo plus form overhead


def client_ip(request: Request) -> str:
    if config.TRUSTED_PROXY:
        fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
        if fwd.strip():
            return fwd.strip()
    return request.client.host if request.client else "unknown"


@dataclass
class Rule:
    rate: float   # tokens per second
    burst: int    # bucket size


# route group -> rule. Reads are cheap (cached); writes and auth are strict.
RULES = {
    "auth": Rule(rate=5 / 60, burst=5),          # login/register: 5 per minute
    "photo": Rule(rate=6 / 60, burst=3),         # photo uploads: 6 per minute
    "write": Rule(rate=30 / 60, burst=10),       # publish, react, delete
    "read": Rule(rate=5, burst=60),              # map, feed, weather
}


def group_of(request: Request) -> str:
    p, m = request.url.path, request.method
    if p.startswith("/auth/"):
        return "auth" if m == "POST" else "read"
    if p.endswith("/photo"):
        return "photo"
    return "write" if m in ("POST", "PUT", "PATCH", "DELETE") else "read"


class _Buckets:
    def __init__(self, max_keys: int = 50_000):
        self.data: OrderedDict[tuple[str, str], tuple[float, float]] = OrderedDict()
        self.max_keys = max_keys

    def take(self, key: tuple[str, str], rule: Rule) -> float:
        """Returns 0 when allowed, otherwise seconds to wait."""
        now = time.monotonic()
        tokens, ts = self.data.pop(key, (float(rule.burst), now))
        tokens = min(rule.burst, tokens + (now - ts) * rule.rate)
        if tokens >= 1:
            self.data[key] = (tokens - 1, now)
            wait = 0.0
        else:
            self.data[key] = (tokens, now)
            wait = (1 - tokens) / rule.rate
        while len(self.data) > self.max_keys:  # an attacker with many IPs must not exhaust memory
            self.data.popitem(last=False)
        return wait


buckets = _Buckets()


class ProtectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Слишком большой запрос"}, status_code=413)
        if config.RATE_LIMIT_ENABLED and request.url.path not in ("/health",):
            g = group_of(request)
            wait = buckets.take((client_ip(request), g), RULES[g])
            if wait > 0:
                return JSONResponse({"detail": "Слишком много запросов. Подождите немного и повторите."},
                                    status_code=429, headers={"Retry-After": str(int(wait) + 1)})
        return await call_next(request)


# ---------- short cache for heavy reads ----------
class TTLCache:
    def __init__(self, ttl_s: float):
        self.ttl = ttl_s
        self.store: dict[str, tuple[float, object]] = {}

    def get(self, key: str):
        hit = self.store.get(key)
        return hit[1] if hit and time.monotonic() - hit[0] < self.ttl else None

    def put(self, key: str, value) -> None:
        self.store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self.store.clear()


read_cache = TTLCache(ttl_s=20)  # /status, /alerts, /clusters; cleared on every write


# ---------- heavy image work ----------
photo_slots = asyncio.Semaphore(max(1, config.PHOTO_WORKERS))
