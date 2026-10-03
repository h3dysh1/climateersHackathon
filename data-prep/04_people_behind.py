"""Link buildings to the coast segment in front of them and rank restoration sites
→ updates buildings.geojson and coast_segments.geojson. Safe to re-run (e.g. after the
WorldPop step adds a 'people' property, or surge_zones.geojson appears).

Each building within --max-coast-m of the coast is assigned to its nearest segment.
People per building come from a 'people' property (from the WorldPop step) or default to
--default-people. Without WorldPop, buildings with a footprint smaller than --min-home-m2
(sheds, cookhouses) or larger than --max-home-m2 (mills, warehouses, schools) count 0 people.
If surge_zones.geojson exists (level_m polygons), buildings inside get surge_m.

priority = surge-exposed people behind the segment × added wave reduction ÷ restorable hectares
(i.e. people protected per hectare restored). Higher = restore first.
Segments with less than --min-restorable-ha restorable get priority 0: in the linear wave
model the hectares cancel out of this ratio, so without a minimum a tiny sliver of
(possibly misclassified) 1996 mangrove would rank as high as a large restorable area.

Usage:
  python 04_people_behind.py [--max-coast-m 1000] [--min-restorable-ha 1]
"""
import argparse

import geopandas as gpd

from common import OUT_DIR, write_json

CRS_M = 3460
DERIVED = ["segment_id", "coast_m", "index_right"]  # columns this script writes; dropped before re-joining


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-coast-m", type=float, default=1000)
    ap.add_argument("--default-people", type=float, default=4,
                    help="people per home when there is no WorldPop 'people' property (check Fiji census household size)")
    ap.add_argument("--min-home-m2", type=float, default=20)
    ap.add_argument("--max-home-m2", type=float, default=600)
    ap.add_argument("--min-restorable-ha", type=float, default=1.0)
    args = ap.parse_args()

    segs = gpd.read_file(OUT_DIR / "coast_segments.geojson").to_crs(CRS_M)
    bld = gpd.read_file(OUT_DIR / "buildings.geojson").to_crs(CRS_M)
    bld = bld.drop(columns=[c for c in DERIVED if c in bld.columns])

    if "people" not in bld.columns or bld["people"].isna().all():
        bld["people"] = float(args.default_people)
        if "area_m2" in bld.columns:
            not_home = (bld["area_m2"] < args.min_home_m2) | (bld["area_m2"] > args.max_home_m2)
            bld.loc[not_home.fillna(False), "people"] = 0.0
            print(f"No WorldPop people yet: {args.default_people:g} per home; "
                  f"{int(not_home.sum())} buildings outside {args.min_home_m2:g}-{args.max_home_m2:g} m² count 0.")
    bld["people"] = bld["people"].fillna(0)

    surge_path = OUT_DIR / "surge_zones.geojson"
    if surge_path.exists():
        surge = gpd.read_file(surge_path).to_crs(CRS_M).sort_values("level_m")
        j = gpd.sjoin(bld[["geometry"]], surge[["level_m", "geometry"]], how="left", predicate="within")
        bld["surge_m"] = j.groupby(level=0)["level_m"].min()
    else:
        bld["surge_m"] = None
        print("No surge_zones.geojson yet: every building near the coast counts as exposed.")

    near = gpd.sjoin_nearest(bld[["geometry"]], segs[["id", "geometry"]].rename(columns={"id": "segment_id"}),
                             how="left", max_distance=args.max_coast_m, distance_col="coast_m")
    near = near[~near.index.duplicated()]
    bld["segment_id"] = near["segment_id"]
    bld["coast_m"] = near["coast_m"].round()

    linked = bld[bld["segment_id"].notna()]
    exposed = linked[linked["surge_m"].notna()] if surge_path.exists() else linked
    segs = segs.set_index("id")
    by_seg = linked.groupby("segment_id")
    segs["people_behind"] = by_seg["people"].sum().reindex(segs.index).fillna(0).round()
    segs["buildings_behind"] = by_seg.size().reindex(segs.index).fillna(0).astype(int)
    segs["surge_people"] = exposed.groupby("segment_id")["people"].sum().reindex(segs.index).fillna(0).round()
    gain = segs["wave_reduction_restored"] - segs["wave_reduction_now"]
    eligible = segs["restorable_ha"] >= args.min_restorable_ha
    segs["priority"] = (segs["surge_people"] * gain / segs["restorable_ha"].where(eligible)).fillna(0).round(2)

    write_json("coast_segments.geojson", segs.reset_index().to_crs(4326).__geo_interface__)
    write_json("buildings.geojson", bld.to_crs(4326).__geo_interface__)
    print(f"{int(linked['people'].sum())} people in {len(linked)} buildings within {args.max_coast_m:g} m of the coast; "
          f"{int(eligible.sum())} of {len(segs)} segments have at least {args.min_restorable_ha:g} ha restorable")
    top = segs.sort_values("priority", ascending=False).head(5)
    print("Top restoration sites:\n", top[["restorable_ha", "existing_width_m", "surge_people", "priority"]])


if __name__ == "__main__":
    main()
