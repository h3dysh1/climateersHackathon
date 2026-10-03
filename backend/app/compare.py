"""Compare the three flood options, then (optionally) layer them in an order the user picks.

The three options (details and assumptions in measures.json):
  - channel_clearing_m: dredging/desilting lowers every flood by a fixed amount (benefit fades as silt returns);
  - nature_based:        riverbank vegetation buffers lower floods by a %, fading for big floods;
  - raise_homes:         lift N homes (optionally in one target area, e.g. the #1 hotspot).

1) Side by side: each option ALONE against doing nothing, so they can be compared fairly. For each:
   people protected at the design flood (water no longer inside their homes), homes, facilities, roads,
   the target area before/after, effort, and a curve across flood sizes (where does it stop working?).
2) Layering (optional): add the options one at a time in the order given. Each step reports what it ADDS
   on top of the steps before. Order matters because homes are picked to raise at the flood that is left
   after earlier steps: raise first and some lifts go to homes the town-wide options would have kept dry
   anyway; raise last and every lift goes to a home still flooding. `orders_compared` shows every order.
Effort counts are not costs. Nothing here is an engineering design.
"""
from itertools import permutations

from . import flood

OPTION_KEYS = ("channel_clearing_m", "nature_based", "raise_homes")


def _people_in_target(result: dict, buildings: list[dict], target: dict | None) -> int:
    if not target:
        return result["people_water_inside"]
    inside = {r["id"] for r in result["buildings"] if r["water_inside"]}
    return round(sum(b.get("people", 0) for b in buildings if b["id"] in inside and flood.in_target(b, target)))


def _effort(key: str, cfg, after: dict) -> dict:
    if key == "raise_homes":
        return {"homes_raised": len(after["homes_raised"]), "height_m": cfg.get("height_m", flood.raise_by_default())}
    if key == "channel_clearing_m":
        return {"channel_lowered_m": cfg}
    return {"reduction_pct": cfg.get("reduction_pct", flood.MEASURES["nature_based"]["default_reduction_pct"])}


def _fix_raise(measures: dict, level_m: float, buildings: list[dict]) -> dict:
    """Pin which homes get raised: chosen at the design flood, after any options already in `measures`."""
    r = measures.get("raise_homes")
    if not r or r.get("ids") is not None:
        return measures
    design = flood.effective_level(float(r.get("design_level_m", level_m)), measures)
    ids = flood.pick_homes_to_raise(buildings, int(r.get("count", 0)), design,
                                    float(r.get("height_m", flood.raise_by_default())), r.get("target"))
    return {**measures, "raise_homes": {**r, "ids": ids}}


def _curve(levels, buildings, facilities, roads, measures):
    return [{"level_m": lv, "people_water_inside": flood.assess(lv, buildings, facilities, roads, measures)["people_water_inside"]}
            for lv in levels]


def _impact(base: dict, after: dict) -> dict:
    return {
        "people_protected": max(0, base["people_water_inside"] - after["people_water_inside"]),
        "people_still_water_inside": after["people_water_inside"],
        "homes_kept_dry": max(0, base["buildings_water_inside"] - after["buildings_water_inside"]),
        "facilities_protected": len(base["facilities_flooded"]) - len(after["facilities_flooded"]),
        "roads_reopened": len(base["roads_cut"]) - len(after["roads_cut"]),
        "flood_lowered_by_m": round(base["effective_level_m"] - after["effective_level_m"], 2),
    }


def _layer(order, options, level_m, buildings, facilities, roads, base):
    """Apply options one by one in `order`; returns (key, measures so far, result, people added) per step."""
    m, prev, steps = {}, base, []
    for key in order:
        m = _fix_raise({**m, key: options[key]}, level_m, buildings)
        after = flood.assess(level_m, buildings, facilities, roads, m)
        steps.append((key, m, after, max(0, prev["people_water_inside"] - after["people_water_inside"])))
        prev = after
    return steps


def compare_options(level_m: float, options: dict, buildings: list[dict], facilities=None, roads=None,
                    levels: list[float] | None = None, target: dict | None = None, order: list[str] | None = None) -> dict:
    facilities, roads, levels = facilities or [], roads or [], levels or []
    options = {k: v for k, v in options.items() if k in OPTION_KEYS and v}
    base = flood.assess(level_m, buildings, facilities, roads)
    base_target = _people_in_target(base, buildings, target)

    # 1) Each option on its own.
    singles = []
    for key, cfg in options.items():
        m = _fix_raise({key: cfg}, level_m, buildings)
        after = flood.assess(level_m, buildings, facilities, roads, m)
        info = flood.MEASURES[key]
        impact = _impact(base, after)
        res = {"key": key, "label": info["label"], "category": info["category"], "settings": cfg,
               "at_design_level": impact,
               "target_area": ({"people_water_inside_before": base_target,
                                "people_water_inside_after": _people_in_target(after, buildings, target)} if target else None),
               "effort": _effort(key, cfg, after),
               "homes_too_deep_to_raise": after["homes_too_deep_to_raise"] if key == "raise_homes" else None,
               "people_protected_per_home_raised": (round(impact["people_protected"] / len(after["homes_raised"]), 2)
                                                    if key == "raise_homes" and after["homes_raised"] else None),
               "assumption": info["assumption"],
               "evidence": info.get("evidence"),
               "sources": info.get("sources", []),
               "curve": _curve(levels, buildings, facilities, roads, m)}
        if key == "nature_based":
            res["co_benefits"] = info["co_benefits"]
        singles.append(res)
    singles.sort(key=lambda r: -r["at_design_level"]["people_protected"])
    for i, r in enumerate(singles, 1):
        r["rank"] = i

    out = {"level_m": level_m, "target": target,
           "baseline": {"people_water_inside": base["people_water_inside"],
                        "people_water_inside_in_target": base_target if target else None,
                        "facilities_flooded": len(base["facilities_flooded"]), "roads_cut": len(base["roads_cut"]),
                        "curve": _curve(levels, buildings, facilities, roads, None)},
           "options": singles, "layering": None}

    # 2) Optional layering in the user's order.
    if order:
        steps = _layer(order, options, level_m, buildings, facilities, roads, base)
        out["layering"] = {
            "order": order,
            "steps": [{"step": i, "added": key, "label": flood.MEASURES[key]["label"],
                       "people_added_protection": added,
                       "people_protected_so_far": max(0, base["people_water_inside"] - after["people_water_inside"]),
                       "people_still_water_inside": after["people_water_inside"],
                       "homes_raised": len(after["homes_raised"]),
                       "flood_lowered_by_m": round(level_m - after["effective_level_m"], 2),
                       "curve": _curve(levels, buildings, facilities, roads, m)}
                      for i, (key, m, after, added) in enumerate(steps, 1)],
            "orders_compared": sorted(
                [{"order": list(p), "people_protected": max(0, base["people_water_inside"] - s[-1][2]["people_water_inside"])}
                 for p in permutations(order) for s in [_layer(p, options, level_m, buildings, facilities, roads, base)]],
                key=lambda o: -o["people_protected"]),
            "note": "Order only changes which homes get raised: homes are picked at the flood left after earlier steps. "
                    "Town-wide options lower the flood the same way whatever the order.",
        }
    return out