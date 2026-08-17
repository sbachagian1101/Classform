from __future__ import annotations

import hashlib
import html
import traceback

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Soccerform", page_icon="⚽", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Caprasimo&family=Figtree:wght@400;600;700&display=swap');
:root{--bg:#f5ead8;--paper:#f9f4ed;--text:#201e1d;--muted:#645c50;--accent:#c67139;--dark:#8c491a;--soft:#ffe1d0;--green:#e1eecc;--line:rgba(32,30,29,.14)}
html,body,[class*="css"]{font-family:Figtree,system-ui,sans-serif}.stApp{background:var(--bg);color:var(--text)}[data-testid="stHeader"]{background:transparent;height:0}[data-testid="stToolbar"],#MainMenu,footer{visibility:hidden}.block-container{max-width:560px;padding:.7rem .8rem 2rem}h1,h2,h3,.serif{font-family:Caprasimo,Georgia,serif!important;font-weight:400!important}.brand{font-family:Caprasimo,Georgia,serif;font-size:1.65rem}.kick{font-size:.69rem;letter-spacing:.11em;text-transform:uppercase;color:var(--dark);font-weight:700}.muted{color:var(--muted);font-size:.84rem}.card{background:var(--paper);border-radius:22px;padding:16px;box-shadow:0 4px 14px rgba(46,43,37,.09);margin:8px 0 12px}.pick{background:var(--green);border-radius:16px;padding:12px;margin-top:10px}.score{font-family:Caprasimo;color:var(--dark);font-size:1.45rem}.big{font-family:Caprasimo;color:var(--dark);font-size:2.15rem;line-height:1}.pill{display:inline-block;border-radius:999px;padding:4px 9px;background:var(--soft);color:var(--dark);font-size:.69rem;font-weight:700;margin:2px 4px 2px 0}.pill.green{background:var(--green);color:#3d472b}.pill.neutral{background:#eee7db;color:#645c50}.divider{height:1px;background:var(--line);margin:12px 0}.evidence{border-left:3px solid var(--accent);padding-left:10px;margin:8px 0;font-size:.86rem}.market-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.market-box{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:11px;text-align:center}.market-box b{font-family:Caprasimo,Georgia,serif;font-size:1.18rem;color:var(--dark)}.stButton>button,.stDownloadButton>button{min-height:46px;border-radius:999px!important;font-weight:700!important;border:1px solid var(--line)!important}.stButton>button[kind="primary"]{background:var(--accent)!important;color:var(--bg)!important;border-color:var(--accent)!important}textarea,input,[data-baseweb="select"]>div{border-radius:16px!important}[data-testid="stFileUploaderDropzone"]{border-radius:18px;background:var(--paper)}@media(max-width:560px){.block-container{padding:.45rem .65rem 1.7rem}.brand{font-size:1.5rem}.stButton>button{min-height:48px}}
</style>
""",unsafe_allow_html=True)

try:
    from soccer_parser import parse_team_page, recent_summary
    from soccer_model import analyse_match
except Exception as exc:
    st.error("Soccerform loaded, but a model module failed to start.");st.exception(exc)
    with st.expander("Technical traceback"): st.code(traceback.format_exc())
    st.stop()


def esc(v): return html.escape(str(v if v is not None else ""))
def pct(v): return f"{100*float(v):.1f}%"

for k,v in {"sf_page":"input","sf_home_raw":"","sf_away_raw":"","sf_home":None,"sf_away":None,"sf_prediction":None,"sf_home_nonce":0,"sf_away_nonce":0,"sf_home_sig":"","sf_away_sig":""}.items():
    if k not in st.session_state: st.session_state[k]=v


def go(page): st.session_state.sf_page=page;st.rerun()

def clear_all():
    st.session_state.sf_home_raw="";st.session_state.sf_away_raw="";st.session_state.sf_home=None;st.session_state.sf_away=None;st.session_state.sf_prediction=None
    st.session_state.sf_home_nonce+=1;st.session_state.sf_away_nonce+=1;st.session_state.sf_home_sig="";st.session_state.sf_away_sig=""


def load_upload(up,raw_key,sig_key):
    if up is None:return
    b=up.getvalue();sig=f"{up.name}:{len(b)}:{hashlib.sha1(b).hexdigest()}"
    if sig!=st.session_state[sig_key]:st.session_state[raw_key]=b.decode("utf-8",errors="replace");st.session_state[sig_key]=sig


def input_page():
    st.markdown('<div class="brand">⚽ Soccerform</div><span class="pill neutral">1X2 · BTTS · O/U 2.5</span>',unsafe_allow_html=True);st.write("")
    st.markdown('<div class="card"><div class="kick">Input</div><h3>Paste both FootyStats team pages</h3><div class="muted">Paste the complete Home Team page first and the complete Away Team page second. Soccerform uses venue splits, xG/xGA, recent form, goals, BTTS/O2.5 tendencies, shots and H2H.</div></div>',unsafe_allow_html=True)
    st.markdown("#### 🏠 Home team")
    uh=st.file_uploader("Optional Home .txt / .md upload",type=["txt","md"],key=f"sf_h_{st.session_state.sf_home_nonce}");load_upload(uh,"sf_home_raw","sf_home_sig")
    hr=st.text_area("Home team data",value=st.session_state.sf_home_raw,height=220,placeholder="Paste the complete FootyStats HOME team page here…",label_visibility="collapsed");st.session_state.sf_home_raw=hr
    st.markdown("#### ✈️ Away team")
    ua=st.file_uploader("Optional Away .txt / .md upload",type=["txt","md"],key=f"sf_a_{st.session_state.sf_away_nonce}");load_upload(ua,"sf_away_raw","sf_away_sig")
    ar=st.text_area("Away team data",value=st.session_state.sf_away_raw,height=220,placeholder="Paste the complete FootyStats AWAY team page here…",label_visibility="collapsed");st.session_state.sf_away_raw=ar
    c1,c2=st.columns([2,1])
    with c1:analyse=st.button("Parse & Predict",type="primary",use_container_width=True)
    with c2:
        if st.button("Clear",use_container_width=True):clear_all();st.rerun()
    if analyse:
        if not hr.strip() or not ar.strip():st.error("Paste both the Home Team and Away Team FootyStats pages.");return
        try:
            with st.spinner("Parsing team data and running the models…"):
                home=parse_team_page(hr);away=parse_team_page(ar);pred=analyse_match(home,away)
            st.session_state.sf_home=home;st.session_state.sf_away=away;st.session_state.sf_prediction=pred;st.session_state.sf_page="match";st.rerun()
        except Exception as exc:
            st.error(f"Could not analyse this match: {exc}")
            with st.expander("Technical traceback"):st.code(traceback.format_exc())


def box(label,value,active=False):
    cls="pill green" if active else "pill neutral"
    return f'<div class="market-box"><div class="{cls}" style="margin-bottom:7px">{esc(label)}</div><b>{pct(value)}</b></div>'


def match_page():
    home=st.session_state.sf_home;away=st.session_state.sf_away;p=st.session_state.sf_prediction
    if not home or not away or not p:go("input");return
    c1,c2=st.columns([1,5])
    with c1:
        if st.button("‹",use_container_width=True):go("input")
    with c2:st.markdown('<div class="kick">Match prediction</div>',unsafe_allow_html=True);st.markdown(f"### {esc(home.name)} vs {esc(away.name)}")
    league=home.league or away.league or "League";st.caption(f"{league} · {home.season or away.season or 'Season N/A'} · Expected goals {p.home_xg:.2f} - {p.away_xg:.2f}")
    view=st.segmented_control("Prediction market",["1X2","BTTS","O/U 2.5"],default="1X2",label_visibility="collapsed") or "1X2"
    if view=="1X2":
        vals=[("1 · Home",p.home_win),("X · Draw",p.draw),("2 · Away",p.away_win)];best=max(vals,key=lambda x:x[1])[0]
        st.markdown('<div class="card"><div class="kick">1X2 probabilities</div><div class="market-grid" style="margin-top:10px">'+''.join(box(l,v,l==best) for l,v in vals)+f'</div><div class="divider"></div><b>Model lean: {esc(best)}</b><div class="muted">Confidence: {esc(p.confidence)}</div></div>',unsafe_allow_html=True)
    elif view=="BTTS":
        vals=[("BTTS Yes",p.btts_yes),("BTTS No",p.btts_no)];best=max(vals,key=lambda x:x[1])[0]
        st.markdown('<div class="card"><div class="kick">Both Teams To Score</div><div class="market-grid" style="grid-template-columns:repeat(2,1fr);margin-top:10px">'+''.join(box(l,v,l==best) for l,v in vals)+f'</div><div class="divider"></div><b>Model lean: {esc(best)}</b></div>',unsafe_allow_html=True)
    else:
        vals=[("Over 2.5",p.over25),("Under 2.5",p.under25)];best=max(vals,key=lambda x:x[1])[0]
        st.markdown('<div class="card"><div class="kick">Total Goals 2.5</div><div class="market-grid" style="grid-template-columns:repeat(2,1fr);margin-top:10px">'+''.join(box(l,v,l==best) for l,v in vals)+f'</div><div class="divider"></div><b>Model lean: {esc(best)}</b></div>',unsafe_allow_html=True)
    st.markdown(f'<div class="card"><div class="kick">Prediction summary</div><div class="pick"><b>1X2:</b> Home {pct(p.home_win)} · Draw {pct(p.draw)} · Away {pct(p.away_win)}</div><div class="pick"><b>BTTS:</b> Yes {pct(p.btts_yes)} · No {pct(p.btts_no)}</div><div class="pick"><b>Goals:</b> Over 2.5 {pct(p.over25)} · Under 2.5 {pct(p.under25)}</div></div>',unsafe_allow_html=True)
    if st.button("Why these predictions?",use_container_width=True):go("why")
    st.markdown("### Most likely scorelines");st.dataframe(pd.DataFrame([{"Score":s,"Probability %":round(v*100,1)} for s,v in p.likely_scores]),use_container_width=True,hide_index=True)
    df=pd.DataFrame([{"Home":home.name,"Away":away.name,"Home Win %":round(p.home_win*100,2),"Draw %":round(p.draw*100,2),"Away Win %":round(p.away_win*100,2),"BTTS Yes %":round(p.btts_yes*100,2),"BTTS No %":round(p.btts_no*100,2),"Over 2.5 %":round(p.over25*100,2),"Under 2.5 %":round(p.under25*100,2),"Home xG":round(p.home_xg,2),"Away xG":round(p.away_xg,2),"Confidence":p.confidence}])
    st.download_button("Export prediction CSV",df.to_csv(index=False).encode("utf-8"),file_name="soccerform_prediction.csv",mime="text/csv",use_container_width=True)


def why_page():
    home=st.session_state.sf_home;away=st.session_state.sf_away;p=st.session_state.sf_prediction
    if not home or not away or not p:go("input");return
    if st.button("‹ Back to prediction",use_container_width=True):go("match")
    st.markdown('<div class="kick">Why these predictions?</div>',unsafe_allow_html=True);st.markdown(f"### {esc(home.name)} vs {esc(away.name)}")
    st.markdown(f'<div class="card"><div style="display:flex;gap:16px"><div style="flex:1"><div class="big">{p.home_xg:.2f}</div><div class="muted">{esc(home.name)} expected goals</div></div><div style="flex:1;text-align:right"><div class="big">{p.away_xg:.2f}</div><div class="muted">{esc(away.name)} expected goals</div></div></div><div class="divider"></div><b>Confidence: {esc(p.confidence)}</b></div>',unsafe_allow_html=True)
    st.markdown("### Team strength / weakness")
    st.dataframe(pd.DataFrame([{"Team":home.name,"Attack Index":round(p.home_attack_index,1),"Attack Weakness":round(100-p.home_attack_index,1),"Defensive Strength":round(100-p.home_def_weakness,1),"Defensive Weakness":round(p.home_def_weakness,1)},{"Team":away.name,"Attack Index":round(p.away_attack_index,1),"Attack Weakness":round(100-p.away_attack_index,1),"Defensive Strength":round(100-p.away_def_weakness,1),"Defensive Weakness":round(p.away_def_weakness,1)}]),use_container_width=True,hide_index=True)
    st.markdown("### Evidence used")
    for line in p.evidence:st.markdown(f'<div class="evidence">{esc(line)}</div>',unsafe_allow_html=True)
    if p.h2h:
        st.markdown("### H2H found in the pasted pages");st.dataframe(pd.DataFrame([{"Date":m.date_label,"Home":m.home,"Score":f"{m.home_goals}-{m.away_goals}","Away":m.away} for m in p.h2h]),use_container_width=True,hide_index=True)
    st.markdown("### Recent form used");hr=recent_summary(home,10);ar=recent_summary(away,10)
    st.dataframe(pd.DataFrame([{"Team":home.name,"Sample":hr['n'],"GF/m":hr['gf'],"GA/m":hr['ga'],"PPG":hr['ppg'],"BTTS %":hr['btts'],"O2.5 %":hr['over25']},{"Team":away.name,"Sample":ar['n'],"GF/m":ar['gf'],"GA/m":ar['ga'],"PPG":ar['ppg'],"BTTS %":ar['btts'],"O2.5 %":ar['over25']}]).round(2),use_container_width=True,hide_index=True)


def method_page():
    st.markdown('<div class="brand">Soccerform method</div>',unsafe_allow_html=True);st.caption("FootyStats paste → mathematical prediction")
    st.markdown('<div class="card"><div class="kick">Expected goals</div><p>Venue-specific goals scored/conceded, venue xG/xGA, last-10 overall, last-10 at the relevant venue, season context and a small H2H adjustment.</p><div class="divider"></div><div class="kick">1X2</div><p>62% Poisson/Dixon-Coles · 20% recent/venue form · 13% attack-v-defence · 5% H2H.</p><div class="divider"></div><div class="kick">BTTS & O/U 2.5</div><p>58% Poisson goal model · 24% home/away empirical tendency · 14% last-10 tendency · 4% H2H.</p><div class="divider"></div><p><b>No bookmaker odds are used.</b> H2H is deliberately low-weight so one old result cannot dominate.</p></div>',unsafe_allow_html=True)


def nav():
    st.markdown('<div class="divider"></div>',unsafe_allow_html=True);c1,c2=st.columns(2)
    with c1:
        if st.button("⚽ Predict",use_container_width=True,type="primary" if st.session_state.sf_page!="method" else "secondary"):st.session_state.sf_page="input";st.rerun()
    with c2:
        if st.button("📊 Method",use_container_width=True,type="primary" if st.session_state.sf_page=="method" else "secondary"):st.session_state.sf_page="method";st.rerun()

{"input":input_page,"match":match_page,"why":why_page,"method":method_page}.get(st.session_state.sf_page,input_page)();nav()
