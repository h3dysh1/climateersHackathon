"""Crop a small image tile around each building from an aerial/satellite GeoTIFF → tiles/<id>.png.

Use openly licensed imagery (e.g. OpenAerialMap, CC-BY 4.0). Do not use Google/Esri basemap
imagery for analysis — their terms restrict it.

Usage:
  python 03_tiles.py --image raw/oam_rakiraki.tif --size 256 --metres 40
"""
import argparse
import json

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform
from rasterio.windows import from_bounds

from common import OUT_DIR, TILE_DIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--size", type=int, default=256, help="output tile size in pixels")
    ap.add_argument("--metres", type=float, default=40, help="ground width of each tile")
    args = ap.parse_args()

    fc = json.loads((OUT_DIR / "buildings.geojson").read_text())
    ok = skipped = 0
    with rasterio.open(args.image) as src:
        for f in fc["features"]:
            bid = f["properties"]["id"]
            lon, lat = f["geometry"]["coordinates"]
            xs, ys = transform("EPSG:4326", src.crs, [lon], [lat])
            x, y = xs[0], ys[0]
            half = args.metres / 2
            if src.crs.is_geographic:  # convert metres to degrees roughly
                half = half / 111_000
            win = from_bounds(x - half, y - half, x + half, y + half, src.transform)
            bands = min(3, src.count)
            arr = src.read(list(range(1, bands + 1)), window=win, boundless=True, fill_value=0)
            if arr.size == 0 or arr.max() == 0:
                skipped += 1
                continue
            arr = np.moveaxis(arr, 0, -1)
            if arr.dtype != np.uint8:
                arr = (255 * (arr - arr.min()) / max(1, arr.max() - arr.min())).astype(np.uint8)
            if bands == 1:
                arr = arr[..., 0]
            Image.fromarray(arr).resize((args.size, args.size)).save(TILE_DIR / f"{bid}.png")
            ok += 1
    print(f"{ok} tiles written, {skipped} outside the image")


if __name__ == "__main__":
    main()
