"""Pull the Global Mangrove Watch v3 tile(s) covering the pilot area out of a yearly zip
→ raw/gmw_<year>.tif. No need to unzip the whole thing or know the tile names.

Download the yearly GeoTIFF zips first (Zenodo record 6894273), e.g.
  raw/gmw_v3_2020_gtiff.zip and raw/gmw_v3_1996_gtiff.zip

Usage:
  python 00_pick_gmw_tile.py --zip raw/gmw_v3_2020_gtiff.zip --year 2020 --bbox 177.35 -17.70 177.80 -17.40
"""
import argparse
import zipfile
from pathlib import Path

import rasterio
from rasterio.merge import merge

from common import RAW_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--year", required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    args = ap.parse_args()
    x0, y0, x1, y1 = args.bbox

    zpath = Path(args.zip).resolve()
    with zipfile.ZipFile(zpath) as z:
        tifs = [n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))]
    print(f"{len(tifs)} tiles in {zpath.name}; checking which overlap the bbox...")

    hits = []
    for name in tifs:
        with rasterio.open(f"/vsizip/{zpath.as_posix()}/{name}") as src:
            b = src.bounds  # GMW tiles are in EPSG:4326 (degrees)
            if b.left < x1 and b.right > x0 and b.bottom < y1 and b.top > y0:
                hits.append(name)
    if not hits:
        raise SystemExit("No tile covers that bbox. Check the bbox order: min_lon min_lat max_lon max_lat.")
    print("Covering tile(s):", ", ".join(hits))

    out = RAW_DIR / f"gmw_{args.year}.tif"
    RAW_DIR.mkdir(exist_ok=True)
    srcs = [rasterio.open(f"/vsizip/{zpath.as_posix()}/{n}") for n in hits]
    arr, transform = merge(srcs, bounds=(x0, y0, x1, y1))
    meta = srcs[0].meta.copy()
    meta.update(height=arr.shape[1], width=arr.shape[2], transform=transform, compress="deflate")
    with rasterio.open(out, "w", **meta) as dst:
        dst.write(arr)
    for s in srcs:
        s.close()
    print(f"wrote {out} ({int((arr == 1).sum())} mangrove pixels in the bbox)")


if __name__ == "__main__":
    main()
