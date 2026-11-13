"""Regenerates data/zones.geojson from the table below.

Centres are approximate points on the ice off well-known fishing spots near Vladivostok.
Before release, draw the real outlines (geojson.io, QGIS) and check offshore-wind sectors
with local rescuers: these are starting values, not verified data.

offshore_from: compass sectors (degrees the wind blows FROM) that push ice away from shore here.
"""
import json
import math
from pathlib import Path

ZONES = [
    # id, name, bay, lat, lon, radius_m, offshore_from, extra
    ("sedanka", "Седанка", "Амурский залив", 43.2050, 131.9020, 1100, [[20, 120]], {}),
    ("defriz", "Де-Фриз", "Амурский залив", 43.2600, 131.9300, 1300, [[0, 100]], {}),
    ("uglovoe", "Угловое", "Амурский залив", 43.3150, 131.9750, 1100, [[330, 40]], {}),
    ("shamora", "Шамора", "Уссурийский залив", 43.1990, 132.1150, 1200, [[350, 100]], {}),
    ("patrokl", "Патрокл", "Уссурийский залив", 43.0780, 131.9600, 900, [[315, 45]],
     {"ban": True, "ban_text": "МЧС: запрет выхода на лёд (пример, укажите реальный источник)"}),
    ("sukhodol", "Суходол", "Уссурийский залив", 43.3750, 132.3200, 1300, [[315, 45]], {}),
]


def hexagon(lat: float, lon: float, r_m: float) -> list[list[float]]:
    dlat = r_m / 111_320.0
    dlon = r_m / (111_320.0 * math.cos(math.radians(lat)))
    pts = []
    for k in range(6):
        a = math.radians(60 * k + 30)
        pts.append([round(lon + dlon * math.cos(a), 6), round(lat + dlat * math.sin(a), 6)])
    pts.append(pts[0])
    return pts


def main() -> None:
    features = []
    for zid, name, bay, lat, lon, r, offshore, extra in ZONES:
        props = {"id": zid, "name": name, "bay": bay, "offshore_from": offshore, **extra}
        features.append({
            "type": "Feature",
            "id": zid,
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [hexagon(lat, lon, r)]},
        })
    out = Path(__file__).resolve().parent.parent / "data" / "zones.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(features)} zones to {out}")


if __name__ == "__main__":
    main()
