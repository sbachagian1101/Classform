from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from db import DB_PATH, connect, fetch_all
from matcher import load_profile

st.set_page_config(page_title="Opportunity Sweeper", page_icon="🎯", layout="wide")

st.title("🎯 Opportunity Sweeper")
st.caption(
    "Jobs, consultancies, tenders and grants matched against your CV, "
    "Eco Marine Consultants Ltd, and Coral Garden Conservation profiles."
)

if not DB_PATH.exists():
    st.warning(
        "No data yet — the hourly sweep (`sweep.py`) hasn't run in this "
        "environment. Run `python sweep.py` once manually, or wait for the "
        "next scheduled cron run (see DEPLOY.md)."
    )
    st.stop()

profile = load_profile()
persona_labels = [p.get("label", k) for k, p in (profile.get("personas") or {}).items()]

conn = connect()
rows = fetch_all(conn, min_score=0.0)
conn.close()

if not rows:
    st.info("No matching opportunities stored yet. Check back after the next sweep.")
    st.stop()

df = pd.DataFrame(rows)
df["matched_personas"] = df["matched_personas"].fillna("")
df["matched_keywords"] = df["matched_keywords"].fillna("")

with st.sidebar:
    st.header("Filters")
    min_score = st.slider("Minimum match score", 0.0, 1.0, float(profile.get("min_match_score", 0.25)), 0.05)
    categories = sorted(df["category"].unique())
    picked_categories = st.multiselect("Category", categories, default=categories)
    personas_present = sorted({p for row in df["matched_personas"] for p in row.split(",") if p})
    picked_personas = st.multiselect("Matched profile", personas_present, default=personas_present)
    sources = sorted(df["source"].unique())
    picked_sources = st.multiselect("Source", sources, default=sources)

filtered = df[
    (df["match_score"] >= min_score)
    & (df["category"].isin(picked_categories))
    & (df["source"].isin(picked_sources))
]
if picked_personas:
    filtered = filtered[filtered["matched_personas"].apply(
        lambda cell: any(p in cell.split(",") for p in picked_personas)
    )]

filtered = filtered.sort_values("match_score", ascending=False)

c1, c2, c3 = st.columns(3)
c1.metric("Opportunities shown", len(filtered))
c2.metric("Total tracked", len(df))
c3.metric("Sources active", df["source"].nunique())

st.dataframe(
    filtered[[
        "title", "category", "source", "match_score", "matched_personas",
        "matched_keywords", "published_date", "url",
    ]].rename(columns={
        "title": "Title",
        "category": "Category",
        "source": "Source",
        "match_score": "Score",
        "matched_personas": "Matched profile",
        "matched_keywords": "Matched keywords",
        "published_date": "Published",
        "url": "Link",
    }),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Link": st.column_config.LinkColumn("Link", display_text="Open ↗"),
        "Score": st.column_config.ProgressColumn("Score", min_value=0.0, max_value=1.0),
    },
)

st.download_button(
    "Download CSV",
    filtered.to_csv(index=False).encode("utf-8"),
    file_name="opportunities.csv",
    mime="text/csv",
)

with st.expander("Eligibility profile currently in use (edit profile.yaml to change)"):
    for key, persona in (profile.get("personas") or {}).items():
        st.markdown(f"**{persona.get('label', key)}**")
        st.write("Keywords:", ", ".join(persona.get("keywords", [])))
        st.write("Geography:", ", ".join(persona.get("geography", [])))
        st.write("Types:", ", ".join(persona.get("opportunity_types", [])))
