from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class HarnessStart:
    finish_pos: Optional[int] = None
    field_size: Optional[int] = None
    finish_status: str = ""
    margin_m: Optional[float] = None
    date_raw: str = ""
    date: Optional[datetime] = None
    track: str = ""
    race_desc: str = ""
    class_score: Optional[float] = None
    prize: Optional[float] = None
    currency: str = ""
    distance_m: Optional[int] = None
    surface: str = ""
    going: str = ""
    driver: str = ""
    draw: str = ""
    sp: Optional[float] = None
    winner: str = ""
    raw: str = ""


@dataclass
class HarnessRunner:
    number: int
    name: str
    form: str = ""
    age: Optional[int] = None
    sex: str = ""
    draw: str = ""
    driver: str = ""
    trainer: str = ""
    odds: Optional[float] = None
    scratched: bool = False
    career_starts: int = 0
    career_wins: int = 0
    career_seconds: int = 0
    career_thirds: int = 0
    course_starts: int = 0
    course_wins: int = 0
    course_seconds: int = 0
    course_thirds: int = 0
    last12_starts: int = 0
    last12_wins: int = 0
    last12_seconds: int = 0
    last12_thirds: int = 0
    dist_starts: int = 0
    dist_wins: int = 0
    dist_seconds: int = 0
    dist_thirds: int = 0
    win_pct: Optional[float] = None
    place_pct: Optional[float] = None
    past_starts: list[HarnessStart] = field(default_factory=list)
    raw: str = ""


@dataclass
class HarnessRace:
    race_no: Optional[int]
    time: str
    name: str
    country: str
    age_condition: str
    race_type: str
    current_class_score: Optional[float]
    prize: Optional[float]
    currency: str
    distance_m: Optional[int]
    surface: str
    going: str
    fastest_time: str
    runners: list[HarnessRunner]
    source_text: str = ""


_RUNNER_LINK_RE = re.compile(
    r"\[\*\*(.+?)\*\*\]\((https?://www\.racingandsports\.com\.au/harness/runner/[^)]+)\)",
    re.I,
)


def _clean(value: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value or "")
    s = s.replace("**", "").replace("######", "").replace("##", "").replace("#", "")
    s = s.replace("\xa0", " ").replace("\u202f", " ").replace("\\:", ":")
    return re.sub(r"\s+", " ", s).strip()


def _money(value: str) -> Optional[float]:
    if not value:
        return None
    m = re.search(r"(?:AUD\s*\$|EUR\s*€|\$|€)\s*([\d,.]+)\s*([kKmM]?)", value)
    if not m:
        return None
    try:
        x = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = m.group(2).lower()
    if suffix == "k":
        x *= 1000
    elif suffix == "m":
        x *= 1_000_000
    return x


def _odds(value: str) -> Optional[float]:
    if not value:
        return None
    m = re.search(r"\$\s*(\d+(?:\.\d+)?)", value)
    if not m:
        return None
    x = float(m.group(1))
    return x if x > 1.0 else None


def _country_currency(raw: str) -> tuple[str, str]:
    u = raw.upper()
    if "/HARNESS/FRANCE/" in u or "EUR €" in u or "EUR " in u:
        return "FRANCE", "EUR"
    if "/HARNESS/AUSTRALIA/" in u or "AUD $" in u or "AUD " in u:
        return "AUSTRALIA", "AUD"
    return "", ""


def _france_letter_level(desc: str) -> Optional[float]:
    u = _clean(desc).upper()
    m = re.search(r"(?:^|\s)([A-H])\s*(\d{1,3})(?:\s+HCP)?(?:\s|$)", u)
    if not m:
        return None
    idx = ord(m.group(1)) - ord("A")
    return 100.0 - 10.0 * idx + min(4.0, max(-4.0, (float(m.group(2)) - 20.0) / 10.0))


def class_strength(desc: str, prize: Optional[float], country: str) -> Optional[float]:
    if country == "FRANCE":
        base = _france_letter_level(desc)
        if base is None and prize is None:
            return None
        if base is None:
            base = 50.0
        if prize:
            base += 5.5 * math.log(max(prize, 4000.0) / 20000.0)
        return base
    if country == "AUSTRALIA":
        if prize is None:
            return 50.0
        return 50.0 + 13.0 * math.log(max(prize, 2500.0) / 9400.0)
    return None


def _record(section: str, label: str) -> tuple[int, int, int, int]:
    m = re.search(rf"\b{re.escape(label)}\s*\**\s*(\d+)\s*:\s*(\d+)\s+(\d+)\s+(\d+)", section, re.I)
    return tuple(map(int, m.groups())) if m else (0, 0, 0, 0)


def _pct(section: str) -> tuple[Optional[float], Optional[float]]:
    m = re.search(r"W%\s*-\s*P%\s*\**\s*(\d+(?:\.\d+)?)%\s*-\s*(\d+(?:\.\d+)?)%", section, re.I)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


def _date(raw: str) -> Optional[datetime]:
    for fmt in ("%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            pass
    return None


def _strip_cell(cell: str) -> str:
    return _clean(cell.strip())


def _parse_finish(cell: str) -> tuple[Optional[int], Optional[int], str]:
    c = _clean(cell).upper()
    m = re.search(r"(\d+)\s+OF\s+(\d+)", c)
    if m:
        return int(m.group(1)), int(m.group(2)), ""
    for code in ("DQG", "DQ", "FF", "F", "PU", "UR"):
        if re.search(rf"\b{code}\b", c):
            return None, None, code
    return None, None, ""


def _parse_margin(cell: str) -> Optional[float]:
    m = re.search(r"([\d.]+)\s*m\b", _clean(cell), re.I)
    return float(m.group(1)) if m else None


def _parse_draw(value: str) -> str:
    s = _clean(value)
    m = re.search(r"\b(?:Fr|Sr)\s*\d+\b|\bFT\b|\b\d+\s*m(?:\s+Fr\d+)?\b", s, re.I)
    return re.sub(r"\s+", "", m.group(0)) if m else ""


def _parse_table_starts(section: str, country: str) -> list[HarnessStart]:
    starts: list[HarnessStart] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not re.search(r"\d{2}-[A-Za-z]{3}-\d{4}", line):
            continue
        cells = [_strip_cell(c) for c in line.strip("|").split("|")]
        if len(cells) < 10:
            continue
        finish_pos, field_size, finish_status = _parse_finish(cells[0])
        margin = _parse_margin(cells[1])
        date_raw = cells[2]
        track = cells[3].split()[0].upper() if cells[3] else ""
        race_desc = cells[4]
        prize = _money(cells[5])
        currency = "EUR" if "EUR" in cells[5].upper() else ("AUD" if "AUD" in cells[5].upper() else "")
        dm = re.search(r"(\d{3,4})m\b", cells[6], re.I)
        distance = int(dm.group(1)) if dm else None
        sg = cells[7].upper().split()
        surface = sg[0] if sg else ""
        going = sg[1] if len(sg) > 1 else ""
        driver = _clean(cells[8])
        rem = cells[9:]
        draw = ""
        sp = None
        winner = ""
        if rem:
            sp_idx = next((i for i, x in enumerate(rem) if re.search(r"\$\s*\d", x)), None)
            if sp_idx is not None:
                if sp_idx > 0:
                    draw = _parse_draw(" ".join(rem[:sp_idx]))
                sp = _odds(rem[sp_idx])
                winner = rem[sp_idx + 1] if sp_idx + 1 < len(rem) else ""
            elif len(rem) >= 2:
                draw = _parse_draw(rem[0])
                winner = rem[-1]
            elif len(rem) == 1:
                winner = rem[0]
        starts.append(HarnessStart(
            finish_pos=finish_pos, field_size=field_size, finish_status=finish_status,
            margin_m=margin, date_raw=date_raw, date=_date(date_raw), track=track,
            race_desc=race_desc, class_score=class_strength(race_desc, prize, country),
            prize=prize, currency=currency, distance_m=distance, surface=surface, going=going,
            driver=driver, draw=draw, sp=sp, winner=winner, raw=raw_line,
        ))
    return starts


def _parse_plain_starts(section: str, country: str) -> list[HarnessStart]:
    starts: list[HarnessStart] = []
    for raw_line in section.splitlines():
        line = _clean(raw_line)
        if not re.search(r"\d{2}-[A-Za-z]{3}-\d{4}", line) or raw_line.strip().startswith("|"):
            continue
        fm = re.match(r"(?:(\d+)\s+of\s+(\d+)|(DQG|DQ|FF|F|PU|UR))\s+([\d.]+m|99m)?\s*(\d{2}-[A-Za-z]{3}-\d{4})\s+(\S+)\s+(.+)", line, re.I)
        if not fm:
            continue
        finish_pos = int(fm.group(1)) if fm.group(1) else None
        field_size = int(fm.group(2)) if fm.group(2) else None
        status = (fm.group(3) or "").upper()
        margin = _parse_margin(fm.group(4) or "")
        date_raw = fm.group(5)
        track = fm.group(6).upper()
        rest = fm.group(7)
        pm = re.search(r"((?:AUD\s*\$|EUR\s*€)[\d,.]+\s*[kKmM]?)", rest)
        prize = _money(pm.group(1)) if pm else None
        currency = "EUR" if pm and "EUR" in pm.group(1).upper() else ("AUD" if pm else "")
        dm = re.search(r"\b(\d{3,4})m\b", rest)
        distance = int(dm.group(1)) if dm else None
        sp_matches = re.findall(r"\$\s*(\d+(?:\.\d+)?)", rest)
        sp = float(sp_matches[-1]) if sp_matches else None
        race_desc = rest[:pm.start()].strip() if pm else ""
        starts.append(HarnessStart(
            finish_pos=finish_pos, field_size=field_size, finish_status=status,
            margin_m=margin, date_raw=date_raw, date=_date(date_raw), track=track,
            race_desc=race_desc, class_score=class_strength(race_desc, prize, country),
            prize=prize, currency=currency, distance_m=distance, sp=sp, raw=raw_line,
        ))
    return starts


def _form_before(text: str, position: int) -> str:
    pre = text[max(0, position - 700):position]
    vals = re.findall(r"(?m)^\s*\**\s*([0-9xX]{2,12})\s*\**\s*$", pre)
    return vals[-1] if vals else ""


def _number_before(text: str, position: int) -> Optional[int]:
    pre = text[max(0, position - 900):position]
    vals = re.findall(r"(?m)^\s*\*\*(\d{1,2})\*\*\s*$", pre)
    if vals:
        return int(vals[-1])
    vals = re.findall(r"(?m)^\s*(\d{1,2})\s*$", pre)
    return int(vals[-1]) if vals else None


def _current_draw(segment: str, driver_start: Optional[int]) -> str:
    before = segment[:driver_start] if driver_start is not None else segment[:1200]
    vals = re.findall(r"(?mi)^\s*\**\s*((?:Fr|Sr)\d+|FT|\d+m)\s*\**\s*$", before)
    return vals[-1] if vals else ""


def _runner_segment(name: str, number: int, form: str, segment: str, country: str) -> HarnessRunner:
    dmatch = re.search(r"\[([^\]]+)\]\(https?://www\.racingandsports\.com\.au/harness/driver/", segment, re.I)
    tmatch = re.search(r"\[([^\]]+)\]\(https?://www\.racingandsports\.com\.au/harness/trainer/", segment, re.I)
    driver = _clean(dmatch.group(1)) if dmatch else ""
    trainer = _clean(tmatch.group(1)) if tmatch else ""
    draw = _current_draw(segment, dmatch.start() if dmatch else None)
    om = re.search(r"\*\*\$(\d+(?:\.\d+)?)\*\*", segment)
    odds = float(om.group(1)) if om else None
    scratched = bool(re.search(r"\*\*\s*Scratched\s*\*\*", segment, re.I))
    detail = re.search(r"######\s+(\d+)yo\s+(.+?)\s+\|", segment, re.I)
    age = int(detail.group(1)) if detail else None
    sex = _clean(detail.group(2)) if detail else ""
    career = _record(segment, "Career")
    course = _record(segment, "Course")
    last12 = _record(segment, "Last 12m")
    dist = _record(segment, "Dist")
    win_pct, place_pct = _pct(segment)
    starts = _parse_table_starts(segment, country) or _parse_plain_starts(segment, country)
    return HarnessRunner(
        number=number, name=_clean(name), form=form, age=age, sex=sex, draw=draw,
        driver=driver, trainer=trainer, odds=odds, scratched=scratched,
        career_starts=career[0], career_wins=career[1], career_seconds=career[2], career_thirds=career[3],
        course_starts=course[0], course_wins=course[1], course_seconds=course[2], course_thirds=course[3],
        last12_starts=last12[0], last12_wins=last12[1], last12_seconds=last12[2], last12_thirds=last12[3],
        dist_starts=dist[0], dist_wins=dist[1], dist_seconds=dist[2], dist_thirds=dist[3],
        win_pct=win_pct, place_pct=place_pct, past_starts=starts, raw=segment,
    )


def _plain_meaningful_lines(raw: str) -> list[tuple[int, str]]:
    out = []
    pos = 0
    for line in raw.splitlines(True):
        stripped = _clean(line)
        if stripped and not re.fullmatch(r"[:\-\s|]+", stripped):
            out.append((pos, stripped))
        pos += len(line)
    return out


def _plain_runner_candidates(raw: str) -> list[tuple[int, int, str, str]]:
    visible = _plain_meaningful_lines(raw)
    candidates = []
    for i in range(len(visible) - 4):
        pos, line = visible[i]
        if not re.fullmatch(r"\d{1,2}", line):
            continue
        n = int(line)
        if not 1 <= n <= 30:
            continue
        form = visible[i + 1][1]
        if not re.fullmatch(r"[0-9xX]{2,12}", form):
            continue
        name = visible[i + 2][1]
        if not re.fullmatch(r"[A-Za-zÀ-ÿ0-9'’.\- ]{2,60}(?:\s*\([A-Z]{2,3}\))?", name):
            continue
        if name.upper() in {"DRIVER", "TRAINER", "TRAINERPP", "SHARE", "FULL FIELDS"}:
            continue
        candidates.append((visible[i + 2][0], n, form, name))
    seen = set()
    out = []
    for c in candidates:
        if c[1] in seen:
            continue
        seen.add(c[1])
        out.append(c)
    return out


def _plain_runner_segment(name: str, number: int, form: str, segment: str, country: str) -> HarnessRunner:
    visible = [x for _, x in _plain_meaningful_lines(segment)]
    try:
        ni = next(i for i, x in enumerate(visible) if x.upper() == _clean(name).upper())
    except StopIteration:
        ni = 0
    age = None
    sex = ""
    draw = ""
    driver = ""
    trainer = ""
    odds = None
    om0 = re.search(r"(?m)^\s*\$(\d+(?:\.\d+)?)\s*$", segment)
    if om0:
        odds = float(om0.group(1))
    for j in range(ni + 1, min(len(visible), ni + 12)):
        x = visible[j]
        am = re.fullmatch(r"(\d{1,2})([A-Z]{1,3})", x.upper())
        if am and age is None:
            age = int(am.group(1))
            sex = am.group(2)
            continue
        if not draw and re.fullmatch(r"(?:Fr|Sr)\d+|FT|\d+m", x, re.I):
            draw = x
            continue
        if odds is None and re.fullmatch(r"\$\d+(?:\.\d+)?", x):
            odds = _odds(x)
    chart_idx = next((i for i in range(ni + 1, min(len(visible), ni + 30)) if visible[i].lower().startswith("chart")), None)
    stop_idx = chart_idx if chart_idx is not None else min(len(visible), ni + 20)
    prior = []
    for x in visible[ni + 1:stop_idx]:
        if re.fullmatch(r"(\d{1,2})([A-Z]{1,3})|(?:Fr|Sr)\d+|FT|\d+m", x, re.I):
            continue
        if x.upper() in {"TRK", "DIST", "CD", "AW", "TURF", "LBF", "FU", "WET", "SAND"}:
            continue
        if re.fullmatch(r"[+-]?\d+%", x):
            continue
        prior.append(x)
    name_like = [x for x in prior if re.fullmatch(r"[A-Za-zÀ-ÿ0-9'’.\-& ]{2,80}", x)]
    if len(name_like) >= 2:
        driver, trainer = name_like[-2], name_like[-1]
    scratched = bool(re.search(r"\bScratched\b", segment, re.I))
    career = _record(segment, "Career")
    course = _record(segment, "Course")
    last12 = _record(segment, "Last 12m")
    dist = _record(segment, "Dist")
    win_pct, place_pct = _pct(segment)
    starts = _parse_table_starts(segment, country) or _parse_plain_starts(segment, country)
    return HarnessRunner(
        number=number, name=_clean(name), form=form, age=age, sex=sex, draw=draw,
        driver=driver, trainer=trainer, odds=odds, scratched=scratched,
        career_starts=career[0], career_wins=career[1], career_seconds=career[2], career_thirds=career[3],
        course_starts=course[0], course_wins=course[1], course_seconds=course[2], course_thirds=course[3],
        last12_starts=last12[0], last12_wins=last12[1], last12_seconds=last12[2], last12_thirds=last12[3],
        dist_starts=dist[0], dist_wins=dist[1], dist_seconds=dist[2], dist_thirds=dist[3],
        win_pct=win_pct, place_pct=place_pct, past_starts=starts, raw=segment,
    )


def parse_harness_race(text: str) -> HarnessRace:
    raw = (text or "").replace("\u202f", " ").replace("\xa0", " ")
    if len(raw.strip()) < 300:
        raise ValueError("Paste the complete Racing & Sports harness race page.")
    country, currency = _country_currency(raw)
    race_no = None
    header_anchor = raw.find("Full Fields")
    search_head = raw[header_anchor:header_anchor + 5000] if header_anchor >= 0 else raw[:5000]
    rn = re.search(r"(?m)^\s*\*\*(\d{1,2})\*\*\s*$", search_head)
    tm = re.search(r"(?m)^\s*(\d{1,2}:\d{2})\s*$", search_head)
    race_time = tm.group(1) if tm else ""
    nm = re.search(r"(?m)^##\s+(.+?)\s*$", raw)
    if nm and ("Monday," in nm.group(1) or "Form Guide" in nm.group(1)):
        nms = re.findall(r"(?m)^##\s+(.+?)\s*$", raw)
        nm_text = next((x for x in nms if not re.search(r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday", x, re.I)), nms[-1] if nms else "Harness Race")
    else:
        nm_text = nm.group(1) if nm else ""
    if not rn or not nm_text:
        vis = _plain_meaningful_lines(search_head)
        for i in range(len(vis) - 3):
            if re.fullmatch(r"\d{1,2}", vis[i][1]) and re.fullmatch(r"\d{1,2}:\d{2}", vis[i + 1][1]):
                if "(LOCAL)" in vis[i + 2][1].upper():
                    if not rn:
                        race_no = int(vis[i][1])
                    if not race_time:
                        race_time = vis[i + 1][1]
                    if not nm_text:
                        nm_text = vis[i + 3][1]
                    break
    if rn:
        race_no = int(rn.group(1))
    name = _clean(nm_text) if nm_text else "Harness Race"
    age_match = re.search(r"Age:\s*\**(.+?)\**\s+(?:WT:|Fastest Time:|Type:)", raw, re.I)
    age_condition = _clean(age_match.group(1)) if age_match else ""
    type_match = re.search(r"Type:\s*\**(.+?)\**\s+Fastest Time:", raw, re.I)
    race_type = _clean(type_match.group(1)) if type_match else ""
    fastest = re.search(r"Fastest Time:\s*\**([^*\n]+)", raw, re.I)
    fastest_time = _clean(fastest.group(1)) if fastest else ""
    prize_match = re.search(r"\**\s*((?:AUD\s*\$|EUR\s*€)[\d,]+(?:\.\d+)?)\s*\**", raw)
    prize = _money(prize_match.group(1)) if prize_match else None
    detail = re.search(r"(?m)^\s*(\d{3,4})m\s+([A-Z ]+?)(?:\s+(GOOD|SOFT|HEAVY|FAST|SLOW|NORMAL))?\s*$", raw, re.I)
    distance = int(detail.group(1)) if detail else None
    surface = _clean(detail.group(2)).upper() if detail else ""
    going = (detail.group(3) or "").upper() if detail else ""
    current_class = class_strength(race_type or name, prize, country)
    matches = list(_RUNNER_LINK_RE.finditer(raw))
    runners = []
    if matches:
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else raw.find("Computer Selection Panels", m.end())
            if end < 0:
                end = len(raw)
            seg = raw[m.start():end]
            num = _number_before(raw, m.start()) or i + 1
            form = _form_before(raw, m.start())
            runners.append(_runner_segment(m.group(1), num, form, seg, country))
    else:
        candidates = _plain_runner_candidates(raw)
        if not candidates:
            raise ValueError("No harness runners were found in the pasted Racing & Sports data.")
        for i, (pos, num, form, rname) in enumerate(candidates):
            end = candidates[i + 1][0] if i + 1 < len(candidates) else raw.find("Computer Selection Panels", pos)
            if end < 0:
                end = len(raw)
            runners.append(_plain_runner_segment(rname, num, form, raw[pos:end], country))
    seen = set()
    uniq = []
    for r in runners:
        if r.number in seen:
            continue
        seen.add(r.number)
        uniq.append(r)
    runners = uniq
    if not runners:
        raise ValueError("No harness runners were parsed.")
    if not any(not r.scratched for r in runners):
        raise ValueError("All parsed runners are marked scratched.")
    return HarnessRace(
        race_no=race_no, time=race_time, name=name, country=country,
        age_condition=age_condition, race_type=race_type, current_class_score=current_class,
        prize=prize, currency=currency, distance_m=distance, surface=surface, going=going,
        fastest_time=fastest_time, runners=runners, source_text=raw,
    )
