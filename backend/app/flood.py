"""Flood model: who floods at a given water level, and what planning measures change.

A deliberately simple "fill to height" (bathtub) model, labelled as indicative in the app:
  - level_m is the flood water surface in metres above sea level.
  - A building is reached by water once level_m >= floods_at_m (precomputed by data-prep using
    connectivity to the river/sea; if missing we fall back to the building's ground height).
  - Water depth at a building = level_m - ground_m.
  - Water enters the home when level_m > floor_m (ground + floor height).
Measures are what-if planning levers, not engineering designs; their assumptions are listed in measures.json and shown in the app.
"""
import json
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


def pick_homes_to_raise(buildings: list[dict], count: int, level: float, raise_by: float) -> list[str]:
    """Pick up to `count` homes where raising by `raise_by` actually keeps water out at `level`.
    Homes in water too deep for that raise are skipped (they need other options, e.g. relocation).
    Most people first; on ties, the home that floods first (it floods most often)."""
    savable = [b for b in buildings
               if b.get("type", "home") == "home" and _reached(b, level) and _floor(b) < level <= _floor(b) + raise_by]
    savable.sort(key=lambda b: (-b.get("people", 0), b.get("floods_at_m", b["ground_m"])))
    return [b["id"] for b in savable[: max(0, count)]]


def assess(level_m: float, buildings: list[dict], facilities: list[dict] | None = None,
           roads: list[dict] | None = None, measures: dict | None = None) -> dict:
    """Impact of one flood level, optionally with measures applied."""
    facilities, roads, m = facilities or [], roads or [], measures or {}

    lowered = max(0.0, float(m.get("lower_flood_level_m", 0) or 0))
    level = level_m - lowered
    raise_cfg = m.get("raise_homes") or {}
    raise_by = float(raise_cfg.get("height_m", MEASURES["raise_homes"]["default_height_m"])) if raise_cfg else 0.0
    # Homes are chosen at the design level (so a chart across many levels keeps the same homes).
    design = float(raise_cfg.get("design_level_m", level_m)) - lowered if raise_cfg else level
    raised = set(pick_homes_to_raise(buildings, int(raise_cfg.get("count", 0)), design, raise_by)) if raise_cfg else set()
    moved = set(m.get("relocate_facilities") or [])

    bands = {name: 0 for _, name in DEPTH_BANDS}
    reached = above_floor = people_reached = people_above_floor = 0
    deep_homes = 0
    per_building = []
    for b in buildings:
        floor = _floor(b) + (raise_by if b["id"] in raised else 0)
        if b.get("type", "home") == "home" and _reached(b, level) and level - floor > raise_by_default():
            deep_homes += 1
        is_reached = _reached(b, level)
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
        hit = f["id"] not in moved and _reached(f, level) and level > f["ground_m"] + f.get("floor_height_m", DEFAULT_FLOOR_HEIGHT_M)
        fac_out.append({"id": f["id"], "name": f.get("name"), "type": f.get("type"), "flooded": hit, "relocated": f["id"] in moved})

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