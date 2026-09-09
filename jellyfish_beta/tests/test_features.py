import numpy as np
import pandas as pd

from jellymru.config import load_beaches, load_params
from jellymru.features import build_daily_features, consecutive_below


def _hourly(beach_id, days, speed, direction, sst=27.0):
    times = pd.date_range("2024-01-01", periods=24 * days, freq="h", tz="UTC")
    return pd.DataFrame({
        "beach_id": beach_id, "time": times,
        "wind_speed_ms": speed, "wind_dir_from_deg": direction,
        "swell_height_m": 1.0, "swell_dir_from_deg": direction,
        "sst_c": sst, "precip_mm": 0.0,
    })


def test_consecutive_below_resets_on_nan_and_threshold():
    out = consecutive_below([1, 2, 6, 1, np.nan, 1, 1], threshold=5)
    assert out.tolist() == [1, 2, 0, 1, 0, 1, 2]


def test_daily_feature_pipeline_shapes_and_projection():
    beaches = load_beaches()
    # belle_mare faces 90; wind from 90 is fully onshore.
    hourly = _hourly("belle_mare", days=4, speed=6.0, direction=90.0)
    feats = build_daily_features(hourly, beaches)
    assert len(feats) == 4
    assert set(["onshore_stress_24h", "onshore_stress_72h", "calm_days", "sst_anom", "lagoon"]) <= set(feats.columns)
    assert np.allclose(feats["onshore_wind_mean"], 6.0)
    assert np.allclose(feats["onshore_stress_24h"], 36.0)
    assert np.allclose(feats["onshore_swell_24h"], 1.0)
    assert feats["lagoon"].all()


def test_calm_days_and_offshore_sign():
    beaches = load_beaches()
    # flic_en_flac faces 275; SE trades (120) are offshore there, and 3 m/s is calm.
    hourly = _hourly("flic_en_flac", days=3, speed=3.0, direction=120.0)
    feats = build_daily_features(hourly, beaches, calm_wind_ms=load_params()["cubozoa"]["calm_wind_ms"])
    assert feats["calm_days"].tolist() == [1, 2, 3]
    assert (feats["onshore_wind_mean"] < 0).all()


def test_unknown_beach_raises():
    beaches = load_beaches()
    hourly = _hourly("atlantis", days=1, speed=5.0, direction=90.0)
    try:
        build_daily_features(hourly, beaches)
    except KeyError as exc:
        assert "atlantis" in str(exc)
    else:
        raise AssertionError("expected KeyError for unknown beach")


def test_beaches_config_is_sane():
    beaches = load_beaches()
    assert beaches["lat"].between(-20.6, -19.9).all()
    assert beaches["lon"].between(57.2, 57.9).all()
    assert beaches["facing_deg"].between(0, 360).all()
