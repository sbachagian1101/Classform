"""Synthetic hourly environment plus synthetic events for offline dry runs.

The climate is a caricature of Mauritius: south-east trade winds that are
stronger in austral winter, occasional multi-day relaxations, warm summer
sea temperatures, and summer rain. Events are drawn so that they are
correlated with the mechanisms the models encode, which makes the pipeline
testable end to end. It says nothing about real skill.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .geo import onshore_component


def synthetic_hourly(beaches: pd.DataFrame, start: date, end: date, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    times = pd.date_range(start, end + timedelta(days=1), freq="h", inclusive="left", tz="UTC")
    n = len(times)
    doy = times.dayofyear.to_numpy()
    # Austral winter (Jun-Aug) trades stronger. Seasonal cycle peaks near day 200.
    season = np.cos(2 * np.pi * (doy - 200) / 365.25)  # +1 in winter, -1 in summer
    base_speed = 6.5 + 2.0 * season

    # Shared island-scale wind: AR(1) anomalies plus relaxation episodes.
    anom = np.zeros(n)
    for i in range(1, n):
        anom[i] = 0.98 * anom[i - 1] + rng.normal(0, 0.35)
    relax = np.zeros(n)
    for _ in range(int(n / (24 * 25))):  # roughly one relaxation per 25 days
        s = rng.integers(0, n)
        length = rng.integers(36, 120)
        relax[s:s + length] = -4.0
    speed = np.clip(base_speed + anom + relax, 0.3, None)
    direction = (120.0 + 25.0 * np.sin(2 * np.pi * doy / 365.25) + rng.normal(0, 18, n)) % 360.0
    # Occasional northerly/westerly reversals (fronts, cyclone outer bands).
    for _ in range(int(n / (24 * 40))):
        s = rng.integers(0, n)
        length = rng.integers(24, 72)
        direction[s:s + length] = (rng.uniform(250, 360)) % 360.0
        speed[s:s + length] = np.clip(speed[s:s + length] + rng.uniform(1, 5), 0.3, None)

    sst = 26.0 - 2.2 * season + rng.normal(0, 0.15, n).cumsum() * 0.02
    precip = np.where(rng.uniform(size=n) < 0.04 + 0.05 * (season < 0), rng.exponential(2.5, n), 0.0)

    frames = []
    for _, b in beaches.iterrows():
        local_speed = speed * rng.uniform(0.85, 1.15)
        swell_dir = (150.0 + rng.normal(0, 20, n)) % 360.0
        swell_h = np.clip(1.4 + 0.5 * season + rng.normal(0, 0.3, n), 0.2, None)
        cur_dir = (direction + 180.0 + rng.normal(0, 40, n)) % 360.0  # currents roughly downwind
        frames.append(pd.DataFrame({
            "beach_id": b["id"],
            "time": times,
            "wind_speed_ms": local_speed,
            "wind_dir_from_deg": direction,
            "wave_height_m": swell_h + 0.3,
            "wave_dir_from_deg": swell_dir,
            "swell_height_m": swell_h,
            "swell_dir_from_deg": swell_dir,
            "sst_c": sst + (0.6 if bool(b["lagoon"]) else 0.0),
            "current_speed_ms": np.clip(0.05 + 0.02 * local_speed + rng.normal(0, 0.03, n), 0.0, None),
            "current_dir_to_deg": cur_dir,
            "precip_mm": precip,
        }))
    return pd.concat(frames, ignore_index=True)


def synthetic_events(daily_features: pd.DataFrame, seed: int = 7,
                     physalia_rate: float = 0.012, cubozoa_rate: float = 0.010) -> pd.DataFrame:
    """Draw events with probability increasing in the mechanisms, at low base rates."""
    rng = np.random.default_rng(seed)
    df = daily_features
    stress = df["onshore_stress_72h"].fillna(0).clip(lower=0)
    p_phys = physalia_rate * (0.2 + stress / (stress.mean() + 1e-9))
    calm = df["calm_days"].clip(upper=5)
    warm = (df["sst_mean"] - 26.0).clip(lower=0)
    p_cubo = cubozoa_rate * (0.2 + 0.6 * calm + 0.5 * warm) * np.where(df["lagoon"], 1.0, 0.2)

    rows = []
    for i, (_, r) in enumerate(df.iterrows()):
        if rng.uniform() < p_phys.iloc[i]:
            rows.append(("physalia", r))
        elif rng.uniform() < p_cubo.iloc[i]:
            rows.append(("cubozoa", r))
    out = pd.DataFrame([{
        "event_id": f"syn-{k:04d}",
        "date": r["date"].date().isoformat(),
        "date_precision": "day",
        "beach_id": r["beach_id"],
        "lat": "", "lon": "",
        "species_group": grp,
        "species": "",
        "count_class": rng.choice(["few", "many", "mass"]),
        "stings": "",
        "source_type": "synthetic",
        "source_url": "",
        "confidence": "high",
        "notes": "synthetic dry-run event, not a real observation",
    } for k, (grp, r) in enumerate(rows)])
    return out
