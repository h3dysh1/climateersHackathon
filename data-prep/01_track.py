"""Extract Cyclone Winston (2016) from an IBTrACS CSV → track.json.

Download the South Pacific file first (v04r01 at time of writing):
  https://www.ncei.noaa.gov/products/international-best-track-archive
  → CSV → ibtracs.SP.list.v04r01.csv

Usage:
  python 01_track.py --ibtracs raw/ibtracs.SP.list.v04r01.csv
"""
import argparse

import pandas as pd

from common import write_json


def saffir_simpson_like(kt):
    """Rough category from 1-min wind (kt). Fiji uses the Australian scale; label as approximate."""
    if pd.isna(kt):
        return None
    for cat, lo in ((5, 137), (4, 113), (3, 96), (2, 83), (1, 64)):
        if kt >= lo:
            return cat
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ibtracs", required=True)
    ap.add_argument("--name", default="WINSTON")
    ap.add_argument("--season", type=int, default=2016)
    args = ap.parse_args()

    # Row 2 of IBTrACS CSVs holds units; skip it.
    df = pd.read_csv(args.ibtracs, skiprows=[1], low_memory=False, keep_default_na=False, na_values=[" ", ""])
    df = df[(df["NAME"] == args.name) & (df["SEASON"].astype(int) == args.season)]
    if df.empty:
        raise SystemExit(f"No rows for {args.name} {args.season}; check the file and spelling.")

    wind_col = "USA_WIND" if "USA_WIND" in df.columns else "WMO_WIND"
    df[wind_col] = pd.to_numeric(df[wind_col], errors="coerce")
    df["LAT"] = pd.to_numeric(df["LAT"])
    df["LON"] = pd.to_numeric(df["LON"])
    # Keep 6-hourly synoptic points to stay small.
    df["ISO_TIME"] = pd.to_datetime(df["ISO_TIME"])
    df = df[df["ISO_TIME"].dt.hour.isin([0, 6, 12, 18])]

    track = []
    for _, r in df.iterrows():
        # Keep 0-360: Winston crossed the 180° line twice (Vanuatu → Tonga → Fiji). Converting to
        # -180..180 makes the drawn track jump across the whole map. Leaflet/MapLibre accept lon > 180.
        lon = r["LON"] % 360
        kt = r[wind_col]
        track.append({
            "time": r["ISO_TIME"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": round(float(r["LAT"]), 3),
            "lon": round(float(lon), 3),
            "wind_kt": None if pd.isna(kt) else int(kt),
            "category": saffir_simpson_like(kt),
        })
    write_json("track.json", track)
    print(f"{len(track)} track points, wind column: {wind_col}")


if __name__ == "__main__":
    main()
