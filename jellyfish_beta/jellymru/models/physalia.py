"""Physalia (bluebottle / Portuguese man o' war) stranding index.

Mechanism: Physalia are passive surface drifters pushed by wind, waves and
surface currents. Strandings on a beach follow sustained onshore wind stress
over the previous one to three days, reinforced by onshore swell. This is the
driver reported for Sydney beaches (BluebottleWatch, UNSW / SLSA) and for
Reunion's west coast, and it is pure physics, so it transfers to Mauritius
with only the weights needing local tuning.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PhysaliaParams:
    bias: float = -3.0
    w_stress_24h: float = 0.05
    w_stress_72h: float = 0.03
    w_swell_24h: float = 0.8

    @classmethod
    def from_dict(cls, d: dict | None) -> "PhysaliaParams":
        d = d or {}
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__dataclass_fields__})


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=float)))


def physalia_index(features: pd.DataFrame, params: PhysaliaParams | None = None) -> pd.Series:
    """Return a 0-1 stranding risk for each daily feature row.

    Missing swell is treated as zero contribution; missing wind stress gives NaN.
    """
    p = params or PhysaliaParams()
    s24 = features["onshore_stress_24h"].astype(float)
    s72 = features["onshore_stress_72h"].astype(float) if "onshore_stress_72h" in features else s24
    swell = features.get("onshore_swell_24h", pd.Series(0.0, index=features.index)).astype(float).fillna(0.0)
    logit = p.bias + p.w_stress_24h * s24 + p.w_stress_72h * s72 + p.w_swell_24h * swell.clip(lower=0.0)
    return pd.Series(_sigmoid(logit), index=features.index, name="physalia_risk")
