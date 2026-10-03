"""Download the guide's four OpenStreetMap layers straight from the Overpass API (no browser)
→ raw/rivers.geojson, raw/facilities.geojson, raw/roads.geojson, raw/places.geojson.

Same queries as the "Nadi Flood Planner: Data Processing Guide" (steps 2-4).

Usage:
  python fetch_osm.py --bbox 177.38 -17.86 177.52 -17.72
  python fetch_osm.py --bbox 177.38 -17.86 177.52 -17.72 --only rivers   (just one layer)
"""
import argparse
import json
import time

import requests

from common import RAW_DIR

SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

QUERIES = {
    "rivers": 'way["waterway"~"river|stream|canal|drain"]({b});',
    "facilities": '(nwr["amenity"~"hospital|clinic|doctors|school|kindergarten|college|police|fire_station|community_centre|shelter"]({b});'
                  'nwr["power"="substation"]({b}););',
    "roads": 'way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential"]({b});',
    "places": 'node["place"~"suburb|neighbourhood|quarter|village|hamlet|town|locality"]({b});',
}
AREA_KEYS = {"amenity", "building", "power", "landuse", "leisure"}


def to_feature(el):
    tags = el.get("tags", {})
    props = {**tags, "id": f"{el['type']}/{el['id']}"}
    if el["type"] == "node":
        geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
    elif el["type"] == "way" and el.get("geometry"):
        coords = [[p["lon"], p["lat"]] for p in el["geometry"] if p]
        closed = len(coords) >= 4 and coords[0] == coords[-1]
        is_area = closed and AREA_KEYS & tags.keys() and not ({"highway", "waterway"} & tags.keys())
        geom = {"type": "Polygon", "coordinates": [coords]} if is_area else {"type": "LineString", "coordinates": coords}
    elif el["type"] == "relation":
        pts = [[p["lon"], p["lat"]] for m in el.get("members", []) for p in (m.get("geometry") or []) if p]
        if not pts:
            return None
        lon = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        geom = {"type": "Point", "coordinates": [lon, lat]}  # e.g. a hospital mapped as a multipolygon
    else:
        return None
    return {"type": "Feature", "properties": props, "geometry": geom}


def fetch(name, bbox):
    w, s, e, n = bbox
    q = f"[out:json][timeout:180];{QUERIES[name].format(b=f'{s},{w},{n},{e}')}out geom;"
    last = None
    for attempt in range(3):
        for url in SERVERS:
            try:
                r = requests.post(url, data={"data": q}, timeout=240,
                                  headers={"User-Agent": "climate-hackathon-nadi-flood-planner/1.0"})
                if r.status_code == 200:
                    return r.json()["elements"]
                last = f"{url} returned {r.status_code}"
            except requests.RequestException as ex:
                last = f"{url}: {ex}"
        time.sleep(10 * (attempt + 1))  # Overpass is busy; wait and retry
    raise SystemExit(f"Could not download {name}: {last}. Try again in a minute, or use overpass-turbo.eu by hand.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    ap.add_argument("--only", choices=list(QUERIES))
    args = ap.parse_args()
    RAW_DIR.mkdir(exist_ok=True)
    for name in ([args.only] if args.only else QUERIES):
        els = fetch(name, args.bbox)
        feats = [f for f in (to_feature(el) for el in els) if f]
        out = RAW_DIR / f"{name}.geojson"
        out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
        print(f"wrote raw/{name}.geojson: {len(feats)} features")
        time.sleep(2)


if __name__ == "__main__":
    main()
