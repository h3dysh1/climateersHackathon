"""Restoration scenario maths for several ecosystem types.

Parameters live in ecosystems.json. Only types with verified=true (cited numbers) count
towards wave protection. Several types on one segment combine as independent filters:
    total reduction = 1 - (1 - r_mangrove) x (1 - r_saltmarsh) x ...

Backward compatible: a segment with only existing_width_m / restorable_width_m is treated
as mangroves. MUST match frontend/src/api.js and data-prep/common.py.
"""
import json
from pathlib import Path

ECOSYSTEMS: dict = {k: v for k, v in json.loads((Path(__file__).parent / "ecosystems.json").read_text()).items()
                    if not k.startswith("_")}
BANDS = ("exposed", "partial", "strong")
STRONG_AT, PARTIAL_AT = 0.4, 0.2

# Kept for older imports and tests.
MATURITY_YEARS = ECOSYSTEMS["mangrove"]["maturity_years"]


def wave_types() -> list[str]:
    """Verified ecosystem types that count towards coastal wave protection."""
    return [k for k, v in ECOSYSTEMS.items() if v["verified"] and v["hazard"] == "coastal_waves"]


def _r(eco: str, width_m: float) -> float:
    p = ECOSYSTEMS[eco]
    return min(p["wave_reduction_cap"], p["wave_reduction_per_100m"] * max(0.0, width_m) / 100)


def wave_reduction(width_m: float, eco: str = "mangrove") -> float:
    return round(_r(eco, width_m), 3)


def combined_reduction(widths: dict[str, float]) -> float:
    keep = 1.0
    for eco, w in widths.items():
        if eco in wave_types():
            keep *= 1 - _r(eco, w)
    return round(1 - keep, 3)


def surge_reduction_m(widths: dict[str, float] | float) -> float:
    if not isinstance(widths, dict):
        widths = {"mangrove": widths}
    total = sum(ECOSYSTEMS[e]["surge_reduction_m_per_km"] * max(0.0, w) / 1000
                for e, w in widths.items() if e in wave_types())
    return round(total, 3)


def band_for(reduction: float) -> str:
    if reduction >= STRONG_AT:
        return "strong"
    if reduction >= PARTIAL_AT:
        return "partial"
    return "exposed"


def protection_band(width_m: float) -> str:
    """Mangrove-only shortcut (kept for compatibility)."""
    return band_for(wave_reduction(width_m))


def growth(years: float, eco: str = "mangrove") -> float:
    """Share of full protective width reached `years` after planting (0-1).
    Illustrative S-curve reaching full value at the type's maturity_years."""
    x = max(0.0, min(1.0, years / ECOSYSTEMS[eco]["maturity_years"]))
    return round(x * x * (3 - 2 * x), 3)


def normalise(seg: dict) -> dict:
    """Fill per-type widths from the older single-width fields."""
    s = dict(seg)
    s.setdefault("existing_by_type", None)
    s.setdefault("restorable_by_type", None)
    if not s["existing_by_type"]:
        s["existing_by_type"] = {"mangrove": s.get("existing_width_m", 0)}
    if not s["restorable_by_type"]:
        s["restorable_by_type"] = {"mangrove": s.get("restorable_width_m", 0)}
    if not s.get("restorable_ha_by_type"):
        s["restorable_ha_by_type"] = {"mangrove": s.get("restorable_ha", 0)}
    return s


def _widths(s: dict, restore: bool, types: list[str], years: float | None) -> dict[str, float]:
    out = dict(s["existing_by_type"])
    if restore:
        for eco, w in s["restorable_by_type"].items():
            if eco in types:
                g = 1.0 if years is None else growth(years, eco)
                out[eco] = out.get(eco, 0) + w * g
    return out


def _hectares(s: dict, types: list[str]) -> float:
    return sum(ha for eco, ha in s["restorable_ha_by_type"].items() if eco in types)


def run_scenario(segments: list[dict], restore_ids: list[str], years: float | None = None,
                 types: list[str] | None = None) -> dict:
    """Restore the chosen segments with the chosen ecosystem types; compare protection.
    `years` = time since planting (None = fully grown). `types` = None means all verified wave types."""
    types = [t for t in (types or wave_types()) if t in wave_types()]
    segs = [normalise(s) for s in segments]
    chosen = set(restore_ids)

    before_r = {s["id"]: combined_reduction(_widths(s, False, types, None)) for s in segs}
    after_w = {s["id"]: _widths(s, s["id"] in chosen, types, years) for s in segs}
    after_r = {k: combined_reduction(w) for k, w in after_w.items()}

    def by_band(red):
        out = {b: 0 for b in BANDS}
        for s in segs:
            out[band_for(red[s["id"]])] += s.get("surge_people", 0)
        return {k: int(round(v)) for k, v in out.items()}

    restored = [s for s in segs if s["id"] in chosen]
    better = sum(s.get("surge_people", 0) for s in restored
                 if BANDS.index(band_for(after_r[s["id"]])) > BANDS.index(band_for(before_r[s["id"]])))
    first_type = types[0] if types else "mangrove"
    return {
        "restored": [s["id"] for s in restored],
        "types": types,
        "hectares": round(sum(_hectares(s, types) for s in restored), 1),
        "people_better_protected": int(round(better)),
        "before": by_band(before_r),
        "after": by_band(after_r),
        "years": years,
        "growth": 1.0 if years is None else growth(years, first_type),
        "segments": [
            {"id": s["id"],
             "width_m": round(sum(after_w[s["id"]].values())),
             "width_by_type": {k: round(v) for k, v in after_w[s["id"]].items()},
             "wave_reduction": after_r[s["id"]],
             "surge_reduction_m": surge_reduction_m(after_w[s["id"]]),
             "band": band_for(after_r[s["id"]]),
             "restored": s["id"] in chosen}
            for s in segs
        ],
    }


def rank_sites(segments: list[dict], types: list[str] | None = None) -> list[dict]:
    """Restorable segments ranked by people protected per hectare (added wave reduction x
    surge-exposed people / hectares)."""
    types = [t for t in (types or wave_types()) if t in wave_types()]
    out = []
    for s in (normalise(x) for x in segments):
        ha = _hectares(s, types)
        if ha <= 0:
            continue
        gain = combined_reduction(_widths(s, True, types, None)) - combined_reduction(_widths(s, False, types, None))
        score = s.get("surge_people", 0) * gain
        out.append({"id": s["id"], "hectares": round(ha, 1), "surge_people": s.get("surge_people", 0),
                    "added_wave_reduction": round(gain, 3), "priority": round(score / ha, 3)})
    return sorted(out, key=lambda r: r["priority"], reverse=True)


def select_by_budget(segments: list[dict], hectares: float, types: list[str] | None = None) -> dict:
    """Greedy: take the highest-priority sites until the hectare budget is used up."""
    picked, used = [], 0.0
    for site in rank_sites(segments, types):
        if site["priority"] <= 0:
            break
        if used + site["hectares"] <= hectares:
            picked.append(site["id"])
            used += site["hectares"]
    result = run_scenario(segments, picked, None, types)
    result["budget_ha"] = hectares
    result["hectares_used"] = round(used, 1)
    return result