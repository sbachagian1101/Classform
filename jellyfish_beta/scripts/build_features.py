"""Build the daily per-beach feature table.

    python scripts/build_features.py --source openmeteo --start 2022-01-01 --end 2024-12-31
    python scripts/build_features.py --source synthetic
    python scripts/build_features.py --source csv --hourly data/raw/my_hourly.csv
"""
import argparse
from datetime import date

import pandas as pd

import _common  # noqa: F401
from jellymru.config import DATA_DIR, load_beaches, load_params
from jellymru.features import build_daily_features


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["openmeteo", "synthetic", "csv"], default="synthetic")
    ap.add_argument("--start", type=date.fromisoformat, default=date(2022, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date.today())
    ap.add_argument("--hourly", type=str, default=None, help="hourly CSV path for --source csv")
    ap.add_argument("--out", type=str, default=str(DATA_DIR / "features" / "daily_features.csv"))
    args = ap.parse_args()

    beaches = load_beaches()
    params = load_params()

    if args.source == "openmeteo":
        from jellymru.fetch.openmeteo import fetch_beach_history
        hourly = fetch_beach_history(beaches, args.start, args.end)
        hourly.to_csv(DATA_DIR / "raw" / "openmeteo_hourly.csv", index=False)
    elif args.source == "synthetic":
        hourly = pd.read_csv(DATA_DIR / "raw" / "synthetic_hourly.csv")
    else:
        if not args.hourly:
            ap.error("--hourly is required with --source csv")
        hourly = pd.read_csv(args.hourly)

    feats = build_daily_features(hourly, beaches, calm_wind_ms=params["cubozoa"]["calm_wind_ms"])
    feats.to_csv(args.out, index=False)
    print(f"wrote {len(feats):,} beach-days for {feats['beach_id'].nunique()} beaches -> {args.out}")


if __name__ == "__main__":
    main()
