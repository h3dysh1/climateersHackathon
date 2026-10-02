"""Shared helpers for the data-prep scripts. Formats follow docs/contracts.md.

The restoration effect model here MUST match backend/app/restoration.py and
frontend/src/api.js. Change all three together.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "frontend" / "public" / "data"
RAW_DIR = Path(__file__).resolve().parent / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Restoration effect model (deliberately conservative; cite in the pitch) ---
# Field studies report 13-66% wave-height reduction over 100 m of mangroves
# (McIvor et al. 2012). We use the LOW end per 100 m and cap at the high end.
WAVE_REDUCTION_PER_100M = 0.13
WAVE_REDUCTION_CAP = 0.66
# Observed storm-surge reduction is small: 0-0.25 m per km of forest. Use 0.1 m/km.
SURGE_REDUCTION_M_PER_KM = 0.10


def wave_reduction(width_m):
    """Fraction of wave height removed by a mangrove belt of this width (0-0.66)."""
    return round(min(WAVE_REDUCTION_CAP, WAVE_REDUCTION_PER_100M * max(0.0, width_m) / 100), 3)


def surge_reduction_m(width_m):
    return round(SURGE_REDUCTION_M_PER_KM * max(0.0, width_m) / 1000, 3)


def protection_band(width_m):
    """How well the coast in front of a building is buffered."""
    r = wave_reduction(width_m)
    if r >= 0.4:
        return "strong"
    if r >= 0.2:
        return "partial"
    return "exposed"


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance. Works across the 180° meridian."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
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
