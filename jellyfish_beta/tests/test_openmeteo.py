"""Offline tests of the Open-Meteo client's error handling using a fake session."""
from datetime import date

import pandas as pd
import pytest

from jellymru.fetch import openmeteo as om


class FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.url = "https://fake"

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Returns canned responses in order; records the requests it received."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params))
        return self.responses.pop(0)


def _ok_hourly(vars_):
    times = ["2024-01-01T00:00", "2024-01-01T01:00"]
    return {"hourly": {"time": times, **{v: [1.0, 2.0] for v in vars_}}}


def test_get_does_not_retry_400(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    sess = FakeSession([FakeResp(400, {"reason": "Cannot initialize variable"})])
    with pytest.raises(om.OpenMeteoError) as exc:
        om._get("https://x", {}, session=sess, retries=3)
    assert exc.value.status == 400 and "Cannot initialize" in str(exc.value)
    assert len(sess.calls) == 1


def test_get_retries_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    sess = FakeSession([FakeResp(503, None, "unavailable"), FakeResp(200, {"hourly": {"time": []}})])
    out = om._get("https://x", {}, session=sess, retries=3)
    assert out == {"hourly": {"time": []}} and len(sess.calls) == 2


def test_get_429_without_window_is_minutely(monkeypatch):
    sess = FakeSession([FakeResp(429, None, "rate limited")])
    with pytest.raises(om.RateLimited) as exc:
        om._get("https://x", {}, session=sess, retries=3)
    assert exc.value.window == "minute" and len(sess.calls) == 1


def test_marine_falls_back_to_waves_then_empty(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    sess = FakeSession([FakeResp(400, {"reason": "bad var"}), FakeResp(200, _ok_hourly(om.MARINE_WAVE_VARS))])
    with pytest.warns(UserWarning):
        df = om.fetch_marine(-20.0, 57.5, start=date(2024, 1, 1), end=date(2024, 1, 2), session=sess)
    assert sess.calls[1][1]["hourly"] == ",".join(om.MARINE_WAVE_VARS)
    assert list(df["wave_height_m"]) == [1.0, 2.0] and "sst_c" not in df.columns

    sess = FakeSession([FakeResp(400, {"reason": "bad"}), FakeResp(400, {"reason": "bad again"})])
    with pytest.warns(UserWarning):
        df = om.fetch_marine(-20.0, 57.5, start=date(2024, 1, 1), end=date(2024, 1, 2), session=sess)
    assert df.empty and "wave_height_m" in df.columns


def test_history_chunks_by_year_and_skips_failed_beach(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    beaches = pd.DataFrame([
        {"id": "a", "name": "A", "lat": -20.0, "lon": 57.5},
        {"id": "b", "name": "B", "lat": -20.1, "lon": 57.6},
    ])
    # beach a: 2 years x (weather ok, marine ok); beach b: weather 400 for both years
    responses = []
    for _ in range(2):
        responses += [FakeResp(200, _ok_hourly(om.WEATHER_VARS)), FakeResp(200, _ok_hourly(om.MARINE_VARS))]
    responses += [FakeResp(400, {"reason": "nope"}), FakeResp(400, {"reason": "nope"})]
    sess = FakeSession(responses)
    with pytest.warns(UserWarning):
        df = om.fetch_beach_history(beaches, date(2023, 6, 1), date(2024, 3, 1), session=sess, progress=None)
    assert set(df["beach_id"]) == {"a"}
    assert len(df) == 4  # 2 rows per year chunk
    # first chunk ends on 31 Dec 2023, second starts on 1 Jan 2024
    assert sess.calls[0][1]["end_date"] == "2023-12-31" and sess.calls[2][1]["start_date"] == "2024-01-01"


def test_history_raises_when_nothing_fetched(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    beaches = pd.DataFrame([{"id": "a", "name": "A", "lat": -20.0, "lon": 57.5}])
    sess = FakeSession([FakeResp(400, {"reason": "nope"})])
    with pytest.raises(om.OpenMeteoError), pytest.warns(UserWarning):
        om.fetch_beach_history(beaches, date(2024, 1, 1), date(2024, 1, 2), session=sess, progress=None)


def test_429_raises_rate_limited_with_window():
    sess = FakeSession([FakeResp(429, {"reason": "Hourly API request limit exceeded. Please try again in the next hour."})])
    with pytest.raises(om.RateLimited) as exc:
        om._get("https://x", {}, session=sess, retries=3)
    assert exc.value.window == "hour" and len(sess.calls) == 1
    sess = FakeSession([FakeResp(429, {"reason": "Daily API request limit exceeded"})])
    with pytest.raises(om.RateLimited) as exc:
        om._get("https://x", {}, session=sess)
    assert exc.value.window == "day"


def test_seconds_until_next_hour():
    # 10:15:00 -> 45 min to 11:00 plus margin
    assert om.seconds_until_next_hour(now=10 * 3600 + 15 * 60, margin_s=45) == 45 * 60 + 45


def test_history_waits_out_hourly_quota_and_resumes(monkeypatch):
    sleeps = []
    monkeypatch.setattr(om.time, "sleep", lambda s: sleeps.append(s))
    beaches = pd.DataFrame([{"id": "a", "name": "A", "lat": -20.0, "lon": 57.5}])
    hourly = {"reason": "Hourly API request limit exceeded"}
    sess = FakeSession([FakeResp(429, hourly), FakeResp(200, _ok_hourly(om.WEATHER_VARS)), FakeResp(200, _ok_hourly(om.MARINE_VARS))])
    df = om.fetch_beach_history(beaches, date(2024, 1, 1), date(2024, 12, 31), session=sess, progress=None)
    assert len(df) == 2 and any(s > 60 for s in sleeps)


def test_history_daily_quota_raises(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    beaches = pd.DataFrame([{"id": "a", "name": "A", "lat": -20.0, "lon": 57.5}])
    sess = FakeSession([FakeResp(429, {"reason": "Daily API request limit exceeded"})])
    with pytest.raises(om.RateLimited):
        om.fetch_beach_history(beaches, date(2024, 1, 1), date(2024, 12, 31), session=sess, progress=None)


def test_history_skips_marine_before_archive_start_and_uses_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    beaches = pd.DataFrame([{"id": "a", "name": "A", "lat": -20.0, "lon": 57.5}])
    # 2019: weather only (no marine call). 2021: weather + marine.
    sess = FakeSession([FakeResp(200, _ok_hourly(om.WEATHER_VARS)),
                        FakeResp(200, _ok_hourly(om.WEATHER_VARS)), FakeResp(200, _ok_hourly(om.MARINE_VARS))])
    df = om.fetch_beach_history(beaches, date(2019, 1, 1), date(2019, 12, 31), session=sess, progress=None, cache_dir=tmp_path)
    assert len(sess.calls) == 1 and (tmp_path / "a_2019.csv").exists()
    df = om.fetch_beach_history(beaches, date(2021, 1, 1), date(2021, 12, 31), session=sess, progress=None, cache_dir=tmp_path)
    assert len(sess.calls) == 3 and sess.calls[2][0] == om.MARINE_URL
    # Second run of the cached years: no network at all.
    sess2 = FakeSession([])
    d19 = om.fetch_beach_history(beaches, date(2019, 1, 1), date(2019, 12, 31), session=sess2, progress=None, cache_dir=tmp_path)
    d21 = om.fetch_beach_history(beaches, date(2021, 1, 1), date(2021, 12, 31), session=sess2, progress=None, cache_dir=tmp_path)
    assert sess2.calls == [] and len(d19) == 2 and len(d21) == 2 and "wave_height_m" in d21.columns
