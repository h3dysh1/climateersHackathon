"""Evidence check against Cyclone Winston: did buildings behind mangroves fare better?
→ validation.json

Data: Paulik et al., "Wind damage dataset for buildings from 2016 tropical cyclone Winston
in Fiji", Zenodo 10.5281/zenodo.14353428. CHECK THE COLUMN NAMES first (--show-columns).

The survey's damage states are DS0 None, DS1 Insignificant, DS2 Minor, DS3 Moderate,
DS4 Severe, DS5 Complete; "severe" here = DS4+ by default. Coordinates are X_coord (lon)
and Y_coord (lat). The survey covers Rakiraki, Tavua and Ba, not Lautoka: run
03_coast_segments.py with --tag _ba over a surveyed coast and pass --segments.

Method: for each surveyed building near the coast, find the coast segment in front of it
and compare the share of severe damage where existing mangroves were >= --min-width-m
vs where there were none. CAUTION: this is a WIND damage survey and mangroves do not reduce
wind, so any difference reflects other factors (building type, town vs village). Present it
as context, never as proof that mangroves protected these buildings.

Usage:
  python 05_validate.py --damage raw/2016TCWinston_DamageData.csv --show-columns
  python 05_validate.py --damage raw/2016TCWinston_DamageData.csv \
      --lat-col Y_coord --lon-col X_coord --damage-col Damage_State --segments coast_segments_ba.geojson
"""
import argparse
import re

import geopandas as gpd
import pandas as pd

from common import OUT_DIR, write_json

CRS_M = 3460


def ds_number(value):
    m = re.search(r"(\d)", str(value))
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--damage", required=True)
    ap.add_argument("--show-columns", action="store_true")
    ap.add_argument("--lat-col")
    ap.add_argument("--lon-col")
    ap.add_argument("--damage-col")
    ap.add_argument("--severe-from", type=int, default=4, help="DS4 = Severe")
    ap.add_argument("--segments", default="coast_segments.geojson", help="segments file in frontend/public/data")
    ap.add_argument("--min-width-m", type=float, default=100)
    ap.add_argument("--max-coast-m", type=float, default=1000)
    args = ap.parse_args()

    df = pd.read_csv(args.damage)
    if args.show_columns or not (args.lat_col and args.lon_col and args.damage_col):
        print("Columns:", list(df.columns))
        print(df.head(3).to_string())
        return

    df["ds"] = df[args.damage_col].map(ds_number)
    df = df.dropna(subset=["ds", args.lat_col, args.lon_col])
    pts = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[args.lon_col], df[args.lat_col]), crs=4326).to_crs(CRS_M)
    segs = gpd.read_file(OUT_DIR / args.segments).to_crs(CRS_M)
    j = gpd.sjoin_nearest(pts, segs[["existing_width_m", "geometry"]], max_distance=args.max_coast_m)
    j = j[~j.index.duplicated()]
    if len(j) < 20:
        raise SystemExit(f"Only {len(j)} surveyed buildings near this coastline; the survey may not overlap the pilot area.")

    with_m = j[j["existing_width_m"] >= args.min_width_m]
    without = j[j["existing_width_m"] == 0]

    def severe_rate(rows):
        return round(float((rows["ds"] >= args.severe_from).mean()), 3) if len(rows) else None

    result = {
        "records": int(len(j)), "near_mangroves": int(len(with_m)), "no_mangroves": int(len(without)),
        "severe_rate_all": severe_rate(j),
        "severe_rate_with_mangroves": severe_rate(with_m),
        "severe_rate_without": severe_rate(without),
        "note": (f"Winston survey buildings within {args.max_coast_m:.0f} m of the coast; "
                 f"severe = DS{args.severe_from}+; mangroves = at least {args.min_width_m:.0f} m wide. "
                 "Wind damage survey: mangroves do not reduce wind, so this is context, not proof of cause."),
        "area": args.segments,
    }
    write_json("validation.json", result)
    print(result)


if __name__ == "__main__":
    main()
