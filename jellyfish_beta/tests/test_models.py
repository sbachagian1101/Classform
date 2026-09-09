import numpy as np
import pandas as pd

from jellymru.config import load_params
from jellymru.models.cubozoa import CubozoaParams, cubozoa_index
from jellymru.models.physalia import PhysaliaParams, physalia_index
from jellymru.risk import score_features


def _feats(**cols):
    base = {
        "onshore_stress_24h": 0.0, "onshore_stress_72h": 0.0, "onshore_swell_24h": 0.0,
        "calm_days": 0, "sst_mean": 25.0, "precip_3d": 0.0, "lagoon": True,
    }
    base.update(cols)
    n = max(len(v) if isinstance(v, list) else 1 for v in base.values())
    return pd.DataFrame({k: (v if isinstance(v, list) else [v] * n) for k, v in base.items()})


def test_physalia_monotone_in_onshore_stress():
    f = _feats(onshore_stress_24h=[-36.0, 0.0, 36.0, 100.0], onshore_stress_72h=[-36.0, 0.0, 36.0, 100.0])
    r = physalia_index(f, PhysaliaParams())
    assert r.is_monotonic_increasing
    assert r.iloc[0] < 0.05 and r.iloc[-1] > 0.95
    assert ((r >= 0) & (r <= 1)).all()


def test_physalia_offshore_swell_does_not_reduce_risk():
    base = physalia_index(_feats(onshore_swell_24h=0.0)).iloc[0]
    off = physalia_index(_feats(onshore_swell_24h=-2.0)).iloc[0]
    on = physalia_index(_feats(onshore_swell_24h=1.0)).iloc[0]
    assert np.isclose(base, off)
    assert on > base


def test_cubozoa_rises_with_calm_days_and_warmth_and_is_discounted_offshore():
    p = CubozoaParams()
    calm = cubozoa_index(_feats(calm_days=[0, 1, 3, 5, 9]), p)
    assert calm.is_monotonic_increasing
    assert np.isclose(calm.iloc[3], calm.iloc[4])  # capped at max_calm_days
    warm = cubozoa_index(_feats(sst_mean=[23.0, 26.0, 29.0]), p)
    assert warm.is_monotonic_increasing
    lagoon = cubozoa_index(_feats(calm_days=3, sst_mean=28.0, lagoon=True), p).iloc[0]
    coast = cubozoa_index(_feats(calm_days=3, sst_mean=28.0, lagoon=False), p).iloc[0]
    assert np.isclose(coast, lagoon * p.non_lagoon_factor)


def test_params_from_yaml_roundtrip():
    params = load_params()
    p = PhysaliaParams.from_dict(params["physalia"])
    assert p.bias == params["physalia"]["bias"]
    c = CubozoaParams.from_dict(params["cubozoa"])
    assert c.max_calm_days == params["cubozoa"]["max_calm_days"]


def test_score_features_tiers():
    params = load_params()
    f = _feats(onshore_stress_24h=[-50.0, 35.0, 120.0], onshore_stress_72h=[-50.0, 35.0, 120.0])
    out = score_features(f, params)
    assert list(out["tier"]) == ["low", "moderate", "high"]
    assert (out["risk_score"] >= out[["physalia_risk", "cubozoa_risk"]].max(axis=1) - 1e-12).all()
