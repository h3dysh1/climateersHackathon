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


class _NearestName:
    """Finds the nearest named building quickly: named buildings are bucketed into ~1 km cells and
    the search widens ring by ring, instead of comparing against every named building."""

    def __init__(self, named: list[dict], lat0: float, cell_m: float = 1000.0):
        self.kx, self.ky, self.cell = 111_320 * math.cos(math.radians(lat0)), 110_540, cell_m
        # Thin the named buildings to one per place per ~50 m: the nearest NAME barely changes,
        # and it makes the search many times faster on real towns.
        thin: dict = {}
        for b in named:
            thin.setdefault((b["area"], round(b["lon"] * self.kx / 50), round(b["lat"] * self.ky / 50)), b)
        self.buckets: dict = {}
        for b in thin.values():
            self.buckets.setdefault(self._key(b["lon"], b["lat"]), []).append(b)
        self.max_ring = 200  # 60 km: far beyond any town

    def _key(self, lon, lat):
        return math.floor(lon * self.kx / self.cell), math.floor(lat * self.ky / self.cell)

    def find(self, lon: float, lat: float) -> dict | None:
        if not self.buckets:
            return None
        cx, cy = self._key(lon, lat)
        best, best_d = None, float("inf")
        for ring in range(self.max_ring + 1):
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    for b in self.buckets.get((cx + dx, cy + dy), ()):
                        d = ((b["lon"] - lon) * self.kx) ** 2 + ((b["lat"] - lat) * self.ky) ** 2
                        if d < best_d:
                            best, best_d = b, d
            # Anything in a further ring is at least `ring * cell` away.
            if best is not None and math.sqrt(best_d) <= ring * self.cell:
                return best
        return best


def _grid_name(cell_buildings: list[dict], centre: tuple[float, float], nearest: "_NearestName") -> tuple[str | None, str]:
    """Name a grid area: the place most of its buildings carry, else the nearest named building's place."""
    names = Counter(b["area"] for b in cell_buildings if b.get("area"))
    if names:
        return names.most_common(1)[0][0], "place"
    near = nearest.find(*centre)
    if near is None:
        return None, "grid"
    return f"near {near['area']}", "nearest place"


_NAME_CACHE: dict = {}  # (lon, lat, place names) -> "near X"; the same buildings arrive on every slider move


def _fill_names(items: list[dict], nearest: "_NearestName", sig) -> list[dict]:
    """Give every unnamed building/facility the name of the nearest named building, as "near <place>"."""
    if len(_NAME_CACHE) > 200_000:
        _NAME_CACHE.clear()
    out = []
    for b in items:
        if b.get("area") or b.get("lon") is None or b.get("lat") is None:
            out.append(b)
            continue
        key = (b["lon"], b["lat"], sig)
        if key not in _NAME_CACHE:
            near = nearest.find(b["lon"], b["lat"])
            _NAME_CACHE[key] = f"near {near['area']}" if near else None
        name = _NAME_CACHE[key]
        out.append({**b, "area": name} if name else b)
    return out


def rank_areas(level_m: float, buildings: list[dict], facilities: list[dict] | None = None,
               cell_m: float = 250.0, top: int = 10, group_by: str = "auto") -> dict:
    """group_by: "auto" (names if 80%+ of buildings have one, else grid), "grid" (250 m squares, named after
    their main place: precise targets for raising homes) or "place" (one row per village/suburb; unnamed
    buildings join "near <nearest place>": the clearest list for people)."""
    facilities = facilities or []
    result = flood.assess(level_m, buildings, facilities)
    per_b = {r["id"]: r for r in result["buildings"]}
    located = [b for b in buildings if b.get("lon") is not None and b.get("lat") is not None]
    lat_c = sum(b["lat"] for b in located) / len(located) if located else 0.0
    nearest = _NearestName([b for b in located if b.get("area")], lat_c)
    if group_by == "place" and located:
        sig = (len(nearest.buckets), tuple(sorted({b["area"] for b in located if b.get("area")})))
        buildings = _fill_names(buildings, nearest, sig)
        facilities = _fill_names(facilities, nearest, sig)
        located = [b for b in buildings if b.get("lon") is not None and b.get("lat") is not None]
    named = sum(1 for b in buildings if b.get("area"))
    if group_by == "place":
        by_name = named > 0
    elif group_by == "grid":
        by_name = False
    else:  # auto: group by name when most buildings have one (unnamed ones go to "Unnamed area"); else grid
        by_name = len(buildings) > 0 and named / len(buildings) >= 0.8
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

    out = []
    for k, a in areas.items():
        if a["people_water_inside"] <= 0 and a["people_deep_water"] <= 0:
            continue
        if by_name:
            name, source = k, ("nearest place" if str(k).startswith("near ") else "place")
            lon = round(sum(a["lons"]) / len(a["lons"]), 6) if a["lons"] else None
            lat = round(sum(a["lats"]) / len(a["lats"]), 6) if a["lats"] else None
        else:
            lon, lat = _cell_centre(*k, lat0, cell_m)
            name, source = _grid_name(a["members"], (lon, lat), nearest)
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
