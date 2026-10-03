"""Who floods as the water rises → flood_levels.json, flood_zones.geojson, rivers.geojson,
and flood fields added to buildings.geojson. Run AFTER 02, 03 and 04 (it needs people per
building, and the coast segments for the mangrove link).

Method (simple, explainable "height above nearest drainage"; label as approximate):
  1. Every ground cell's height is compared with its nearest drainage: the river (its local
     low point = water surface) or the sea (0 m).
  2. Water rises in steps (0.5 m by default). A cell floods at level L when it is less than L
     above its drainage AND connected to the river/sea through other flooded cells
     (so hollows behind a ridge don't count).
  3. Each building gets floods_at_m: the lowest water rise that reaches it.
  4. Measures computed from geometry only, no invented effect sizes:
     - raised floors: a home raised R m floods only when the water is R m higher;
     - evacuation reach: flooded people more than --evac-km from dry ground;
     - mangroves: flooded coastal people whose coast has no mangrove buffer now vs after
       restoration (waves ride on top of coastal floods; mangroves cut wave height,
       see common.wave_reduction). Mangroves do NOT lower river floods.

Inputs:
  --dem        elevation GeoTIFF covering the bbox (Copernicus GLO-30 or FABDEM tile)
  --rivers     OSM waterway=river/stream lines (Overpass Turbo GeoJSON export)
  --coastline  OSM coastline (same file as 03) so the sea counts as drainage

Usage:
  python 05_flood_levels.py --bbox 177.37 -17.85 177.52 -17.72 --dem raw\\dem.tif \\
      --rivers raw\\rivers.geojson --coastline raw\\coastline.geojson
"""
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy import ndimage
from shapely.geometry import box, shape

from common import OUT_DIR, read_layer, write_json

CRS_M = 3460
FLOOD_COLS = ["ground_m", "hand_m", "floods_at_m", "drain", "dist_drain_m"]
SEA, RIVER = 1, 2


def load_dem(path, bbox, pixel_m):
    """DEM for the bbox, reprojected to Fiji Map Grid metres at pixel_m resolution."""
    with rasterio.open(path) as src:
        sb = src.bounds
        if not (sb.left <= bbox[0] and sb.right >= bbox[2] and sb.bottom <= bbox[1] and sb.top >= bbox[3]):
            raise SystemExit(f"DEM covers lon {sb.left:.2f}..{sb.right:.2f}, lat {sb.bottom:.2f}..{sb.top:.2f}, "
                             f"which does not contain the bbox. Download the tile that covers it.")
        x0, y0, x1, y1 = transform_bounds(4326, CRS_M, *bbox)
        w, h = int((x1 - x0) / pixel_m), int((y1 - y0) / pixel_m)
        tr = from_origin(x0, y1, pixel_m, pixel_m)
        dem = np.full((h, w), np.nan, dtype="float32")
        reproject(rasterio.band(src, 1), dem, src_nodata=src.nodata, dst_nodata=np.nan,
                  dst_transform=tr, dst_crs=f"EPSG:{CRS_M}", resampling=Resampling.bilinear)
    return dem, tr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    ap.add_argument("--dem", required=True)
    ap.add_argument("--rivers", required=True)
    ap.add_argument("--coastline")
    ap.add_argument("--pixel-m", type=float, default=30)
    ap.add_argument("--max-level", type=float, default=5.0, help="highest water rise to model (m)")
    ap.add_argument("--step", type=float, default=0.5)
    ap.add_argument("--zone-levels", nargs="+", type=float, default=[1, 2, 3, 4, 5], help="levels drawn as map polygons")
    ap.add_argument("--raise-m", nargs="+", type=float, default=[0.5, 1.0], help="raised-floor heights to test")
    ap.add_argument("--evac-km", type=float, default=1.0)
    ap.add_argument("--max-drain-km", type=float, default=5.0, help="cells farther than this from any river/sea never flood")
    ap.add_argument("--river-window-m", type=float, default=150, help="window for the river's local low point")
    ap.add_argument("--ground-window-m", type=float, default=90,
                    help="search this far around each building for street-level ground. Copernicus measures roofs "
                         "and trees, so in dense towns use ~150-210; with FABDEM (roofs removed) keep 90")
    args = ap.parse_args()

    dem, tr = load_dem(args.dem, args.bbox, args.pixel_m)
    h, w = dem.shape
    px = args.pixel_m

    # --- drainage: rivers (local low point) and sea (0 m) ---
    rivers = read_layer(args.rivers, args.bbox, as_lines=True).to_crs(CRS_M)
    if rivers.empty:
        raise SystemExit("No rivers inside the bbox; check the Overpass export.")
    drain = np.zeros((h, w), dtype="uint8")
    drain[features.rasterize(((g, 1) for g in rivers.geometry), out_shape=(h, w), transform=tr, all_touched=True) == 1] = RIVER
    sea = np.nan_to_num(dem, nan=0.0) <= 0.0
    if args.coastline:
        coast = read_layer(args.coastline, args.bbox, as_lines=True).to_crs(CRS_M)
        if not coast.empty:
            sea |= features.rasterize(((g, 1) for g in coast.geometry), out_shape=(h, w), transform=tr, all_touched=True) == 1
    drain[sea] = SEA

    win = max(3, int(round(args.river_window_m / px)) | 1)
    low = ndimage.minimum_filter(np.nan_to_num(dem, nan=1e4), size=win)
    ref = np.where(drain == SEA, 0.0, np.maximum(low, 0.0))  # water surface at each drainage cell

    dist_px, (iy, ix) = ndimage.distance_transform_edt(drain == 0, return_indices=True)
    dist_m = dist_px * px
    hand = dem - ref[iy, ix]
    drain_type = drain[iy, ix]
    hand[(dist_m > args.max_drain_km * 1000) | np.isnan(dem)] = np.inf
    hand[drain > 0] = 0.0

    # --- raise the water step by step; keep only cells connected to the drainage ---
    levels = np.round(np.arange(args.step, args.max_level + 1e-9, args.step), 2)
    floods_at = np.full((h, w), np.nan, dtype="float32")
    is_drain = drain > 0
    for L in levels:
        wet = (hand < L) | is_drain
        lab, _ = ndimage.label(wet, structure=np.ones((3, 3)))
        keep = np.unique(lab[is_drain])
        connected = np.isin(lab, keep[keep > 0])
        floods_at[connected & np.isnan(floods_at) & ~is_drain] = L

    # --- buildings ---
    bld = gpd.read_file(OUT_DIR / "buildings.geojson").to_crs(CRS_M)
    bld = bld.drop(columns=[c for c in FLOOD_COLS if c in bld.columns])
    if "people" not in bld.columns:
        raise SystemExit("buildings.geojson has no 'people'; run 04_people_behind.py first.")
    rows, cols = rasterio.transform.rowcol(tr, bld.geometry.x.values, bld.geometry.y.values)
    rows, cols = np.clip(rows, 0, h - 1), np.clip(cols, 0, w - 1)
    # Neighbourhood around each building: the DEM may include roofs/trees, so use the lowest nearby
    # ground / flood level (= the street the water would come down)
    gw = max(1, int(round(args.ground_window_m / px)) | 1)
    fa_min = ndimage.minimum_filter(np.nan_to_num(floods_at, nan=np.inf), size=gw)
    gr_min = ndimage.minimum_filter(np.nan_to_num(dem, nan=np.inf), size=gw)
    hand_min = ndimage.minimum_filter(hand, size=gw)
    fa = fa_min[rows, cols]
    bld["ground_m"] = np.round(gr_min[rows, cols], 1)
    bld["hand_m"] = np.round(np.where(np.isfinite(hand_min[rows, cols]), hand_min[rows, cols], np.nan), 1)
    bld["floods_at_m"] = np.where(np.isfinite(fa), fa, np.nan)
    bld["drain"] = np.where(drain_type[rows, cols] == SEA, "sea", "river")
    bld["dist_drain_m"] = np.round(dist_m[rows, cols])

    # coastal mangrove buffer for each building (from 03/04), if linked to a coast segment
    band_now = band_restored = None
    if "segment_id" in bld.columns and (OUT_DIR / "coast_segments.geojson").exists():
        segs = gpd.read_file(OUT_DIR / "coast_segments.geojson").set_index("id")
        band_now = bld["segment_id"].map(segs["band_now"])
        band_restored = bld["segment_id"].map(segs["band_restored"])

    people = bld["people"].fillna(0).values
    fa_b = bld["floods_at_m"].fillna(np.inf).values
    coastal = (bld["drain"] == "sea").values & (bld["segment_id"].notna().values if "segment_id" in bld.columns else False)
    table = []
    for L in levels:
        flooded = fa_b <= L
        dry = ~(floods_at <= L) & ~is_drain & np.isfinite(dem)
        to_dry_m = ndimage.distance_transform_edt(~dry) * px
        far = flooded & (to_dry_m[rows, cols] > args.evac_km * 1000)
        row = {
            "level_m": float(L),
            "buildings": int(flooded.sum()),
            "people": int(people[flooded].sum()),
            "people_far_from_dry": int(people[far].sum()),
        }
        for r in args.raise_m:
            row[f"people_raised_{str(r).replace('.', '_')}m"] = int(people[fa_b + r <= L].sum())
        if band_now is not None:
            cf = flooded & coastal
            row["coastal_people"] = int(people[cf].sum())
            row["coastal_unbuffered_now"] = int(people[cf & (band_now == "exposed").values].sum())
            row["coastal_unbuffered_restored"] = int(people[cf & (band_restored == "exposed").values].sum())
        table.append(row)

    write_json("flood_levels.json", {
        "levels": table,
        "settings": {"step_m": args.step, "evac_km": args.evac_km, "raise_m": args.raise_m,
                     "pixel_m": px, "ground_window_m": args.ground_window_m, "dem": str(args.dem).replace("\\", "/").split("/")[-1]},
        "note": ("Water rise above normal river/sea level. Height-above-nearest-drainage model on a "
                 f"{px:g} m elevation grid: shows which areas flood first, not exact depths or timing."),
    })
    write_json("buildings.geojson", bld.to_crs(4326).__geo_interface__)

    # --- map layers ---
    zones = []
    for L in sorted(set(args.zone_levels)):
        mask = (floods_at <= L).astype("uint8")
        polys = [shape(g) for g, v in features.shapes(mask, mask=mask == 1, transform=tr) if v == 1]
        if polys:
            zones.append({"level_m": L, "geometry": gpd.GeoSeries(polys, crs=CRS_M).union_all().simplify(px / 2)})
    if zones:
        zg = gpd.GeoDataFrame(zones, crs=CRS_M).to_crs(4326)
        write_json("flood_zones.geojson", zg.__geo_interface__)
    rv = rivers.to_crs(4326).clip(box(*args.bbox))
    rv["geometry"] = rv.geometry.simplify(0.00005)
    write_json("rivers.geojson", rv[["geometry"]].__geo_interface__)

    print("Water rise → people flooded:")
    for row in table:
        extra = f"  (raised 0.5 m: {row.get('people_raised_0_5m', '-')}, far from dry ground: {row['people_far_from_dry']})"
        print(f"  {row['level_m']:>4} m: {row['people']:>6} people in {row['buildings']:>5} buildings{extra}")


if __name__ == "__main__":
    main()
