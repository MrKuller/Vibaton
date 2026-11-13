"""Geometry helpers. Zones are small polygons, so plain spherical math is enough."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

EARTH_M = 6_371_000.0
ZONES_FILE = Path(__file__).resolve().parent.parent / "data" / "zones.geojson"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_M * math.asin(math.sqrt(a))


def ring(geometry: dict) -> list[list[float]]:
    """Outer ring of a GeoJSON Polygon as [[lon, lat], ...]."""
    if geometry.get("type") != "Polygon":
        raise ValueError("only Polygon zones are supported")
    return geometry["coordinates"][0]


def centroid(geometry: dict) -> tuple[float, float]:
    pts = ring(geometry)[:-1] or ring(geometry)
    lat = sum(p[1] for p in pts) / len(pts)
    lon = sum(p[0] for p in pts) / len(pts)
    return lat, lon


def point_in_polygon(lat: float, lon: float, geometry: dict) -> bool:
    pts = ring(geometry)
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def distance_to_zone_m(lat: float, lon: float, geometry: dict) -> float:
    """0 inside the polygon, otherwise distance to the closest vertex (good enough for ~1 km zones)."""
    if point_in_polygon(lat, lon, geometry):
        return 0.0
    return min(haversine_m(lat, lon, p[1], p[0]) for p in ring(geometry))


def coarsen(lat: float, lon: float, step_m: float = 200.0) -> tuple[float, float]:
    """Snap a point to a ~200 m grid so a fishing spot is not exposed exactly."""
    dlat = step_m / 111_320.0
    dlon = step_m / (111_320.0 * math.cos(math.radians(lat)))
    return round(round(lat / dlat) * dlat, 5), round(round(lon / dlon) * dlon, 5)


def angle_in_ranges(deg: float, ranges: Iterable[Iterable[float]]) -> bool:
    deg %= 360
    for lo, hi in ranges:
        lo %= 360
        hi %= 360
        if (lo <= hi and lo <= deg <= hi) or (lo > hi and (deg >= lo or deg <= hi)):
            return True
    return False


def load_zones_geojson(path: Path = ZONES_FILE) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"{path} is not a FeatureCollection")
    return data
