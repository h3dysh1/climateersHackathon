"""Link buildings to the coast segment in front of them and rank restoration sites
→ updates buildings.geojson and coast_segments.geojson.

Each building within --max-coast-m of the coast is assigned to its nearest segment.
People per building come from a 'people' property (from the WorldPop step) or default to 4.
If surge_zones.geojson exists (level_m polygons), buildings inside get surge_m.

priority = surge-exposed people behind the segment × added wave reduction ÷ restorable hectares
(i.e. people protected per hectare restored). Higher = restore first.

Usage:
  python 04_people_behind.py [--max-coast-m 1000]
"""
import argparse

import geopandas as gpd

from common import OUT_DIR, write_json

CRS_M = 3460


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-coast-m", type=float, default=1000)
    ap.add_argument("--default-people", type=float, default=4)
    args = ap.parse_args()

    segs = gpd.read_file(OUT_DIR / "coast_segments.geojson").to_crs(CRS_M)
    bld = gpd.read_file(OUT_DIR / "buildings.geojson").to_crs(CRS_M)
    if "people" not in bld.columns:
        bld["people"] = args.default_people
    bld["people"] = bld["people"].fillna(args.default_people)

    surge_path = OUT_DIR / "surge_zones.geojson"
    if surge_path.exists():
        surge = gpd.read_file(surge_path).to_crs(CRS_M).sort_values("level_m")
        j = gpd.sjoin(bld[["geometry"]], surge[["level_m", "geometry"]], how="left", predicate="within")
        bld["surge_m"] = j.groupby(level=0)["level_m"].min()
    elif "surge_m" not in bld.columns:
        bld["surge_m"] = None
        print("No surge_zones.geojson yet: every building near the coast counts as exposed.")

    near = gpd.sjoin_nearest(bld, segs[["id", "geometry"]].rename(columns={"id": "segment_id"}),
                             how="left", max_distance=args.max_coast_m, distance_col="coast_m")
    near = near[~near.index.duplicated()]
    bld["segment_id"] = near["segment_id"]
    bld["coast_m"] = near["coast_m"].round()

    exposed = bld[bld["segment_id"].notna() & (bld["surge_m"].notna() if surge_path.exists() else True)]
    by_seg = bld[bld["segment_id"].notna()].groupby("segment_id")
    segs = segs.set_index("id")
    segs["people_behind"] = by_seg["people"].sum().reindex(segs.index).fillna(0).round()
    segs["buildings_behind"] = by_seg.size().reindex(segs.index).fillna(0).astype(int)
    segs["surge_people"] = exposed.groupby("segment_id")["people"].sum().reindex(segs.index).fillna(0).round()
    gain = segs["wave_reduction_restored"] - segs["wave_reduction_now"]
    segs["priority"] = (segs["surge_people"] * gain / segs["restorable_ha"].where(segs["restorable_ha"] > 0)).fillna(0).round(2)

    write_json("coast_segments.geojson", segs.reset_index().to_crs(4326).__geo_interface__)
    write_json("buildings.geojson", bld.to_crs(4326).__geo_interface__)
    top = segs.sort_values("priority", ascending=False).head(5)
    print("Top restoration sites:\n", top[["restorable_ha", "surge_people", "priority"]])


if __name__ == "__main__":
    main()
