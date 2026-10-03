"""Town settings. Each town is one file in backend/places/<id>.json (copy nadi.json to add a town).
Everything town-specific lives there, so the model, hotspots and comparison stay the same everywhere."""
import json
from pathlib import Path

# backend/app/places.py -> backend/places/
DIR = Path(__file__).parent.parent / "places"


def all_places() -> dict:
    """Every town file, keyed by its file name: {"nadi": {...}}."""
    return {p.stem: json.loads(p.read_text()) for p in sorted(DIR.glob("*.json"))}


def get(place_id: str | None) -> dict | None:
    """One town's settings, or None if no id was given or the town doesn't exist."""
    if not place_id:
        return None
    return all_places().get(place_id)