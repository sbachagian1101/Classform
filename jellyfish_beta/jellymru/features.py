"""Turn tidy hourly environmental rows into a daily per-beach feature table.

Expected hourly columns (missing ones are tolerated and become NaN features):
    beach_id, time (UTC, hourly),
    wind_speed_ms, wind_dir_from_deg,
    wave_height_m, wave_dir_from_deg,
    swell_height_m, swell_dir_from_deg,
    sst_c,
    current_speed_ms, current_dir_to_deg,
    precip_mm
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .geo import onshore_component, signed_square

HOURLY_COLUMNS = [
    "beach_id", "time",
    "wind_speed_ms", "wind_dir_from_deg",
    "wave_height_m", "wave_dir_from_deg",
    "swell_height_m", "swell_dir_from_deg",
    "sst_c",
    "current_speed_ms", "current_dir_to_deg",
    "precip_mm",
]


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in HOURLY_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    out["time"] = pd.to_datetime(out["time"], utc=True)
    return out


def add_hourly_projections(hourly: pd.DataFrame, beaches: pd.DataFrame) -> pd.DataFrame:
    """Add onshore projections of wind, swell, waves and current per row."""
    df = _ensure_columns(hourly)
    facing = df["beach_id"].map(beaches["facing_deg"])
    if facing.isna().any():
        unknown = sorted(df.loc[facing.isna(), "beach_id"].unique())
        raise KeyError(f"hourly rows reference unknown beach ids: {unknown}")
    facing = facing.to_numpy(dtype=float)

    df["onshore_wind_ms"] = onshore_component(df["wind_speed_ms"], df["wind_dir_from_deg"], facing)
    df["onshore_stress"] = signed_square(df["onshore_wind_ms"])
    df["onshore_swell_m"] = onshore_component(df["swell_height_m"], df["swell_dir_from_deg"], facing)
    df["onshore_wave_m"] = onshore_component(df["wave_height_m"], df["wave_dir_from_deg"], facing)
    df["onshore_current_ms"] = onshore_component(
        df["current_speed_ms"], df["current_dir_to_deg"], facing, convention="to"
    )
    return df


def daily_aggregate(hourly_proj: pd.DataFrame) -> pd.DataFrame:
    """Collapse projected hourly rows to one row per beach per UTC day."""
    df = hourly_proj.copy()
    df["date"] = df["time"].dt.floor("D").dt.tz_localize(None)
    agg = {
        "wind_speed_ms": "mean",
        "onshore_wind_ms": "mean",
        "onshore_stress": "mean",
        "onshore_swell_m": "mean",
        "onshore_wave_m": "mean",
        "onshore_current_ms": "mean",
        "sst_c": "mean",
        "precip_mm": "sum",
    }
    daily = df.groupby(["beach_id", "date"]).agg(agg).reset_index()
    daily = daily.rename(columns={
        "wind_speed_ms": "wind_speed_mean",
        "onshore_wind_ms": "onshore_wind_mean",
        "onshore_stress": "onshore_stress_24h",
        "onshore_swell_m": "onshore_swell_24h",
        "onshore_wave_m": "onshore_wave_24h",
        "onshore_current_ms": "onshore_current_24h",
        "sst_c": "sst_mean",
        "precip_mm": "precip_24h",
    })
    return daily.sort_values(["beach_id", "date"]).reset_index(drop=True)


def consecutive_below(values, threshold: float) -> np.ndarray:
    """Count of consecutive trailing values strictly below threshold, per position.

    NaN breaks the run.
    """
    v = np.asarray(values, dtype=float)
    out = np.zeros(len(v), dtype=int)
    run = 0
    for i, x in enumerate(v):
        if np.isnan(x) or x >= threshold:
            run = 0
        else:
            run += 1
        out[i] = run
    return out


def add_rolling_features(daily: pd.DataFrame, calm_wind_ms: float = 5.0) -> pd.DataFrame:
    """Add multi-day windows, calm-day runs and a crude SST anomaly.

    Rolling windows are computed per beach on the daily table, so a gap in the
    data simply shortens the window (min_periods=1).
    """
    df = daily.sort_values(["beach_id", "date"]).copy()
    g = df.groupby("beach_id", group_keys=False)

    df["onshore_stress_48h"] = g["onshore_stress_24h"].transform(lambda s: s.rolling(2, min_periods=1).mean())
    df["onshore_stress_72h"] = g["onshore_stress_24h"].transform(lambda s: s.rolling(3, min_periods=1).mean())
    df["onshore_swell_48h"] = g["onshore_swell_24h"].transform(lambda s: s.rolling(2, min_periods=1).mean())
    df["precip_3d"] = g["precip_24h"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    df["calm_days"] = g["wind_speed_mean"].transform(lambda s: pd.Series(consecutive_below(s.to_numpy(), calm_wind_ms), index=s.index))

    df["month"] = df["date"].dt.month
    # Month-of-year climatology per beach; with a single year this is ~0 by construction.
    clim = df.groupby(["beach_id", "month"])["sst_mean"].transform("mean")
    df["sst_anom"] = df["sst_mean"] - clim
    return df.reset_index(drop=True)


def build_daily_features(hourly: pd.DataFrame, beaches: pd.DataFrame, calm_wind_ms: float = 5.0) -> pd.DataFrame:
    """Full pipeline: hourly rows -> projected -> daily -> rolling features."""
    proj = add_hourly_projections(hourly, beaches)
    daily = daily_aggregate(proj)
    feats = add_rolling_features(daily, calm_wind_ms=calm_wind_ms)
    feats["lagoon"] = feats["beach_id"].map(beaches["lagoon"]).astype(bool)
    return feats
