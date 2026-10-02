"""Risk bands and the upgrade rule. Must match docs/contracts.md and the frontend fallback."""

UPGRADE_FACTOR = 0.5  # an upgraded roof halves vulnerability (assumption — state it in the pitch)
BANDS = ("high", "medium", "low")


def band(risk: float) -> str:
    if risk >= 0.5:
        return "high"
    if risk >= 0.25:
        return "medium"
    return "low"


def counts(buildings: list[dict]) -> dict:
    return {b: sum(1 for x in buildings if x["band"] == b) for b in BANDS}


def plan_upgrades(buildings: list[dict], budget: int) -> dict:
    """Upgrade the `budget` highest-risk buildings and re-score them."""
    ranked = sorted(buildings, key=lambda b: b["risk"], reverse=True)
    chosen = {b["id"] for b in ranked[: max(0, budget)]}
    after = []
    for b in buildings:
        if b["id"] in chosen:
            v = round(b["vulnerability"] * UPGRADE_FACTOR, 3)
            r = round(b["exposure"] * v, 3)
            after.append({**b, "vulnerability": v, "risk": r, "band": band(r), "upgraded": True})
        else:
            after.append({**b, "upgraded": False})
    return {
        "upgraded": [b["id"] for b in ranked[: max(0, budget)]],
        "before": counts(buildings),
        "after": counts(after),
        "buildings": after,
    }
