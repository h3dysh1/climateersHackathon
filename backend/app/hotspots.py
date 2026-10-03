"""Find the most affected areas at a given river rise.

Buildings are grouped into areas, either:
  - by name, if at least 80% of buildings carry an "area" (a settlement or suburb name from OpenStreetMap), or
  - by a square grid (default 250 m cells), using each building's lon/lat. Each grid area is then named after
    the place most of its buildings belong to, or else the nearest named building ("near Namotomoto"), so the
    list shows names people know instead of "Area 1". Names repeat with a number ("Namotomoto 2") when one
    place covers several cells.
Areas are ranked by people with water inside their homes, then by people in deep water (over 1 m).

This is predicted EXPOSURE from the HAND planning model, not observed damage: label it
"most affected areas" in the app, and check the top areas against past flood reports.
"""
import math
from collections import Counter

from . import flood

DEEP_M = 1.0  # water this deep or more at the building counts as "deep water"


def _cell(lon: float, lat: float, lat0: float, size_m: float) -> tuple[int, int]:
    x = lon * 111_320 * math.cos(math.radians(lat0))
    y = lat * 110_540
    return math.floor(x / size_m), math.floor(y / size_m)


def _cell_centre(cx: int, cy: int, lat0: float, size_m: float) -> tuple[float, float]:
    lon = (cx + 0.5) * size_m / (111_320 * math.cos(math.radians(lat0)))
    lat = (cy + 0.5) * size_m / 110_540
    return round(lon, 6), round(lat, 6)


def _grid_name(cell_buildings: list[dict], centre: tuple[float, float], named: list[dict], lat0: float) -> tuple[str | None, str]:
    """Name a grid area: the place most of its buildings carry, else the nearest named building's place."""
    names = Counter(b["area"] for b in cell_buildings if b.get("area"))
    if names:
        return names.most_common(1)[0][0], "place"
    if not named:
        return None, "grid"
    kx = 111_320 * math.cos(math.radians(lat0))
    near = min(named, key=lambda b: ((b["lon"] - centre[0]) * kx) ** 2 + ((b["lat"] - centre[1]) * 110_540) ** 2)
    return f"near {near['area']}", "nearest place"


def rank_areas(level_m: float, buildings: list[dict], facilities: list[dict] | None = None,
               cell_m: float = 250.0, top: int = 10) -> dict:
    facilities = facilities or []
    result = flood.assess(level_m, buildings, facilities)
    per_b = {r["id"]: r for r in result["buildings"]}
    # Group by name when most buildings have one (unnamed ones go to "Unnamed area"); else use a grid.
    named = sum(1 for b in buildings if b.get("area"))
    by_name = len(buildings) > 0 and named / len(buildings) >= 0.8
    located = [b for b in buildings if b.get("lon") is not None and b.get("lat") is not None]
    if not by_name and not located:
        return {"level_m": level_m, "grouping": "none", "areas": [],
                "note": "Buildings need lon/lat (or an 'area' name) to be grouped into areas."}
    lat0 = sum(b["lat"] for b in located) / len(located) if located else 0.0

    def key(item):
        if by_name:
            return item.get("area") or "Unnamed area"
        if item.get("lon") is None or item.get("lat") is None:
            return None
        return _cell(item["lon"], item["lat"], lat0, cell_m)

    areas: dict = {}
    for b in buildings:
        k = key(b)
        if k is None:
            continue
        a = areas.setdefault(k, {"buildings": 0, "people": 0.0, "buildings_water_inside": 0,
                                 "people_water_inside": 0.0, "people_deep_water": 0.0,
                                 "max_depth_m": 0.0, "lons": [], "lats": [], "facilities_flooded": [], "members": []})
        a["members"].append(b)
        r = per_b[b["id"]]
        a["buildings"] += 1
        a["people"] += b.get("people", 0)
        if r["water_inside"]:
            a["buildings_water_inside"] += 1
            a["people_water_inside"] += b.get("people", 0)
        if r["depth_m"] >= DEEP_M:
            a["people_deep_water"] += b.get("people", 0)
        a["max_depth_m"] = max(a["max_depth_m"], r["depth_m"])
        if b.get("lon") is not None:
            a["lons"].append(b["lon"])
            a["lats"].append(b["lat"])

    flooded_ids = {f["id"] for f in result["facilities_flooded"]}
    for f in facilities:
        if f["id"] in flooded_ids:
            k = key(f)
            if k in areas:
                areas[k]["facilities_flooded"].append(f.get("name") or f["id"])

    named_located = [b for b in located if b.get("area")]
    out = []
    for k, a in areas.items():
        if a["people_water_inside"] <= 0 and a["people_deep_water"] <= 0:
            continue
        if by_name:
            name, source = k, "place"
            lon = round(sum(a["lons"]) / len(a["lons"]), 6) if a["lons"] else None
            lat = round(sum(a["lats"]) / len(a["lats"]), 6) if a["lats"] else None
        else:
            lon, lat = _cell_centre(*k, lat0, cell_m)
            name, source = _grid_name(a["members"], (lon, lat), named_located, lat0)
        out.append({
            "name": name, "name_source": source, "lon": lon, "lat": lat,
            "buildings": a["buildings"],
            "buildings_water_inside": a["buildings_water_inside"],
            "share_water_inside": round(a["buildings_water_inside"] / a["buildings"], 2),
            "people_water_inside": round(a["people_water_inside"]),
            "people_deep_water": round(a["people_deep_water"]),
            "max_depth_m": round(a["max_depth_m"], 2),
            "facilities_flooded": a["facilities_flooded"],
        })
    out.sort(key=lambda x: (-x["people_water_inside"], -x["people_deep_water"], -x["max_depth_m"]))
    seen: Counter = Counter()
    for i, x in enumerate(out, 1):
        x["rank"] = i
        if x["name"] is None:
            x["name"] = f"Area {i}"
        else:
            seen[x["name"]] += 1
            if seen[x["name"]] > 1:  # one place spread over several cells: "Namotomoto", "Namotomoto 2"
                x["name"] = f"{x['name']} {seen[x['name']]}"
    total = result["people_water_inside"]
    top_list = out[: max(1, top)]
    return {
        "level_m": level_m,
        "grouping": "name" if by_name else f"grid {int(cell_m)} m",
        "areas_affected": len(out),
        "people_water_inside_total": total,
        "top_areas_share_of_people": round(sum(x["people_water_inside"] for x in top_list) / total, 2) if total else 0,
        "areas": top_list,
    }