from __future__ import annotations

import html
import traceback

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Greyform", page_icon="🐕", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root{--bg:#f2eadc;--paper:#fffaf3;--text:#211f1d;--muted:#6b6258;--accent:#bf6a34;--dark:#82451f;--green:#e4efd3;--line:rgba(32,30,29,.13)}
.stApp{background:var(--bg);color:var(--text)}
[data-testid="stHeader"]{background:transparent}.block-container{max-width:760px;padding-top:.8rem;padding-bottom:2rem}
.gf-brand{font-family:Georgia,serif;font-size:2rem;font-weight:800}.gf-kicker{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--dark);font-weight:800}.gf-muted{color:var(--muted);font-size:.88rem}
.gf-card{background:var(--paper);border-radius:22px;padding:17px;border:1px solid var(--line);box-shadow:0 4px 14px rgba(40,35,28,.07);margin:9px 0 13px}.gf-box{width:42px;height:42px;min-width:42px;border-radius:12px;background:#ffe0cc;color:var(--dark);display:flex;align-items:center;justify-content:center;font-weight:900;font-size:1.08rem}.gf-box.first{background:var(--accent);color:white}.gf-prob{font-family:Georgia,serif;font-size:1.36rem;font-weight:800;color:var(--dark)}.gf-pill{display:inline-block;border-radius:999px;padding:4px 9px;background:#eee7dc;color:#62584e;font-size:.72rem;font-weight:700;margin:2px 4px 2px 0}.gf-pill.green{background:var(--green);color:#40502d}
.stButton>button,.stDownloadButton>button{min-height:46px;border-radius:999px!important;font-weight:700!important}.stButton>button[kind="primary"]{background:var(--accent)!important;color:white!important;border-color:var(--accent)!important}textarea{border-radius:16px!important}
@media(max-width:640px){.block-container{padding:.5rem .65rem 1.5rem}.gf-brand{font-size:1.65rem}.gf-card{padding:14px}}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="gf-brand">🐕 Greyform</div>', unsafe_allow_html=True)
st.caption("Greyhound predictor · Racing & Sports paste → Form + Market → Final")

try:
    from greyhound_parser import parse_greyhound_race
    from greyhound_model import analyse_greyhound_race
except Exception as exc:
    st.error("Greyform loaded, but a model module failed to start.")
    st.exception(exc)
    with st.expander("Technical traceback"):
        st.code(traceback.format_exc())
    st.stop()


def esc(v):
    return html.escape(str(v if v is not None else ""))


for key, value in {"gf_raw":"","gf_race":None,"gf_results":None,"gf_market_weight":35,"gf_upload_nonce":0}.items():
    if key not in st.session_state:
        st.session_state[key] = value


def clear_all():
    st.session_state.gf_raw = ""
    st.session_state.gf_race = None
    st.session_state.gf_results = None
    st.session_state.gf_upload_nonce += 1


st.markdown("""
<div class="gf-card"><div class="gf-kicker">Input</div><h3 style="margin:.45rem 0 .3rem">Paste Racing & Sports greyhound race data</h3><div class="gf-muted">Copy the complete R&S greyhound race page and paste it below. Greyform reads runners, boxes, current odds, explicit scratchings, grade, distance and past starts.</div></div>
""", unsafe_allow_html=True)

uploaded = st.file_uploader("Optional .txt / .md upload", type=["txt","md"], key=f"gf_upload_{st.session_state.gf_upload_nonce}")
if uploaded is not None:
    decoded = uploaded.getvalue().decode("utf-8", errors="replace")
    if decoded != st.session_state.gf_raw:
        st.session_state.gf_raw = decoded

raw = st.text_area("Race data", value=st.session_state.gf_raw, height=270, placeholder="Paste the complete Racing & Sports greyhound race page here...", label_visibility="collapsed")
st.session_state.gf_raw = raw

market_weight = st.slider("Market / odds weight", 0, 40, int(st.session_state.gf_market_weight), 5, help="0% = form only. Current odds are capped at 40% of the final model. Default is 35%.")
st.session_state.gf_market_weight = market_weight

c1,c2 = st.columns([2,1])
with c1:
    analyse = st.button("Parse & Predict", type="primary", use_container_width=True)
with c2:
    st.button("Clear", on_click=clear_all, use_container_width=True)

if analyse:
    if not raw.strip():
        st.error("Paste the Racing & Sports greyhound race first.")
    else:
        try:
            with st.spinner("Parsing runners and running the model..."):
                race = parse_greyhound_race(raw)
                results = analyse_greyhound_race(race, market_weight / 100.0)
            st.session_state.gf_race = race
            st.session_state.gf_results = results
        except Exception as exc:
            st.error(f"Could not analyse this race: {exc}")
            with st.expander("Technical traceback"):
                st.code(traceback.format_exc())

race = st.session_state.gf_race
results = st.session_state.gf_results
if race is None or not results:
    st.stop()

active = [r for r in race.runners if not r.scratched]
scratched = [r for r in race.runners if r.scratched]

st.markdown(f"""
<div class="gf-card"><div class="gf-kicker">Parsed race</div><h3 style="margin:.4rem 0 .25rem">Race {esc(race.race_no or '—')} · {esc(race.name)}</h3><div class="gf-muted">{esc(race.grade_label)} · {esc(race.distance_m or '—')}m · {esc(race.surface)} {esc(race.going)} · {len(active)} active runners</div></div>
""", unsafe_allow_html=True)

check_df = pd.DataFrame([{"Box":r.box,"Runner":r.name,"Form":r.form,"Trainer":r.trainer,"Odds":r.odds,"Past starts":len(r.past_starts),"Status":"SCRATCHED" if r.scratched else "Active"} for r in race.runners])
with st.expander("Check parsed field"):
    st.dataframe(check_df, use_container_width=True, hide_index=True)
    if scratched:
        st.warning("Excluded as scratched: " + ", ".join(f"Box {r.box} {r.name}" for r in scratched))

final_rows=[]
for x in results:
    final_rows.append({"Final Rank":x.rank,"Box":x.box,"Runner":x.runner,"Final %":round(x.final_prob*100,1),"Form %":round(x.form_prob*100,1),"Market %":round(x.market_prob*100,1),"Top 2 %":round(x.top2_prob*100,1),"Top 3 %":round(x.top3_prob*100,1),"Odds":x.odds,"Value":x.value_label,"Form Score":round(x.form_score,1),"Confidence":x.confidence})
final_df = pd.DataFrame(final_rows)
form_df = final_df.sort_values(["Form %","Box"], ascending=[False,True]).reset_index(drop=True); form_df.insert(0,"Form Rank",range(1,len(form_df)+1))
market_df = final_df.sort_values(["Market %","Box"], ascending=[False,True]).reset_index(drop=True); market_df.insert(0,"Market Rank",range(1,len(market_df)+1))

st.markdown("## Prediction")
if sum(1 for r in active if r.odds is not None) >= 2 and market_weight > 0:
    st.success(f"Final model = {100-market_weight}% Form + {market_weight}% Market.")
else:
    st.info("Final ranking is currently Form-only because sufficient current odds were not parsed.")

tab_final,tab_form,tab_market,tab_factors,tab_method = st.tabs(["🏆 Final","📋 Form","💹 Market","🧩 Factors","ℹ️ Method"])
with tab_final:
    st.dataframe(final_df[["Final Rank","Box","Runner","Final %","Top 2 %","Top 3 %","Odds","Value","Confidence"]], use_container_width=True, hide_index=True)
with tab_form:
    st.dataframe(form_df[["Form Rank","Box","Runner","Form %","Form Score","Confidence"]], use_container_width=True, hide_index=True)
with tab_market:
    st.dataframe(market_df[["Market Rank","Box","Runner","Odds","Market %","Value"]], use_container_width=True, hide_index=True)
with tab_factors:
    rows=[]
    for x in results:
        row={"Box":x.box,"Runner":x.runner}; row.update({k:round(v,1) for k,v in x.components.items()}); rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
with tab_method:
    st.markdown("""
**Form model (before current odds)**

- 25% recent finishing performance — last 5 starts, recency weighted
- 18% class/grade strength — performance relative to today's grade
- 12% course record
- 12% distance record
- 10% empirical box suitability from previous draws
- 8% career win/place consistency
- 8% available sectional speed near today's distance
- 7% recent trend

The Form score becomes a win probability. Current R&S odds are separately converted into normalised market probabilities. Final probability blends Form and Market using the slider, with market weight capped at **40%**. Top-2 and Top-3 probabilities come from deterministic race simulations. Explicit R&S scratchings are excluded automatically.
""")

st.markdown("### Final race card")
for x in results:
    rank_class = " first" if x.rank == 1 else ""
    odds_text = f"{x.odds:.2f}" if x.odds is not None else "N/A"
    value_class = " green" if x.value_label in {"Strong value","Possible value"} else ""
    st.markdown(f"""
<div class="gf-card"><div style="display:flex;gap:12px;align-items:center"><div class="gf-box{rank_class}">{x.box}</div><div style="flex:1;min-width:0"><div style="font-weight:800;font-size:1.03rem">#{x.rank} · {esc(x.runner)}</div><div class="gf-muted">Box {x.box} · {esc(x.confidence)} confidence</div></div><div style="text-align:right"><div class="gf-prob">{x.final_prob*100:.1f}%</div><div class="gf-muted">Odds {odds_text}</div></div></div><div style="margin-top:10px"><span class="gf-pill green">Form {x.form_prob*100:.1f}%</span><span class="gf-pill">Market {x.market_prob*100:.1f}%</span><span class="gf-pill">Top 2 {x.top2_prob*100:.1f}%</span><span class="gf-pill">Top 3 {x.top3_prob*100:.1f}%</span><span class="gf-pill{value_class}">{esc(x.value_label)}</span></div></div>
""", unsafe_allow_html=True)
    with st.expander(f"Why {x.runner}?"):
        st.write(x.explanation)
        st.markdown("**Factor scores /100**")
        st.dataframe(pd.DataFrame([{"Factor":k,"Score":round(v,1)} for k,v in x.components.items()]).sort_values("Score",ascending=False), use_container_width=True, hide_index=True)
        st.markdown("**Evidence**")
        for e in x.evidence:
            st.markdown(f"- {e}")

st.download_button("Export predictions CSV", final_df.to_csv(index=False).encode("utf-8"), file_name=f"Greyform_R{race.race_no or 'X'}_predictions.csv", mime="text/csv", use_container_width=True)

st.markdown("### Inspect runner history")
options=[f"Box {r.box} · {r.name}" for r in active]
chosen=st.selectbox("Runner", options, label_visibility="collapsed")
runner=active[options.index(chosen)]
if runner.past_starts:
    history=pd.DataFrame([{"Date":s.date_raw,"Finish":f"{s.finish_pos}/{s.field_size}" if s.finish_pos and s.field_size else s.finish_status,"Margin":s.margin,"Track":s.track,"Grade":s.grade_label,"Distance":s.distance_m,"Box":s.box,"SP":s.sp,"Sectional":s.sectional} for s in runner.past_starts])
    st.dataframe(history, use_container_width=True, hide_index=True)
else:
    st.info("No previous starts were parsed for this runner.")
