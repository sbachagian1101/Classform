from __future__ import annotations

import math
from dataclasses import dataclass, field

from soccer_parser import TeamProfile, MatchResult, recent_summary, h2h_matches, canonical_team


@dataclass
class SoccerPrediction:
    home: str
    away: str
    home_xg: float
    away_xg: float
    home_win: float
    draw: float
    away_win: float
    btts_yes: float
    btts_no: float
    over25: float
    under25: float
    home_attack_index: float
    home_def_weakness: float
    away_attack_index: float
    away_def_weakness: float
    confidence: str
    likely_scores: list[tuple[str, float]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    diagnostics: dict[str, float] = field(default_factory=dict)
    h2h: list[MatchResult] = field(default_factory=list)


def _clip(x, lo, hi): return max(lo, min(hi, float(x)))
def _mean(*values, default=1.5):
    xs=[float(x) for x in values if x is not None]
    return sum(xs)/len(xs) if xs else default

def _pct(value, default=50.0): return default if value is None else float(value)
def _poisson(k, lam): return math.exp(-lam)*(lam**k)/math.factorial(k)


def _score_matrix(lh, la, rho=-0.06, max_goals=10):
    matrix={}
    for h in range(max_goals+1):
        for a in range(max_goals+1):
            p=_poisson(h,lh)*_poisson(a,la)
            if h==0 and a==0: p*=max(0.01,1-lh*la*rho)
            elif h==0 and a==1: p*=max(0.01,1+lh*rho)
            elif h==1 and a==0: p*=max(0.01,1+la*rho)
            elif h==1 and a==1: p*=max(0.01,1-rho)
            matrix[(h,a)]=p
    total=sum(matrix.values()) or 1.0
    return {k:v/total for k,v in matrix.items()}


def _three_way(matrix):
    return (
        sum(p for (h,a),p in matrix.items() if h>a),
        sum(p for (h,a),p in matrix.items() if h==a),
        sum(p for (h,a),p in matrix.items() if h<a),
    )


def _norm3(values):
    total=sum(values) or 1.0
    return tuple(v/total for v in values)


def _form_1x2(home, away, hr, ar):
    hp=0.38*_mean(home.ppg_home,default=1.5)+0.27*_mean(home.ppg_overall,default=1.5)+0.35*_mean(hr.get('ppg'),default=1.5)
    ap=0.38*_mean(away.ppg_away,default=1.5)+0.27*_mean(away.ppg_overall,default=1.5)+0.35*_mean(ar.get('ppg'),default=1.5)
    diff=_clip(hp-ap,-2,2)
    h=math.exp(0.72*diff); a=math.exp(-0.72*diff)
    goal_hint=_mean(home.avg_goals[1] if len(home.avg_goals)>1 else None, away.avg_goals[2] if len(away.avg_goals)>2 else None, default=3.0)
    d=_clip(1.05-0.07*(goal_hint-2.5),0.50,1.05)
    return _norm3((h,d,a)),hp,ap


def _attack_defence_1x2(lh,la):
    diff=_clip(lh-la,-3,3)
    return _norm3((math.exp(0.55*diff),_clip(0.92-0.045*(lh+la-2.5),0.48,1.0),math.exp(-0.55*diff)))


def _h2h_1x2(home,matches):
    if not matches:return (1/3,1/3,1/3)
    hk=canonical_team(home.name); h=d=a=1.2
    weights=[0.75,0.55,0.40,0.30,0.22]
    for w,m in zip(weights,matches):
        if canonical_team(m.home)==hk: hg,ag=m.home_goals,m.away_goals
        else: hg,ag=m.away_goals,m.home_goals
        if hg>ag:h+=3*w
        elif hg==ag:d+=3*w
        else:a+=3*w
    return _norm3((h,d,a))


def _blend3(parts):
    return _norm3(tuple(sum(w*p[i] for w,p in parts) for i in range(3)))


def _team_index(attack_actual,attack_xg,weak_actual,weak_xg):
    attack_signal=0.58*attack_actual+0.42*attack_xg
    weak_signal=0.58*weak_actual+0.42*weak_xg
    return _clip(50+18*(attack_signal-1.5),5,95),_clip(50+16*(weak_signal-1.5),5,95)


def _recent_rates(hr,ar):
    b=[x for x in (hr.get('btts'),ar.get('btts')) if x is not None]
    o=[x for x in (hr.get('over25'),ar.get('over25')) if x is not None]
    return ((sum(b)/len(b) if b else 50)/100,(sum(o)/len(o) if o else 50)/100)


def _h2h_goal_rates(home,matches):
    if not matches:return None,None
    hk=canonical_team(home.name); b=o=0
    for m in matches:
        if canonical_team(m.home)==hk:hg,ag=m.home_goals,m.away_goals
        else:hg,ag=m.away_goals,m.home_goals
        b+=int(hg>0 and ag>0); o+=int(hg+ag>2)
    return b/len(matches),o/len(matches)


def analyse_match(home: TeamProfile, away: TeamProfile) -> SoccerPrediction:
    hr10=recent_summary(home,10); ar10=recent_summary(away,10)
    hrv=recent_summary(home,10,'home'); arv=recent_summary(away,10,'away')
    h2h=h2h_matches(home,away,5)

    h_actual=_mean(home.gf[1] if len(home.gf)>1 else None,away.ga[2] if len(away.ga)>2 else None)
    a_actual=_mean(away.gf[2] if len(away.gf)>2 else None,home.ga[1] if len(home.ga)>1 else None)
    h_xg=_mean(home.xgf[1] if len(home.xgf)>1 else None,away.xga[2] if len(away.xga)>2 else None)
    a_xg=_mean(away.xgf[2] if len(away.xgf)>2 else None,home.xga[1] if len(home.xga)>1 else None)
    h_recent=_mean(hr10.get('gf'),ar10.get('ga'),default=h_actual)
    a_recent=_mean(ar10.get('gf'),hr10.get('ga'),default=a_actual)
    h_vrecent=_mean(hrv.get('gf'),arv.get('ga'),default=h_actual)
    a_vrecent=_mean(arv.get('gf'),hrv.get('ga'),default=a_actual)
    h_overall=_mean(home.gf[0] if home.gf else None,away.ga[0] if away.ga else None)
    a_overall=_mean(away.gf[0] if away.gf else None,home.ga[0] if home.ga else None)

    lh=0.28*h_actual+0.28*h_xg+0.20*h_recent+0.14*h_vrecent+0.10*h_overall
    la=0.28*a_actual+0.28*a_xg+0.20*a_recent+0.14*a_vrecent+0.10*a_overall

    if h2h:
        hk=canonical_team(home.name); hg=[];ag=[]
        for m in h2h:
            if canonical_team(m.home)==hk: hg.append(m.home_goals);ag.append(m.away_goals)
            else: hg.append(m.away_goals);ag.append(m.home_goals)
        shrink=min(0.07,0.025*len(h2h))
        lh=(1-shrink)*lh+shrink*(sum(hg)/len(hg)); la=(1-shrink)*la+shrink*(sum(ag)/len(ag))

    lh=_clip(lh,0.2,4.6); la=_clip(la,0.2,4.6)
    matrix=_score_matrix(lh,la)
    poisson=_three_way(matrix)
    form,hp,ap=_form_1x2(home,away,hr10,ar10)
    ad=_attack_defence_1x2(lh,la); h2hp=_h2h_1x2(home,h2h)
    final=_blend3([(0.62,poisson),(0.20,form),(0.13,ad),(0.05,h2hp)])

    pbtts=1-math.exp(-lh)-math.exp(-la)+math.exp(-(lh+la))
    pover=1-sum(_poisson(t,lh+la) for t in range(3))
    venue_btts=(_pct(home.btts[1] if len(home.btts)>1 else None)+_pct(away.btts[2] if len(away.btts)>2 else None))/200
    venue_o25=(_pct(home.over25[1] if len(home.over25)>1 else None)+_pct(away.over25[2] if len(away.over25)>2 else None))/200
    recent_btts,recent_o25=_recent_rates(hr10,ar10)
    hb,ho=_h2h_goal_rates(home,h2h)
    if hb is None:hb,ho=recent_btts,recent_o25
    btts=_clip(0.58*pbtts+0.24*venue_btts+0.14*recent_btts+0.04*hb,0.03,0.97)
    over=_clip(0.58*pover+0.24*venue_o25+0.14*recent_o25+0.04*ho,0.03,0.97)

    h_attack,h_weak=_team_index(_mean(home.gf[1] if len(home.gf)>1 else None,hr10.get('gf')),_mean(home.xgf[1] if len(home.xgf)>1 else None,home.xgf[0] if home.xgf else None),_mean(home.ga[1] if len(home.ga)>1 else None,hr10.get('ga')),_mean(home.xga[1] if len(home.xga)>1 else None,home.xga[0] if home.xga else None))
    a_attack,a_weak=_team_index(_mean(away.gf[2] if len(away.gf)>2 else None,ar10.get('gf')),_mean(away.xgf[2] if len(away.xgf)>2 else None,away.xgf[0] if away.xgf else None),_mean(away.ga[2] if len(away.ga)>2 else None,ar10.get('ga')),_mean(away.xga[2] if len(away.xga)>2 else None,away.xga[0] if away.xga else None))

    scores=sorted(((f'{h}-{a}',p) for (h,a),p in matrix.items()),key=lambda x:x[1],reverse=True)[:6]
    evidence=[
        f'Expected goals: {home.name} {lh:.2f} - {la:.2f} {away.name}.',
        f'Venue scoring/conceding signal: {home.name} {h_actual:.2f}; {away.name} {a_actual:.2f}.',
        f'Venue xG/xGA signal: {home.name} {h_xg:.2f}; {away.name} {a_xg:.2f}.',
        f'Last 10 overall PPG: {home.name} {hr10.get("ppg") or 0:.2f}; {away.name} {ar10.get("ppg") or 0:.2f}.',
        f'Home/away season PPG: {home.name} {home.ppg_home or 0:.2f}; {away.name} {away.ppg_away or 0:.2f}.',
        f'Venue BTTS tendency: {venue_btts*100:.0f}%; venue Over 2.5 tendency: {venue_o25*100:.0f}%.',
    ]
    if h2h:
        m=h2h[0]; evidence.append(f'Recent H2H included with low weight: {m.home} {m.home_goals}-{m.away_goals} {m.away}.')

    available=sum(x is not None for x in [home.gf[1],home.ga[1],home.xgf[1],home.xga[1],away.gf[2],away.ga[2],away.xgf[2],away.xga[2],home.over25[1],home.btts[1],away.over25[2],away.btts[2]])
    ordered=sorted(final,reverse=True);gap=ordered[0]-ordered[1]
    confidence='High' if available>=10 and gap>=0.12 else ('Medium' if available>=8 and gap>=0.05 else 'Cautious')

    return SoccerPrediction(home.name,away.name,lh,la,final[0],final[1],final[2],btts,1-btts,over,1-over,h_attack,h_weak,a_attack,a_weak,confidence,scores,evidence,{
        'Poisson Home':poisson[0],'Poisson Draw':poisson[1],'Poisson Away':poisson[2],
        'Form Home':form[0],'Form Draw':form[1],'Form Away':form[2],
        'Home form PPG index':hp,'Away form PPG index':ap,
        'Poisson BTTS':pbtts,'Poisson Over 2.5':pover,'Venue BTTS':venue_btts,'Venue Over 2.5':venue_o25,
    },h2h)
