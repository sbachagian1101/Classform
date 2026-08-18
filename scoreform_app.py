from __future__ import annotations

import hashlib
import pandas as pd
import streamlit as st

from scoreform_parser import parse_race
from scoreform_model import analyse_race, component_rows, WEIGHTS, CAPS

st.set_page_config(page_title="ScoreForm Predictor", page_icon="🏇", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root { --sf-green:#173f35; --sf-gold:#b78b3c; --sf-soft:#f6f2e8; --sf-ink:#1d2724; --sf-red:#9a3d38; }
.block-container { max-width: 1180px; padding-top: 1rem; }
h1,h2,h3 { color: var(--sf-ink); }
.sf-hero { background:linear-gradient(135deg,#173f35,#25584a); color:white; padding:22px 24px; border-radius:22px; margin-bottom:14px; }
.sf-hero h1 { color:white; margin:0; font-size:2rem; }
.sf-hero p { margin:.35rem 0 0; opacity:.9; }
[data-testid="stMetric"] { background:#fff; border:1px solid #ece7dc; padding:10px; border-radius:16px; }
.stButton>button { border-radius:999px; min-height:44px; font-weight:700; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="sf-hero">
  <h1>🏇 ScoreForm Predictor</h1>
  <p>Paste Racing & Sports Enhanced Form → parse the race → score every runner → rank the field with transparent evidence.</p>
</div>
""", unsafe_allow_html=True)

with st.expander("How this version scores the race", expanded=False):
    st.markdown("**Fixed component weights:** Horse Suitability 30%, Recent Form & Fitness 20%, Ability & Class 15%, Jockey 10%, Trainer 10%, Race Setup 10%, Head-to-Head 5%.\n\n**Bookmaker/Betfair odds have zero scoring weight.** They are displayed only for comparison. Unknown evidence is neutral (0); proven weaknesses may receive negative points. Category caps limit double-counting.")

raw = st.text_area("Paste the complete Racing & Sports Enhanced Form page", height=320, placeholder="Paste from 'Lingfield Form Guide (Race ...)' through the runner histories and Head to Head sections...", key="scoreform_input")

def _clear_scoreform():
    st.session_state["scoreform_input"] = ""
    st.session_state.pop("scoreform_result", None)

c1, c2 = st.columns([1, 1])
with c1:
    run_clicked = st.button("Parse & Predict", type="primary", use_container_width=True)
with c2:
    st.button("Clear", use_container_width=True, on_click=_clear_scoreform)

if run_clicked:
    if not raw.strip():
        st.warning("Paste the race data first.")
    else:
        race = parse_race(raw)
        if not race.runners:
            st.error("No runners were detected. Make sure the paste includes the numbered runner profile blocks: runner number → form → betfair price → HORSE NAME → age/BP/weight.")
        else:
            scores = analyse_race(race)
            st.session_state.scoreform_result = (hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest(), race, scores)

result = st.session_state.get("scoreform_result")
if result:
    _, race, scores = result
    st.subheader(f"Race {race.race_no or '?'} · {race.track or 'Track not parsed'} · {race.time or ''}")
    meta=[]
    if race.name: meta.append(race.name)
    if race.distance_raw: meta.append(f"{race.distance_raw} (~{race.distance_m}m)" if race.distance_m else race.distance_raw)
    if race.surface: meta.append(race.surface)
    if race.going: meta.append(race.going)
    if race.race_type: meta.append(race.race_type)
    st.caption(" · ".join(meta))

    if scores:
        top=scores[0]
        m1,m2,m3,m4=st.columns(4)
        m1.metric("Top selection",top.horse)
        m2.metric("Score",f"{top.total:.1f} / 100")
        m3.metric("Relative model win %",f"{top.win_pct:.1f}%")
        m4.metric("Evidence coverage",f"{top.coverage_pct:.0f}%")
        st.info("Relative model win % is a score-derived share across this field, not a calibrated betting probability. Market odds are not used to calculate it.")

    tabs=st.tabs(["Prediction","Breakdown","Horse explanations","Parsed data","Method"])
    with tabs[0]:
        pred=pd.DataFrame([{"Rank":s.rank,"No.":s.number,"Horse":s.horse,"Score /100":round(s.total,1),"Relative Win %":round(s.win_pct,1),"Odds (0% weight)":s.odds,"OHR":s.latest_ohr,"Running Style":s.running_style,"Coverage %":round(s.coverage_pct)} for s in scores])
        st.dataframe(pred,use_container_width=True,hide_index=True)
        st.download_button("Download prediction CSV",pred.to_csv(index=False).encode("utf-8"),file_name=f"scoreform_race_{race.race_no or 'race'}_prediction.csv",mime="text/csv")
        st.markdown("### Top 3")
        for s in scores[:3]:
            positives=[e for e in s.evidence if e.points>0]; negatives=[e for e in s.evidence if e.points<0]
            strongest=sorted(positives,key=lambda e:e.points,reverse=True)[:3]; risks=sorted(negatives,key=lambda e:e.points)[:2]
            st.markdown(f"**#{s.rank} {s.horse} — {s.total:.1f}/100 ({s.win_pct:.1f}%)**")
            if strongest: st.write("Strengths: "+" · ".join(f"{e.subcriterion} {e.points:+g}" for e in strongest))
            if risks: st.write("Risks: "+" · ".join(f"{e.subcriterion} {e.points:+g}" for e in risks))

    with tabs[1]:
        st.dataframe(pd.DataFrame(component_rows(scores)),use_container_width=True,hide_index=True)
        st.caption("Raw scores are capped, then converted to weighted points using the fixed 30/20/15/10/10/10/5 structure.")

    with tabs[2]:
        horse_names=[f"#{s.rank} · {s.horse}" for s in scores]
        selected=st.selectbox("Horse",horse_names)
        s=scores[horse_names.index(selected)]
        st.markdown(f"### {s.horse} — {s.total:.1f}/100")
        cols=st.columns(7)
        for col,comp in zip(cols,WEIGHTS):
            col.metric(comp.replace(" & ","/"),f"{s.weighted[comp]:.1f}/{WEIGHTS[comp]:.0f}",f"raw {s.raw[comp]:.1f}/{CAPS[comp]:.0f}")
        evdf=pd.DataFrame([{"Component":e.component,"Criterion":e.subcriterion,"Points":e.points if e.available else None,"Evidence / explanation":e.text,"Source":e.source,"Status":"Scored" if e.points!=0 else ("Available/neutral" if e.available else "Unavailable / neutral")} for e in s.evidence])
        st.dataframe(evdf,use_container_width=True,hide_index=True)

    with tabs[3]:
        runner_rows=[]
        for r in race.runners:
            runner_rows.append({"No.":r.number,"Horse":r.horse,"Form":r.form,"Wt kg":r.weight,"BP":r.barrier,"Jockey":r.jockey,"Claim":r.jockey_claim,"Jockey Last50 Win%":None if r.jockey_last50_win is None else round(r.jockey_last50_win*100,1),"Trainer":r.trainer,"Trainer Last50 Win%":None if r.trainer_last50_win is None else round(r.trainer_last50_win*100,1),"J/H":None if r.jh_starts is None else f"{(r.jh_win or 0):.0%}-{(r.jh_place or 0):.0%}-{r.jh_starts}","J/T":None if r.jt_starts is None else f"{(r.jt_win or 0):.0%}-{(r.jt_place or 0):.0%}-{r.jt_starts}","Past runs parsed":len(r.past_runs),"DLS":r.dls})
        st.dataframe(pd.DataFrame(runner_rows),use_container_width=True,hide_index=True)
        chosen=st.selectbox("Inspect parsed historical runs",[r.horse for r in race.runners],key="parsed_runner")
        rr=next(r for r in race.runners if r.horse==chosen)
        hist=pd.DataFrame([{"Date":p.date_raw,"Finish":p.finish_pos,"Field":p.field_size,"OHR":p.ohr,"Track":p.track,"Race":p.race_name,"Distance":p.distance_m,"Surface":p.surface,"Going":p.going,"Race type":p.race_type,"Margin L":p.margin,"Jockey":p.jockey,"Weight":p.weight,"BP":p.barrier,"Trainer":p.trainer,"Ongoing":None if p.ongoing_starts is None else f"{p.ongoing_wins:02d}-{p.ongoing_places:02d}-{p.ongoing_starts:02d}","Settling":p.settling_pos} for p in rr.past_runs])
        st.dataframe(hist,use_container_width=True,hide_index=True)

    with tabs[4]:
        st.markdown("""
### Scoring engine

| Component | Weight | Raw cap |
|---|---:|---:|
| Horse Suitability | 30% | 20 |
| Recent Form & Fitness | 20% | 15 |
| Ability & Class | 15% | 15 |
| Jockey | 10% | 10 |
| Trainer | 10% | 10 |
| Race Setup | 10% | 10 |
| Head-to-Head | 5% | 3 |

**Safeguards**
- Odds are **0% weight**.
- Missing evidence is **0**, not a negative score.
- Proven weaknesses can score negatively.
- Category caps reduce double-counting.
- UK R&S `Class` values such as `3 HCP` or `3U OPEN` are not assumed to be UK Class 1–7.
- Raw race times are not treated as cross-track speed figures.
- Barrier remains neutral until a proper track × distance × field-size draw-bias database is added.
- Pace is inferred only when enough settling-position history exists.
- Jockey last 10 mounts remains neutral because those rides are not included in this paste.
""")

st.caption("For analytical/entertainment use. Always verify the race field and conditions against an official source.")
