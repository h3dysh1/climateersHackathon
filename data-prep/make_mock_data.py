"""Write fake data so P1 and P3 can build before the real pipeline is ready.

Creates track.json, coast_segments.geojson, mangroves.geojson, buildings.geojson and
validation.json in frontend/public/data/, matching docs/contracts.md.
Everything here is INVENTED. Delete once real data lands.
"""
import math
import random

from common import protection_band, surge_reduction_m, wave_reduction, write_json

random.seed(7)

# Illustrative track only (NOT Winston's real path).
TRACK = [
    {"time": "2016-02-20T00:00:00Z", "lat": -17.20, "lon": 178.80, "wind_kt": 155, "category": 5},
    {"time": "2016-02-20T06:00:00Z", "lat": -17.35, "lon": 178.20, "wind_kt": 155, "category": 5},
    {"time": "2016-02-20T12:00:00Z", "lat": -17.50, "lon": 177.60, "wind_kt": 140, "category": 5},
    {"time": "2016-02-20T18:00:00Z", "lat": -17.75, "lon": 177.00, "wind_kt": 120, "category": 4},
]

# A made-up coastline running roughly north-south west of "Lautoka".
COAST = [(177.405 + 0.006 * math.sin(i / 3), -17.575 - i * 0.0045) for i in range(21)]
SEG_LEN_M = 500


def offset(lon, lat, dx_m, dy_m):
    return lon + dx_m / (111_320 * math.cos(math.radians(lat))), lat + dy_m / 110_540


def main():
    segments, mangroves, buildings = [], [], []
    bid = 0
    for i in range(len(COAST) - 1):
        (lon1, lat1), (lon2, lat2) = COAST[i], COAST[i + 1]
        sid = f"s{i + 1:02d}"
        existing = random.choice([0, 0, 0, 40, 80, 150, 250])
        restorable = random.choice([0, 100, 200, 300, 400]) if existing < 250 else 0
        surge_people = 0
        people_total = 0
        n_b = random.randint(5, 40)
        for _ in range(n_b):
            bid += 1
            d = random.uniform(50, 1000)
            lon, lat = offset((lon1 + lon2) / 2, (lat1 + lat2) / 2, d, random.uniform(-200, 200))
            people = random.randint(2, 7)
            surge_m = 1 if d < 300 else (2 if d < 600 else None)
            people_total += people
            surge_people += people if surge_m else 0
            buildings.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                "properties": {"id": f"b{bid:04d}", "segment_id": sid, "people": people,
                               "surge_m": surge_m, "coast_m": round(d)},
            })
        segments.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[round(lon1, 5), round(lat1, 5)], [round(lon2, 5), round(lat2, 5)]]},
            "properties": {
                "id": sid, "length_m": SEG_LEN_M,
                "existing_width_m": existing, "restorable_width_m": restorable,
                "restorable_ha": round(SEG_LEN_M * restorable / 10_000, 1),
                "people_behind": people_total, "surge_people": surge_people,
                "buildings_behind": n_b,
                "wave_reduction_now": wave_reduction(existing),
                "wave_reduction_restored": wave_reduction(existing + restorable),
                "surge_reduction_restored_m": surge_reduction_m(existing + restorable),
                "band_now": protection_band(existing),
                "band_restored": protection_band(existing + restorable),
            },
        })
        if existing:
            # Mangrove belt drawn as a strip on the seaward (west) side.
            a = offset(lon1, lat1, -existing, 0)
            b = offset(lon2, lat2, -existing, 0)
            mangroves.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[lon1, lat1], [lon2, lat2], list(b), list(a), [lon1, lat1]]]},
                "properties": {"segment_id": sid, "year": 2020},
            })

    for s in segments:
        p = s["properties"]
        gain = p["wave_reduction_restored"] - p["wave_reduction_now"]
        p["priority"] = round(p["surge_people"] * gain / p["restorable_ha"], 2) if p["restorable_ha"] else 0

    write_json("track.json", TRACK)
    write_json("coast_segments.geojson", {"type": "FeatureCollection", "features": segments})
    write_json("mangroves.geojson", {"type": "FeatureCollection", "features": mangroves})
    write_json("buildings.geojson", {"type": "FeatureCollection", "features": buildings})
    write_json("validation.json", {
        "records": 120, "near_mangroves": 38, "severe_rate_with_mangroves": 0.21,
        "severe_rate_without": 0.34,
        "note": "MOCK NUMBERS — replace with 05_validate.py output.", "mock": True,
    })
    print(f"{len(segments)} segments, {len(buildings)} buildings, {len(mangroves)} mangrove strips")


if __name__ == "__main__":
    main()
