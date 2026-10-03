"""Clip building footprints (or points) to the pilot area → buildings.geojson (points with ids).

Input can be any vector file geopandas reads (GeoJSON, GeoPackage, Shapefile) from
Overture, Microsoft/Google building footprints or OpenStreetMap. Optional village points file
assigns each building to its nearest village.

Footprint area (area_m2) is kept when the input has polygons, so 04_people_behind.py can
skip sheds/cookhouses and large non-residential buildings when counting people.

Usage:
  python 02_buildings.py --input raw/buildings.geojson \
      --bbox 177.35 -17.70 177.55 -17.50 --villages raw/villages.geojson
  (bbox = min_lon min_lat max_lon max_lat)
"""
import argparse

import geopandas as gpd
from shapely.geometry import box

from common import write_json

CRS_M = 3460  # Fiji Map Grid (metres)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    ap.add_argument("--villages", help="points with a 'name' column (e.g. OSM place=village)")
    ap.add_argument("--max", type=int, default=None,
                    help="optional cap for quick tests ONLY: sampling undercounts people")
    args = ap.parse_args()

    gdf = gpd.read_file(args.input, bbox=tuple(args.bbox)).to_crs(4326)
    gdf = gdf[gdf.intersects(box(*args.bbox))].reset_index(drop=True)
    if gdf.empty:
        raise SystemExit("No buildings in that bbox.")
    if args.max and len(gdf) > args.max:
        print(f"WARNING: sampling {args.max} of {len(gdf)} buildings; people counts will be too low.")
        gdf = gdf.sample(args.max, random_state=42).reset_index(drop=True)

    metric = gdf.to_crs(CRS_M)
    is_poly = metric.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    area = metric.geometry.area.where(is_poly)
    pts = metric.geometry.centroid.to_crs(4326)

    village_names = [None] * len(gdf)
    if args.villages:
        v = gpd.read_file(args.villages).to_crs(CRS_M)
        joined = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=metric.geometry.centroid), v[["name", "geometry"]], how="left")
        village_names = joined.groupby(level=0)["name"].first().reindex(range(len(gdf))).tolist()

    features = []
    for i, p in enumerate(pts):
        bid = f"b{i + 1:04d}"
        props = {"id": bid, "village": village_names[i]}
        if is_poly.iloc[i]:
            props["area_m2"] = round(float(area.iloc[i]))
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(p.x, 6), round(p.y, 6)]},
            "properties": props,
        })
    write_json("buildings.geojson", {"type": "FeatureCollection", "features": features})
    print(f"{len(features)} buildings ({int(is_poly.sum())} with footprint area)")


if __name__ == "__main__":
    main()
