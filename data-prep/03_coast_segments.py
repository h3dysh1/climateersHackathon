"""Split the coastline into segments and measure existing vs restorable mangrove width
in front of each one → coast_segments.geojson, mangroves.geojson.

Inputs (clip all to the pilot area first):
  --coastline   OSM natural=coastline lines (overpass-turbo export) or similar
  --mangroves   Global Mangrove Watch extent for the latest year (e.g. 2020)
  --restorable  EITHER Global Mangrove Watch extent for an earlier year (e.g. 1996; we use
                the area lost since then) OR a mangrove restoration-potential layer
  --earlier     set this flag when --restorable is an earlier extent (loss = earlier - latest)

Width is approximated as mangrove area inside a buffer on the seaward side / segment length.
Simple and explainable; label as approximate in the app.

Usage:
  python 03_coast_segments.py --coastline raw/coastline.geojson \
      --mangroves raw/gmw_2020.geojson --restorable raw/gmw_1996.geojson --earlier
"""
import argparse

import geopandas as gpd
from shapely.geometry import LineString
from shapely.ops import linemerge, unary_union

from common import protection_band, surge_reduction_m, wave_reduction, write_json

CRS_M = 3460  # Fiji Map Grid (metres)


def split_line(line, seg_len):
    pts = [line.interpolate(d) for d in range(0, int(line.length), seg_len)] + [line.interpolate(line.length)]
    return [LineString([a, b]) for a, b in zip(pts, pts[1:]) if a.distance(b) > 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coastline", required=True)
    ap.add_argument("--mangroves", required=True)
    ap.add_argument("--restorable", required=True)
    ap.add_argument("--earlier", action="store_true")
    ap.add_argument("--segment-m", type=int, default=500)
    ap.add_argument("--buffer-m", type=int, default=800, help="how far seaward to look for mangroves")
    args = ap.parse_args()

    coast = gpd.read_file(args.coastline).to_crs(CRS_M)
    mang = unary_union(gpd.read_file(args.mangroves).to_crs(CRS_M).geometry)
    rest = unary_union(gpd.read_file(args.restorable).to_crs(CRS_M).geometry)
    if args.earlier:
        rest = rest.difference(mang)  # lost since the earlier year = restorable

    union = unary_union(coast.geometry)
    merged = union if union.geom_type == "LineString" else linemerge(union)
    lines = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    segs = [s for line in lines for s in split_line(line, args.segment_m)]

    rows = []
    for i, seg in enumerate(segs, 1):
        zone = seg.buffer(args.buffer_m)  # both sides; mangroves only grow in the intertidal zone anyway
        length = seg.length
        existing = mang.intersection(zone).area / length
        restorable = rest.intersection(zone).area / length
        rows.append({
            "id": f"s{i:03d}", "length_m": round(length),
            "existing_width_m": round(existing), "restorable_width_m": round(restorable),
            "restorable_ha": round(rest.intersection(zone).area / 10_000, 1),
            "wave_reduction_now": wave_reduction(existing),
            "wave_reduction_restored": wave_reduction(existing + restorable),
            "surge_reduction_restored_m": surge_reduction_m(existing + restorable),
            "band_now": protection_band(existing),
            "band_restored": protection_band(existing + restorable),
            "geometry": seg,
        })
    gdf = gpd.GeoDataFrame(rows, crs=CRS_M).to_crs(4326)
    gdf["geometry"] = gdf.geometry.simplify(0.00001)
    write_json("coast_segments.geojson", gdf.__geo_interface__)

    mang_gdf = gpd.GeoDataFrame(geometry=[mang], crs=CRS_M).explode(index_parts=False).to_crs(4326)
    mang_gdf["geometry"] = mang_gdf.geometry.simplify(0.00003)
    write_json("mangroves.geojson", mang_gdf.__geo_interface__)
    print(f"{len(rows)} segments; {sum(r['restorable_ha'] for r in rows):.0f} ha restorable in total")
    print("Next: run 04_people_behind.py to add people and priority.")


if __name__ == "__main__":
    main()
