"""The water grid (data/grid.geojson, built by tools/build_grid.py) and named places (data/places.json).

Cells are H3 hexagons of three sizes: open water (res 8, ~0.74 km²), near the shore (res 9, ~0.1 km²)
and along rivers (res 10, ~0.015 km²). Every cell is a "участок". Places are labels for search and
display ("у Седанки"); they carry offshore-wind sectors and official bans for cells within a radius.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import h3

from . import geo
from .config import DATA_DIR

PLACE_RADIUS_M = 4000      # a cell is "у <места>" when the place is this close
SNAP_MAX_M = 1500          # GPS points farther than this from any water cell are rejected
RESOLUTIONS = (10, 9, 8)   # finest first: a point belongs to the smallest cell that exists there


@dataclass
class Place:
    id: str
    name: str
    lat: float
    lon: float
    offshore_from: list
    ban: bool = False
    ban_radius_m: float = 0
    ban_text: str | None = None
    cell_id: str = ""
    bay: str = ""


@dataclass
class Cell:
    id: str
    bay: str
    kind: str          # open | coast | river
    lat: float
    lon: float
    geometry: dict
    river: str | None = None
    place: Place | None = None
    offshore_from: list = field(default_factory=list)
    ban: bool = False
    ban_text: str | None = None

    @property
    def name(self) -> str:
        if self.river:
            return f"Река {self.river}" + (f" у {genitive(self.place.name)}" if self.place else "")
        if self.place:
            return f"{'Берег' if self.kind == 'coast' else 'Участок'} у {genitive(self.place.name)}"
        return f"{self.bay}, {'у берега' if self.kind == 'coast' else 'открытая часть'}"


def genitive(name: str) -> str:
    """Седанка → Седанки, Угловое → Углового, Патрокл → Патрокла (enough for our place names)."""
    if name.endswith("ка"):
        return name[:-1] + "и"
    if name.endswith("ое"):
        return name[:-2] + "ого"
    if name.endswith("ая"):
        return name[:-2] + "ой"
    if name.endswith("а"):
        return name[:-1] + "ы"
    if name[-1] in "бвгджзклмнпрстфхцчшщ":
        return name + "а"
    return name


@dataclass
class Grid:
    cells: dict[str, Cell]
    places: dict[str, Place]
    compact_bytes: bytes     # what /grid sends: ids and centres; the app draws hexagons from the ids
    etag: str
    bay_centers: dict[str, tuple[float, float]]

    def cell_for_point(self, lat: float, lon: float) -> tuple[Cell | None, float]:
        """The H3 cell containing the point; off the grid — the nearest cell and its distance."""
        for res in RESOLUTIONS:
            c = self.cells.get(h3.latlng_to_cell(lat, lon, res))
            if c:
                return c, 0.0
        best, best_d = None, float("inf")
        for c in self.cells.values():
            d = geo.haversine_m(lat, lon, c.lat, c.lon)
            if d < best_d:
                best, best_d = c, d
        return best, best_d

    def resolve(self, zone_or_place_id: str) -> Cell | None:
        if zone_or_place_id in self.cells:
            return self.cells[zone_or_place_id]
        p = self.places.get(zone_or_place_id)
        return self.cells.get(p.cell_id) if p else None


@lru_cache(maxsize=1)
def load(data_dir: Path = DATA_DIR) -> Grid:
    fc = json.loads((data_dir / "grid.geojson").read_bytes())
    pl = json.loads((data_dir / "places.json").read_text(encoding="utf-8"))
    cells: dict[str, Cell] = {}
    for f in fc["features"]:
        p = f["properties"]
        cells[f["id"]] = Cell(id=f["id"], bay=p["bay"], kind=p.get("kind", "open"), river=p.get("river"),
                              lat=p["center"]["lat"], lon=p["center"]["lon"], geometry=f["geometry"])

    bays = sorted({c.bay for c in cells.values()})
    kinds = ["open", "coast", "river"]
    compact = {"v": 2, "kinds": kinds, "bays": bays,
               "cells": [[c.id, kinds.index(c.kind), bays.index(c.bay), round(c.lat, 5), round(c.lon, 5)]
                         for c in cells.values()]}
    raw = json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode()
    grid = Grid(cells=cells, places={}, compact_bytes=raw, etag=hashlib.sha1(raw).hexdigest()[:16], bay_centers={})
    for bay in bays:
        bc = [c for c in cells.values() if c.bay == bay]
        grid.bay_centers[bay] = (sum(c.lat for c in bc) / len(bc), sum(c.lon for c in bc) / len(bc))

    for d in pl["places"]:
        place = Place(id=d["id"], name=d["name"], lat=d["lat"], lon=d["lon"], offshore_from=d.get("offshore_from", []),
                      ban=bool(d.get("ban")), ban_radius_m=float(d.get("ban_radius_m", 0)), ban_text=d.get("ban_text"))
        cell, _ = grid.cell_for_point(place.lat, place.lon)
        place.cell_id, place.bay = cell.id, cell.bay
        grid.places[place.id] = place

    defaults = pl.get("default_offshore_from", {})
    for c in cells.values():
        near = [(geo.haversine_m(c.lat, c.lon, p.lat, p.lon), p) for p in grid.places.values()]
        d, p = min(near, key=lambda x: x[0]) if near else (float("inf"), None)
        if p and d <= PLACE_RADIUS_M:
            c.place = p
        c.offshore_from = (p.offshore_from if c.place else None) or defaults.get(c.bay, [])
        for bp in grid.places.values():
            if bp.ban and geo.haversine_m(c.lat, c.lon, bp.lat, bp.lon) <= max(bp.ban_radius_m, 1):
                c.ban, c.ban_text = True, bp.ban_text
    for bp in grid.places.values():  # the place's own cell is always covered by its ban
        if bp.ban:
            cells[bp.cell_id].ban, cells[bp.cell_id].ban_text = True, bp.ban_text
    return grid
