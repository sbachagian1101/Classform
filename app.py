from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass

import pandas as pd
import streamlit as st

from race_parser import parse_race
from class_model import (
    analyse_race,
    _current_reference_level,
    _effective_level,
    _reference_label,
)

# -----------------------------------------------------------------------------
# App shell
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Classform",
    page_icon="🏇",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Caprasimo&family=Figtree:wght@400;600;700&display=swap');

:root {
  --cf-bg: #f5ead8;
  --cf-surface: #ebddc5;
  --cf-paper: #f9f4ed;
  --cf-text: #201e1d;
  --cf-muted: #645c50;
  --cf-accent: #c67139;
  --cf-accent-dark: #8c491a;
  --cf-accent-soft: #ffe1d0;
  --cf-green: #7a8a5e;
  --cf-green-soft: #e1eecc;
  --cf-line: rgba(32,30,29,.14);
}

html, body, [class*="css"] { font-family: "Figtree", system-ui, sans-serif; }
.stApp { background: var(--cf-bg); color: var(--cf-text); }
[data-testid="stHeader"] { background: transparent; height: 0; }
[data-testid="stToolbar"], #MainMenu, footer { visibility: hidden; }
.block-container {
  max-width: 520px;
  padding-top: .8rem;
  padding-bottom: 2.2rem;
  padding-left: .85rem;
  padding-right: .85rem;
}
h1, h2, h3, .cf-serif { font-family: "Caprasimo", Georgia, serif !important; font-weight: 400 !important; }
h1 { font-size: 1.85rem !important; }
h2 { font-size: 1.45rem !important; }
h3 { font-size: 1.15rem !important; }

.cf-brand { font-family: "Caprasimo", Georgia, serif; font-size: 1.65rem; line-height: 1.1; }
.cf-kicker { font-size: .69rem; letter-spacing: .11em; text-transform: uppercase; color: var(--cf-accent-dark); font-weight: 700; }
.cf-muted { color: var(--cf-muted); font-size: .84rem; }
.cf-card {
  background: var(--cf-paper);
  border-radius: 22px;
  padding: 16px;
  border: 1px solid rgba(32,30,29,.05);
  box-shadow: 0 4px 14px rgba(46,43,37,.09);
  margin: 8px 0 12px;
}
.cf-card-flat { background: var(--cf-surface); box-shadow: none; }
.cf-pick {
  background: var(--cf-green-soft);
  border-radius: 16px;
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}
.cf-rank {
  width: 38px; height: 38px; min-width: 38px; border-radius: 999px;
  background: var(--cf-accent-soft); color: var(--cf-accent-dark);
  display: inline-flex; align-items: center; justify-content: center;
  font-family: "Caprasimo", Georgia, serif; font-size: 1rem;
}
.cf-rank.first { background: var(--cf-accent); color: var(--cf-bg); }
.cf-score { font-family: "Caprasimo", Georgia, serif; font-size: 1.28rem; color: var(--cf-accent-dark); }
.cf-pill {
  display: inline-block; border-radius: 999px; padding: 4px 9px;
  background: var(--cf-accent-soft); color: var(--cf-accent-dark);
  font-size: .69rem; font-weight: 700; margin-right: 4px;
}
.cf-pill.green { background: var(--cf-green-soft); color: #3d472b; }
.cf-pill.neutral { background: #eee7db; color: #645c50; }
.cf-divider { height: 1px; background: var(--cf-line); margin: 12px 0; }
.cf-bigscore { font-family: "Caprasimo", Georgia, serif; font-size: 2.1rem; color: var(--cf-accent-dark); line-height: 1; }
.cf-evidence { border-left: 3px solid var(--cf-accent); padding-left: 10px; margin: 8px 0; font-size: .86rem; }
.cf-stat { text-align:center; background:var(--cf-paper); border-radius:16px; padding:11px 8px; min-height:72px; }
.cf-stat b { font-family:"Caprasimo", Georgia, serif; font-size:1.15rem; font-weight:400; }

.stButton > button, .stDownloadButton > button {
  min-height: 46px;
  border-radius: 999px !important;
  font-weight: 700 !important;
  border: 1px solid var(--cf-line) !important;
}
.stButton > button[kind="primary"] {
  background: var(--cf-accent) !important;
  color: var(--cf-bg) !important;
  border-color: var(--cf-accent) !important;
}
textarea, input, [data-baseweb="select"] > div {
  border-radius: 16px !important;
}
[data-testid="stFileUploaderDropzone"] { border-radius: 18px; background: var(--cf-paper); }
[data-testid="stMetric"] { background: var(--cf-paper); border-radius: 15px; padding: 9px; }
[data-testid="stMetricLabel"] { font-size: .72rem; }
[data-testid="stMetricValue"] { font-family: "Caprasimo", Georgia, serif; font-size: 1.1rem; }

/* Mobile bottom-navigation feel */
.cf-nav-title { text-align:center; font-size:.67rem; color:var(--cf-muted); margin-top:-4px; }

@media (max-width: 560px) {
  .block-container { padding: .45rem .65rem 1.7rem; }
  .cf-brand { font-size: 1.5rem; }
  h1 { font-size: 1.65rem !important; }
  p, li { font-size: .91rem; }
  .stButton > button { min-height: 48px; }
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# State helpers
# -----------------------------------------------------------------------------
def _init_state() -> None:
    defaults = {
        "cf_page": "today",
        "cf_onboarding": True,
        "cf_ob_step": 0,
        "cf_raw": "",
        "cf_input": "",
        "cf_race": None,
        "cf_analyses": None,
        "cf_selected_rank": 0,
        "cf_sort": "model",
        "cf_picks": {},
        "cf_upload_nonce": 0,
        "cf_last_upload_sig": "",
        "cf_show_input": True,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_state()


def go(page: str) -> None:
    st.session_state.cf_page = page
    st.rerun()


def clear_input() -> None:
    st.session_state.cf_raw = ""
    st.session_state.cf_input = ""
    st.session_state.cf_last_upload_sig = ""
    st.session_state.cf_upload_nonce += 1
    st.session_state.cf_show_input = True


def race_key(race) -> str:
    return "|".join(
        str(x or "")
        for x in (getattr(race, "country", ""), getattr(race, "race_no", ""), getattr(race, "name", ""), getattr(race, "time", ""))
    )


def fmt_odds(odds) -> str:
    if odds is None:
        return "N/A"
    try:
        return f"{float(odds):.2f}"
    except Exception:
        return str(odds)


def analysis_df(analyses) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Rank": a.rank,
                "No.": a.number,
                "Horse": a.horse,
                "Odds": a.odds,
                "Class Score /10": a.score,
                "Confidence": a.confidence,
                "Movement": a.movement,
                "Assessment": a.assessment,
            }
            for a in analyses
        ]
    )


def selected_analysis():
    analyses = st.session_state.cf_analyses or []
    if not analyses:
        return None
    idx = max(0, min(st.session_state.cf_selected_rank, len(analyses) - 1))
    return analyses[idx]


def find_runner(race, number):
    for runner in getattr(race, "runners", []) or []:
        if str(getattr(runner, "number", "")) == str(number):
            return runner
    return None


# -----------------------------------------------------------------------------
# Onboarding — mirrors the supplied Classform mobile design
# -----------------------------------------------------------------------------
def render_onboarding() -> None:
    step = st.session_state.cf_ob_step
    top1, top2 = st.columns([4, 1])
    with top1:
        st.markdown('<div class="cf-brand">Classform</div>', unsafe_allow_html=True)
    with top2:
        if st.button("Skip", use_container_width=True):
            st.session_state.cf_onboarding = False
            st.rerun()

    st.write("")
    if step == 0:
        st.markdown(
            """
            <div class="cf-card" style="padding:28px 22px;text-align:center;">
              <div style="width:150px;height:150px;border-radius:999px;background:#ffe1d0;margin:8px auto 24px;display:flex;align-items:center;justify-content:center;">
                <span class="cf-serif" style="font-size:54px;color:#8c491a;">Cf</span>
              </div>
              <div class="cf-kicker">Classform</div>
              <h1 style="text-align:left;margin-top:8px;">Class is the only signal.</h1>
              <p style="text-align:left;color:#645c50;">One score per horse, 0–10, built from the class strength each runner has actually proven. Odds are shown, but do not drive the class score.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif step == 1:
        st.markdown(
            """
            <div class="cf-card" style="padding:28px 22px;text-align:center;">
              <div style="display:inline-block;background:#c67139;color:#f5ead8;border-radius:999px;padding:12px 22px;font-family:Caprasimo;font-size:20px;">Model 7.4 <span style="font-family:Figtree;font-size:11px;">/10</span></div>
              <div style="margin:10px 0;color:#82796a;font-weight:700;">0% weight</div>
              <div style="display:inline-block;border:1px solid rgba(32,30,29,.2);border-radius:999px;padding:12px 22px;font-family:Caprasimo;font-size:18px;">Market 3.50</div>
              <div class="cf-kicker" style="text-align:left;margin-top:28px;">Value spotting</div>
              <h1 style="text-align:left;margin-top:8px;">Odds carry zero weight.</h1>
              <p style="text-align:left;color:#645c50;">Market prices sit beside the model so you can spot disagreement without contaminating the class calculation.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="cf-card" style="padding:28px 22px;">
              <div style="display:flex;gap:10px;align-items:center;">
                <div style="flex:1;text-align:center;background:#e1eecc;border-radius:20px;padding:18px 8px;"><div class="cf-serif" style="font-size:22px;">FR</div><div class="cf-muted">French class ladder</div></div>
                <div class="cf-serif" style="font-size:18px;">≠</div>
                <div style="flex:1;text-align:center;background:#ffe1d0;border-radius:20px;padding:18px 8px;"><div class="cf-serif" style="font-size:22px;">AUS</div><div class="cf-muted">Benchmark ladder</div></div>
              </div>
              <div class="cf-kicker" style="margin-top:28px;">Two countries</div>
              <h1 style="margin-top:8px;">Two class systems, read natively.</h1>
              <p style="color:#645c50;">French classes and Australian benchmark ratings keep their own semantics, with purse strength used as a supporting proxy when needed.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    dots = "".join(
        f'<span style="display:inline-block;width:{22 if i == step else 8}px;height:8px;border-radius:999px;background:{"#c67139" if i == step else "#dcd3c4"};margin:0 3px;"></span>'
        for i in range(3)
    )
    st.markdown(f'<div style="text-align:center;margin:10px 0 14px;">{dots}</div>', unsafe_allow_html=True)
    label = "Start with a race" if step == 2 else "Continue"
    if st.button(label, type="primary", use_container_width=True):
        if step < 2:
            st.session_state.cf_ob_step += 1
        else:
            st.session_state.cf_onboarding = False
        st.rerun()


# -----------------------------------------------------------------------------
# Race input
# -----------------------------------------------------------------------------
def render_input_card() -> None:
    with st.container(border=False):
        st.markdown('<div class="cf-card">', unsafe_allow_html=True)
        st.markdown('<div class="cf-kicker">Analyse a race</div>', unsafe_allow_html=True)
        st.markdown("### Paste or upload race data")
        st.caption("Racing & Sports text/markdown. Scratched / NON PARTANT runners are excluded by the existing parser.")

        uploaded = st.file_uploader(
            "Upload .txt or .md",
            type=["txt", "md"],
            key=f"cf_upload_{st.session_state.cf_upload_nonce}",
            label_visibility="collapsed",
        )
        if uploaded is not None:
            raw_bytes = uploaded.getvalue()
            sig = f"{uploaded.name}:{len(raw_bytes)}:{hashlib.sha1(raw_bytes).hexdigest()}"
            if sig != st.session_state.cf_last_upload_sig:
                try:
                    decoded = raw_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    decoded = raw_bytes.decode("latin-1")
                st.session_state.cf_input = decoded
                st.session_state.cf_raw = decoded
                st.session_state.cf_last_upload_sig = sig

        raw = st.text_area(
            "Race data",
            height=230,
            key="cf_input",
            placeholder="Paste the complete race page here…",
            label_visibility="collapsed",
        )
        st.session_state.cf_raw = raw

        b1, b2 = st.columns([2, 1])
        with b1:
            analyse = st.button("Analyse race", type="primary", use_container_width=True)
        with b2:
            st.button("Clear", use_container_width=True, on_click=clear_input)

        if analyse:
            if not raw.strip():
                st.error("Paste or upload a race first.")
            else:
                try:
                    race = parse_race(raw)
                    analyses = analyse_race(race)
                except Exception as exc:
                    st.error(f"Could not analyse this race: {exc}")
                    st.markdown('</div>', unsafe_allow_html=True)
                    return
                if not getattr(race, "runners", None):
                    st.error("No active runners were parsed. Include the runner field and horse names.")
                elif not analyses:
                    st.error("The race parsed, but no class predictions were produced.")
                else:
                    st.session_state.cf_race = race
                    st.session_state.cf_analyses = analyses
                    st.session_state.cf_selected_rank = 0
                    st.session_state.cf_show_input = False
                    st.session_state.cf_page = "race"
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------
def render_today() -> None:
    race = st.session_state.cf_race
    analyses = st.session_state.cf_analyses

    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div class="cf-brand">Classform</div><span class="cf-pill neutral">FR · AUS</span>', unsafe_allow_html=True)
    with c2:
        if race and st.button("＋ New", use_container_width=True):
            st.session_state.cf_show_input = True
            st.rerun()

    st.write("")
    if not race or not analyses or st.session_state.cf_show_input:
        render_input_card()
        if race and analyses:
            if st.button("Back to current race", use_container_width=True):
                st.session_state.cf_show_input = False
                st.rerun()
        return

    top = analyses[0]
    ref = _current_reference_level(race)
    ref_text = f" · strength {ref:.2f}" if ref is not None else ""
    st.markdown(
        f"""
        <div class="cf-card">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
            <span class="cf-kicker">Current race</span><span class="cf-pill">Race {getattr(race,'race_no','') or '—'}</span>
          </div>
          <div class="cf-serif" style="font-size:1.28rem;margin-top:8px;">{getattr(race,'name','') or 'Unnamed race'}</div>
          <div class="cf-muted">{getattr(race,'race_type','') or '—'} · {getattr(race,'distance_m','') or '—'}m · {getattr(race,'going','') or '—'}{ref_text}</div>
          <div class="cf-pick">
            <div class="cf-rank first">{top.number}</div>
            <div style="flex:1;min-width:0;"><b>{top.horse}</b><div class="cf-muted">Top class pick · {top.confidence} confidence</div></div>
            <div style="text-align:right;"><div class="cf-score">{top.score:.1f}</div><div class="cf-muted">class /10</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open race card", type="primary", use_container_width=True):
        go("race")

    st.markdown("### Model principles")
    st.markdown(
        """
        <div class="cf-card cf-card-flat">
          <span class="cf-pill green">Class only</span><span class="cf-pill neutral">Odds = display</span>
          <p style="margin-top:10px;margin-bottom:0;">The score is based on demonstrated class strength and competitiveness. France and Australia use separate class semantics.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_race() -> None:
    race = st.session_state.cf_race
    analyses = st.session_state.cf_analyses
    if not race or not analyses:
        st.info("Analyse a race first.")
        if st.button("Go to input", type="primary", use_container_width=True):
            go("today")
        return

    back, title = st.columns([1, 5])
    with back:
        if st.button("‹", use_container_width=True):
            go("today")
    with title:
        st.markdown('<div class="cf-kicker">Race card</div>', unsafe_allow_html=True)
        st.markdown(f"### {getattr(race,'name','') or 'Race'}")

    ref = _current_reference_level(race)
    ref_label = _reference_label(race, ref) if ref is not None else ""
    st.caption(
        f"Race {getattr(race,'race_no','') or '—'} · {getattr(race,'race_type','') or '—'} · "
        f"{getattr(race,'distance_m','') or '—'}m · {getattr(race,'going','') or '—'}"
        + (f" · {ref:.2f} {ref_label}" if ref is not None else "")
    )

    sort = st.segmented_control(
        "Sort",
        options=["Model", "Market"],
        default="Model" if st.session_state.cf_sort == "model" else "Market",
        label_visibility="collapsed",
        key="cf_sort_control",
    )
    st.session_state.cf_sort = "market" if sort == "Market" else "model"
    ordered = list(analyses)
    if st.session_state.cf_sort == "market":
        ordered.sort(key=lambda a: (a.odds is None, a.odds if a.odds is not None else 9999))

    for a in ordered:
        rank_cls = " first" if a.rank == 1 else ""
        st.markdown(
            f"""
            <div class="cf-card" style="margin-bottom:4px;">
              <div style="display:flex;align-items:center;gap:11px;">
                <div class="cf-rank{rank_cls}">{a.rank}</div>
                <div style="flex:1;min-width:0;">
                  <div style="font-weight:700;font-size:1rem;">{a.number}. {a.horse}</div>
                  <div class="cf-muted">{a.movement}</div>
                </div>
                <div style="text-align:right;">
                  <div class="cf-score">{a.score:.1f}</div>
                  <div class="cf-muted">Odds {fmt_odds(a.odds)}</div>
                </div>
              </div>
              <div style="margin-top:9px;"><span class="cf-pill {'green' if a.confidence == 'High' else 'neutral'}">{a.confidence}</span><span class="cf-pill neutral">#{a.rank} model</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(f"Why {a.horse}?", key=f"why_{a.rank}_{a.number}", use_container_width=True):
            st.session_state.cf_selected_rank = analyses.index(a)
            go("why")

    df = analysis_df(analyses)
    st.download_button(
        "Export predictions CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"Race_{getattr(race,'race_no','X') or 'X'}_class_predictions.csv",
        mime="text/csv",
        use_container_width=True,
    )


def render_why() -> None:
    race = st.session_state.cf_race
    a = selected_analysis()
    if not race or not a:
        go("today")
        return

    b, t = st.columns([1, 5])
    with b:
        if st.button("‹", use_container_width=True):
            go("race")
    with t:
        st.markdown('<div class="cf-kicker">Why this score</div>', unsafe_allow_html=True)
        st.markdown(f"### {a.number}. {a.horse}")

    st.markdown(
        f"""
        <div class="cf-card">
          <div style="display:flex;align-items:center;gap:16px;">
            <div style="flex:1;"><div class="cf-bigscore">{a.score:.1f}</div><div class="cf-muted">Class score /10</div></div>
            <div style="text-align:right;"><span class="cf-pill green">{a.confidence}</span><div class="cf-muted" style="margin-top:6px;">Odds {fmt_odds(a.odds)}</div></div>
          </div>
          <div class="cf-divider"></div>
          <div><span class="cf-kicker">Movement</span><br><b>{a.movement}</b></div>
          <div class="cf-divider"></div>
          <div><span class="cf-kicker">Proven at</span><br>{a.proven_level}</div>
          <div class="cf-divider"></div>
          <div><span class="cf-kicker">Assessment</span><br>{a.assessment}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### Model explanation")
    st.write(a.explanation)
    if a.evidence_lines:
        st.markdown("### Evidence used")
        for line in a.evidence_lines:
            st.markdown(f'<div class="cf-evidence">{line}</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Full form history", use_container_width=True):
            go("horse")
    with c2:
        key = race_key(race) + f"|{a.number}"
        already = key in st.session_state.cf_picks
        if st.button("✓ Saved" if already else "Save my pick", type="primary" if not already else "secondary", use_container_width=True):
            if not already:
                st.session_state.cf_picks[key] = {
                    "horse": a.horse,
                    "number": a.number,
                    "score": a.score,
                    "confidence": a.confidence,
                    "race": getattr(race, "name", "") or "Race",
                    "race_no": getattr(race, "race_no", "") or "",
                    "country": getattr(race, "country", "") or "",
                }
            st.rerun()


def render_horse() -> None:
    race = st.session_state.cf_race
    a = selected_analysis()
    if not race or not a:
        go("today")
        return
    runner = find_runner(race, a.number)

    b, t = st.columns([1, 5])
    with b:
        if st.button("‹", use_container_width=True):
            go("why")
    with t:
        st.markdown('<div class="cf-kicker">Form history</div>', unsafe_allow_html=True)
        st.markdown(f"### {a.number}. {a.horse}")

    st.markdown(
        f"""
        <div class="cf-card">
          <span class="cf-pill">Today</span>
          <div class="cf-serif" style="font-size:1.2rem;margin:8px 0 3px;">{a.score:.1f}/10</div>
          <div class="cf-muted">{a.movement}</div>
          <div class="cf-divider"></div>
          <b>{a.relevant_previous_class}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if runner is None or not getattr(runner, "past_races", None):
        st.info("No parsed past-race history is available for this runner.")
        return

    rows = []
    for x in runner.past_races:
        eff = _effective_level(x)
        rows.append(
            {
                "Date": getattr(x, "date_raw", ""),
                "Finish": getattr(x, "finish_status", None) or getattr(x, "finish_pos", None),
                "Field": getattr(x, "field_size", None),
                "Margin": getattr(x, "margin", None),
                "Track": getattr(x, "track", ""),
                "Race": getattr(x, "race_desc", ""),
                "Class": getattr(x, "grade_label", "") or getattr(x, "level_label", ""),
                "Strength": round(eff, 2) if eff is not None else None,
                "Prize": getattr(x, "prize_raw", ""),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=min(520, 80 + 36 * len(rows)))


def render_picks() -> None:
    st.markdown('<div class="cf-brand">My picks</div>', unsafe_allow_html=True)
    st.caption("Saved during this session")
    picks = st.session_state.cf_picks
    if not picks:
        st.markdown(
            '<div class="cf-card"><div class="cf-serif" style="font-size:1.15rem;">No saved picks yet.</div><p class="cf-muted">Open a horse explanation and tap “Save my pick”.</p></div>',
            unsafe_allow_html=True,
        )
        return

    for key, p in reversed(list(picks.items())):
        st.markdown(
            f"""
            <div class="cf-card">
              <div class="cf-kicker">{p['country']} · Race {p['race_no']}</div>
              <div class="cf-serif" style="font-size:1.15rem;margin-top:5px;">{p['number']}. {p['horse']}</div>
              <div class="cf-muted">{p['race']}</div>
              <div style="margin-top:9px;"><span class="cf-pill green">{p['score']:.1f}/10</span><span class="cf-pill neutral">{p['confidence']} confidence</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(f"Remove {p['horse']}", key=f"remove_{hash(key)}", use_container_width=True):
            del st.session_state.cf_picks[key]
            st.rerun()


def render_record() -> None:
    st.markdown('<div class="cf-brand">Model record</div>', unsafe_allow_html=True)
    st.caption("Current class-model tuning audit")
    st.markdown(
        """
        <div class="cf-card">
          <div class="cf-kicker">Deauville validation snapshot</div>
          <div style="display:flex;gap:8px;margin-top:10px;">
            <div class="cf-stat" style="flex:1;"><b>17/32</b><div class="cf-muted">top-four overlap</div></div>
            <div class="cf-stat" style="flex:1;"><b>12/32</b><div class="cf-muted">previous version</div></div>
          </div>
          <p class="cf-muted" style="margin:12px 0 0;">This is a tuning audit of top-four overlap, not a full win-rate or profitability metric. Racing outcomes include many factors intentionally excluded from a class-only model.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### What the model uses")
    st.markdown(
        "- Proven class strength and competitiveness\n"
        "- Finishing position, field context, beaten margin and purse/class proxies\n"
        "- France and Australia interpreted with separate class ladders\n"
        "- Odds displayed for comparison but given **zero scoring weight**"
    )


# -----------------------------------------------------------------------------
# Bottom navigation
# -----------------------------------------------------------------------------
def render_bottom_nav() -> None:
    st.markdown('<div class="cf-divider" style="margin-top:20px;"></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🏇 Today", use_container_width=True, type="primary" if st.session_state.cf_page in {"today", "race", "why", "horse"} else "secondary"):
            st.session_state.cf_page = "today"
            st.rerun()
    with c2:
        if st.button("🔖 My picks", use_container_width=True, type="primary" if st.session_state.cf_page == "picks" else "secondary"):
            st.session_state.cf_page = "picks"
            st.rerun()
    with c3:
        if st.button("📊 Record", use_container_width=True, type="primary" if st.session_state.cf_page == "record" else "secondary"):
            st.session_state.cf_page = "record"
            st.rerun()


# -----------------------------------------------------------------------------
# Router
# -----------------------------------------------------------------------------
if st.session_state.cf_onboarding:
    render_onboarding()
else:
    page = st.session_state.cf_page
    if page == "today":
        render_today()
    elif page == "race":
        render_race()
    elif page == "why":
        render_why()
    elif page == "horse":
        render_horse()
    elif page == "picks":
        render_picks()
    elif page == "record":
        render_record()
    else:
        st.session_state.cf_page = "today"
        st.rerun()

    render_bottom_nav()
