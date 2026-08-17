from __future__ import annotations

import hashlib
import html
import traceback

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Harnessform", page_icon="🐎", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Caprasimo&family=Figtree:wght@400;600;700&display=swap');
:root{--bg:#f5ead8;--paper:#f9f4ed;--text:#201e1d;--muted:#645c50;--accent:#c67139;--dark:#8c491a;--soft:#ffe1d0;--green:#e1eecc;--line:rgba(32,30,29,.14)}
html,body,[class*="css"]{font-family:Figtree,system-ui,sans-serif}.stApp{background:var(--bg);color:var(--text)}[data-testid="stHeader"]{background:transparent;height:0}[data-testid="stToolbar"],#MainMenu,footer{visibility:hidden}.block-container{max-width:560px;padding:.7rem .8rem 2rem}h1,h2,h3,.serif{font-family:Caprasimo,Georgia,serif!important;font-weight:400!important}.brand{font-family:Caprasimo,Georgia,serif;font-size:1.65rem}.kick{font-size:.69rem;letter-spacing:.11em;text-transform:uppercase;color:var(--dark);font-weight:700}.muted{color:var(--muted);font-size:.84rem}.card{background:var(--paper);border-radius:22px;padding:16px;box-shadow:0 4px 14px rgba(46,43,37,.09);margin:8px 0 12px}.rank{width:38px;height:38px;min-width:38px;border-radius:999px;background:var(--soft);color:var(--dark);display:flex;align-items:center;justify-content:center;font-family:Caprasimo}.rank.first{background:var(--accent);color:var(--bg)}.score{font-family:Caprasimo;color:var(--dark);font-size:1.28rem}.bigscore{font-family:Caprasimo;color:var(--dark);font-size:2.1rem}.pill{display:inline-block;border-radius:999px;padding:4px 9px;background:var(--soft);color:var(--dark);font-size:.69rem;font-weight:700;margin:2px 4px 2px 0}.pill.green{background:var(--green);color:#3d472b}.pill.neutral{background:#eee7db;color:#645c50}.divider{height:1px;background:var(--line);margin:12px 0}.evidence{border-left:3px solid var(--accent);padding-left:10px;margin:8px 0;font-size:.86rem}.stButton>button,.stDownloadButton>button{min-height:46px;border-radius:999px!important;font-weight:700!important;border:1px solid var(--line)!important}.stButton>button[kind="primary"]{background:var(--accent)!important;color:var(--bg)!important;border-color:var(--accent)!important}textarea,input,[data-baseweb="select"]>div{border-radius:16px!important}[data-testid="stFileUploaderDropzone"]{border-radius:18px;background:var(--paper)}@media(max-width:560px){.block-container{padding:.45rem .65rem 1.7rem}.brand{font-size:1.5rem}.stButton>button{min-height:48px}}
</style>
""", unsafe_allow_html=True)

try:
    from harness_parser import parse_harness_race
    from harness_model import analyse_harness_race
except Exception as exc:
    st.error("Harnessform loaded, but a model module failed to start.")
    st.exception(exc)
    with st.expander("Technical traceback"):
        st.code(traceback.format_exc())
    st.stop()


def esc(v):
    return html.escape(str(v if v is not None else ""))


def odds(v):
    try:
        return "N/A" if v is None else f"{float(v):.2f}"
    except Exception:
        return str(v)


for k,v in {"page":"today","raw":"","race":None,"results":None,"selected":0,"view":"Final","market_weight":35,"upload_nonce":0,"upload_sig":""}.items():
    if k not in st.session_state:
        st.session_state[k]=v


def go(page):
    st.session_state.page=page
    st.rerun()


def clear_all():
    st.session_state.raw=""
    st.session_state.race=None
    st.session_state.results=None
    st.session_state.selected=0
    st.session_state.upload_nonce+=1
    st.session_state.upload_sig=""


def selected():
    a=st.session_state.results or []
    return a[max(0,min(st.session_state.selected,len(a)-1))] if a else None


def runner_for(n):
    return next((r for r in getattr(st.session_state.race,"runners",[]) if str(r.number)==str(n)),None)


def input_page():
    st.markdown('<div class="brand">Harnessform</div><span class="pill neutral">AU · FR</span>',unsafe_allow_html=True)
    st.write("")
    st.markdown('<div class="card"><div class="kick">Input</div><h3>Paste Racing & Sports harness race data</h3><div class="muted">Copy the complete R&S harness race page and paste it below. Harnessform reads runners, draws, drivers, current odds, class/level, distance and past starts.</div></div>',unsafe_allow_html=True)
    up=st.file_uploader("Optional .txt / .md upload",type=["txt","md"],key=f"up_{st.session_state.upload_nonce}")
    if up is not None:
        b=up.getvalue();sig=f"{up.name}:{len(b)}:{hashlib.sha1(b).hexdigest()}"
        if sig!=st.session_state.upload_sig:
            st.session_state.raw=b.decode("utf-8",errors="replace");st.session_state.upload_sig=sig
    raw=st.text_area("Race data",value=st.session_state.raw,height=280,placeholder="Paste the complete Racing & Sports harness race page here…",label_visibility="collapsed")
    st.session_state.raw=raw
    mw=st.slider("Market / odds weight",0,40,int(st.session_state.market_weight),5,help="0% = form only. Current R&S odds can contribute up to 40% of the final ranking. Default 35%.")
    st.session_state.market_weight=mw
    c1,c2=st.columns([2,1])
    with c1: analyse=st.button("Parse & Predict",type="primary",use_container_width=True)
    with c2:
        if st.button("Clear",use_container_width=True): clear_all();st.rerun()
    if analyse:
        if not raw.strip(): st.error("Paste the Racing & Sports harness race first.");return
        try:
            with st.spinner("Parsing harness form and running the model…"):
                race=parse_harness_race(raw);results=analyse_harness_race(race,mw)
            if not results: st.error("The race parsed, but no active-runner predictions were produced.");return
            st.session_state.race=race;st.session_state.results=results;st.session_state.selected=0;st.session_state.view="Final";st.session_state.page="race";st.rerun()
        except Exception as exc:
            st.error(f"Could not analyse this race: {exc}")
            with st.expander("Technical traceback"): st.code(traceback.format_exc())


def rnk(a,view): return a.rank if view=="Final" else (a.form_rank if view=="Form" else a.market_rank)
def metric(a,view):
    if view=="Final": return f"{a.final_prob*100:.1f}%","Final"
    if view=="Form": return f"{a.form_prob*100:.1f}%","Form"
    return f"{a.market_prob*100:.1f}%","Market"


def race_page():
    race=st.session_state.race;results=st.session_state.results or []
    if not race or not results: go("today");return
    c1,c2=st.columns([1,5])
    with c1:
        if st.button("‹",use_container_width=True): go("today")
    with c2:
        st.markdown('<div class="kick">Race card</div>',unsafe_allow_html=True);st.markdown(f"### {race.name}")
    prize=f"{race.currency} {race.prize:,.0f}" if race.prize is not None else "Prize N/A"
    st.caption(f"Race {race.race_no or '—'} · {race.country or '—'} · {race.race_type or race.age_condition or 'Harness'} · {race.distance_m or '—'}m · {race.surface or '—'} {race.going or ''} · {prize}")
    scratches=[r.name for r in race.runners if r.scratched]
    if scratches: st.info("Scratched and excluded: "+", ".join(scratches))
    view=st.segmented_control("View",["Final","Form","Market"],default=st.session_state.view,label_visibility="collapsed") or "Final"
    st.session_state.view=view
    for a in sorted(results,key=lambda x:(rnk(x,view),x.number)):
        rank=rnk(a,view);val,label=metric(a,view);first=" first" if rank==1 else "";draw=f" · {esc(a.draw)}" if a.draw else ""
        st.markdown(f'<div class="card"><div style="display:flex;gap:11px;align-items:center"><div class="rank{first}">{rank}</div><div style="flex:1"><b>{a.number}. {esc(a.runner)}</b><div class="muted">{esc(a.class_movement)}{draw}</div></div><div style="text-align:right"><div class="score">{val}</div><div class="muted">{label} · Odds {odds(a.odds)}</div></div></div><div style="margin-top:9px"><span class="pill {"green" if a.confidence=="High" else "neutral"}">{esc(a.confidence)}</span><span class="pill neutral">Final #{a.rank}</span><span class="pill neutral">Form #{a.form_rank}</span><span class="pill neutral">Market #{a.market_rank}</span></div></div>',unsafe_allow_html=True)
        if st.button(f"Why {a.runner}?",key=f"why_{a.number}_{rank}",use_container_width=True): st.session_state.selected=results.index(a);go("why")
    df=pd.DataFrame([{"Final Rank":a.rank,"Form Rank":a.form_rank,"Market Rank":a.market_rank,"No.":a.number,"Runner":a.runner,"Draw":a.draw,"Driver":a.driver,"Odds":a.odds,"Form Score /100":round(a.form_score,1),"Form %":round(a.form_prob*100,1),"Market %":round(a.market_prob*100,1),"Final %":round(a.final_prob*100,1),"Class Movement":a.class_movement,"Confidence":a.confidence,"Value":a.value_label} for a in results])
    st.download_button("Export predictions CSV",df.to_csv(index=False).encode("utf-8"),file_name=f"Harness_Race_{race.race_no or 'X'}_predictions.csv",mime="text/csv",use_container_width=True)


def why_page():
    race=st.session_state.race;a=selected()
    if not race or not a: go("today");return
    c1,c2=st.columns([1,5])
    with c1:
        if st.button("‹",use_container_width=True): go("race")
    with c2:
        st.markdown('<div class="kick">Why this runner?</div>',unsafe_allow_html=True);st.markdown(f"### {a.number}. {a.runner}")
    st.markdown(f'<div class="card"><div style="display:flex;gap:16px;align-items:center"><div style="flex:1"><div class="bigscore">{a.final_prob*100:.1f}%</div><div class="muted">Final win probability</div></div><div style="text-align:right"><span class="pill green">{esc(a.confidence)}</span><div class="muted">Odds {odds(a.odds)}</div></div></div><div class="divider"></div><b>Final #{a.rank} · Form #{a.form_rank} · Market #{a.market_rank}</b><div class="divider"></div><span class="kick">Class movement</span><br><b>{esc(a.class_movement)}</b><div class="divider"></div><span class="kick">Draw / driver</span><br>{esc(a.draw or "N/A")} · {esc(a.driver or "N/A")}<div class="divider"></div><span class="kick">Proven level</span><br>{esc(a.proven_level)}<div class="divider"></div><span class="kick">Market value</span><br>{esc(a.value_label)}</div>',unsafe_allow_html=True)
    st.markdown("### Model explanation");st.write(a.explanation)
    st.markdown("### Factor scores");st.dataframe(pd.DataFrame([{"Factor":k,"Score /100":round(v,1)} for k,v in sorted(a.components.items(),key=lambda kv:-kv[1])]),use_container_width=True,hide_index=True)
    if a.evidence:
        st.markdown("### Evidence used")
        for line in a.evidence: st.markdown(f'<div class="evidence">{esc(line)}</div>',unsafe_allow_html=True)
    if st.button("Full form history",use_container_width=True): go("horse")


def horse_page():
    a=selected();race=st.session_state.race
    if not a or not race: go("today");return
    runner=runner_for(a.number)
    if st.button("‹ Back",use_container_width=True): go("why")
    st.markdown('<div class="kick">Form history</div>',unsafe_allow_html=True);st.markdown(f"### {a.number}. {a.runner}")
    if not runner or not runner.past_starts: st.info("No previous harness starts were parsed for this runner.");return
    rows=[]
    for s in runner.past_starts:
        finish=s.finish_status or (f"{s.finish_pos}/{s.field_size}" if s.finish_pos and s.field_size else "—")
        rows.append({"Date":s.date_raw,"Finish":finish,"Margin":s.margin_m,"Track":s.track,"Race/Class":s.race_desc,"Prize":s.prize,"Distance":s.distance_m,"Surface":s.surface,"Driver":s.driver,"Draw":s.draw,"SP":s.sp})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=min(560,80+36*len(rows)))


def method_page():
    st.markdown('<div class="brand">Harnessform method</div>',unsafe_allow_html=True);st.caption("Australia + France")
    st.markdown('<div class="card"><div class="kick">Form model</div><p><b>Recent form 26%</b> · class fit 20% · distance 10% · course 8% · draw/handicap 9% · reliability 9% · consistency 7% · driver 5% · trend 6%.</p><p>French class codes use the R&S letter hierarchy (A strongest through H) with purse refinement. Australian harness class context relies more heavily on purse level because R&S race labels are often age conditions such as 4U.</p><p>Disqualifications/non-finishes are penalised through both recent form and reliability. Australian Fr/Sr draws and standing-start handicaps are modelled separately.</p><p>The final ranking blends the Form model with normalised current R&S odds. Market weight defaults to 35% and is capped at 40%.</p></div>',unsafe_allow_html=True)


def nav():
    st.markdown('<div class="divider"></div>',unsafe_allow_html=True);c1,c2=st.columns(2)
    with c1:
        if st.button("🐎 Today",use_container_width=True,type="primary" if st.session_state.page in {"today","race","why","horse"} else "secondary"): st.session_state.page="today";st.rerun()
    with c2:
        if st.button("📊 Method",use_container_width=True,type="primary" if st.session_state.page=="method" else "secondary"): st.session_state.page="method";st.rerun()


{"today":input_page,"race":race_page,"why":why_page,"horse":horse_page,"method":method_page}.get(st.session_state.page,input_page)();nav()
