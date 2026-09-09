"""Cubozoan (box jellyfish) lagoon calm-window index.

Mechanism: in the Queensland Irukandji work, dangerous cubozoan influxes
coincide with relaxation of the prevailing south-east trade winds and warm
water. Mauritius sits in the same trade-wind regime, so the hypothesis carried
into the beta is: risk rises with the number of consecutive calm days, with
sea temperature above a seasonal threshold, inside reef lagoons, and after
rain that freshens and warms the lagoon surface. All thresholds are priors.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class CubozoaParams:
    calm_wind_ms: float = 5.0
    max_calm_days: int = 5
    sst_threshold_c: float = 26.0
    bias: float = -2.5
    w_calm: float = 0.8
    w_sst: float = 0.5
    w_rain: float = 0.02
    non_lagoon_factor: float = 0.3

    @classmethod
    def from_dict(cls, d: dict | None) -> "CubozoaParams":
        d = d or {}
        kwargs = {}
        for k, v in d.items():
            if k in cls.__dataclass_fields__:
                kwargs[k] = int(v) if k == "max_calm_days" else float(v)
        return cls(**kwargs)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def cubozoa_index(features: pd.DataFrame, params: CubozoaParams | None = None) -> pd.Series:
    """Return a 0-1 cubozoan presence risk for each daily feature row."""
    p = params or CubozoaParams()
    calm = features["calm_days"].astype(float).clip(upper=p.max_calm_days)
    sst = features["sst_mean"].astype(float)
    rain = features.get("precip_3d", pd.Series(0.0, index=features.index)).astype(float).fillna(0.0)
    lagoon = features.get("lagoon", pd.Series(True, index=features.index)).astype(bool)

    logit = p.bias + p.w_calm * calm + p.w_sst * (sst - p.sst_threshold_c) + p.w_rain * rain
    risk = _sigmoid(logit)
    factor = np.where(lagoon.to_numpy(), 1.0, p.non_lagoon_factor)
    return pd.Series(risk * factor, index=features.index, name="cubozoa_risk")
