"""Shared helpers for the data-prep scripts. Formats follow docs/contracts.md.

The restoration effect model here MUST match backend/app/restoration.py and
frontend/src/api.js. Change all three together.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "frontend" / "public" / "data"
RAW_DIR = Path(__file__).resolve().parent / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Restoration effect model (deliberately conservative; cite in the pitch) ---
# Field studies report 13-66% wave-height reduction over 100 m of mangroves
# (McIvor et al. 2012). We use the LOW end per 100 m and cap at the high end.
WAVE_REDUCTION_PER_100M = 0.13
WAVE_REDUCTION_CAP = 0.66
# Observed storm-surge reduction is small: 0-0.25 m per km of forest. Use 0.1 m/km.
SURGE_REDUCTION_M_PER_KM = 0.10


def wave_reduction(width_m):
    """Fraction of wave height removed by a mangrove belt of this width (0-0.66)."""
    return round(min(WAVE_REDUCTION_CAP, WAVE_REDUCTION_PER_100M * max(0.0, width_m) / 100), 3)


def surge_reduction_m(width_m):
    return round(SURGE_REDUCTION_M_PER_KM * max(0.0, width_m) / 1000, 3)


def protection_band(width_m):
    """How well the coast in front of a building is buffered."""
    r = wave_reduction(width_m)
    if r >= 0.4:
        return "strong"
    if r >= 0.2:
        return "partial"
    return "exposed"


def read_layer(path, bbox=None, as_lines=False):
    """Read a vector file, or a 0/1 GeoTIFF (e.g. a Global Mangrove Watch tile, 1 = mangrove),
    as polygons in EPSG:4326. bbox = (min_lon, min_lat, max_lon, max_lat) avoids loading a
    whole global file and clips the result.
    as_lines=True (for coastlines): polygons are turned into their outlines BEFORE clipping,
    because Overpass Turbo exports closed coastline ways (islands) as polygons, and clipping a
    polygon first would add a fake coast along the bbox edge."""
    import geopandas as gpd
    from shapely.geometry import box, shape

    if str(path).lower().endswith((".tif", ".tiff")):
        import rasterio
        from rasterio import features, windows
        from rasterio.warp import transform_bounds

        with rasterio.open(path) as src:
            win = None
            if bbox:
                b = transform_bounds(4326, src.crs, *bbox)
                win = windows.from_bounds(*b, src.transform).round_offsets().round_lengths()
            arr = src.read(1, window=win)
            tr = src.window_transform(win) if win else src.transform
            geoms = [shape(g) for g, v in features.shapes(arr, mask=arr == 1, transform=tr) if v == 1]
            gdf = gpd.GeoDataFrame(geometry=geoms, crs=src.crs).to_crs(4326)
    else:
        gdf = gpd.read_file(path, bbox=tuple(bbox) if bbox else None).to_crs(4326)
    if as_lines:
        gdf = gdf.set_geometry(gdf.geometry.apply(
            lambda g: g.boundary if g is not None and g.geom_type in ("Polygon", "MultiPolygon") else g))
    if bbox:
        gdf = gdf.clip(box(*bbox))
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if as_lines:  # keep only line parts (clipping can leave stray points)
        gdf = gdf.explode(index_parts=False)
        gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "LinearRing"])]
    return gdf


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance. Works across the 180° meridian."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def write_json(name, data):
    path = OUT_DIR / name
    path.write_text(json.dumps(data, indent=1))
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def read_json(name, default=None):
    path = OUT_DIR / name
    if not path.exists():
        return default
    return json.loads(path.read_text())
