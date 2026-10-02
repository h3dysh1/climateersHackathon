"""Restoration scenario maths. MUST match data-prep/common.py and frontend/src/api.js."""

WAVE_REDUCTION_PER_100M = 0.13  # low end of 13-66% per 100 m (McIvor et al. 2012)
WAVE_REDUCTION_CAP = 0.66
SURGE_REDUCTION_M_PER_KM = 0.10  # observed range 0-0.25 m per km
BANDS = ("exposed", "partial", "strong")


def wave_reduction(width_m: float) -> float:
    return round(min(WAVE_REDUCTION_CAP, WAVE_REDUCTION_PER_100M * max(0.0, width_m) / 100), 3)


def surge_reduction_m(width_m: float) -> float:
    return round(SURGE_REDUCTION_M_PER_KM * max(0.0, width_m) / 1000, 3)


def protection_band(width_m: float) -> str:
    r = wave_reduction(width_m)
    if r >= 0.4:
        return "strong"
    if r >= 0.2:
        return "partial"
    return "exposed"


def _people_by_band(segments: list[dict], width_key) -> dict:
    out = {b: 0 for b in BANDS}
    for s in segments:
        out[protection_band(width_key(s))] += s.get("surge_people", 0)
    return out


def run_scenario(segments: list[dict], restore_ids: list[str]) -> dict:
    """Restore mangroves on the chosen segments and compare protection before/after."""
    chosen = set(restore_ids)

    def width_after(s):
        return s["existing_width_m"] + (s["restorable_width_m"] if s["id"] in chosen else 0)

    restored = [s for s in segments if s["id"] in chosen]
    people_better = sum(
        s.get("surge_people", 0) for s in restored
        if BANDS.index(protection_band(width_after(s))) > BANDS.index(protection_band(s["existing_width_m"]))
    )
    return {
        "restored": [s["id"] for s in restored],
        "hectares": round(sum(s.get("restorable_ha", 0) for s in restored), 1),
        "people_better_protected": int(people_better),
        "before": _people_by_band(segments, lambda s: s["existing_width_m"]),
        "after": _people_by_band(segments, width_after),
        "segments": [
            {"id": s["id"], "width_m": width_after(s), "wave_reduction": wave_reduction(width_after(s)),
             "surge_reduction_m": surge_reduction_m(width_after(s)), "band": protection_band(width_after(s)),
             "restored": s["id"] in chosen}
            for s in segments
        ],
    }
