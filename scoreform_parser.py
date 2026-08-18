from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class StatTriplet:
    wins: int = 0
    places: int = 0
    starts: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.starts if self.starts else 0.0

    @property
    def place_rate(self) -> float:
        return self.places / self.starts if self.starts else 0.0


@dataclass
class PastRun:
    finish_pos: Optional[int] = None
    field_size: Optional[int] = None
    campaign_stage: str = ""
    days_gap_label: str = ""
    ohr: Optional[int] = None
    race_name: str = ""
    date: Optional[datetime] = None
    date_raw: str = ""
    track: str = ""
    margin: Optional[float] = None
    distance_m: Optional[int] = None
    surface: str = ""
    going: str = ""
    class_raw: str = ""
    race_type: str = ""
    prize_raw: str = ""
    api: Optional[float] = None
    race_time: str = ""
    jockey: str = ""
    trainer: str = ""
    weight: Optional[float] = None
    barrier: Optional[int] = None
    ongoing_wins: Optional[int] = None
    ongoing_places: Optional[int] = None
    ongoing_starts: Optional[int] = None
    settling_pos: Optional[int] = None
    raw: str = ""

    @property
    def is_win(self) -> bool:
        return self.finish_pos == 1

    @property
    def is_place(self) -> bool:
        return self.finish_pos is not None and 1 <= self.finish_pos <= 3


@dataclass
class H2HMeeting:
    meeting: str
    entries: list[tuple[int, str, Optional[float]]] = field(default_factory=list)


@dataclass
class Runner:
    number: int
    horse: str
    form: str = ""
    odds: Optional[float] = None
    age_sex: str = ""
    weight: Optional[float] = None
    barrier: Optional[int] = None
    jockey: str = ""
    jockey_claim: Optional[float] = None
    jockey_last50_win: Optional[float] = None
    jockey_last50_place: Optional[float] = None
    trainer: str = ""
    trainer_last50_win: Optional[float] = None
    trainer_last50_place: Optional[float] = None
    jh_win: Optional[float] = None
    jh_place: Optional[float] = None
    jh_starts: Optional[int] = None
    jt_win: Optional[float] = None
    jt_place: Optional[float] = None
    jt_starts: Optional[int] = None
    filters: dict[str, StatTriplet] = field(default_factory=dict)
    dls: Optional[int] = None
    current_stage: str = ""
    dod: Optional[float] = None
    past_runs: list[PastRun] = field(default_factory=list)
    h2h: list[H2HMeeting] = field(default_factory=list)
    raw: str = ""


@dataclass
class Race:
    race_no: Optional[int] = None
    date: Optional[datetime] = None
    date_raw: str = ""
    time: str = ""
    track: str = ""
    name: str = ""
    age: str = ""
    weight_condition: str = ""
    race_type: str = ""
    distance_raw: str = ""
    distance_m: Optional[int] = None
    surface: str = ""
    going: str = ""
    prize_raw: str = ""
    runners: list[Runner] = field(default_factory=list)
    source_text: str = ""


GOING_ALIASES = {
    "STANDARD": "N",
    "N": "N",
    "STANDARD TO SLOW": "NS",
    "STANDARD/SLOW": "NS",
    "NS": "NS",
    "GOOD TO FIRM": "GF",
    "GOOD-FIRM": "GF",
    "GF": "GF",
    "GOOD": "G",
    "G": "G",
    "GOOD TO SOFT": "GS",
    "GOOD-SOFT": "GS",
    "GS": "GS",
    "SOFT": "S",
    "S": "S",
    "HEAVY": "H",
    "H": "H",
    "SOFT-HEAVY": "SH",
    "SH": "SH",
}


def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\u00a0", " ").replace("\u202f", " ")).strip()


def _norm_name(s: str) -> str:
    return _norm_space(s).upper().replace("’", "'")


def _norm_surface(s: str) -> str:
    u = _norm_space(s).upper()
    if u in {"AW", "ALL WEATHER", "ALL-WEATHER", "SYNTHETIC"}:
        return "AW"
    if u in {"T", "TURF"}:
        return "TURF"
    if "DIRT" in u:
        return "DIRT"
    return u


def _norm_going(s: str) -> str:
    u = _norm_space(s).upper().replace("–", "-").replace("—", "-")
    return GOING_ALIASES.get(u, u)


def _parse_float(s: str) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def _parse_date_long(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = _norm_space(s)
    for fmt in ("%d %b %Y", "%d %B %Y", "%d/%b/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _parse_imperial_distance(raw: str) -> Optional[int]:
    if not raw:
        return None
    s = raw.lower().replace(" ", "")
    m = re.fullmatch(r"(\d{3,5})m", s)
    if m:
        return int(m.group(1))
    miles = furlongs = yards = 0
    mm = re.search(r"(\d+)m", s)
    ff = re.search(r"(\d+)f", s)
    yy = re.search(r"(\d+)y", s)
    if mm:
        miles = int(mm.group(1))
    if ff:
        furlongs = int(ff.group(1))
    if yy:
        yards = int(yy.group(1))
    if miles or furlongs or yards:
        return int(round(miles * 1609.344 + furlongs * 201.168 + yards * 0.9144))
    return None


def _stat(text: str, label: str) -> Optional[StatTriplet]:
    pat = rf"(?i)(?:^|\n|(?<=\d)){re.escape(label)}\s*\n?\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)"
    m = re.search(pat, text)
    return StatTriplet(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _parse_percent_triplet(text: str, label: str) -> tuple[Optional[float], Optional[float], Optional[int]]:
    m = re.search(rf"(?i){re.escape(label)}\s*([0-9]+(?:\.[0-9]+)?)%\s*-\s*([0-9]+(?:\.[0-9]+)?)%\s*-\s*(\d+)", text)
    if not m:
        return None, None, None
    return float(m.group(1)) / 100.0, float(m.group(2)) / 100.0, int(m.group(3))


def _find_runner_starts(text: str) -> list[tuple[int, int, str, str, Optional[float], str, int, float]]:
    pat = re.compile(
        r"(?ms)^\s*(?P<num>\d{1,2})\s*\n"
        r"\s*(?P<form>[0-9xXpPfFuUrRbBdD-]{1,14})\s*\n"
        r"\s*(?:betfair\$\s*(?P<odds>[0-9]+(?:\.[0-9]+)?)\s*\n)?"
        r"\s*(?P<horse>[A-Z][A-Z0-9'’ .&\-/]+?)\s+"
        r"(?P<age>\d+yo\s+[A-Z]{1,3}(?:\s+(?:Gelding|Mare|Filly|Horse|Colt))?)\s*"
        r"\(BP:\s*(?P<bp>\d{1,2})\)\s*(?P<wt>[0-9]+(?:\.[0-9]+)?)kg\s*$"
    )
    out = []
    for m in pat.finditer(text):
        out.append((m.start(), int(m.group("num")), m.group("form"), _norm_space(m.group("horse")), _parse_float(m.group("odds")), _norm_space(m.group("age")), int(m.group("bp")), float(m.group("wt"))))
    return out


def _parse_field_table(text: str) -> dict[int, dict]:
    pre = text.split("Explanations", 1)[0]
    rows: dict[int, dict] = {}
    for raw in pre.splitlines():
        if "\t" not in raw:
            continue
        cells = [_norm_space(c) for c in raw.split("\t") if _norm_space(c)]
        if len(cells) < 7 or not re.fullmatch(r"\d{1,2}", cells[0]):
            continue
        num = int(cells[0])
        mw = re.search(r"\|\s*([0-9]+(?:\.[0-9]+)?)", cells[2])
        wt = float(mw.group(1)) if mw else None
        bp = int(cells[3]) if re.fullmatch(r"\d{1,2}", cells[3]) else None
        jockey = cells[4]
        claim = None
        mc = re.search(r"\(a\s*([0-9]+(?:\.[0-9]+)?)\)", jockey, re.I)
        if mc:
            claim = float(mc.group(1))
            jockey = re.sub(r"\s*\(a[^)]*\)", "", jockey, flags=re.I).strip()
        rows[num] = {"horse": cells[1], "weight": wt, "barrier": bp, "jockey": jockey, "claim": claim, "trainer": cells[6], "odds": _parse_float(cells[-1])}
    return rows


def _parse_past_run_segment(seg: str) -> Optional[PastRun]:
    head = re.match(r"(?ms)^\s*(\d{1,2})\s+of\s+(\d{1,2})\s*\n(.*)$", seg)
    if not head:
        return None
    pos, field, rest = int(head.group(1)), int(head.group(2)), head.group(3)
    stage = gap = ""
    mstage = re.search(r"(?m)^\s*([A-Z0-9]+)\s*-\s*([^\n]+)\s*$", rest)
    if mstage:
        stage, gap = _norm_space(mstage.group(1)), _norm_space(mstage.group(2))
    ohr = None
    race_name = ""
    mohr = re.search(r"(?m)^\s*(\d{2,3})\s*\n\s*OHR\s*\n\s*([^\n]+)", rest)
    if mohr:
        ohr, race_name = int(mohr.group(1)), _norm_space(mohr.group(2))
    mdetail = re.search(r"(?m)^\s*(\d{2}\s+[A-Za-z]{3}\s+\d{4})\s+(.+)$", rest)
    if not mdetail:
        return PastRun(finish_pos=pos, field_size=field, campaign_stage=stage, days_gap_label=gap, ohr=ohr, race_name=race_name, raw=seg)
    date_raw, detail = mdetail.group(1), _norm_space(mdetail.group(2))
    mt = re.match(r"(.+?)\s*:\s*Margin\b", detail) or re.match(r"(.+?)\s+(?:Margin|Distance|Surface|SOT|Class)\b", detail)
    track = _norm_space(mt.group(1)) if mt else ""
    def grab(pattern: str) -> Optional[str]:
        m = re.search(pattern, detail, re.I)
        return _norm_space(m.group(1)) if m else None
    margin = _parse_float(grab(r"\bMargin\s+([0-9]+(?:\.[0-9]+)?)L"))
    dist = grab(r"\bDistance\s+(\d{3,5})m\b")
    surface = grab(r"\bSurface\s+([A-Z]+)\b") or ""
    going = grab(r"\bSOT\s+([A-Z]+)\b") or ""
    class_raw = grab(r"\bClass\s+(.+?)\s+Prize\b") or ""
    prize = grab(r"\bPrize\s+(.+?)(?:\s+Prize Won|\s+API|\s+Race Time)\b") or ""
    api = _parse_float(grab(r"\bAPI\s+([0-9]+(?:\.[0-9]+)?)"))
    race_time = grab(r"\bRace Time\s+([0-9]+:[0-9]+(?:\.[0-9]+)?)") or ""
    jockey = grab(r"\bJockey\s+(.+?)\s+Weight\b") or ""
    weight = _parse_float(grab(r"\bWeight\s+([0-9]+(?:\.[0-9]+)?)\b"))
    bp = grab(r"\bBP\s+(\d{1,2}|-)\b")
    barrier = int(bp) if bp and bp.isdigit() else None
    trainer = grab(r"\bTrainer\s+(.+?)\s+Ongoing Winners\b") or ""
    ow = op = os = None
    mow = re.search(r"\bOngoing Winners\s+(\d{2})-(\d{2})-(\d{2})\b", detail, re.I)
    if mow:
        ow, op, os = map(int, mow.groups())
    settling = None
    ms = re.search(r"\bInrunning Position\s+(\d{1,2})(?:st|nd|rd|th)\s+Place\s+on\s+settling\b", detail, re.I)
    if ms:
        settling = int(ms.group(1))
    uclass = class_raw.upper()
    if "HCP" in uclass:
        rtype = "HCP"
    elif "MDN" in uclass or "MAIDEN" in race_name.upper():
        rtype = "MDN"
    elif "NOV" in uclass or "NOVICE" in race_name.upper():
        rtype = "NOV"
    elif "OPEN" in uclass:
        rtype = "OPEN"
    elif "APP" in uclass:
        rtype = "APP"
    else:
        rtype = ""
    return PastRun(finish_pos=pos, field_size=field, campaign_stage=stage, days_gap_label=gap, ohr=ohr, race_name=race_name, date=_parse_date_long(date_raw), date_raw=date_raw, track=track, margin=margin, distance_m=int(dist) if dist else None, surface=_norm_surface(surface), going=_norm_going(going), class_raw=class_raw, race_type=rtype, prize_raw=prize, api=api, race_time=race_time, jockey=jockey, trainer=trainer, weight=weight, barrier=barrier, ongoing_wins=ow, ongoing_places=op, ongoing_starts=os, settling_pos=settling, raw=seg)


def _parse_past_runs(block: str) -> list[PastRun]:
    hist = block.split("Head to Head", 1)[0]
    anchors = list(re.finditer(r"(?m)^\s*\d{1,2}\s+of\s+\d{1,2}\s*$", hist))
    runs: list[PastRun] = []
    for i, m in enumerate(anchors):
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(hist)
        run = _parse_past_run_segment(hist[m.start():end])
        if run:
            runs.append(run)
    return runs


def _parse_h2h(block: str) -> list[H2HMeeting]:
    if "Head to Head" not in block:
        return []
    text = block.split("Head to Head", 1)[1]
    text = re.sub(r"^.*?last 2 years\)\s*", "", text, count=1, flags=re.I | re.S)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    meetings: list[H2HMeeting] = []
    current: Optional[H2HMeeting] = None
    header_re = re.compile(r"^(.+?\s+-\s+\d{2}/[A-Za-z]{3}/\d{4})$")
    entry_re = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)\s+-([A-Z][A-Z0-9'’ .&\-/]+?)\s+([0-9]+(?:\.[0-9]+)?)L\b", re.I)
    for line in lines:
        if header_re.match(line):
            current = H2HMeeting(meeting=_norm_space(line)); meetings.append(current); continue
        me = entry_re.match(line)
        if me and current is not None:
            current.entries.append((int(me.group(1)), _norm_space(me.group(2)), float(me.group(3))))
    return meetings


def _parse_runner_block(number: int, form: str, horse: str, odds: Optional[float], age_sex: str, barrier: int, weight: float, block: str, table_row: dict) -> Runner:
    r = Runner(number=number, horse=horse, form=form, odds=odds, age_sex=age_sex, barrier=barrier, weight=weight, raw=block)
    if table_row:
        r.weight = table_row.get("weight") or r.weight
        r.barrier = table_row.get("barrier") or r.barrier
        r.odds = r.odds if r.odds is not None else table_row.get("odds")
        r.jockey_claim = table_row.get("claim")
        r.jockey = table_row.get("jockey") or r.jockey
        r.trainer = table_row.get("trainer") or r.trainer
    mj = re.search(r"(?ms)\bJockey\s*\n?\s*([A-Z][A-Z .&'’\-/]+?)\s*\n?\s*Last50\s*([0-9.]+)%\s*-\s*([0-9.]+)%\s*-\s*50", block)
    if mj:
        r.jockey = r.jockey or _norm_space(mj.group(1)); r.jockey_last50_win = float(mj.group(2)) / 100.0; r.jockey_last50_place = float(mj.group(3)) / 100.0
    mt = re.search(r"(?ms)\bTrainer\s*\n?\s*([A-Z][A-Z0-9 .&'’\-/]+?)\s*\n?\s*Last50\s*([0-9.]+)%\s*-\s*([0-9.]+)%\s*-\s*50", block)
    if mt:
        r.trainer = r.trainer or _norm_space(mt.group(1)); r.trainer_last50_win = float(mt.group(2)) / 100.0; r.trainer_last50_place = float(mt.group(3)) / 100.0
    r.jh_win, r.jh_place, r.jh_starts = _parse_percent_triplet(block, "J/H")
    r.jt_win, r.jt_place, r.jt_starts = _parse_percent_triplet(block, "J/T")
    for label in ["Car", "12m", "Crs", "Dist", "Crs & Dist", "Firm", "Good", "Soft", "Heavy", "AW", "Turf", "FU", "2U", "3U", "ClockW", "AClockW", "Dirt", "Sand"]:
        s = _stat(block, label)
        if s:
            r.filters[label] = s
    mdls = re.search(r"\bDLS\s*\n?\s*(\d+)", block, re.I)
    if mdls:
        r.dls = int(mdls.group(1))
    mstage = re.search(r"Days Since Last Run:\s*\d+\s*days\s*\(([^)]+)\)", block, re.I)
    if mstage:
        r.current_stage = _norm_space(mstage.group(1))
    mdod = re.search(r"\bDOD\s*\n?\s*(-?[0-9]+(?:\.[0-9]+)?)", block, re.I)
    if mdod:
        r.dod = float(mdod.group(1))
    r.past_runs = _parse_past_runs(block)
    r.h2h = _parse_h2h(block)
    return r


def parse_race(text: str) -> Race:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    race = Race(source_text=raw)
    mr = re.search(r"Form Guide\s*\(Race\s*(\d{1,2})\)", raw, re.I)
    if mr:
        race.race_no = int(mr.group(1))
    mt = re.search(r"(?m)^\s*(\d{1,2}:\d{2})\s*$", raw)
    if mt:
        race.time = mt.group(1)
    mtrack = re.search(r"(?mi)^\s*([A-Za-z][A-Za-z .'-]+)\s+Form Guide\s*\(Race", raw)
    if mtrack:
        race.track = _norm_space(mtrack.group(1))
    md = re.search(r"(?mi)^\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})\s*$", raw)
    if md:
        race.date_raw = f"{md.group(1)} {md.group(2)} {md.group(3)}"; race.date = _parse_date_long(race.date_raw)
    mh = re.search(r"(?ms)^\s*([^\n]+)\s*\n\s*Age:\s*(.*?)\s+WT:\s*(.*?)\s+Type:\s*(.*?)(?:\s+Fastest Time:|\n)", raw)
    if mh:
        race.name = _norm_space(mh.group(1)); race.age = _norm_space(mh.group(2)); race.weight_condition = _norm_space(mh.group(3)); race.race_type = _norm_space(mh.group(4)).upper()
    ml = re.search(r"(?mi)^\s*((?:\d+m)?(?:\d+f)?(?:\d+y)?|\d{3,5}m)\s+(ALL WEATHER|TURF|DIRT)\s+([A-Z][A-Z /-]*)\s*$", raw)
    if ml:
        race.distance_raw = ml.group(1); race.distance_m = _parse_imperial_distance(race.distance_raw); race.surface = _norm_surface(ml.group(2)); race.going = _norm_going(ml.group(3))
    mp = re.search(r"(?mi)^\s*((?:GBP|EUR|AUD|NZD|USD|ZAR)\s*[£€$R]?\s*[0-9,]+(?:\.[0-9]+)?)\s*$", raw)
    if mp:
        race.prize_raw = _norm_space(mp.group(1))
    table = _parse_field_table(raw)
    starts = _find_runner_starts(raw)
    for i, meta in enumerate(starts):
        start, number, form, horse, odds, age_sex, bp, wt = meta
        end = starts[i + 1][0] if i + 1 < len(starts) else len(raw)
        race.runners.append(_parse_runner_block(number, form, horse, odds, age_sex, bp, wt, raw[start:end], table.get(number, {})))
    return race
