"""Builds data/grid.geojson: an adaptive hexagonal grid over all water of the Amur and Ussuri bays.

Data: data/coast/land.geojson (GSHHG full-resolution coastline, ~100 m) and data/coast/rivers.geojson.
Cells are H3 hexagons (hierarchical: every cell splits into 7 smaller ones):
- open water, farther than COAST_BAND_M from the shore: resolution 8, ~0.74 km², ~460 m edge;
- near the shore: resolution 9, ~0.1 km², ~175 m edge — kept when at least MIN_WATER_SHARE of it is water,
  so bays, coves and the shore line itself are covered;
- rivers: resolution 10, ~0.015 km², ~65 m edge, along the river line (buffer = width_m / 2).

    pip install -r requirements-dev.txt      (shapely, h3)
    python tools/build_grid.py

To add a river or fix the coast, edit the files in data/coast/ (GeoJSON, [lon, lat]) and run again.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import h3
from shapely import affinity
from shapely.geometry import LineString, Polygon, box, shape
from shapely.ops import unary_union
from shapely.prepared import prep

DATA = Path(__file__).resolve().parent.parent / "data"
BBOX = {"lat_min": 42.95, "lat_max": 43.45, "lon_min": 131.55, "lon_max": 132.45}
RES_OPEN, RES_COAST, RES_RIVER = 8, 9, 10
COAST_BAND_M = 300
MIN_WATER_SHARE = 0.35
LAT0 = (BBOX["lat_min"] + BBOX["lat_max"]) / 2
M_PER_DEG = 111_320.0
KX = M_PER_DEG * math.cos(math.radians(LAT0))


def to_m(g):
    """lon/lat degrees -> local metres (equirectangular around LAT0): accurate enough for a 50 km area."""
    return affinity.scale(g, xfact=KX, yfact=M_PER_DEG, origin=(0, 0))


def bay_of(lat: float, lon: float) -> str:
    """The Muravyov-Amursky peninsula splits the bays north of ~43.10; further south the split runs at ~131.90."""
    if lat >= 43.10:
        return "Амурский залив" if lon < 132.02 else "Уссурийский залив"
    return "Амурский залив" if lon < 131.90 else "Уссурийский залив"


def cell_polygon(c: str) -> Polygon:
    return Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)])


def main() -> None:
    land = unary_union([shape(f["geometry"]).buffer(0) for f in
                        json.loads((DATA / "coast" / "land.geojson").read_text(encoding="utf-8"))["features"]])
    area = box(BBOX["lon_min"], BBOX["lat_min"], BBOX["lon_max"], BBOX["lat_max"])
    water = area.difference(land)
    water_m = to_m(water)
    shore_band_m = to_m(land).boundary.buffer(COAST_BAND_M)
    p_water_m = prep(water_m)
    p_band_m = prep(shore_band_m)

    cells: dict[str, str] = {}  # id -> kind
    # 1) open-water cells covering the whole area (cells crossing the coast are refined below)
    outer = h3.LatLngPoly([(lat, lng) for lng, lat in area.exterior.coords])
    for c in h3.polygon_to_cells(outer, RES_OPEN):
        poly_m = to_m(cell_polygon(c))
        if not p_water_m.intersects(poly_m):
            continue
        if p_water_m.contains(poly_m) and not p_band_m.intersects(poly_m):
            cells[c] = "open"
            continue
        for ch in h3.cell_to_children(c, RES_COAST):  # near the shore: 7 smaller cells
            ch_m = to_m(cell_polygon(ch))
            if ch_m.intersection(water_m).area / ch_m.area >= MIN_WATER_SHARE:
                cells[ch] = "coast"

    # 2) rivers: a chain of small cells along the line
    rivers = json.loads((DATA / "coast" / "rivers.geojson").read_text(encoding="utf-8"))["features"]
    river_cells = 0
    for f in rivers:
        line = LineString(f["geometry"]["coordinates"]).intersection(area)
        if line.is_empty:
            continue
        width = float(f["properties"].get("width_m", 100))
        corridor_m = to_m(line).buffer(max(width / 2, 40))
        corridor = affinity.scale(corridor_m, xfact=1 / KX, yfact=1 / M_PER_DEG, origin=(0, 0))
        poly = corridor if corridor.geom_type == "Polygon" else max(corridor.geoms, key=lambda g: g.area)
        for c in h3.polygon_to_cells(h3.LatLngPoly([(lat, lng) for lng, lat in poly.exterior.coords]), RES_RIVER):
            parent9, parent8 = h3.cell_to_parent(c, RES_COAST), h3.cell_to_parent(c, RES_OPEN)
            if parent9 in cells or parent8 in cells:
                continue  # already covered by bay cells
            cells[c] = "river:" + f["properties"].get("name", "река")
            river_cells += 1

    features = []
    for cid, kind in sorted(cells.items()):
        lat, lng = h3.cell_to_latlng(cid)
        ring = [[round(lng_, 5), round(lat_, 5)] for lat_, lng_ in h3.cell_to_boundary(cid)]
        ring.append(ring[0])
        river = kind.split(":", 1)[1] if kind.startswith("river:") else None
        features.append({
            "type": "Feature", "id": cid,
            "properties": {"id": cid, "kind": "river" if river else kind, "river": river,
                           "bay": f"р. {river}" if river else bay_of(lat, lng),
                           "res": h3.get_resolution(cid), "center": {"lat": round(lat, 6), "lon": round(lng, 6)}},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })
    out = {"type": "FeatureCollection",
           "properties": {"source": "GSHHG full coastline + H3 grid", "bbox": BBOX,
                          "resolutions": {"open": RES_OPEN, "coast": RES_COAST, "river": RES_RIVER},
                          "coast_band_m": COAST_BAND_M, "min_water_share": MIN_WATER_SHARE},
           "features": features}
    (DATA / "grid.geojson").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kinds = {k: sum(1 for v in cells.values() if v.split(":")[0] == k) for k in ("open", "coast", "river")}
    print(f"wrote {len(features)} cells ({kinds}) to {DATA / 'grid.geojson'}; water area "
          f"{water_m.area / 1e6:.0f} km², covered "
          f"{sum(to_m(cell_polygon(c)).intersection(water_m).area for c in cells if cells[c] != 'river' and not cells[c].startswith('river')) / water_m.area:.1%}")


if __name__ == "__main__":
    main()
