"""Nadi Flood Planner data step: open data → the files the app and backend read.

Implements the "Nadi Flood Planner: Data Processing Guide" (same command, same output files).
For every 30 m patch of ground it works out how many metres it sits above the river or sea it
drains to (HAND, height above nearest drainage). "The river rises L m" floods every patch with
HAND below L that is connected to the river/sea. Each home, facility and road section then gets
the river rise at which water first reaches it. All heights are metres above normal river/sea
level, the same unit as the app's slider. 99 = not reached within --max-level.

Simplification vs a full hydrological HAND: the nearest drainage is found by straight-line
distance to the mapped rivers/sea, not by tracing flow paths, and unmapped channels are not
detected. Say so in the "About" panel. It is a planning screen, not a flow simulation.

Outputs (frontend/public/data/):
  buildings.json         [{id, lon, lat, ground_m (=HAND), floods_at_m, people, type, area}]
  facilities.json        [{id, name, type, lon, lat, ground_m, floods_at_m}]
  roads.json             [{id, name, low_point_m, length_m}]   (sections up to 500 m)
  roads.geojson          same sections as lines, for the map
  flood_extents.geojson  water outline at every 0.5 m (property level_m)
  rivers.geojson         the waterways used as drainage, for the map
  hand_summary.json      settings and sanity-check numbers (post in team chat)
Also raw/hand.tif and raw/floods_at.tif for checking in QGIS (not used by the app).

Usage (Windows PowerShell, one line):
  python hand_flood.py --bbox 177.38 -17.86 177.52 -17.72 --dem raw\\fabdem_download.tif
      --buildings raw\\buildings_raw.geojson --rivers raw\\rivers.geojson
      --facilities raw\\facilities.geojson --roads raw\\roads.geojson
      --places raw\\places.geojson --worldpop raw\\fji_ppp_2020.tif
"""
import argparse
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.transform
import rasterio.windows
from rasterio import features
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy import ndimage
from shapely.geometry import box, shape
from shapely.ops import substring

from common import OUT_DIR, RAW_DIR, read_layer

CRS_M = 3460  # Fiji Map Grid, metres
NEVER = 99.0
SEA, RIVER = 1, 2


def write(name, data):
    path = OUT_DIR / name
    path.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {path.relative_to(OUT_DIR.parent.parent.parent)} ({path.stat().st_size / 1e6:.1f} MB)")


# ---------------------------------------------------------------- elevation and HAND

def load_dem(path, bbox, px):
    with rasterio.open(path) as src:
        sb = src.bounds
        tol = 0.002  # ~200 m: tiles cut to the bbox can be a fraction of a pixel short
        if not (sb.left <= bbox[0] + tol and sb.right >= bbox[2] - tol and sb.bottom <= bbox[1] + tol and sb.top >= bbox[3] - tol):
            raise SystemExit(f"DEM covers lon {sb.left:.3f}..{sb.right:.3f}, lat {sb.bottom:.3f}..{sb.top:.3f}, "
                             "which does not contain the bbox. Re-extract it with a bigger box.")
        x0, y0, x1, y1 = transform_bounds(4326, CRS_M, *bbox)
        w, h = int((x1 - x0) / px), int((y1 - y0) / px)
        tr = from_origin(x0, y1, px, px)
        dem = np.full((h, w), np.nan, dtype="float32")
        reproject(rasterio.band(src, 1), dem, src_nodata=src.nodata, dst_nodata=np.nan,
                  dst_transform=tr, dst_crs=f"EPSG:{CRS_M}", resampling=Resampling.bilinear)
    return dem, tr


def compute_hand(dem, tr, rivers, coast, px, river_window_m, max_drain_km):
    h, w = dem.shape
    drain = np.zeros((h, w), dtype="uint8")
    if len(rivers):
        drain[features.rasterize(((g, 1) for g in rivers.geometry), out_shape=(h, w), transform=tr, all_touched=True) == 1] = RIVER
    sea = np.isnan(dem) | (dem <= 0.0)          # guide: sea and below-sea cells become 0 m
    if coast is not None and len(coast):
        sea |= features.rasterize(((g, 1) for g in coast.geometry), out_shape=(h, w), transform=tr, all_touched=True) == 1
    drain[sea] = SEA
    dem0 = np.where(sea, 0.0, dem)

    win = max(3, int(round(river_window_m / px)) | 1)
    low = ndimage.minimum_filter(np.nan_to_num(dem0, nan=1e4), size=win)
    ref = np.where(drain == SEA, 0.0, np.maximum(low, 0.0))  # water surface at each drainage cell

    # Water drains downhill, so each cell may only use drainage at or below its own height.
    # Work up in 1 m elevation bands: cells in band [t, t+1) use the nearest drainage with ref <= t.
    hand = np.full(dem0.shape, np.inf, dtype="float32")
    dist_m = np.full(dem0.shape, np.inf, dtype="float32")
    z = np.nan_to_num(dem0, nan=0.0)
    is_d = drain > 0
    ref_min = float(ref[is_d].min()) if is_d.any() else 0.0
    t_hi = float(np.nanmax(z)) + 1
    for t in np.arange(np.floor(ref_min), t_hi, 1.0):
        band = (z >= t) & (z < t + 1) if t > np.floor(ref_min) else (z < t + 1)
        if not band.any():
            continue
        src = is_d & (ref <= max(t, ref_min))
        if not src.any():
            continue
        d_px, (iy, ix) = ndimage.distance_transform_edt(~src, return_indices=True)
        hand[band] = (z - ref[iy, ix])[band]
        dist_m[band] = (d_px * px)[band]
    hand[dist_m > max_drain_km * 1000] = np.inf
    hand[is_d] = 0.0
    hand = np.maximum(hand, 0.0)
    return hand, drain, dist_m


def flood_levels(hand, drain, levels):
    """Lowest level at which each cell is under water that is connected to the river/sea."""
    floods_at = np.full(hand.shape, NEVER, dtype="float32")
    is_drain = drain > 0
    floods_at[is_drain] = 0.0
    for L in levels:
        wet = (hand < L) | is_drain
        lab, _ = ndimage.label(wet, structure=np.ones((3, 3)))
        keep = np.unique(lab[is_drain])
        connected = np.isin(lab, keep[keep > 0])
        floods_at[connected & (floods_at == NEVER)] = L
    return floods_at


def save_tif(path, arr, tr):
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1,
                       dtype="float32", crs=f"EPSG:{CRS_M}", transform=tr, compress="deflate") as d:
        d.write(np.where(np.isfinite(arr), arr, NEVER).astype("float32"), 1)


def sample(arr_min, tr, xs, ys):
    h, w = arr_min.shape
    r, c = rasterio.transform.rowcol(tr, xs, ys)
    r, c = np.clip(np.asarray(r), 0, h - 1), np.clip(np.asarray(c), 0, w - 1)
    return arr_min[r, c]


# ---------------------------------------------------------------- inputs

def osm_label(row, keys):
    for k in keys:
        v = row.get(k)
        if isinstance(v, str) and v:
            return v
    return None


def worldpop_people(pts_ll, areas, path, bbox):
    """Share each WorldPop cell's people across the buildings in it, by footprint area."""
    with rasterio.open(path) as src:
        win = rasterio.windows.from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
        pop = src.read(1, window=win, boundless=True, fill_value=0).astype("float64")
        wtr = src.window_transform(win)
        if src.nodata is not None:
            pop[pop == src.nodata] = 0
    pop[~np.isfinite(pop) | (pop < 0)] = 0
    r, c = rasterio.transform.rowcol(wtr, pts_ll.x.values, pts_ll.y.values)
    r, c = np.asarray(r), np.asarray(c)
    inside = (r >= 0) & (r < pop.shape[0]) & (c >= 0) & (c < pop.shape[1])
    cell = np.where(inside, r * pop.shape[1] + c, -1)
    df = pd.DataFrame({"cell": cell, "a": np.maximum(areas, 1.0)})
    tot = df[df.cell >= 0].groupby("cell")["a"].transform("sum")
    people = np.zeros(len(df))
    ok = df.cell >= 0
    people[ok.values] = pop.ravel()[df.cell[ok].values] * df.a[ok].values / tot.values
    covered = pop.ravel()[np.unique(cell[cell >= 0])].sum()
    return people, float(pop.sum()), float(covered)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    ap.add_argument("--dem", help="elevation GeoTIFF (FABDEM recommended). If omitted, tries the fabdem package.")
    ap.add_argument("--buildings", required=True)
    ap.add_argument("--rivers", required=True)
    ap.add_argument("--facilities")
    ap.add_argument("--roads")
    ap.add_argument("--places")
    ap.add_argument("--worldpop")
    ap.add_argument("--coastline", help="optional OSM coastline; the sea is otherwise taken from elevation <= 0 m")
    ap.add_argument("--waterways", default="river,stream,canal,drain",
                    help="which OSM waterway types count as drainage (try 'river,canal' to compare)")
    ap.add_argument("--max-level", type=float, default=6.0)
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--extent-step", type=float, default=0.5)
    ap.add_argument("--max-buildings", type=int, default=15000)
    ap.add_argument("--default-people", type=float, default=4.0)
    ap.add_argument("--pixel-m", type=float, default=30)
    ap.add_argument("--ground-window-m", type=float, default=90,
                    help="search this far around a building/facility for its lowest ground (30 m grid cells)")
    ap.add_argument("--river-window-m", type=float, default=150)
    ap.add_argument("--max-drain-km", type=float, default=5.0)
    ap.add_argument("--area-max-km", type=float, default=1.5)
    ap.add_argument("--road-section-m", type=float, default=500)
    ap.add_argument("--keep-shelters", action="store_true",
                    help="keep every OSM amenity=shelter; by default only shelter_type=evacuation is kept, "
                         "because most OSM shelters are bus stops, gazebos or carports")
    args = ap.parse_args()
    bbox, px = args.bbox, args.pixel_m

    # 1. elevation
    dem_path = args.dem
    if not dem_path:
        dem_path = str(RAW_DIR / "fabdem_download.tif")
        try:
            import fabdem
            fabdem.download(tuple(bbox), output_path=dem_path, show_progress=True)
        except Exception as e:  # the package's download link has been broken (404)
            raise SystemExit(f"FABDEM download failed ({e}). Download S20E170-S10W180_FABDEM_V1-2.zip by hand, "
                             "extract the tile with 00_pick_gmw_tile.py and pass --dem.")
    dem, tr = load_dem(dem_path, bbox, px)
    h, w = dem.shape

    # 2-5. drainage, HAND, flood levels
    rivers = read_layer(args.rivers, bbox, as_lines=True)
    if "waterway" in rivers.columns:
        rivers = rivers[rivers["waterway"].isin([t.strip() for t in args.waterways.split(",")])]
    rivers = rivers.to_crs(CRS_M)
    if rivers.empty:
        raise SystemExit("No rivers in the bbox after filtering; check raw/rivers.geojson and --waterways.")
    coast = read_layer(args.coastline, bbox, as_lines=True).to_crs(CRS_M) if args.coastline else None
    hand, drain, dist_m = compute_hand(dem, tr, rivers, coast, px, args.river_window_m, args.max_drain_km)
    levels = np.round(np.arange(args.step, args.max_level + 1e-9, args.step), 3)
    floods_at = flood_levels(hand, drain, levels)
    save_tif(RAW_DIR / "hand.tif", hand, tr)
    save_tif(RAW_DIR / "floods_at.tif", floods_at, tr)

    gw = max(1, int(round(args.ground_window_m / px)) | 1)
    hand_lo = ndimage.minimum_filter(np.where(np.isfinite(hand), hand, NEVER), size=gw)
    fa_lo = ndimage.minimum_filter(floods_at, size=gw)

    def heights(gdf_m):
        xs, ys = gdf_m.geometry.x.values, gdf_m.geometry.y.values
        g = np.round(np.minimum(sample(hand_lo, tr, xs, ys), NEVER), 2)
        f = np.round(sample(fa_lo, tr, xs, ys), 2)
        return g, np.where(f >= args.max_level + 1e-6, NEVER, f)

    # place names
    places = None
    if args.places:
        places = read_layer(args.places, bbox).to_crs(CRS_M)
        places["pname"] = [osm_label(r, ["name", "name:en"]) for _, r in places.iterrows()]
        places = places[places["pname"].notna()][["pname", "geometry"]]
        places["geometry"] = places.geometry.representative_point()

    def area_names(pts_m):
        if places is None or places.empty:
            return [None] * len(pts_m)
        j = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=pts_m.geometry.values, crs=CRS_M), places,
                              how="left", max_distance=args.area_max_km * 1000)
        j = j[~j.index.duplicated()]
        return [n if isinstance(n, str) else None for n in j["pname"].reindex(range(len(pts_m)))]

    # 6a. buildings: people are shared out over ALL buildings first, then the cap keeps every
    # building the water can reach, so flood counts and people totals are not cut by the cap.
    bld = read_layer(args.buildings, bbox).reset_index(drop=True)
    bld_m = bld.to_crs(CRS_M)
    area_m2 = bld_m.geometry.area.values
    pts_m = gpd.GeoDataFrame(geometry=bld_m.geometry.representative_point(), crs=CRS_M)
    pts_ll = pts_m.to_crs(4326).geometry
    if args.worldpop:
        people, pop_box, pop_covered = worldpop_people(pts_ll, area_m2, args.worldpop, bbox)
        people_source = "WorldPop 2020 (shared by footprint area)"
    else:
        is_home = (area_m2 >= 20) & (area_m2 <= 600) | (area_m2 == 0)
        people = np.where(is_home, args.default_people, 0.0)
        pop_box = pop_covered = None
        people_source = f"default {args.default_people:g} per building (20-600 m2)"
    g, f = heights(pts_m)
    keep = np.arange(len(bld))
    n_total = len(bld)
    if n_total > args.max_buildings:
        reached = np.where(f < NEVER)[0]
        dry = np.where(f >= NEVER)[0]
        if len(reached) > args.max_buildings:
            print(f"WARNING: {len(reached)} buildings can flood but --max-buildings is {args.max_buildings}; "
                  "the app will undercount. Raise --max-buildings (the backend accepts up to 20,000).")
        room = max(0, args.max_buildings - len(reached))
        rng = np.random.default_rng(42)
        keep = np.sort(np.concatenate([reached[: args.max_buildings], rng.choice(dry, size=min(room, len(dry)), replace=False)]))
    names = area_names(pts_m.iloc[keep].reset_index(drop=True))
    buildings = [{
        "id": f"b{i + 1:05d}", "lon": round(float(pts_ll.iloc[k].x), 6), "lat": round(float(pts_ll.iloc[k].y), 6),
        "ground_m": float(g[k]), "floods_at_m": float(f[k]), "people": round(float(people[k]), 2),
        "type": "home", "area": names[i],
    } for i, k in enumerate(keep)]
    for b in buildings:
        if b["area"] is None:
            del b["area"]
    write("buildings.json", buildings)

    # 6b. facilities
    facilities = []
    if args.facilities:
        fac = read_layer(args.facilities, bbox).reset_index(drop=True)
        if len(fac) and not args.keep_shelters and "amenity" in fac.columns:
            st = fac["shelter_type"].astype(str) if "shelter_type" in fac.columns else ""
            drop = (fac["amenity"] == "shelter") & ~(st == "evacuation")
            print(f"Skipping {int(drop.sum())} OSM shelters that are not evacuation shelters (use --keep-shelters to keep them)")
            fac = fac[~drop].reset_index(drop=True)
        if len(fac):
            fac_m = fac.to_crs(CRS_M)
            fpts = gpd.GeoDataFrame(geometry=fac_m.geometry.representative_point(), crs=CRS_M)
            fll = fpts.to_crs(4326).geometry
            fg, ff = heights(fpts)
            fnames = area_names(fpts)
            for i, (_, r) in enumerate(fac.iterrows()):
                item = {"id": f"f{i + 1:04d}", "name": osm_label(r, ["name", "name:en"]),
                        "type": osm_label(r, ["amenity", "power", "healthcare", "building"]),
                        "lon": round(float(fll.iloc[i].x), 6), "lat": round(float(fll.iloc[i].y), 6),
                        "ground_m": float(fg[i]), "floods_at_m": float(ff[i])}
                if fnames[i]:
                    item["area"] = fnames[i]
                facilities.append(item)
    write("facilities.json", facilities)

    # 6c. roads: sections up to 500 m; low point = lowest height water must reach along the section,
    # sampled every grid cell, skipping bridges and samples on the river channel itself.
    roads, road_feats = [], []
    if args.roads:
        rd = read_layer(args.roads, bbox, as_lines=True).reset_index(drop=True)
        if "bridge" in rd.columns:
            rd = rd[~rd["bridge"].fillna("no").astype(str).isin(["yes", "viaduct", "true", "1"])]
        rd_m = rd.to_crs(CRS_M)
        eff = np.maximum(np.where(np.isfinite(hand), hand, NEVER), floods_at)  # disconnected hollows stay dry
        eff = np.where(eff >= args.max_level + 1e-6, NEVER, eff)
        n = 0
        for (_, r), line in zip(rd.iterrows(), rd_m.geometry):
            if line is None or line.length < 1:
                continue
            k = max(1, int(np.ceil(line.length / args.road_section_m)))
            step = line.length / k
            for s in range(k):
                sec = substring(line, s * step, (s + 1) * step)
                d = np.arange(0, sec.length + 1e-9, px)
                xy = [sec.interpolate(t) for t in d]
                xs, ys = np.array([p.x for p in xy]), np.array([p.y for p in xy])
                rr, cc = rasterio.transform.rowcol(tr, xs, ys)
                rr, cc = np.clip(np.asarray(rr), 0, h - 1), np.clip(np.asarray(cc), 0, w - 1)
                on_channel = drain[rr, cc] == RIVER
                vals = eff[rr, cc][~on_channel]
                low = float(np.round(vals.min(), 2)) if vals.size else NEVER
                n += 1
                rid = f"r{n:05d}"
                name = osm_label(r, ["name", "ref"])
                roads.append({"id": rid, "name": name, "low_point_m": low, "length_m": round(sec.length)})
                road_feats.append({"id": rid, "name": name, "low_point_m": low, "length_m": round(sec.length), "geometry": sec})
    write("roads.json", roads)
    if road_feats:
        rg = gpd.GeoDataFrame(road_feats, crs=CRS_M).to_crs(4326)
        rg["geometry"] = rg.geometry.simplify(0.00002)
        write("roads.geojson", json.loads(rg.to_json()))

    # 7. flood extents every 0.5 m
    ext = []
    for L in np.round(np.arange(args.extent_step, args.max_level + 1e-9, args.extent_step), 3):
        mask = ((floods_at <= L) & (drain != SEA)).astype("uint8")
        polys = [shape(geom) for geom, v in features.shapes(mask, mask=mask == 1, transform=tr) if v == 1]
        if polys:
            ext.append({"level_m": float(L), "geometry": gpd.GeoSeries(polys, crs=CRS_M).union_all().simplify(px / 2)})
    if ext:
        eg = gpd.GeoDataFrame(ext, crs=CRS_M).to_crs(4326).clip(box(*bbox)).sort_values("level_m")
        write("flood_extents.geojson", json.loads(eg.to_json()))

    # rivers used as drainage, for the map
    rv = rivers.to_crs(4326).clip(box(*bbox))
    rv = gpd.GeoDataFrame({"waterway": rv["waterway"] if "waterway" in rv.columns else "river"}, geometry=rv.geometry.simplify(0.00003), crs=4326)
    write("rivers.geojson", json.loads(rv.to_json()))

    # summary for team checks
    f_all = f  # every building, before the cap
    reached_at = {f"{L:g}": int((f_all <= L).sum()) for L in range(1, int(args.max_level) + 1)}
    people_at = {f"{L:g}": round(float(people[f_all <= L].sum())) for L in range(1, int(args.max_level) + 1)}
    summary = {
        "bbox": bbox, "dem": str(dem_path).replace("\\", "/").split("/")[-1], "pixel_m": px,
        "method": "HAND by straight-line nearest drainage (mapped rivers + sea), connected-water flood fill",
        "waterways": args.waterways, "max_level_m": args.max_level, "step_m": args.step,
        "drainage": {"river_cells": int((drain == RIVER).sum()), "sea_cells": int((drain == SEA).sum()),
                     "river_km_mapped": round(float(rivers.length.sum()) / 1000, 1)},
        "buildings_total": n_total, "buildings": len(buildings),
        "buildings_dropped_by_cap": n_total - len(buildings),
        "buildings_reached_at": reached_at, "people_reached_at": people_at,
        "people_total": round(float(people.sum())), "people_source": people_source,
        "worldpop_people_in_box": round(pop_box) if pop_box is not None else None,
        "worldpop_people_in_cells_with_buildings": round(pop_covered) if pop_covered is not None else None,
        "buildings_with_area_name": sum(1 for b in buildings if b.get("area")),
        "facilities": len(facilities),
        "facilities_reached_at_2m": sum(1 for x in facilities if x["floods_at_m"] <= 2),
        "road_sections": len(roads), "roads_cut_at_1m_km": round(sum(r["length_m"] for r in roads if 1 - r["low_point_m"] >= 0.3) / 1000, 1),
        "note": "Heights are metres above normal river/sea level (99 = not reached). Planning screen, not a flow simulation.",
    }
    write("hand_summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("buildings_total", "buildings", "buildings_reached_at", "people_source",
                                              "buildings_with_area_name", "facilities", "road_sections")}, indent=1))


if __name__ == "__main__":
    main()
