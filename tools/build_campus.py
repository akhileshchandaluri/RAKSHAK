"""Build data/rvce/campus.json from verified sources.

Sources, in order of precedence
  1. data/rvce/overrides.json          values confirmed by the project team (optional)
  2. OpenStreetMap (data/rvce/source/osm_rvce_area.json, ODbL 1.0, (c) OpenStreetMap
     contributors): campus outline (way 55685638), named buildings with
     building:levels, roads, paths, the Mysuru-Bengaluru metro line, the
     Vrishabhavati river.
  3. Microsoft Global ML Building Footprints (ODbL): buildings OSM does not map.
  4. RVCE documents (data/rvce/facts.json): built-up area, hostel capacities,
     rooftop solar (500 kW, eight named buildings), backup generators, HT supply.
  5. Declared assumptions, marked "assumed" per field: floor height 3.5 m,
     default floors where OSM has none, BEE benchmark energy intensity by use.

The ACE Group Architects key plan (NAAC Cr. 4.1.1) was registered to satellite
imagery and agrees with the OSM outline; see data/rvce/source/keyplan_registration.json.

    python tools/build_campus.py
"""

import json
import math
import re
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "rvce" / "source"
OUT = ROOT / "data" / "rvce" / "campus.json"
FACTS = json.loads((ROOT / "data" / "rvce" / "facts.json").read_text())
OVERRIDES = ROOT / "data" / "rvce" / "overrides.json"

LAT0, LON0 = 12.9239, 77.4997
KX = math.cos(math.radians(LAT0)) * 111_320.0
KY = 110_574.0
FLOOR_HEIGHT_M = 3.5
CAMPUS_WAY = 55685638

EPI = {   # kWh/m2/yr, BEE / UNDP-GEF benchmarks, Moderate climate zone
    "academic": (129, "BEE benchmark: Institutes, Moderate zone"),
    "library": (129, "BEE benchmark: Institutes, Moderate zone"),
    "admin": (94, "BEE benchmark: Office buildings <50 % AC, Moderate zone"),
    "hostel": (94, "Proxy: BEE Office <50 % AC (no BEE residential benchmark)"),
    "food": (129, "BEE benchmark: Institutes, Moderate zone"),
    "health": (247, "BEE benchmark: Hospitals, Moderate zone"),
    "sports": (94, "Proxy: BEE Office <50 % AC"),
    "residential": (94, "Proxy: BEE Office <50 % AC"),
    "construction": (0, "Under construction: no load"),
    "other": (94, "Proxy: BEE Office <50 % AC"),
}
DEFAULT_FLOORS = {"academic": 3, "library": 3, "admin": 3, "hostel": 4, "food": 2, "health": 2,
                  "sports": 2, "residential": 3, "construction": 4, "other": 2}


def local(lat, lon):
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


def classify(name, tags):
    n = (name or "").lower()
    if tags.get("building") == "construction" or tags.get("amenity") == "construction" or "u/c" in n \
            or tags.get("construction") or tags.get("building") == "construction":
        return "construction"
    if re.search(r"hostel|cauvery|chamundi|krishna hostel|jubli|jubilee|m ?v hostel", n):
        return "hostel"
    if re.search(r"medical|health|clinic", n) or tags.get("amenity") in ("hospital", "clinic"):
        return "health"
    if re.search(r"mingos|food|canteen|cafe|mess", n) or tags.get("amenity") in ("fast_food", "restaurant", "cafe"):
        return "food"
    if "library" in n:
        return "library"
    if re.search(r"admin|placement", n):
        return "admin"
    if re.search(r"sport|gymnatorium|gym", n):
        return "sports"
    if re.search(r"quarters", n):
        return "residential"
    return "academic"


def osm_polygon(e):
    if e["type"] == "way" and e.get("geometry"):
        pts = [local(p["lat"], p["lon"]) for p in e["geometry"]]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts).buffer(0)
    if e["type"] == "relation":
        members = [m for m in e.get("members", []) if m.get("geometry")]
        outer = [m for m in members if m.get("role") == "outer"] or [m for m in members if m.get("role") != "inner"]
        lines = [LineString([local(p["lat"], p["lon"]) for p in m["geometry"]]) for m in outer if len(m["geometry"]) > 1]
        polys = list(polygonize(unary_union(lines))) if lines else []
        if polys:
            return max(polys, key=lambda p: p.area)
    return None


def main():
    osm = json.loads((SRC / "osm_rvce_area.json").read_text())["elements"]
    msb = json.loads((SRC / "microsoft_buildings_rvce_area.geojson").read_text())["features"]
    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {}

    campus_poly = next(osm_polygon(e) for e in osm if e["type"] == "way" and e["id"] == CAMPUS_WAY)

    # ------------------------------------------------------------ buildings
    buildings = []
    osm_polys = []
    for e in osm:
        tags = e.get("tags", {})
        if "building" not in tags:
            continue
        poly = osm_polygon(e)
        if poly is None or poly.area < 15 or poly.geom_type != "Polygon":
            continue
        osm_polys.append(poly)
        buildings.append({"source": "OpenStreetMap", "osm": f"{e['type']}/{e['id']}", "poly": poly,
                          "name": tags.get("name"), "tags": tags})
    osm_union = unary_union(osm_polys)
    for i, f in enumerate(msb):
        ring = [local(lat, lon) for lon, lat in f["geometry"]["coordinates"][0]]
        poly = Polygon(ring).buffer(0)
        if poly.area < 15:
            continue
        if poly.intersection(osm_union).area > 0.3 * poly.area:
            continue        # already mapped in OSM
        buildings.append({"source": "Microsoft ML footprints", "msb": i, "poly": poly, "name": None, "tags": {}})

    # Named campus elements mapped as non-building areas (e.g. "Medical Centre") lend their
    # name to the building that contains their centre.
    named_areas = []
    for e in osm:
        tags = e.get("tags", {})
        if tags.get("name") and "building" not in tags and e["type"] in ("way", "relation") and (
                tags.get("amenity") or tags.get("building:part") or tags.get("landuse") == "university"):
            p = osm_polygon(e)
            if p is not None and p.area < 15000 and campus_poly.contains(p.centroid):
                named_areas.append((p, tags["name"], tags))
    # Building relations delivered without member geometry: fall back to their bounding box.
    for e in osm:
        tags = e.get("tags", {})
        if e["type"] == "relation" and "building" in tags and tags.get("name") and not e.get("members") and e.get("bounds"):
            b = e["bounds"]
            (x0, y0), (x1, y1) = local(b["minlat"], b["minlon"]), local(b["maxlat"], b["maxlon"])
            box = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            if campus_poly.contains(box.centroid):
                named_areas.append((box, tags["name"], tags))

    out_buildings = []
    for k, b in enumerate(buildings):
        poly = b["poly"]
        c = poly.centroid
        on_campus = campus_poly.contains(c)
        name, tags = b["name"], b["tags"]
        if on_campus and not name:
            best = max(((poly.intersection(p).area / poly.area, n, t) for p, n, t in named_areas), default=(0, None, None))
            if best[0] > 0.4:
                name, tags = best[1], {**best[2], **tags}
        key = b.get("osm") or f"msb/{b['msb']}"
        o = overrides.get(key, {})
        use = o.get("use") or (classify(name, tags) if on_campus else "other")
        levels_tag = tags.get("building:levels")
        if o.get("floors"):
            floors, floors_src = int(o["floors"]), "confirmed"
        elif levels_tag and re.fullmatch(r"\d+(\.\d+)?", levels_tag) and float(levels_tag) > 0:
            floors, floors_src = int(round(float(levels_tag))), "OpenStreetMap building:levels"
        else:
            floors, floors_src = (DEFAULT_FLOORS[use] if on_campus else (3 if poly.area > 300 else 2)), "assumed"
        institution = None
        if on_campus:
            institution = "RV University" if re.match(r"rvu\b|rv univ", (name or "").lower()) else "RVCE"
        epi, epi_src = EPI.get(use, EPI["other"])
        floor_area = poly.area * floors
        annual = floor_area * epi
        out_buildings.append({
            "id": k, "key": key, "source": b["source"],
            "name": o.get("name") or name, "campus": on_campus, "institution": institution,
            "use": use, "floors": floors, "floors_source": floors_src,
            "height_m": round(floors * FLOOR_HEIGHT_M, 1),
            "footprint_m2": round(poly.area, 1), "floor_area_m2": round(floor_area, 1),
            "epi_kwh_m2_yr": epi, "epi_source": epi_src,
            "annual_kwh": round(annual), "average_kw": round(annual / 8760, 2),
            "verified": bool(o) or (b["source"] == "OpenStreetMap" and bool(name)),
            "centroid": [round(c.x, 1), round(c.y, 1)],
            "polygon": [[round(x, 2), round(y, 2)] for x, y in list(poly.exterior.coords)[:-1]],
        })

    # Calibrate energy to documented floor areas: RVCE built-up area (academic and support,
    # 67,721 m2) and boys' hostels (38,659 m2), both from the NAAC SSR. Geometry is kept; the
    # energy-bearing floor area of each building is scaled by its group's factor.
    groups = {"hostel": FACTS["hostels"]["boys"]["area_m2"], "rest": FACTS["campus"]["built_up_m2"]}
    rvce_live = [b for b in out_buildings if b["campus"] and b["institution"] == "RVCE" and b["use"] != "construction"]
    for g, target in groups.items():
        members = [b for b in rvce_live if (b["use"] == "hostel") == (g == "hostel")]
        modelled = sum(b["floor_area_m2"] for b in members)
        factor = target / modelled if modelled else 1.0
        for b in members:
            b["energy_floor_area_m2"] = round(b["floor_area_m2"] * factor, 1)
            b["calibration_factor"] = round(factor, 3)
            b["annual_kwh"] = round(b["energy_floor_area_m2"] * b["epi_kwh_m2_yr"])
            b["average_kw"] = round(b["annual_kwh"] / 8760, 2)
            b["epi_source"] += f"; floor area scaled x{factor:.2f} to the documented total"

    # Rooftop solar: 500 kW SRTPV on eight named buildings (BESCOM commissioning report;
    # NAAC Cr. 7.1.2). Split by roof area, which the documents do not give per building.
    solar = FACTS["solar"]
    hosts = []
    for name_pattern in solar["buildings_osm_name_patterns"]:
        match = [b for b in out_buildings if b["campus"] and b["name"] and re.search(name_pattern, b["name"], re.I)]
        if match:
            hosts.append(max(match, key=lambda b: b["footprint_m2"]))
    roof = sum(b["footprint_m2"] for b in hosts)
    for b in hosts:
        b["solar_kwp"] = round(solar["capacity_kw"] * b["footprint_m2"] / roof, 1)
        b["solar_source"] = solar["source"] + " (share by roof area: assumed)"

    # ------------------------------------------------------------ linework
    widths = {"trunk": 21.0, "primary": 14.0, "tertiary": 8.0, "service": 5.0, "residential": 6.0,
              "unclassified": 6.0, "footway": 2.5, "path": 2.0, "pedestrian": 4.0, "steps": 2.0}
    roads, rail, river = [], [], []
    for e in osm:
        tags = e.get("tags", {})
        if e["type"] != "way" or not e.get("geometry"):
            continue
        pts = [[round(v, 1) for v in local(p["lat"], p["lon"])] for p in e["geometry"]]
        if tags.get("highway") in widths:
            roads.append({"name": tags.get("name"), "kind": tags["highway"], "width_m": widths[tags["highway"]],
                          "points": pts})
        elif tags.get("railway") in ("subway", "light_rail", "rail") and not tags.get("service"):
            rail.append({"name": tags.get("name"), "points": pts})
        elif tags.get("name") == "Vrishabhavati" or tags.get("waterway") in ("river", "stream"):
            river.append({"name": tags.get("name") or "stream", "points": pts})

    # Streetlights along campus roads: the SSR reports solar-powered streetlights; spacing
    # of 25 m is illustrative.
    lights = []
    for r in roads:
        if r["kind"] not in ("service", "tertiary", "residential", "pedestrian"):
            continue
        line = LineString(r["points"])
        if not campus_poly.buffer(20).intersects(line):
            continue
        for s in range(0, int(line.length), 25):
            p = line.interpolate(s)
            if campus_poly.buffer(10).contains(p):
                lights.append([round(p.x, 1), round(p.y, 1)])

    # ------------------------------------------------------------ neighbourhood
    def fleet_type(i):
        first = ["house", "house", "clinic", "house", "shop", "house",
                 "house", "apartment", "cold_chain", "water_service", "house", "house"]
        if i < len(first):
            return first[i]
        return "apartment" if i % 20 == 0 else "clinic" if i % 50 == 0 else "house"

    near = sorted((b for b in out_buildings if not b["campus"] and b["footprint_m2"] >= 30),
                  key=lambda b: math.hypot(*b["centroid"]))[:500]
    by_size = sorted(near, key=lambda b: -b["footprint_m2"])
    assignment = dict(zip([i for i in range(500) if fleet_type(i) != "house"], by_size))
    rest = [b for b in near if all(b is not v for v in assignment.values())]
    for i in range(500):
        if i not in assignment:
            assignment[i] = rest.pop(0)
    households = [{"fleet_index": i, "footprint_id": assignment[i]["id"], "type": fleet_type(i)} for i in range(500)]

    campus = [b for b in out_buildings if b["campus"]]
    rvce = [b for b in campus if b["institution"] == "RVCE" and b["use"] != "construction"]
    out = {
        "origin": {"lat": LAT0, "lon": LON0, "source": "RVCE published coordinates"},
        "projection": "equirectangular about origin; x east, y north, metres",
        "sources": {
            "outline_names_roads": "OpenStreetMap contributors, ODbL 1.0",
            "unmapped_footprints": "Microsoft Global ML Building Footprints, ODbL 1.0",
            "key_plan": "ACE Group Architects key plan in RVCE NAAC Cr. 4.1.1, registered to Esri World Imagery",
            "facts": "RVCE NAAC SSR (2024), BESCOM SRTPV commissioning report, RVCE website",
            "epi": "BEE / UNDP-GEF Energy benchmarks for Commercial Buildings (Moderate zone)",
        },
        "assumptions": [
            "Floor height 3.5 m. Floors default by use where OpenStreetMap has no building:levels.",
            "Energy from floor area x BEE benchmark; RVCE meter data would replace it.",
            "Rooftop solar shares per building follow roof area (total 500 kW is documented).",
            "Streetlight spacing (25 m) is illustrative; the SSR reports solar streetlights.",
            "The 500 households are simulated, placed on the nearest non-campus footprints.",
        ],
        "facts": FACTS,
        "boundary": [[round(x, 1), round(y, 1)] for x, y in list(campus_poly.exterior.coords)[:-1]],
        "roads": roads, "rail": rail, "river": river, "streetlights": lights,
        "summary": {
            "campus_area_acres": round(campus_poly.area / 4046.86, 2),
            "campus_buildings": len(campus), "named": sum(1 for b in campus if b["name"]),
            "rvce_floor_area_m2": round(sum(b["floor_area_m2"] for b in rvce)),
            "rvce_energy_floor_area_m2": round(sum(b.get("energy_floor_area_m2", b["floor_area_m2"]) for b in rvce)),
            "rvce_documented_built_up_m2": FACTS["campus"]["built_up_m2"],
            "campus_average_kw": round(sum(b["average_kw"] for b in campus), 1),
            "solar_hosts": [b["name"] for b in hosts],
        },
        "households": households,
        "buildings": out_buildings,
    }
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    print(json.dumps(out["summary"], indent=1))


if __name__ == "__main__":
    main()
