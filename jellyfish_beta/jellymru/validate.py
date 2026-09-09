"""Validate risk scores against the local event table with sparse labels.

Design
------
* Unit of analysis is the beach-day.
* label = 1 on a beach-day with a recorded event at that beach.
* score  = max risk over [D - lead_days, D], so a model that warns a day or
           two early is rewarded.
* Beach-days within ``negative_buffer_days`` of an event (before or after) are
  dropped from the negatives, because "no report" near an event is not a
  reliable absence.
* Everything else is a pseudo-absence. Absence of a report is not absence of
  jellyfish, so all metrics are relative, and the honest comparison is against
  a seasonal climatology built the same way.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Callable

import numpy as np
import pandas as pd

EVENT_COLUMNS = [
    "event_id", "date", "date_precision", "beach_id", "lat", "lon",
    "species_group", "species", "count_class", "stings",
    "source_type", "source_url", "confidence", "notes",
]


def load_events(path, species_group: str | None = None, min_confidence: str = "low") -> pd.DataFrame:
    """Load the event CSV, keeping only rows with a usable date."""
    order = {"low": 0, "medium": 1, "high": 2}
    df = pd.read_csv(path, dtype=str).fillna("")
    missing = set(EVENT_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"events file missing columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()]
    df = df[df["date_precision"].str.lower().isin(["day", ""])]
    df["confidence"] = df["confidence"].str.lower().replace("", "low")
    df = df[df["confidence"].map(order).fillna(0) >= order[min_confidence]]
    if species_group:
        df = df[df["species_group"].str.lower() == species_group.lower()]
    return df.reset_index(drop=True)


@dataclass
class ValidationSettings:
    lead_days: int = 2
    alert_budget: float = 0.10
    negative_buffer_days: int = 3

    @classmethod
    def from_dict(cls, d: dict | None) -> "ValidationSettings":
        d = d or {}
        return cls(
            lead_days=int(d.get("lead_days", 2)),
            alert_budget=float(d.get("alert_budget", 0.10)),
            negative_buffer_days=int(d.get("negative_buffer_days", 3)),
        )


def label_beach_days(scored: pd.DataFrame, events: pd.DataFrame, score_col: str,
                     settings: ValidationSettings) -> pd.DataFrame:
    """Return beach-day rows with columns: beach_id, date, label, score, year.

    Rows inside the negative buffer around an event are removed unless they are
    the event day itself.
    """
    df = scored[["beach_id", "date", score_col]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["beach_id", "date"]).reset_index(drop=True)
    window = settings.lead_days + 1
    df["score"] = df.groupby("beach_id")[score_col].transform(lambda s: s.rolling(window, min_periods=1).max())

    ev = events[["beach_id", "date"]].drop_duplicates()
    ev["date"] = pd.to_datetime(ev["date"]).dt.normalize()
    ev["label"] = 1
    df = df.merge(ev, on=["beach_id", "date"], how="left")
    df["label"] = df["label"].fillna(0).astype(int)

    if settings.negative_buffer_days > 0 and len(ev):
        buffer = pd.Timedelta(days=settings.negative_buffer_days)
        keep = np.ones(len(df), dtype=bool)
        for beach, grp in ev.groupby("beach_id"):
            mask_beach = (df["beach_id"] == beach).to_numpy()
            for d in grp["date"]:
                near = mask_beach & (abs(df["date"] - d) <= buffer).to_numpy() & (df["label"].to_numpy() == 0)
                keep &= ~near
        df = df[keep]

    df["year"] = df["date"].dt.year
    return df.reset_index(drop=True)


def metrics(labels, scores, alert_budget: float = 0.10) -> dict:
    """AUC, average precision, and hit rate / false-alarm ratio at a fixed alert budget."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    ok = ~np.isnan(s)
    y, s = y[ok], s[ok]
    out = {"n": int(len(y)), "n_events": int(y.sum()), "event_rate": float(y.mean()) if len(y) else np.nan}
    if y.sum() == 0 or y.sum() == len(y):
        out.update({"roc_auc": np.nan, "avg_precision": np.nan, "hit_rate": np.nan, "false_alarm_ratio": np.nan})
        return out
    out["roc_auc"] = float(roc_auc_score(y, s))
    out["avg_precision"] = float(average_precision_score(y, s))
    thr = np.quantile(s, 1.0 - alert_budget)
    alert = s >= thr
    out["alert_threshold"] = float(thr)
    out["alert_fraction"] = float(alert.mean())
    out["hit_rate"] = float((y[alert] == 1).sum() / y.sum())
    out["false_alarm_ratio"] = float((y[alert] == 0).sum() / max(alert.sum(), 1))
    return out


def climatology_scores(labelled: pd.DataFrame) -> pd.Series:
    """Leave-one-year-out (beach, month) event frequency as a baseline score."""
    df = labelled.copy()
    df["month"] = df["date"].dt.month
    scores = pd.Series(np.nan, index=df.index)
    for year in df["year"].unique():
        train = df[df["year"] != year]
        if train.empty:
            continue
        freq = train.groupby(["beach_id", "month"])["label"].mean()
        test_idx = df.index[df["year"] == year]
        keys = list(zip(df.loc[test_idx, "beach_id"], df.loc[test_idx, "month"]))
        scores.loc[test_idx] = [freq.get(k, 0.0) for k in keys]
    return scores.fillna(0.0)


def evaluate(scored: pd.DataFrame, events: pd.DataFrame, score_col: str,
             settings: ValidationSettings) -> pd.DataFrame:
    """Model vs climatology metrics as a two-row DataFrame."""
    lab = label_beach_days(scored, events, score_col, settings)
    rows = []
    rows.append({"model": score_col, **metrics(lab["label"], lab["score"], settings.alert_budget)})
    if lab["year"].nunique() >= 2:
        clim = climatology_scores(lab)
        rows.append({"model": "climatology", **metrics(lab["label"], clim, settings.alert_budget)})
    return pd.DataFrame(rows)


def leave_one_year_out_grid(
    features: pd.DataFrame,
    events: pd.DataFrame,
    score_fn: Callable[[pd.DataFrame, dict], pd.Series],
    grid: dict[str, list],
    settings: ValidationSettings,
    objective: str = "avg_precision",
) -> pd.DataFrame:
    """Tune a few parameters honestly with leave-one-year-out selection.

    For each held-out year, pick the grid point that maximises ``objective`` on
    the other years, then report that point's score on the held-out year.
    """
    keys = list(grid.keys())
    combos = [dict(zip(keys, vals)) for vals in product(*[grid[k] for k in keys])]
    feats = features.copy()
    feats["date"] = pd.to_datetime(feats["date"])
    years = sorted(feats["date"].dt.year.unique())

    cache = {}
    for i, combo in enumerate(combos):
        s = feats[["beach_id", "date"]].copy()
        s["s"] = score_fn(feats, combo).to_numpy()
        cache[i] = label_beach_days(s, events, "s", settings)

    results = []
    for year in years:
        best_i, best_val = None, -np.inf
        for i in cache:
            train = cache[i][cache[i]["year"] != year]
            m = metrics(train["label"], train["score"], settings.alert_budget)
            val = m.get(objective, np.nan)
            if not np.isnan(val) and val > best_val:
                best_i, best_val = i, val
        if best_i is None:
            continue
        test = cache[best_i][cache[best_i]["year"] == year]
        m = metrics(test["label"], test["score"], settings.alert_budget)
        results.append({"held_out_year": year, **combos[best_i], "train_" + objective: best_val, **m})
    return pd.DataFrame(results)
