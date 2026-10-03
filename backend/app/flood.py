"""Flood model: who floods at a given water level, and what planning measures change.

A deliberately simple planning model, labelled as indicative in the app. Heights are HAND
(height above nearest drainage) from data-prep/hand_flood.py:
  - level_m is how far the river (or sea) rises above its normal level, in metres.
  - A building is reached by water once level_m >= floods_at_m (precomputed by data-prep using
    connectivity to the river/sea; if missing we fall back to the building's ground height).
  - Water depth at a building = level_m - ground_m (ground_m is the building's HAND).
  - Water enters the home when level_m > floor_m (ground + floor height).
It does NOT simulate river flow, rainfall or timing. The three options are what-if planning levers,
not engineering designs; their assumptions are listed in measures.json and shown in the app:
  - channel_clearing_m: dredging/desilting lowers every flood by a fixed amount (town-wide);
  - nature_based: riverbank vegetation buffers lower floods by a %, fading for big floods (town-wide);
  - raise_homes: lift chosen homes, optionally in one target area, e.g. a hotspot:
    {"area": "Riverside"} or {"lon": 177.44, "lat": -17.80, "radius_m": 300}.
"""
import json
import math
from pathlib import Path

MEASURES: dict = json.loads((Path(__file__).parent / "measures.json").read_text())

DEFAULT_FLOOR_HEIGHT_M = MEASURES["_defaults"]["floor_height_m"]
IMPASSABLE_DEPTH_M = MEASURES["_defaults"]["impassable_depth_m"]
DEPTH_BANDS = [(0.5, "under_0_5m"), (1.0, "0_5_to_1m"), (2.0, "1_to_2m"), (float("inf"), "over_2m")]


def _depth_band(depth: float) -> str:
    for upper, name in DEPTH_BANDS:
        if depth < upper:
            return name
    return "over_2m"


def _reached(b: dict, level: float) -> bool:
    return level >= b.get("floods_at_m", b["ground_m"])


def raise_by_default() -> float:
    return MEASURES["raise_homes"]["default_height_m"]


def _floor(b: dict) -> float:
    return b["ground_m"] + b.get("floor_height_m", DEFAULT_FLOOR_HEIGHT_M)


def _is_home(b: dict) -> bool:
    return b.get("type", "home") == "home"


def in_target(item: dict, target: dict | None) -> bool:
    """Is a building/facility inside the targeted area? No target = everywhere."""
    if not target:
        return True
    if target.get("area"):
        return item.get("area") == target["area"]
    if target.get("lon") is not None and target.get("lat") is not None:
        if item.get("lon") is None or item.get("lat") is None:
            return False
        dx = (item["lon"] - target["lon"]) * 111_320 * math.cos(math.radians(target["lat"]))
        dy = (item["lat"] - target["lat"]) * 110_540
        return math.hypot(dx, dy) <= float(target.get("radius_m", 250))
    return True


def pick_homes_to_raise(buildings: list[dict], count: int, level: float, raise_by: float,
                        target: dict | None = None) -> list[str]:
    """Pick up to `count` homes where raising by `raise_by` actually keeps water out at `level`.
    Homes in water too deep for that raise are skipped (they need other options).
    Most people first; on ties, the home that floods first (it floods most often)."""
    savable = [b for b in buildings
               if _is_home(b) and in_target(b, target) and _reached(b, level) and _floor(b) < level <= _floor(b) + raise_by]
    savable.sort(key=lambda b: (-b.get("people", 0), b.get("floods_at_m", b["ground_m"])))
    return [b["id"] for b in savable[: max(0, count)]]


def nature_reduction_m(level_m: float, reduction_pct: float) -> float:
    """How much riverbank vegetation lowers a flood of `level_m` (m).
    Full percentage for floods up to full_effect_up_to_m, fading linearly to big_flood_effect_share of it
    by big_flood_m (and staying there), because vegetation stores and slows less of a very big flood."""
    if level_m <= 0 or reduction_pct <= 0:
        return 0.0
    cfg = MEASURES["nature_based"]
    full, big, share = cfg["full_effect_up_to_m"], cfg["big_flood_m"], cfg["big_flood_effect_share"]
    fade = 1.0 if level_m <= full else max(share, 1.0 - (1.0 - share) * (level_m - full) / (big - full))
    return level_m * reduction_pct / 100 * fade


def effective_level(level_m: float, measures: dict | None) -> float:
    """River rise after the two town-wide options. Vegetation acts on the incoming flood,
    then a cleared channel lowers what is left. Neither can push the river below normal."""
    m = measures or {}
    level = level_m
    nb = m.get("nature_based") or {}
    if nb:
        level -= nature_reduction_m(level_m, float(nb.get("reduction_pct", MEASURES["nature_based"]["default_reduction_pct"])))
    level -= max(0.0, float(m.get("channel_clearing_m", 0) or 0))
    return min(level_m, max(level, min(level_m, 0.0)))


def assess(level_m: float, buildings: list[dict], facilities: list[dict] | None = None,
           roads: list[dict] | None = None, measures: dict | None = None) -> dict:
    """Impact of one flood level, optionally with any of the three options applied:
    channel_clearing_m (dredging), nature_based {reduction_pct} and raise_homes {count, height_m, target}."""
    facilities, roads, m = facilities or [], roads or [], measures or {}
    level = effective_level(level_m, m)

    # Raise homes: chosen at the design level (so a chart across many levels keeps the same homes).
    # A caller can pass "ids" to fix exactly which homes are raised (used when layering options).
    raise_cfg = m.get("raise_homes") or {}
    raise_by = float(raise_cfg.get("height_m", raise_by_default())) if raise_cfg else 0.0
    if raise_cfg.get("ids") is not None:
        raised = set(raise_cfg["ids"])
    elif raise_cfg:
        design = effective_level(float(raise_cfg.get("design_level_m", level_m)), m)
        raised = set(pick_homes_to_raise(buildings, int(raise_cfg.get("count", 0)), design, raise_by, raise_cfg.get("target")))
    else:
        raised = set()

    bands = {name: 0 for _, name in DEPTH_BANDS}
    reached = above_floor = people_reached = people_above_floor = deep_homes = 0
    per_building = []
    for b in buildings:
        floor = _floor(b) + (raise_by if b["id"] in raised else 0)
        is_reached = _reached(b, level)
        if _is_home(b) and is_reached and level - floor > raise_by_default():
            deep_homes += 1
        depth = round(max(0.0, level - b["ground_m"]), 2) if is_reached else 0.0
        inside = is_reached and level > floor
        if is_reached:
            reached += 1
            people_reached += b.get("people", 0)
            bands[_depth_band(depth)] += 1
        if inside:
            above_floor += 1
            people_above_floor += b.get("people", 0)
        per_building.append({"id": b["id"], "depth_m": depth, "water_inside": inside, "raised": b["id"] in raised})

    fac_out = []
    for f in facilities:
        hit = _reached(f, level) and level > f["ground_m"] + f.get("floor_height_m", DEFAULT_FLOOR_HEIGHT_M)
        fac_out.append({"id": f["id"], "name": f.get("name"), "type": f.get("type"), "flooded": hit})

    cut = [r["id"] for r in roads if level - r["low_point_m"] >= IMPASSABLE_DEPTH_M]

    return {
        "level_m": level_m,
        "effective_level_m": round(level, 2),
        "buildings_reached": reached,
        "buildings_water_inside": above_floor,
        "people_reached": round(people_reached),
        "people_water_inside": round(people_above_floor),
        "depth_bands": bands,
        "facilities_flooded": [f for f in fac_out if f["flooded"]],
        "roads_cut": cut,
        "roads_cut_km": round(sum(r.get("length_m", 0) for r in roads if r["id"] in cut) / 1000, 2),
        "homes_raised": sorted(raised),
        "homes_too_deep_to_raise": deep_homes,
        "buildings": per_building,
    }


def compare(level_m, buildings, facilities=None, roads=None, measures=None) -> dict:
    """Baseline vs with-measures at one level, plus what the measures saved."""
    base = assess(level_m, buildings, facilities, roads)
    after = assess(level_m, buildings, facilities, roads, measures)
    saved = {
        "people_kept_dry_inside": base["people_water_inside"] - after["people_water_inside"],
        "homes_kept_dry_inside": base["buildings_water_inside"] - after["buildings_water_inside"],
        "facilities_protected": len(base["facilities_flooded"]) - len(after["facilities_flooded"]),
        "roads_reopened": len(base["roads_cut"]) - len(after["roads_cut"]),
    }
    return {"baseline": base, "with_measures": after, "saved": saved, "measures": measures or {}}


def curve(levels: list[float], buildings, facilities=None, roads=None, measures=None) -> list[dict]:
    """Counts at many levels, for a chart. Per-building detail is dropped to keep it small."""
    out = []
    for lv in levels:
        b = assess(lv, buildings, facilities, roads)
        a = assess(lv, buildings, facilities, roads, measures) if measures else b
        out.append({"level_m": lv,
                    "people_water_inside": b["people_water_inside"],
                    "people_water_inside_with_measures": a["people_water_inside"],
                    "buildings_reached": b["buildings_reached"],
                    "roads_cut": len(b["roads_cut"])})
    return out