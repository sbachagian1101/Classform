"""Combine hazard components into a per-beach, per-day risk score and tier."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .models.cubozoa import CubozoaParams, cubozoa_index
from .models.physalia import PhysaliaParams, physalia_index

TIER_LABELS = ["low", "moderate", "high"]


def score_features(features: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Add physalia_risk, cubozoa_risk, risk_score and tier columns."""
    out = features.copy()
    p_phys = PhysaliaParams.from_dict(params.get("physalia"))
    p_cubo = CubozoaParams.from_dict(params.get("cubozoa"))
    out["physalia_risk"] = physalia_index(out, p_phys)
    out["cubozoa_risk"] = cubozoa_index(out, p_cubo)

    weights = (params.get("combine") or {}).get("weights") or {}
    w_p = float(weights.get("physalia", 1.0))
    w_c = float(weights.get("cubozoa", 1.0))
    out["risk_score"] = np.fmax(w_p * out["physalia_risk"], w_c * out["cubozoa_risk"])
    out["tier"] = assign_tiers(out["risk_score"], params)
    return out


def assign_tiers(score: pd.Series, params: dict) -> pd.Series:
    tiers = (params.get("combine") or {}).get("tiers") or {}
    moderate = float(tiers.get("moderate", 0.35))
    high = float(tiers.get("high", 0.60))
    if not moderate < high:
        raise ValueError("tiers.moderate must be below tiers.high")
    bins = [-np.inf, moderate, high, np.inf]
    return pd.cut(score, bins=bins, labels=TIER_LABELS, right=False).astype(str)
