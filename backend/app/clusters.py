"""Groups danger reports that are close in space and time.

A cluster = danger/risk reports within RADIUS_M of each other in the last WINDOW,
from at least MIN_USERS different people. Several posts by one person count once,
so nobody can create "confirmations" alone. 200 m is a starting value for experiments,
not a safety boundary: tune it to GPS accuracy and the shape of the bays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import geo
from .status import as_utc, counts_for_status, is_wrong, severity

RADIUS_M = 200
WINDOW = timedelta(hours=6)
MIN_USERS = 2


@dataclass
class Cluster:
    lat: float
    lon: float
    zone_id: str
    observation_ids: list[int] = field(default_factory=list)
    users: int = 0
    level: str = "risk"
    signs: list[str] = field(default_factory=list)


def find_clusters(observations: list, now: datetime) -> list[Cluster]:
    pts = [o for o in observations
           if o.lat is not None and o.lon is not None and severity(o) != "clear" and not is_wrong(o) and counts_for_status(o)
           and now - as_utc(o.observed_at) < WINDOW]
    pts.sort(key=lambda o: as_utc(o.observed_at), reverse=True)
    used: set[int] = set()
    out: list[Cluster] = []
    for seed in pts:
        if seed.id in used:
            continue
        group = [o for o in pts if o.id not in used
                 and geo.haversine_m(seed.lat, seed.lon, o.lat, o.lon) <= RADIUS_M]
        users = {o.user_id for o in group}
        if len(users) < MIN_USERS:
            continue
        used.update(o.id for o in group)
        signs = sorted({o.type for o in group})
        out.append(Cluster(
            lat=sum(o.lat for o in group) / len(group), lon=sum(o.lon for o in group) / len(group),
            zone_id=seed.zone_id, observation_ids=[o.id for o in group], users=len(users),
            level="danger" if any(severity(o) == "danger" for o in group) else "risk", signs=signs,
        ))
    return out
