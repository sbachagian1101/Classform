import numpy as np
import pandas as pd

from jellymru.validate import (ValidationSettings, climatology_scores, evaluate,
                               label_beach_days, leave_one_year_out_grid, metrics)


def _scored(days=400, beaches=("a", "b"), seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for b in beaches:
        dates = pd.date_range("2023-01-01", periods=days, freq="D")
        rows.append(pd.DataFrame({"beach_id": b, "date": dates, "s": rng.uniform(size=days)}))
    return pd.concat(rows, ignore_index=True)


def _events(rows):
    return pd.DataFrame(rows, columns=["beach_id", "date"])


def test_label_uses_lead_window_max_and_buffers_negatives():
    scored = _scored(days=10, beaches=("a",))
    scored["s"] = [0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    ev = _events([("a", "2023-01-04")])
    settings = ValidationSettings(lead_days=2, alert_budget=0.5, negative_buffer_days=1)
    lab = label_beach_days(scored, ev, "s", settings)
    # event day is 2023-01-04; window [Jan 2, Jan 4] max = 0.9
    row = lab[lab["date"] == "2023-01-04"].iloc[0]
    assert row["label"] == 1 and np.isclose(row["score"], 0.9)
    # Jan 3 and Jan 5 are inside the 1-day buffer and dropped
    assert not (lab["date"].isin(pd.to_datetime(["2023-01-03", "2023-01-05"]))).any()
    assert lab["label"].sum() == 1
    assert len(lab) == 10 - 2


def test_metrics_reward_a_skilful_score():
    y = np.array([0] * 90 + [1] * 10)
    good = np.concatenate([np.random.default_rng(1).uniform(0, 0.5, 90), np.linspace(0.6, 1.0, 10)])
    m = metrics(y, good, alert_budget=0.10)
    assert m["roc_auc"] > 0.99 and m["hit_rate"] == 1.0 and m["n_events"] == 10
    bad = metrics(y, np.zeros(100), alert_budget=0.10)
    assert np.isclose(bad["roc_auc"], 0.5)


def test_metrics_degenerate_labels_are_nan():
    m = metrics([0, 0, 0], [0.1, 0.2, 0.3])
    assert np.isnan(m["roc_auc"]) and m["n_events"] == 0


def test_evaluate_includes_climatology_with_two_years():
    scored = _scored(days=730)
    # Make score skilful: events happen where s is high.
    top = scored.sort_values("s", ascending=False).head(12)
    ev = _events(list(zip(top["beach_id"], top["date"].dt.strftime("%Y-%m-%d"))))
    res = evaluate(scored, ev, "s", ValidationSettings(lead_days=1, alert_budget=0.1, negative_buffer_days=0))
    assert set(res["model"]) == {"s", "climatology"}
    assert res.loc[res["model"] == "s", "roc_auc"].iloc[0] > 0.95


def test_climatology_is_leave_one_year_out():
    lab = pd.DataFrame({
        "beach_id": ["a"] * 4, "date": pd.to_datetime(["2023-01-05", "2023-01-20", "2024-01-05", "2024-06-01"]),
        "label": [1, 1, 0, 0], "score": [0, 0, 0, 0], "year": [2023, 2023, 2024, 2024],
    })
    clim = climatology_scores(lab)
    # 2024 January rows are scored from 2023 January frequency (=1.0); 2024 June has no history -> 0.
    assert np.isclose(clim.iloc[2], 1.0) and np.isclose(clim.iloc[3], 0.0)
    # 2023 rows are scored from 2024 (frequency 0).
    assert np.isclose(clim.iloc[0], 0.0)


def test_grid_search_returns_one_row_per_year():
    scored = _scored(days=730)
    feats = scored.rename(columns={"s": "x"})
    top = feats.sort_values("x", ascending=False).head(10)
    ev = _events(list(zip(top["beach_id"], top["date"].dt.strftime("%Y-%m-%d"))))

    def score_fn(f, combo):
        return combo["w"] * f["x"]

    res = leave_one_year_out_grid(feats, ev, score_fn, {"w": [1.0, -1.0]}, ValidationSettings(1, 0.1, 0))
    assert len(res) == 2
    assert (res["w"] == 1.0).all()
