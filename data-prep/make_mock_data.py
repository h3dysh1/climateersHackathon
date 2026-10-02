"""Write small fake data so P1 and P3 can start before the real data is ready.

Creates track.json, buildings.geojson, roof_labels.json, risk.json and validation.json
in frontend/public/data/, matching docs/contracts.md. Clearly fake: delete once real data lands.
"""
import random

from common import band, haversine_km, read_json, vulnerability, write_json

random.seed(42)

# Rough, illustrative Winston-like path across northern Viti Levu (NOT the real track).
TRACK = [
    {"time": "2016-02-19T18:00:00Z", "lat": -16.9, "lon": 179.6, "wind_kt": 150, "category": 5},
    {"time": "2016-02-20T00:00:00Z", "lat": -17.1, "lon": 179.0, "wind_kt": 155, "category": 5},
    {"time": "2016-02-20T06:00:00Z", "lat": -17.3, "lon": 178.3, "wind_kt": 155, "category": 5},
    {"time": "2016-02-20T12:00:00Z", "lat": -17.5, "lon": 177.6, "wind_kt": 140, "category": 5},
    {"time": "2016-02-20T18:00:00Z", "lat": -17.8, "lon": 176.9, "wind_kt": 120, "category": 4},
]

VILLAGES = [
    ("Village A", -17.40, 178.18),
    ("Village B", -17.45, 178.05),
    ("Village C", -17.55, 178.25),
    ("Village D", -17.62, 177.95),
]
MATERIALS = ["corrugated_iron"] * 6 + ["concrete"] * 2 + ["timber", "thatch"]
SHAPES = ["gable", "gable", "hip", "flat", "skillion"]
CONDITIONS = ["good", "fair", "fair", "poor", "damaged"]


def exposure(lat, lon, track):
    """0-1: closer to stronger track points = higher. Mirrors 04_risk.py."""
    best = 0.0
    max_wind = max(p["wind_kt"] for p in track)
    for p in track:
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        e = max(0.0, 1 - d / 150) * (p["wind_kt"] / max_wind)
        best = max(best, e)
    return round(best, 3)


def main():
    features, labels, risk = [], {}, []
    n = 0
    for name, vlat, vlon in VILLAGES:
        for _ in range(60):
            n += 1
            bid = f"b{n:04d}"
            lat = vlat + random.gauss(0, 0.012)
            lon = vlon + random.gauss(0, 0.012)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                "properties": {"id": bid, "village": name, "tile": None},
            })
            lab = {
                "roof_material": random.choice(MATERIALS),
                "roof_shape": random.choice(SHAPES),
                "condition": random.choice(CONDITIONS),
                "confidence": round(random.uniform(0.5, 0.95), 2),
            }
            labels[bid] = lab
            e = exposure(lat, lon, TRACK)
            v = vulnerability(lab)
            r = round(e * v, 3)
            risk.append({"id": bid, "exposure": e, "vulnerability": v, "risk": r, "band": band(r)})

    write_json("track.json", TRACK)
    write_json("buildings.geojson", {"type": "FeatureCollection", "features": features})
    write_json("roof_labels.json", labels)
    write_json("risk.json", {"buildings": risk})
    write_json("validation.json", {
        "n_test": 72, "severe_damage_test": 25,
        "model_recall_severe": 0.68, "baseline_recall_severe": 0.52,
        "model_precision_high": 0.47,
        "note": "MOCK NUMBERS — replace with 05_validate.py output.",
        "mock": True,
    })
    counts = {b: sum(1 for x in risk if x["band"] == b) for b in ("high", "medium", "low")}
    print(f"{len(features)} mock buildings; bands: {counts}")
    assert read_json("risk.json")


if __name__ == "__main__":
    main()
