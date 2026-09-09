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


def _get(url: str, params: dict, session=None, retries: int = 3, backoff_s: float = 2.0) -> dict:
    import requests

    sess = session or requests.Session()
    last = None
    for attempt in range(retries):
        try:
            resp = sess.get(url, params=params, timeout=60)
            if resp.status_code == 429:
                raise requests.HTTPError("rate limited", response=resp)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:  # pragma: no cover - network
            last = exc
            time.sleep(backoff_s * (2 ** attempt))
    raise RuntimeError(f"Open-Meteo request failed after {retries} attempts: {last}")


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
                 forecast_days: int | None = None, past_days: int | None = None, session=None) -> pd.DataFrame:
    """Marine history (start/end) or forecast (forecast_days, past_days)."""
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": ",".join(MARINE_VARS),
        "timezone": "UTC",
    }
    if start is not None and end is not None:
        params["start_date"] = start.isoformat()
        params["end_date"] = end.isoformat()
    else:
        params["forecast_days"] = int(forecast_days or 7)
        params["past_days"] = int(past_days or 7)
    return _hourly_frame(_get(MARINE_URL, params, session), MARINE_RENAME)


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


def fetch_beach_history(beaches: pd.DataFrame, start: date, end: date, pause_s: float = 0.5, session=None) -> pd.DataFrame:
    """Hourly history for every beach in the table, concatenated."""
    frames = []
    for _, b in beaches.iterrows():
        w = fetch_weather_history(b["lat"], b["lon"], start, end, session)
        m = fetch_marine(b["lat"], b["lon"], start=start, end=end, session=session)
        frames.append(_merge(w, m, b["id"]))
        time.sleep(pause_s)
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
