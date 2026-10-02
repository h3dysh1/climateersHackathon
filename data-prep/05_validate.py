"""Validate the risk score against the real Winston building damage survey → validation.json.

Data: Paulik et al., "Wind damage dataset for buildings from 2016 tropical cyclone Winston in Fiji",
Zenodo 10.5281/zenodo.14353428 (2016TCWinston_DamageData.csv).

CHECK THE COLUMN NAMES in the CSV first (print them with --show-columns) and pass them in.
Damage states run DS0 (none) to DS3 (complete); "severe" here = DS2 or worse by default.

Method (honest by design):
  1. Match each survey record to the nearest scored building within --max-dist-m.
  2. Shuffle and split 70/30 (fixed seed). Tune weights in common.py using the 70% ONLY.
  3. Report on the 30%: share of severely damaged buildings our model flagged "high"
     (recall), compared with an exposure-only baseline that ignores the roof scan.

Usage:
  python 05_validate.py --damage raw/2016TCWinston_DamageData.csv --show-columns
  python 05_validate.py --damage raw/2016TCWinston_DamageData.csv \
      --lat-col Latitude --lon-col Longitude --damage-col Structure_DS
"""
import argparse
import random
import re

import pandas as pd

from common import band, haversine_km, read_json, write_json


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
    ap.add_argument("--severe-from", type=int, default=2, help="damage state counted as severe (DS2+)")
    ap.add_argument("--max-dist-m", type=float, default=30)
    ap.add_argument("--test-share", type=float, default=0.3)
    args = ap.parse_args()

    df = pd.read_csv(args.damage)
    if args.show_columns or not (args.lat_col and args.lon_col and args.damage_col):
        print("Columns:", list(df.columns))
        print(df.head(3).to_string())
        return

    risk = {b["id"]: b for b in read_json("risk.json")["buildings"]}
    fc = read_json("buildings.geojson")
    pts = [(f["properties"]["id"], f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]) for f in fc["features"]]

    matched = []
    for _, r in df.iterrows():
        ds = ds_number(r[args.damage_col])
        if ds is None or pd.isna(r[args.lat_col]):
            continue
        lat, lon = float(r[args.lat_col]), float(r[args.lon_col])
        best = min(pts, key=lambda p: haversine_km(lat, lon, p[1], p[2]))
        if haversine_km(lat, lon, best[1], best[2]) * 1000 <= args.max_dist_m:
            matched.append({"id": best[0], "ds": ds, **{k: risk[best[0]][k] for k in ("exposure", "risk", "band")}})

    if len(matched) < 10:
        raise SystemExit(f"Only {len(matched)} matches — check the pilot area overlaps the survey, or raise --max-dist-m.")

    random.Random(42).shuffle(matched)
    cut = int(len(matched) * (1 - args.test_share))
    test = matched[cut:]
    severe = [m for m in test if m["ds"] >= args.severe_from]
    flagged = [m for m in test if m["band"] == "high"]

    def recall(rows, pred):
        return round(sum(pred(m) for m in rows) / len(rows), 3) if rows else None

    result = {
        "n_matched": len(matched),
        "n_test": len(test),
        "severe_damage_test": len(severe),
        "model_recall_severe": recall(severe, lambda m: m["band"] == "high"),
        # Baseline: same exposure, no roof scan (vulnerability fixed at 0.6 = "unknown").
        "baseline_recall_severe": recall(severe, lambda m: band(m["exposure"] * 0.6) == "high"),
        "model_precision_high": recall(flagged, lambda m: m["ds"] >= args.severe_from),
        "note": f"Held-out {int(args.test_share * 100)}% of matched survey records; severe = DS{args.severe_from}+.",
    }
    write_json("validation.json", result)
    print(result)


if __name__ == "__main__":
    main()
