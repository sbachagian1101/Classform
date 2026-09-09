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


def test_get_retries_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    sess = FakeSession([FakeResp(429, None, "rate limited"), FakeResp(200, {"hourly": {"time": []}})])
    out = om._get("https://x", {}, session=sess, retries=3)
    assert out == {"hourly": {"time": []}} and len(sess.calls) == 2


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
