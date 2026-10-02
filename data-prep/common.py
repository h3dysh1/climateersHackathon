"""Shared helpers for the data-prep scripts. Formats follow docs/contracts.md."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "frontend" / "public" / "data"
TILE_DIR = ROOT / "frontend" / "public" / "tiles"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TILE_DIR.mkdir(parents=True, exist_ok=True)

# Roof vulnerability weights (0-1). Tune on the 70% training split only, then document choices.
MATERIAL_WEIGHT = {
    "thatch": 0.9, "timber": 0.8, "corrugated_iron": 0.6,
    "tile": 0.5, "concrete": 0.25, "unknown": 0.6,
}
SHAPE_ADJ = {"gable": 0.05, "skillion": 0.05, "flat": 0.0, "hip": -0.05, "unknown": 0.0}
CONDITION_ADJ = {"good": -0.1, "fair": 0.0, "poor": 0.1, "damaged": 0.2, "unknown": 0.0}


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def band(risk):
    if risk >= 0.5:
        return "high"
    if risk >= 0.25:
        return "medium"
    return "low"


def vulnerability(labels):
    """Roof vulnerability 0-1 from a roof_labels entry."""
    if not labels:
        return MATERIAL_WEIGHT["unknown"]
    v = MATERIAL_WEIGHT.get(labels.get("roof_material", "unknown"), 0.6)
    v += SHAPE_ADJ.get(labels.get("roof_shape", "unknown"), 0.0)
    v += CONDITION_ADJ.get(labels.get("condition", "unknown"), 0.0)
    return round(clamp(v), 3)


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance. Works across the 180° meridian."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def write_json(name, data):
    path = OUT_DIR / name
    path.write_text(json.dumps(data, indent=1))
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def read_json(name, default=None):
    path = OUT_DIR / name
    if not path.exists():
        return default
    return json.loads(path.read_text())
