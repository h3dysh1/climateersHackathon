"""Combine Winston exposure and roof vulnerability → risk.json.

Needs track.json, buildings.geojson and roof_labels.json (from the backend's batch classify).

Usage:
  python 04_risk.py [--radius-km 150]
"""
import argparse

from common import band, haversine_km, read_json, vulnerability, write_json


def exposure(lat, lon, track, radius_km):
    """0-1. Highest where the building was close to a strong part of the track.
    Simplified on purpose — label as approximate in the UI."""
    winds = [p["wind_kt"] or 0 for p in track]
    max_wind = max(winds) or 1
    best = 0.0
    for p, w in zip(track, winds):
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        best = max(best, max(0.0, 1 - d / radius_km) * (w / max_wind))
    return round(best, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--radius-km", type=float, default=150)
    args = ap.parse_args()

    track = read_json("track.json")
    fc = read_json("buildings.geojson")
    labels = read_json("roof_labels.json", {})
    if not track or not fc:
        raise SystemExit("Need track.json and buildings.geojson first.")

    out, missing = [], 0
    for f in fc["features"]:
        bid = f["properties"]["id"]
        lon, lat = f["geometry"]["coordinates"]
        lab = labels.get(bid)
        missing += lab is None
        e = exposure(lat, lon, track, args.radius_km)
        v = vulnerability(lab)
        r = round(e * v, 3)
        out.append({"id": bid, "exposure": e, "vulnerability": v, "risk": r, "band": band(r)})

    write_json("risk.json", {"buildings": out})
    counts = {b: sum(1 for x in out if x["band"] == b) for b in ("high", "medium", "low")}
    print(f"{len(out)} buildings, bands {counts}; {missing} without roof labels (scored as unknown)")


if __name__ == "__main__":
    main()
