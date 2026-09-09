"""Score the next days for every beach and write data/outputs/latest_risk.csv.

    python scripts/run_forecast.py --days 7
    python scripts/run_forecast.py --source synthetic   # offline dry run on the synthetic tail
"""
import argparse
from datetime import datetime, timezone

import pandas as pd

import _common  # noqa: F401
from jellymru.config import DATA_DIR, load_beaches, load_params
from jellymru.features import build_daily_features
from jellymru.risk import score_features

OUT_COLUMNS = [
    "beach_id", "name", "region", "date", "tier", "risk_score", "physalia_risk", "cubozoa_risk",
    "wind_speed_mean", "onshore_wind_mean", "onshore_stress_24h", "onshore_stress_72h",
    "onshore_swell_24h", "calm_days", "sst_mean", "precip_3d",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["openmeteo", "synthetic"], default="openmeteo")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--past-days", type=int, default=7)
    args = ap.parse_args()

    beaches = load_beaches()
    params = load_params()

    if args.source == "openmeteo":
        from jellymru.fetch.openmeteo import fetch_beach_forecast
        hourly = fetch_beach_forecast(beaches, forecast_days=args.days, past_days=args.past_days)
    else:
        hourly = pd.read_csv(DATA_DIR / "raw" / "synthetic_hourly.csv")
        hourly["time"] = pd.to_datetime(hourly["time"], utc=True)
        cutoff = hourly["time"].max() - pd.Timedelta(days=args.days + args.past_days)
        hourly = hourly[hourly["time"] >= cutoff]

    feats = build_daily_features(hourly, beaches, calm_wind_ms=params["cubozoa"]["calm_wind_ms"])
    scored = score_features(feats, params)
    scored["name"] = scored["beach_id"].map(beaches["name"])
    scored["region"] = scored["beach_id"].map(beaches["region"])
    scored["issued_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    out = scored[OUT_COLUMNS + ["issued_utc"]].sort_values(["date", "beach_id"])
    out_path = DATA_DIR / "outputs" / "latest_risk.csv"
    out.to_csv(out_path, index=False)
    print(f"wrote {len(out)} beach-days -> {out_path}")
    print(out[out["date"] == out["date"].max()][["name", "date", "tier", "risk_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
