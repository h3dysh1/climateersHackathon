"""Clip building footprints (or points) to the pilot area → buildings.geojson (points with ids).

Input can be any vector file geopandas reads (GeoJSON, GeoPackage, Shapefile) from
Microsoft/Google building footprints or OpenStreetMap. Optional village points file
assigns each building to its nearest village.

Usage:
  python 02_buildings.py --input raw/fiji_buildings.geojson \
      --bbox 177.9 -17.7 178.4 -17.3 --villages raw/fiji_villages.geojson --max 400
  (bbox = min_lon min_lat max_lon max_lat)
"""
import argparse

import geopandas as gpd
from shapely.geometry import box

from common import write_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    ap.add_argument("--villages", help="points with a 'name' column (e.g. OSM place=village)")
    ap.add_argument("--max", type=int, default=400, help="cap buildings to keep CV cost and time down")
    args = ap.parse_args()

    gdf = gpd.read_file(args.input, bbox=tuple(args.bbox)).to_crs(4326)
    gdf = gdf[gdf.intersects(box(*args.bbox))]
    if gdf.empty:
        raise SystemExit("No buildings in that bbox.")
    if len(gdf) > args.max:
        gdf = gdf.sample(args.max, random_state=42)

    # Centroids in a metric CRS (Fiji Map Grid, EPSG:3460), back to WGS84.
    pts = gdf.to_crs(3460).geometry.centroid.to_crs(4326)

    village_names = None
    if args.villages:
        v = gpd.read_file(args.villages).to_crs(3460)
        joined = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=pts.to_crs(3460)), v[["name", "geometry"]], how="left")
        village_names = joined.groupby(level=0)["name"].first().tolist()

    features = []
    for i, p in enumerate(pts):
        bid = f"b{i + 1:04d}"
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(p.x, 6), round(p.y, 6)]},
            "properties": {"id": bid, "village": village_names[i] if village_names else None, "tile": f"tiles/{bid}.png"},
        })
    write_json("buildings.geojson", {"type": "FeatureCollection", "features": features})
    print(f"{len(features)} buildings")


if __name__ == "__main__":
    main()
