"""Split the coastline into segments and measure existing vs restorable mangrove width
in front of each one → coast_segments.geojson, mangroves.geojson, restorable.geojson.

Inputs (vector files or 0/1 GeoTIFF tiles; --bbox clips everything to the pilot area):
  --coastline   OSM natural=coastline lines (overpass-turbo export) or similar
  --mangroves   Global Mangrove Watch extent for the latest year (e.g. 2020)
  --restorable  EITHER Global Mangrove Watch extent for an earlier year (e.g. 1996; we use
                the area lost since then) OR a mangrove restoration-potential layer
  --earlier     set this flag when --restorable is an earlier extent (loss = earlier - latest)

Width = mangrove area inside the segment's zone / segment length. Each segment's zone is a
flat-ended strip reaching --buffer-m either side of the coast, and zones never overlap, so
every hectare is counted once. Simple and explainable; label as approximate in the app.

Usage:
  python 03_coast_segments.py --bbox 177.35 -17.70 177.55 -17.50 \
      --coastline raw/coastline.geojson --mangroves raw/gmw_2020.tif \
      --restorable raw/gmw_1996.tif --earlier
  Add --tag _ba to write coast_segments_ba.geojson etc. (e.g. a second area for 05_validate.py)
  without overwriting the pilot files.
"""
import argparse

import geopandas as gpd
from shapely.ops import linemerge, substring, unary_union

from common import protection_band, read_layer, surge_reduction_m, wave_reduction, write_json

CRS_M = 3460  # Fiji Map Grid (metres)


def split_line(line, seg_len):
    """Cut a line into equal pieces of about seg_len that follow its shape
    (e.g. 5,010 m → 10 × 501 m), so no tiny stub segments appear."""
    n = max(1, round(line.length / seg_len))
    step = line.length / n
    return [substring(line, i * step, (i + 1) * step) for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coastline", required=True)
    ap.add_argument("--mangroves", required=True)
    ap.add_argument("--restorable", required=True)
    ap.add_argument("--earlier", action="store_true")
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"),
                    help="pilot area; strongly recommended for global or tiled inputs")
    ap.add_argument("--segment-m", type=int, default=500)
    ap.add_argument("--buffer-m", type=int, default=800, help="how far either side of the coast to look for mangroves")
    ap.add_argument("--min-patch-ha", type=float, default=0.25,
                    help="drop restorable patches smaller than this (1996 maps are noisier; 0.25 ha = 4 GMW pixels)")
    ap.add_argument("--min-coast-m", type=float, default=200, help="ignore coastline pieces shorter than this (tiny islets)")
    ap.add_argument("--tag", default="", help="suffix for output names, e.g. _ba")
    args = ap.parse_args()

    coast = read_layer(args.coastline, args.bbox, as_lines=True).to_crs(CRS_M)
    mang = unary_union(read_layer(args.mangroves, args.bbox).to_crs(CRS_M).geometry).buffer(0)
    rest = unary_union(read_layer(args.restorable, args.bbox).to_crs(CRS_M).geometry).buffer(0)
    if args.earlier:
        rest = rest.difference(mang)  # lost since the earlier year = restorable
    min_m2 = args.min_patch_ha * 10_000
    rest_parts = [p for p in getattr(rest, "geoms", [rest]) if p.area >= min_m2]
    rest = unary_union(rest_parts)

    union = unary_union(coast.geometry)
    merged = union if union.geom_type == "LineString" else linemerge(union)
    lines = [ln for ln in (merged.geoms if hasattr(merged, "geoms") else [merged]) if ln.length >= args.min_coast_m]
    segs = [s for line in lines for s in split_line(line, args.segment_m)]
    if not segs:
        raise SystemExit("No coastline inside the bbox.")

    # Non-overlapping zones: each segment claims a flat-ended strip, minus what earlier
    # segments already claimed (only matters at bends), so hectares are never double counted.
    claimed = None
    rows = []
    for i, seg in enumerate(segs, 1):
        zone = seg.buffer(args.buffer_m, cap_style="flat")
        if claimed is not None:
            zone = zone.difference(claimed)
        claimed = zone if claimed is None else claimed.union(zone)
        length = seg.length
        existing_m2 = mang.intersection(zone).area
        rest_m2 = rest.intersection(zone).area
        existing, restorable = existing_m2 / length, rest_m2 / length
        rows.append({
            "id": f"s{i:03d}", "length_m": round(length),
            "existing_width_m": round(existing), "restorable_width_m": round(restorable),
            "existing_ha": round(existing_m2 / 10_000, 1),
            "restorable_ha": round(rest_m2 / 10_000, 1),
            "wave_reduction_now": wave_reduction(existing),
            "wave_reduction_restored": wave_reduction(existing + restorable),
            "surge_reduction_restored_m": surge_reduction_m(existing + restorable),
            "band_now": protection_band(existing),
            "band_restored": protection_band(existing + restorable),
            "geometry": seg,
        })
    gdf = gpd.GeoDataFrame(rows, crs=CRS_M).to_crs(4326)
    gdf["geometry"] = gdf.geometry.simplify(0.00001)
    write_json(f"coast_segments{args.tag}.geojson", gdf.__geo_interface__)

    for name, geom, year in ((f"mangroves{args.tag}.geojson", mang, "latest"),
                             (f"restorable{args.tag}.geojson", rest, "lost since earlier year")):
        layer = gpd.GeoDataFrame(geometry=[geom], crs=CRS_M).explode(index_parts=False)
        layer = layer[~layer.geometry.is_empty].to_crs(4326)
        layer["geometry"] = layer.geometry.simplify(0.00003)
        layer["kind"] = year
        write_json(name, layer.__geo_interface__)

    total_rest = sum(r["restorable_ha"] for r in rows)
    print(f"{len(rows)} segments; {sum(r['existing_ha'] for r in rows):.0f} ha mangroves now, "
          f"{total_rest:.0f} ha restorable (of {rest.area / 10_000:.0f} ha lost in the bbox; "
          f"the rest lies beyond {args.buffer_m} m of the coast)")
    print("Next: run 04_people_behind.py to add people and priority.")


if __name__ == "__main__":
    main()
