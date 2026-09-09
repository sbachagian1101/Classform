"""Open-Meteo fetchers: keyless JSON access to ERA5-based weather history,
wave / SST / current products, and forecasts. Good enough to build and
validate the beta; switch to the primary sources (ERA5 via CDS, CMEMS) for
the operational system.

Endpoints
---------
weather history : https://archive-api.open-meteo.com/v1/archive
weather forecast: https://api.open-meteo.com/v1/forecast
marine (history and forecast): https://marine-api.open-meteo.com/v1/marine

All functions return tidy hourly rows in the schema used by
``jellymru.features`` (see HOURLY_COLUMNS).
"""
from __future__ import annotations

import time
import warnings
from datetime import date

import pandas as pd

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

WEATHER_VARS = ["wind_speed_10m", "wind_direction_10m", "precipitation"]
MARINE_VARS = [
    "wave_height", "wave_direction",
    "swell_wave_height", "swell_wave_direction",
    "sea_surface_temperature",
    "ocean_current_velocity", "ocean_current_direction",
]
# Fallback when the archive rejects SST or currents for a period: waves only.
MARINE_WAVE_VARS = ["wave_height", "wave_direction", "swell_wave_height", "swell_wave_direction"]

WEATHER_RENAME = {
    "wind_speed_10m": "wind_speed_ms",
    "wind_direction_10m": "wind_dir_from_deg",
    "precipitation": "precip_mm",
}
MARINE_RENAME = {
    "wave_height": "wave_height_m",
    "wave_direction": "wave_dir_from_deg",
    "swell_wave_height": "swell_height_m",
    "swell_wave_direction": "swell_dir_from_deg",
    "sea_surface_temperature": "sst_c",
    "ocean_current_velocity": "current_speed_ms",
    "ocean_current_direction": "current_dir_to_deg",
}


class OpenMeteoError(RuntimeError):
    """HTTP or API error from Open-Meteo, carrying the status and the API's reason text."""

    def __init__(self, status: int, reason: str, url: str = ""):
        super().__init__(f"Open-Meteo {status}: {reason} ({url})")
        self.status = status
        self.reason = reason


_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _get(url: str, params: dict, session=None, retries: int = 4, backoff_s: float = 2.0) -> dict:
    import requests

    sess = session or requests.Session()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = sess.get(url, params=params, timeout=60)
        except requests.RequestException as exc:  # network trouble: retry
            last = exc
            time.sleep(backoff_s * (2 ** attempt))
            continue
        if resp.status_code == 200:
            return resp.json()
        try:
            reason = resp.json().get("reason", "") or resp.text[:200]
        except ValueError:
            reason = resp.text[:200]
        err = OpenMeteoError(resp.status_code, reason, getattr(resp, "url", url))
        if resp.status_code in _RETRY_STATUSES:
            last = err
            time.sleep(backoff_s * (2 ** attempt))
            continue
        raise err  # 400-class errors are not retried: the request itself is wrong
    status = getattr(last, "status", 0)
    raise OpenMeteoError(status, f"failed after {retries} attempts: {last}", url)


def _hourly_frame(payload: dict, rename: dict) -> pd.DataFrame:
    hourly = payload.get("hourly") or {}
    if "time" not in hourly:
        return pd.DataFrame(columns=["time", *rename.values()])
    df = pd.DataFrame(hourly)
    df = df.rename(columns=rename)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def fetch_weather_history(lat: float, lon: float, start: date, end: date, session=None) -> pd.DataFrame:
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ",".join(WEATHER_VARS),
        "wind_speed_unit": "ms", "timezone": "UTC",
    }
    return _hourly_frame(_get(ARCHIVE_URL, params, session), WEATHER_RENAME)


def fetch_marine(lat: float, lon: float, start: date | None = None, end: date | None = None,
                 forecast_days: int | None = None, past_days: int | None = None, session=None,
                 variables: list[str] | None = None) -> pd.DataFrame:
    """Marine history (start/end) or forecast (forecast_days, past_days).

    If the API rejects the full variable set (HTTP 400), retry with waves only;
    if that is rejected too, return an empty frame and let the caller carry on
    with wind-only features.
    """
    vars_ = list(variables or MARINE_VARS)
    params = {"latitude": lat, "longitude": lon, "hourly": ",".join(vars_), "timezone": "UTC"}
    if start is not None and end is not None:
        params["start_date"] = start.isoformat()
        params["end_date"] = end.isoformat()
    else:
        params["forecast_days"] = int(forecast_days or 7)
        params["past_days"] = int(past_days or 7)
    try:
        return _hourly_frame(_get(MARINE_URL, params, session), MARINE_RENAME)
    except OpenMeteoError as exc:
        if exc.status != 400:
            raise
        if vars_ != MARINE_WAVE_VARS:
            warnings.warn(f"marine request rejected ({exc.reason}); retrying with wave variables only")
            return fetch_marine(lat, lon, start, end, forecast_days, past_days, session, variables=MARINE_WAVE_VARS)
        warnings.warn(f"marine request rejected even for waves ({exc.reason}); continuing without marine data")
        return _hourly_frame({}, MARINE_RENAME)


def fetch_weather_forecast(lat: float, lon: float, forecast_days: int = 7, past_days: int = 7, session=None) -> pd.DataFrame:
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(WEATHER_VARS),
        "wind_speed_unit": "ms", "timezone": "UTC",
        "forecast_days": int(forecast_days), "past_days": int(past_days),
    }
    return _hourly_frame(_get(FORECAST_URL, params, session), WEATHER_RENAME)


def _merge(weather: pd.DataFrame, marine: pd.DataFrame, beach_id: str) -> pd.DataFrame:
    df = weather.merge(marine, on="time", how="outer").sort_values("time")
    df.insert(0, "beach_id", beach_id)
    return df.reset_index(drop=True)


def _year_chunks(start: date, end: date):
    y = start
    while y <= end:
        chunk_end = min(date(y.year, 12, 31), end)
        yield y, chunk_end
        y = date(y.year + 1, 1, 1)


def fetch_beach_history(beaches: pd.DataFrame, start: date, end: date, pause_s: float = 0.5,
                        session=None, progress=print) -> pd.DataFrame:
    """Hourly history for every beach, fetched one calendar year at a time.

    A beach whose weather request fails is skipped with a warning; a beach
    whose marine request fails keeps its wind data. Raises only if nothing at
    all could be fetched.
    """
    frames, failed = [], []
    for _, b in beaches.iterrows():
        beach_frames = []
        for y0, y1 in _year_chunks(start, end):
            try:
                w = fetch_weather_history(b["lat"], b["lon"], y0, y1, session)
            except OpenMeteoError as exc:
                warnings.warn(f"{b['id']} {y0.year}: weather history failed: {exc}")
                continue
            m = fetch_marine(b["lat"], b["lon"], start=y0, end=y1, session=session)
            beach_frames.append(_merge(w, m, b["id"]))
            time.sleep(pause_s)
        if beach_frames:
            frames.append(pd.concat(beach_frames, ignore_index=True))
            if progress:
                progress(f"  {b['name']}: {sum(len(f) for f in beach_frames):,} hourly rows")
        else:
            failed.append(b["id"])
    if not frames:
        raise OpenMeteoError(0, f"no history could be fetched for any beach (failed: {failed})", ARCHIVE_URL)
    if failed:
        warnings.warn(f"no history for beaches: {failed}")
    return pd.concat(frames, ignore_index=True)


def fetch_beach_forecast(beaches: pd.DataFrame, forecast_days: int = 7, past_days: int = 7,
                         pause_s: float = 0.5, session=None) -> pd.DataFrame:
    """Recent past plus forecast for every beach (past days feed the rolling windows)."""
    frames = []
    for _, b in beaches.iterrows():
        w = fetch_weather_forecast(b["lat"], b["lon"], forecast_days, past_days, session)
        m = fetch_marine(b["lat"], b["lon"], forecast_days=forecast_days, past_days=past_days, session=session)
        frames.append(_merge(w, m, b["id"]))
        time.sleep(pause_s)
    return pd.concat(frames, ignore_index=True)
