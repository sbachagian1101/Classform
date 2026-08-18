from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional
from scoreform_parser import Race, Runner, PastRun, StatTriplet, _norm_name

WEIGHTS={"Horse Suitability":30.,"Recent Form & Fitness":20.,"Ability & Class":15.,"Jockey":10.,"Trainer":10.,"Race Setup":10.,"Head-to-Head":5.}
CAPS={"Horse Suitability":20.,"Recent Form & Fitness":15.,"Ability & Class":15.,"Jockey":10.,"Trainer":10.,"Race Setup":10.,"Head-to-Head":3.}

@dataclass
class Evidence:
    component:str; subcriterion:str; points:float; text:str; source:str=""; available:bool=True
@dataclass
class RunnerScore:
    number:int; horse:str; odds:Optional[float]; raw:dict[str,float]; weighted:dict[str,float]; total:float
    win_pct:float=0.; rank:int=0; evidence:list[Evidence]=field(default_factory=list); coverage_pct:float=0.; running_style:str="Unknown"; latest_ohr:Optional[int]=None

def cap(v,c): return max(-c,min(c,v))
def add(ev,c,s,p,t,src=""): ev.append(Evidence(c,s,p,t,src,True)); return p
def miss(ev,c,s,t): ev.append(Evidence(c,s,0.,t,"",False)); return 0.
def stat(r,k)->Optional[StatTriplet]: return r.filters.get(k)
def runs(r,n=5):
    x=[p for p in r.past_runs if p.date]
    return sorted(x,key=lambda p:p.date,reverse=True)[:n] if x else r.past_runs[:n]
def days(race,p): return max(0,(race.date.date()-p.date.date()).days) if race.date and p.date else None
def latest_ohr(r):
    for p in runs(r,10):
        if p.ohr is not None:return p.ohr
    return None
def race_type(race):
    u=(race.race_type+" "+race.name).upper()
    if "HCP" in u or "HANDICAP" in u:return "HCP"
    if "MAIDEN" in u or "MDN" in u:return "MDN"
    if "NOVICE" in u or " NOV" in u:return "NOV"
    if "CLASSIFIED" in u or "OPEN" in u:return "OPEN"
    return ""

def suitability(race,r,ev):
    c="Horse Suitability"; z=0.
    d=stat(r,"Dist")
    if d and d.starts:
        if d.wins:z+=add(ev,c,"Distance",3,f"Won at today's distance: {d.wins}-{d.places}-{d.starts}.","Filters: Dist"); z+=add(ev,c,"Distance strike rate",2,f"Strong distance win rate ({d.win_rate:.0%}).","Filters: Dist") if d.starts>=4 and d.win_rate>=.25 else 0
        elif d.places:z+=add(ev,c,"Distance",2,f"Placed at today's distance: {d.wins}-{d.places}-{d.starts}.","Filters: Dist"); z+=add(ev,c,"Distance consistency",1,f"Strong distance place rate ({d.place_rate:.0%}).","Filters: Dist") if d.starts>=3 and d.place_rate>=.5 else 0
        elif d.starts>=3:z+=add(ev,c,"Distance",-2,f"No placing from {d.starts} runs at today's distance.","Filters: Dist")
    else: miss(ev,c,"Distance","No reliable distance filter.")
    sk="AW" if race.surface=="AW" else "Turf" if race.surface=="TURF" else "Dirt" if race.surface=="DIRT" else ""; s=stat(r,sk) if sk else None
    if s and s.starts:
        if s.wins:z+=add(ev,c,"Surface",3,f"Won on today's {race.surface} surface ({s.wins}-{s.places}-{s.starts}).",f"Filters: {sk}"); z+=add(ev,c,"Surface record",1,"Strong overall record on today's surface.",f"Filters: {sk}") if s.starts>=4 and (s.win_rate>=.2 or s.place_rate>=.5) else 0
        elif s.places:z+=add(ev,c,"Surface",2,f"Placed on today's {race.surface} surface ({s.wins}-{s.places}-{s.starts}).",f"Filters: {sk}")
        elif s.starts>=3:z+=add(ev,c,"Surface",-2,f"No placing from {s.starts} starts on today's surface.",f"Filters: {sk}")
    else: miss(ev,c,"Surface","No reliable surface filter.")
    g=[p for p in r.past_runs if race.going and p.going==race.going and p.surface==race.surface]
    gw=[p for p in g if p.is_win]; gp=[p for p in g if p.is_place]
    if gw:z+=add(ev,c,"Going",3,f"Won on today's going ({race.going}) on the same surface.",gw[0].date_raw)
    elif gp:z+=add(ev,c,"Going",2,f"Placed on today's going ({race.going}) on the same surface.",gp[0].date_raw)
    elif len(g)>=3:z+=add(ev,c,"Going",-2,f"Repeated failures on today's going ({len(g)} runs).","Historical runs")
    else:miss(ev,c,"Going",f"Insufficient exact {race.going or 'going'} evidence.")
    cd,cr=stat(r,"Crs & Dist"),stat(r,"Crs")
    if cd and cd.starts and (cd.wins or cd.places): z+=add(ev,c,"Course & distance",3 if cd.wins else 2,f"Course-distance {'win' if cd.wins else 'placing'} evidence ({cd.wins}-{cd.places}-{cd.starts}).","Filters: Crs & Dist")
    elif cr and cr.starts:
        if cr.wins:z+=add(ev,c,"Course",2,f"Course winner ({cr.wins}-{cr.places}-{cr.starts}).","Filters: Crs")
        elif cr.places:z+=add(ev,c,"Course",1,f"Placed at course ({cr.wins}-{cr.places}-{cr.starts}).","Filters: Crs")
        elif cr.starts>=3:z+=add(ev,c,"Course",-1.5,f"Multiple course failures ({cr.starts}).","Filters: Crs")
    else:miss(ev,c,"Course","No course evidence.")
    typ=race_type(race); tr=[p for p in r.past_races if p.race_type==typ] if hasattr(r,"past_races") and typ else [p for p in r.past_runs if p.race_type==typ] if typ else []
    tw=[p for p in tr if p.is_win]; tp=[p for p in tr if p.is_place]
    if tw:z+=add(ev,c,"Race condition/type",2,f"Won under the same broad race type ({typ}).",tw[0].date_raw)
    elif tp:z+=add(ev,c,"Race condition/type",1,f"Placed under the same broad race type ({typ}).",tp[0].date_raw)
    elif len(tr)>=4:z+=add(ev,c,"Race condition/type",-1,f"Repeatedly unplaced in {typ} races.","Historical runs")
    else:miss(ev,c,"Race condition/type",f"Insufficient {typ or 'race-type'} evidence.")
    good=[p for p in runs(r,8) if p.is_place and p.weight is not None]
    if r.weight is not None:
        hw=[p for p in good if p.is_win and p.weight>=r.weight-.1]; hp=[p for p in good if p.weight>=r.weight-.1]
        if hw:z+=add(ev,c,"Weight history",2,f"Won carrying {hw[0].weight:.1f}kg, at least today's {r.weight:.1f}kg.",hw[0].date_raw)
        elif hp:z+=add(ev,c,"Weight history",1,f"Placed carrying {hp[0].weight:.1f}kg, at least today's {r.weight:.1f}kg.",hp[0].date_raw)
        else:miss(ev,c,"Weight history","No comparable win/place at today's weight or higher.")
        if good:
            delta=good[0].weight-r.weight; p=2 if delta>=3 else 1 if delta>=1 else -2 if delta<=-3 else -1 if delta<=-1 else 0
            if p:z+=add(ev,c,"Weight change",p,f"Carries {abs(delta):.1f}kg {'less' if delta>0 else 'more'} than latest strong run.",good[0].date_raw)
            else:miss(ev,c,"Weight change","Today's weight is broadly similar to latest strong run.")
    return cap(z,CAPS[c])

def form_score(race,r,ev):
    c="Recent Form & Fitness";z=0.; rr=runs(r,5)
    q=[]
    for p in rr:
        d=days(race,p)
        if d is not None and d<=90 and p.is_place:q.append((d,p))
    if q:
        d,p=min(q,key=lambda x:x[0]); win=p.is_win
        pts=(4 if win else 2) if d<=14 else (3 if win else 2) if d<=30 else (2 if win else 1) if d<=60 else (1 if win else .5)
        z+=add(ev,c,"Recent result",pts,f"Finished {p.finish_pos}/{p.field_size or '?'} {d} days ago.",p.date_raw)
    else:miss(ev,c,"Recent result","No win/place within 90 days.")
    vals=[]; ws=[5,4,3,2,1]
    for i,p in enumerate(rr):
        if p.finish_pos and p.field_size and p.field_size>1:vals.append((1-(p.finish_pos-1)/(p.field_size-1),ws[i]))
    if vals:
        x=sum(a*w for a,w in vals)/sum(w for _,w in vals); pts=3 if x>=.8 else 2 if x>=.65 else .5 if x>=.45 else -1 if x>=.3 else -2
        z+=add(ev,c,"Last-5 trend",pts,f"Weighted last-5 form index {x:.2f}.","Last 5 runs")
    else:miss(ev,c,"Last-5 trend","Insufficient last-5 field-size data.")
    top=sum(p.is_place for p in rr)
    if len(rr)>=3:
        pts=3 if top>=4 else 2 if top==3 else 1 if top==2 else -2 if top==0 else 0
        z+=add(ev,c,"Consistency",pts,f"{top} top-3 finish(es) in last {len(rr)} runs.","Last 5 runs") if pts else 0
    mr=next((p for p in rr if (days(race,p) or 999)<=90 and p.is_place and p.margin is not None),None)
    if mr:
        pts=2 if mr.is_win and mr.margin>=3 else 1 if (mr.is_win and mr.margin>=1) or (not mr.is_win and mr.margin<=1) else -1 if (not mr.is_win and mr.margin>5) else 0
        if pts:z+=add(ev,c,"Finishing margin",pts,f"Recent {'win' if mr.is_win else 'placing'} margin: {mr.margin:.1f}L.",mr.date_raw)
    d=r.dls
    if d is not None:
        fu=stat(r,"FU")
        if d>120 and fu and fu.starts>=3 and (fu.wins or fu.place_rate>=.4):miss(ev,c,"Fitness / DLS",f"Long break ({d}d) but proven first-up profile; neutral.")
        else:
            pts=2 if 7<=d<=21 else 1 if 22<=d<=35 else 0 if 36<=d<=60 else -1 if d<=120 else -2
            z+=add(ev,c,"Fitness / DLS",pts,f"{d} days since last run.","DLS") if pts else miss(ev,c,"Fitness / DLS",f"{d} days since last run: neutral band.")
    key=r.current_stage.upper() if r.current_stage.upper() in {"FU","2U","3U"} else ""; ss=stat(r,key) if key else None
    if ss and ss.starts:
        if ss.wins or ss.place_rate>=.5:z+=add(ev,c,"Campaign stage",2,f"Strong {key} profile ({ss.wins}-{ss.places}-{ss.starts}).",f"Filters: {key}")
        elif ss.starts>=3 and not ss.places:z+=add(ev,c,"Campaign stage",-1,f"Poor {key} profile.",f"Filters: {key}")
    else:miss(ev,c,"Campaign stage","No directly comparable FU/2U/3U evidence.")
    return cap(z,CAPS[c])

def ability(race,r,ohrs,ev):
    c="Ability & Class";z=0.; miss(ev,c,"Class performance","R&S UK 'Class 3 HCP/3U OPEN' is often an age/race-condition code, not a trustworthy UK Class 1-7 ladder; no fabricated class points."); miss(ev,c,"Class movement today","No reliable current-vs-prior UK class ladder in this paste.")
    o=latest_ohr(r)
    if o is not None and ohrs:
        order=sorted(ohrs,reverse=True);avg=sum(ohrs)/len(ohrs);rk=order.index(o)+1;pts=3 if o==order[0] else 2 if rk<=3 else 1 if o>avg else -2 if o<avg-8 else 0
        z+=add(ev,c,"Official rating",pts,f"Latest OHR {o}; field average {avg:.1f}.","Latest parsed OHR") if pts else miss(ev,c,"Official rating",f"Latest OHR {o}; neutral relative to field.")
    else:miss(ev,c,"Official rating","No comparable OHR field set.")
    miss(ev,c,"Speed/performance","No normalized speed figure is supplied; raw times are not compared across tracks/distances.")
    v=[p.ongoing_wins/p.ongoing_starts for p in runs(r,3) if p.ongoing_starts and p.ongoing_wins is not None]
    if v:
        x=sum(v)/len(v);pts=2 if x>=.25 else 1 if x>=.1 else -1 if x==0 and len(v)>=2 else 0
        z+=add(ev,c,"Strength of opposition",pts,f"Recent subsequent-winner rate {x:.0%}.","Ongoing Winners") if pts else miss(ev,c,"Strength of opposition",f"Subsequent-winner rate {x:.0%}: neutral.")
    else:miss(ev,c,"Strength of opposition","No ongoing-winner evidence.")
    return cap(z,CAPS[c])

def jockey(r,ev):
    c="Jockey";z=0.
    if r.jh_starts:
        if (r.jh_win or 0)>0:z+=add(ev,c,"Horse/Jockey",2,f"Jockey has won with horse (J/H {r.jh_win:.0%}).","J/H")
        elif (r.jh_place or 0)>0:z+=add(ev,c,"Horse/Jockey",1,f"Jockey has placed with horse (J/H {r.jh_place:.0%}).","J/H")
    else:miss(ev,c,"Horse/Jockey","No prior J/H sample.")
    miss(ev,c,"Last 10 mounts","Actual jockey last 10 rides are not contained in this pasted page; criterion left neutral.")
    jw=r.jockey_last50_win
    if jw is not None:
        pts=2 if jw>=.2 else 1 if jw>=.15 else -1 if jw<.05 else 0
        z+=add(ev,c,"Overall strike rate",pts,f"Jockey Last50 win rate {jw:.0%}.","Jockey Last50") if pts else miss(ev,c,"Overall strike rate",f"Jockey Last50 {jw:.0%}: neutral.")
    miss(ev,c,"Course record","Jockey course stats are not supplied in this paste.")
    jt=r.jt_win
    if jt is not None:
        pts=3 if jt>=.2 else 2 if jt>=.15 else 1 if jt>=.1 else -1 if jt<.05 else 0
        z+=add(ev,c,"Jockey/Trainer",pts,f"J/T win rate {jt:.0%}.","J/T") if pts else miss(ev,c,"Jockey/Trainer",f"J/T {jt:.0%}: neutral.")
    cl=r.jockey_claim
    if cl:
        pts=2 if jw is not None and jw>=.15 and cl>=1.5 else 1 if jw is not None and jw>=.05 else -1 if jw is not None and jw<.05 else 0
        z+=add(ev,c,"Apprentice claim",pts,f"Apprentice claim {cl:g} with jockey Last50 profile.","Field table") if pts else miss(ev,c,"Apprentice claim","Claim detected but evidence insufficient to grade.")
    else:miss(ev,c,"Apprentice claim","No apprentice claim detected.")
    return cap(z,CAPS[c])

def trainer(r,ev):
    c="Trainer";z=0.;tw=r.trainer_last50_win
    if tw is not None:
        pts=3 if tw>=.2 else 2 if tw>=.15 else 1 if tw>=.1 else -1 if tw<.05 else 0
        z+=add(ev,c,"Recent trainer form",pts,f"Trainer Last50 win rate {tw:.0%}.","Trainer Last50") if pts else miss(ev,c,"Recent trainer form",f"Trainer Last50 {tw:.0%}: neutral.")
    else:miss(ev,c,"Recent trainer form","Trainer Last50 not parsed.")
    miss(ev,c,"Trainer/Course","Trainer course stats are not supplied."); miss(ev,c,"Trainer/Jockey","J/T is scored once under Jockey to avoid double-counting.")
    cur=_norm_name(r.trainer); tr=[p for p in runs(r,8) if cur and _norm_name(p.trainer)==cur and p.ohr is not None]
    if len(tr)>=2:
        delta=tr[0].ohr-tr[-1].ohr;pts=2 if delta>=5 else 1 if delta>=-3 else -1 if delta<=-8 else 0
        z+=add(ev,c,"Horse under trainer",pts,f"Current-trainer OHR {tr[-1].ohr} → {tr[0].ohr}.","Historical OHR") if pts else miss(ev,c,"Horse under trainer","Current-trainer OHR trend: neutral.")
    else:miss(ev,c,"Horse under trainer","Insufficient current-trainer OHR history.")
    return cap(z,CAPS[c])

def style(r):
    v=[(p.settling_pos-1)/(p.field_size-1) for p in runs(r,4) if p.settling_pos and p.field_size and p.field_size>1]
    if not v:return "Unknown"
    x=sum(v)/len(v);return "Leader" if x<=.2 else "On-pace" if x<=.42 else "Midfield" if x<=.68 else "Backmarker"
def setup(r,styles,ev):
    c="Race Setup";z=0.;miss(ev,c,"Barrier / draw","Barrier is parsed/displayed but neutral until a track×distance×field-size draw-bias database is added.")
    s=styles.get(r.number,"Unknown"); leaders=sum(x in {"Leader","On-pace"} for x in styles.values());known=sum(x!="Unknown" for x in styles.values())
    if s=="Unknown" or known<3:miss(ev,c,"Pace setup","Insufficient settling-position data for a dependable pace map.")
    else:
        pts=(3 if s=="Leader" else 2 if s=="On-pace" else 0) if leaders<=1 else (1 if s in {"On-pace","Midfield"} else 0) if leaders<=3 else (2 if s=="Backmarker" else 1 if s=="Midfield" else -2 if s=="Leader" else 0)
        z+=add(ev,c,"Pace setup",pts,f"Projected pace pressure: {leaders} leader/on-pace runner(s); style {s}.","Inrunning positions") if pts else miss(ev,c,"Pace setup",f"Pace map neutral for {s} style.")
    miss(ev,c,"Running style / track","No track-specific style bias database yet.");miss(ev,c,"Field/setup","No external field-size bias database in v1.");return cap(z,CAPS[c])
def h2h(r,ev):
    c="Head-to-Head";z=0.;name=_norm_name(r.horse);w=l=dec=meet=0
    for m in r.h2h:
        me=next((x for x in m.entries if _norm_name(x[1])==name),None)
        if not me or len(m.entries)<2:continue
        meet+=1
        for o in m.entries:
            if _norm_name(o[1])==name:continue
            if me[0]<o[0]:w+=1;dec+=int(o[0]-me[0]>=3)
            elif me[0]>o[0]:l+=1
    if w:z+=add(ev,c,"Head-to-head",2 if w>=2 else 1,f"Finished ahead of today's rivals {w} time(s) in parsed H2H.","Head to Head")
    if l>=2 and l>w:z+=add(ev,c,"Head-to-head",-1.5,f"Repeated H2H losses ({l}).","Head to Head")
    if dec:z+=add(ev,c,"Head-to-head margin",1,"At least one clearly superior H2H finishing-position result.","Head to Head")
    if not meet:miss(ev,c,"Head-to-head","No usable H2H meeting supplied.")
    return cap(z,CAPS[c])
def coverage(ev):
    d={}
    for e in ev:d[(e.component,e.subcriterion)]=d.get((e.component,e.subcriterion),False) or e.available
    return 100*sum(d.values())/len(d) if d else 0.
def analyse_race(race):
    o=[x for x in (latest_ohr(r) for r in race.runners) if x is not None];styles={r.number:style(r) for r in race.runners};out=[]
    for r in race.runners:
        ev=[];raw={"Horse Suitability":suitability(race,r,ev),"Recent Form & Fitness":form_score(race,r,ev),"Ability & Class":ability(race,r,o,ev),"Jockey":jockey(r,ev),"Trainer":trainer(r,ev),"Race Setup":setup(r,styles,ev),"Head-to-Head":h2h(r,ev)}
        weighted={k:cap(raw[k],CAPS[k])/CAPS[k]*WEIGHTS[k] for k in WEIGHTS};out.append(RunnerScore(r.number,r.horse,r.odds,raw,weighted,sum(weighted.values()),evidence=ev,coverage_pct=coverage(ev),running_style=styles[r.number],latest_ohr=latest_ohr(r)))
    if out:
        mx=max(x.total for x in out);ex=[math.exp((x.total-mx)/6) for x in out];den=sum(ex) or 1
        for x,e in zip(out,ex):x.win_pct=100*e/den
    out.sort(key=lambda x:(x.total,x.coverage_pct),reverse=True)
    for i,x in enumerate(out,1):x.rank=i
    return out
def component_rows(scores):
    out=[]
    for s in scores:
        row={"Rank":s.rank,"No.":s.number,"Horse":s.horse,"Score /100":round(s.total,1),"Model Win %":round(s.win_pct,1)}
        for k in WEIGHTS:row[f"{k} raw"]=round(s.raw[k],1);row[f"{k} weighted"]=round(s.weighted[k],1)
        row["Coverage %"]=round(s.coverage_pct);out.append(row)
    return out
