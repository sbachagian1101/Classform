"""Generate a synthetic hourly dataset and event table for an offline dry run.

    python scripts/make_synthetic.py --start 2023-01-01 --end 2024-12-31
"""
import argparse
from datetime import date

import _common  # noqa: F401
from jellymru.config import DATA_DIR, load_beaches, load_params
from jellymru.features import build_daily_features
from jellymru.synthetic import synthetic_events, synthetic_hourly


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=date.fromisoformat, default=date(2023, 1, 1))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2024, 12, 31))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    beaches = load_beaches()
    params = load_params()
    hourly = synthetic_hourly(beaches, args.start, args.end, seed=args.seed)
    raw_path = DATA_DIR / "raw" / "synthetic_hourly.csv"
    hourly.to_csv(raw_path, index=False)

    feats = build_daily_features(hourly, beaches, calm_wind_ms=params["cubozoa"]["calm_wind_ms"])
    events = synthetic_events(feats, seed=args.seed)
    ev_path = DATA_DIR / "events" / "synthetic_events.csv"
    events.to_csv(ev_path, index=False)
    print(f"wrote {len(hourly):,} hourly rows -> {raw_path}")
    print(f"wrote {len(events):,} synthetic events -> {ev_path}")


if __name__ == "__main__":
    main()
