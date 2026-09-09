"""Score a feature table and validate against an event table.

    python scripts/validate.py --features data/features/daily_features.csv \
        --events data/events/mru_events.csv
    python scripts/validate.py --events data/events/synthetic_events.csv --tune

Prints model-vs-climatology metrics per hazard and, with --tune, a
leave-one-year-out grid search over a few Physalia weights.
"""
import argparse

import pandas as pd

import _common  # noqa: F401
from jellymru.config import DATA_DIR, load_params
from jellymru.models.physalia import PhysaliaParams, physalia_index
from jellymru.risk import score_features
from jellymru.validate import ValidationSettings, evaluate, leave_one_year_out_grid, load_events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default=str(DATA_DIR / "features" / "daily_features.csv"))
    ap.add_argument("--events", default=str(DATA_DIR / "events" / "mru_events.csv"))
    ap.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low")
    ap.add_argument("--tune", action="store_true")
    args = ap.parse_args()

    params = load_params()
    settings = ValidationSettings.from_dict(params.get("validation"))
    feats = pd.read_csv(args.features, parse_dates=["date"])
    scored = score_features(feats, params)

    tables = []
    for group, col in [("physalia", "physalia_risk"), ("cubozoa", "cubozoa_risk"), (None, "risk_score")]:
        events = load_events(args.events, species_group=group, min_confidence=args.min_confidence)
        if events.empty:
            print(f"[{group or 'all'}] no dated events, skipping")
            continue
        res = evaluate(scored, events, col, settings)
        res.insert(0, "events", group or "all")
        tables.append(res)
    if tables:
        report = pd.concat(tables, ignore_index=True)
        pd.set_option("display.width", 200)
        print(report.round(3).to_string(index=False))
        report.to_csv(DATA_DIR / "outputs" / "validation.csv", index=False)

    if args.tune:
        events = load_events(args.events, species_group="physalia", min_confidence=args.min_confidence)
        if events.empty:
            print("no physalia events to tune on")
            return
        base = PhysaliaParams.from_dict(params.get("physalia"))

        def score_fn(f, combo):
            p = PhysaliaParams(bias=base.bias, **combo)
            return physalia_index(f, p)

        grid = {
            "w_stress_24h": [0.02, 0.05, 0.10],
            "w_stress_72h": [0.0, 0.03, 0.06],
            "w_swell_24h": [0.0, 0.8, 1.6],
        }
        res = leave_one_year_out_grid(feats, events, score_fn, grid, settings)
        print("\nleave-one-year-out tuning (physalia):")
        print(res.round(3).to_string(index=False))
        res.to_csv(DATA_DIR / "outputs" / "tuning_physalia.csv", index=False)


if __name__ == "__main__":
    main()
