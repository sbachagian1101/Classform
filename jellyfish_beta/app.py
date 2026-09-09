"""Streamlit dashboard for the Mauritius jellyfish risk beta.

Reads data/outputs/latest_risk.csv (written by scripts/run_forecast.py) and,
if present, the event table for overlay. Run with:  streamlit run app.py
"""
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
RISK_PATH = ROOT / "data" / "outputs" / "latest_risk.csv"
EVENTS_PATH = ROOT / "data" / "events" / "mru_events.csv"
BEACHES_PATH = ROOT / "config" / "beaches.yaml"

TIER_COLOR = {"low": "#2e8b57", "moderate": "#e0a800", "high": "#c0392b"}

st.set_page_config(page_title="Mauritius Jellyfish Risk (beta)", layout="wide")
st.title("Mauritius jellyfish risk, beta")
st.caption(
    "Mechanistic indices only. Physalia = onshore wind and swell; cubozoa = calm warm lagoon days. "
    "Parameters are priors from other regions and are not yet validated on Mauritian events."
)


@st.cache_data
def load_risk():
    if not RISK_PATH.exists():
        return None
    df = pd.read_csv(RISK_PATH, parse_dates=["date"])
    return df


@st.cache_data
def load_beaches():
    import yaml
    with open(BEACHES_PATH, "r", encoding="utf-8") as fh:
        return pd.DataFrame(yaml.safe_load(fh)["beaches"]).set_index("id", drop=False)


@st.cache_data
def load_events():
    if not EVENTS_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(EVENTS_PATH, dtype=str).fillna("")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


risk = load_risk()
beaches = load_beaches()
events = load_events()

if risk is None or risk.empty:
    st.warning("No forecast found. Run `python scripts/run_forecast.py` first.")
    st.stop()

dates = sorted(risk["date"].unique())
sel_date = st.select_slider("Forecast day", options=dates, value=dates[-1] if len(dates) == 1 else dates[min(len(dates) - 1, 7)],
                            format_func=lambda d: pd.Timestamp(d).strftime("%a %d %b"))
day = risk[risk["date"] == sel_date].merge(beaches[["id", "lat", "lon"]].reset_index(drop=True), left_on="beach_id", right_on="id", how="left")
day["color"] = day["tier"].map(TIER_COLOR)

left, right = st.columns([1, 1])
with left:
    st.subheader("Beaches")
    st.map(day.rename(columns={"lat": "latitude", "lon": "longitude"}), latitude="latitude", longitude="longitude",
           color="color", size=1500)
with right:
    st.subheader(f"Risk tiers, {pd.Timestamp(sel_date).strftime('%d %b %Y')}")
    show = day[["name", "region", "tier", "risk_score", "physalia_risk", "cubozoa_risk",
                "onshore_wind_mean", "calm_days", "sst_mean"]].sort_values("risk_score", ascending=False)
    st.dataframe(show.style.format({"risk_score": "{:.2f}", "physalia_risk": "{:.2f}", "cubozoa_risk": "{:.2f}",
                                    "onshore_wind_mean": "{:.1f}", "sst_mean": "{:.1f}"}),
                 width="stretch", hide_index=True)

st.subheader("Beach detail")
beach_id = st.selectbox("Beach", options=list(beaches["id"]), format_func=lambda b: beaches.loc[b, "name"])
series = risk[risk["beach_id"] == beach_id].set_index("date").sort_index()

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Hazard components** (0 to 1). The overall score is the larger of the two.")
    st.line_chart(series[["physalia_risk", "cubozoa_risk"]], color=["#1f77b4", "#d62728"])
with c2:
    st.markdown("**Overall risk score** with tier thresholds.")
    score = series[["risk_score"]].copy()
    score["moderate threshold"] = 0.35
    score["high threshold"] = 0.60
    st.line_chart(score, color=["#333333", "#e0a800", "#c0392b"])

c3, c4 = st.columns(2)
with c3:
    st.markdown("**Wind** (m/s). Onshore is positive toward the beach. Days below the calm line add to the cubozoan index.")
    wind = series[["wind_speed_mean", "onshore_wind_mean"]].copy()
    wind["calm threshold"] = 5.0
    st.line_chart(wind, color=["#1f77b4", "#2ca02c", "#999999"])
with c4:
    st.markdown("**Day by day**")
    detail = series[["tier", "risk_score", "calm_days", "sst_mean", "onshore_stress_72h", "onshore_swell_24h"]].copy()
    detail.index = detail.index.strftime("%a %d %b")
    st.dataframe(detail.style.format({"risk_score": "{:.2f}", "sst_mean": "{:.1f}", "onshore_stress_72h": "{:.0f}",
                                      "onshore_swell_24h": "{:.2f}"}), width="stretch")

if not events.empty:
    st.subheader("Recorded events at this beach")
    ev = events[events["beach_id"] == beach_id].sort_values("date", ascending=False)
    st.dataframe(ev[["date", "species_group", "count_class", "source_type", "confidence", "source_url"]],
                 width="stretch", hide_index=True)

st.caption(f"Issued {risk['issued_utc'].iloc[0]} UTC. Beach positions and orientations are approximate.")
