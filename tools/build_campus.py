"""Build data/rvce/campus.json from source footprints and declared assumptions.

Inputs
  data/rvce/source/microsoft_buildings_rvce_area.geojson
      Microsoft Global ML Building Footprints (release 2026-02-03, quadkey 123303312),
      filtered to the RVCE neighbourhood. Licence: ODbL 1.0. Footprints are
      machine-detected from imagery; heights are not provided for this region (-1).
  data/rvce/overrides.json  (optional, hand-maintained)
      Verified names, uses, floor counts, campus membership per footprint id.
      Anything listed there replaces the defaults below and is marked verified.

Defaults (declared assumptions, all marked "verified": false in the output)
  * Campus membership: footprints south-east of the Mysore Road corridor and within
    260 m of RVCE's published coordinates (12.9239 N, 77.4997 E, Wikipedia infobox).
  * Floors: 3 for footprints of 300 m2 or more, 2 otherwise. Floor-to-floor height
    3.5 m (above the 2.75 m minimum habitable height of NBC 2016 Part 3).
  * Use: "academic" (BEE "Institutes"), unless overridden.
  * Annual energy = floor area x EPI, with EPI for the Moderate climate zone (Bengaluru)
    from BEE / UNDP-GEF "Energy benchmarks for Commercial Buildings":
    Institutes 129, Hospitals 247, Office (<50 % AC) 94 kWh/m2/yr.
    Hostels use the Office (<50 % AC) value as the closest non-AC benchmark (proxy).
  * Average demand = annual energy / 8760 h.
  * Local coordinates: equirectangular projection about the published coordinate
    (metres east/north); distortion is negligible over < 1 km.

    python tools/build_campus.py
"""

import json
import math
from pathlib import Path

from shapely.geometry import LineString, Point, shape
from shapely.affinity import rotate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "rvce" / "source" / "microsoft_buildings_rvce_area.geojson"
OVERRIDES = ROOT / "data" / "rvce" / "overrides.json"
OUT = ROOT / "data" / "rvce" / "campus.json"

LAT0, LON0 = 12.9239, 77.4997
KX = math.cos(math.radians(LAT0)) * 111_320.0
KY = 110_574.0

EPI = {  # kWh/m2/yr, BEE/UNDP-GEF benchmarks, Moderate zone
    "academic": (129, "BEE benchmark: Institutes, Moderate zone"),
    "library": (129, "BEE benchmark: Institutes, Moderate zone"),
    "admin": (94, "BEE benchmark: Office buildings <50% AC, Moderate zone"),
    "hostel": (94, "Proxy: BEE Office <50% AC (no BEE residential benchmark)"),
    "canteen": (129, "BEE benchmark: Institutes, Moderate zone"),
    "health": (247, "BEE benchmark: Hospitals, Moderate zone"),
    "other": (94, "Proxy: BEE Office <50% AC"),
}
FLOOR_HEIGHT_M = 3.5


def local(lon, lat):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def main():
    features = json.loads(SOURCE.read_text())["features"]
    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}
    polygons = []
    for i, f in enumerate(features):
        ring = [local(x, y) for x, y in f["geometry"]["coordinates"][0]]
        polygons.append((i, shape({"type": "Polygon", "coordinates": [ring]})))

    # Mysore Road corridor axis: the longest elongated footprint in the area
    # (375 m x 37 m, the elevated metro structure along the road median).
    def elongation(poly):
        rect = poly.minimum_rotated_rectangle
        xs, ys = rect.exterior.xy
        edges = [math.hypot(xs[k + 1] - xs[k], ys[k + 1] - ys[k]) for k in range(2)]
        return max(edges), min(edges), rect

    corridor_id, corridor = max(polygons, key=lambda p: elongation(p[1])[0] if elongation(p[1])[0] / max(elongation(p[1])[1], 1) > 6 else 0)
    length, width, rect = elongation(corridor)
    xs, ys = rect.exterior.xy
    edges = [((xs[k], ys[k]), (xs[k + 1], ys[k + 1])) for k in range(4)]
    (ax, ay), (bx, by) = max(edges, key=lambda e: math.dist(*e))
    angle = math.atan2(by - ay, bx - ax)
    ux, uy = math.cos(angle), math.sin(angle)
    cx, cy = corridor.centroid.x, corridor.centroid.y
    road = LineString([(cx - 900 * ux, cy - 900 * uy), (cx + 900 * ux, cy + 900 * uy)])

    def side(x, y):  # >0 north-west of the corridor axis, <0 south-east
        return ux * (y - cy) - uy * (x - cx)

    buildings = []
    for i, poly in polygons:
        if i == corridor_id:
            continue
        c = poly.centroid
        key = str(i)
        o = overrides.get(key, {})
        default_campus = side(c.x, c.y) < -25 and math.hypot(c.x, c.y) <= 260 and poly.area >= 40
        campus = o.get("campus", default_campus)
        floors = o.get("floors", 3 if poly.area >= 300 else 2)
        use = o.get("use", "academic" if campus else "other")
        epi, epi_source = EPI.get(use, EPI["other"])
        floor_area = poly.area * floors
        annual_kwh = floor_area * epi
        buildings.append({
            "id": i,
            "name": o.get("name", f"Block {i}" if campus else None),
            "campus": bool(campus),
            "use": use,
            "floors": floors,
            "height_m": round(floors * FLOOR_HEIGHT_M, 1),
            "footprint_m2": round(poly.area, 1),
            "floor_area_m2": round(floor_area, 1),
            "epi_kwh_m2_yr": epi,
            "epi_source": epi_source,
            "annual_kwh": round(annual_kwh),
            "average_kw": round(annual_kwh / 8760, 2),
            "verified": bool(o),
            "centroid": [round(c.x, 1), round(c.y, 1)],
            "polygon": [[round(x, 2), round(y, 2)] for x, y in list(poly.exterior.coords)[:-1]],
        })

    # Mysore Road carriageways either side of the metro median. NH-275 is a
    # six-lane divided highway on this stretch; carriageway width 10.5 m per side
    # (3 lanes x 3.5 m, IRC:SP:84 lane width) is a declared assumption.
    half = width / 2 + 10.5 / 2 + 1.0
    nx, ny = -uy, ux
    road_lines = []
    for sgn in (1, -1):
        p0 = (cx - 700 * ux + sgn * half * nx, cy - 700 * uy + sgn * half * ny)
        p1 = (cx + 700 * ux + sgn * half * nx, cy + 700 * uy + sgn * half * ny)
        road_lines.append({"name": "Mysore Road (NH-275) carriageway", "width_m": 10.5,
                           "points": [[round(p0[0], 1), round(p0[1], 1)], [round(p1[0], 1), round(p1[1], 1)]]})
    # Streetlights on the carriageway edges every 30 m (illustrative spacing; IS 1944
    # sets spacing from mounting height and lantern class, not modelled here).
    lights = []
    for sgn in (1, -1):
        for k in range(-23, 24):
            s = k * 30.0
            off = half + sgn * 0 + 10.5 / 2 + 0.8
            lights.append([round(cx + s * ux + sgn * off * nx, 1), round(cy + s * uy + sgn * off * ny, 1)])

    campus = [b for b in buildings if b["campus"]]
    out = {
        "origin": {"lat": LAT0, "lon": LON0, "source": "RVCE published coordinates (Wikipedia infobox)"},
        "projection": "equirectangular about origin; x east, y north, metres",
        "sources": {
            "footprints": "Microsoft Global ML Building Footprints, release 2026-02-03, ODbL 1.0",
            "epi": "BEE / UNDP-GEF, Energy benchmarks for Commercial Buildings (Moderate zone)",
        },
        "assumptions": [
            "Campus membership, building names, uses and floor counts are defaults until verified in data/rvce/overrides.json.",
            "Floor-to-floor height 3.5 m.",
            "Annual energy from BEE EPI benchmarks; replace with RVCE meter data when available.",
            "Road carriageway width and streetlight spacing are illustrative.",
        ],
        "corridor": {"id": corridor_id, "length_m": round(length, 1), "width_m": round(width, 1),
                     "polygon": [[round(x, 2), round(y, 2)] for x, y in list(corridor.exterior.coords)[:-1]]},
        "roads": road_lines,
        "streetlights": lights,
        "summary": {"campus_buildings": len(campus), "context_buildings": len(buildings) - len(campus),
                    "campus_floor_area_m2": round(sum(b["floor_area_m2"] for b in campus)),
                    "campus_annual_mwh": round(sum(b["annual_kwh"] for b in campus) / 1000, 1),
                    "campus_average_kw": round(sum(b["average_kw"] for b in campus), 1),
                    "verified_buildings": sum(b["verified"] for b in buildings)},
        "buildings": buildings,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
