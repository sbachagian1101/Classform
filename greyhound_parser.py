from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class GreyhoundStart:
    finish_pos: Optional[int] = None
    field_size: Optional[int] = None
    finish_status: str = ""
    margin: Optional[float] = None
    date_raw: str = ""
    date: Optional[datetime] = None
    track: str = ""
    grade_label: str = ""
    grade_num: Optional[float] = None
    prize: Optional[float] = None
    distance_m: Optional[int] = None
    surface: str = ""
    going: str = ""
    box: Optional[int] = None
    sp: Optional[float] = None
    sectional: Optional[float] = None
    winner: str = ""
    raw: str = ""


@dataclass
class GreyhoundRunner:
    name: str
    box: Optional[int]
    trainer: str = ""
    odds: Optional[float] = None
    form: str = ""
    age: Optional[int] = None
    sex: str = ""
    scratched: bool = False
    career_starts: int = 0
    career_wins: int = 0
    career_seconds: int = 0
    career_thirds: int = 0
    course_starts: int = 0
    course_wins: int = 0
    course_seconds: int = 0
    course_thirds: int = 0
    dist_starts: int = 0
    dist_wins: int = 0
    dist_seconds: int = 0
    dist_thirds: int = 0
    win_pct: Optional[float] = None
    place_pct: Optional[float] = None
    past_starts: list[GreyhoundStart] = field(default_factory=list)
    raw: str = ""


@dataclass
class GreyhoundRace:
    race_no: Optional[int]
    time: str
    name: str
    grade_label: str
    grade_num: Optional[float]
    prize: Optional[float]
    distance_m: Optional[int]
    surface: str
    going: str
    fastest_time: str
    runners: list[GreyhoundRunner]
    source_text: str = ""


_RUNNER_LINK_RE = re.compile(
    r"\[\*\*(.+?)\*\*\]\((https?://www\.racingandsports\.com\.au/greyhound/runner/[^)]+)\)",
    re.I,
)
_FORM_LINE_RE = re.compile(r"^[0-9xX]{3,10}$")

_STOP_LINES = {
    "TRK", "DIST", "CD", "AW", "WET", "TURF", "FU", "LBF", "TOP", "BOOKMAKER",
    "CHART", "SHARE", "IMPACT", "STATISTICS", "FULL FIELDS", "ODDS COMPARISON",
    "BEST ODDS FLUC", "RUNNER DETAILS", "SCRATCHED",
}


def _clean_md(value: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value or "")
    s = s.replace("**", "").replace("######", "").replace("##", "")
    s = s.replace("\xa0", " ").replace("\u202f", " ").replace("\\:", ":")
    return re.sub(r"\s+", " ", s).strip()


def _money(value: str) -> Optional[float]:
    if not value:
        return None
    m = re.search(r"\$?\s*([\d,.]+)\s*([kKmM]?)", value)
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    suffix = m.group(2).lower()
    if suffix == "k":
        amount *= 1000.0
    elif suffix == "m":
        amount *= 1_000_000.0
    return amount


def grade_value(value: str) -> tuple[Optional[float], str]:
    u = _clean_md(value).upper()
    if re.search(r"\bFFA\b", u):
        return 1.0, "FFA"
    if re.search(r"\bOPEN\b", u):
        return 1.5, "OPEN"
    m = re.search(r"\bGR(?:ADE)?\s*([1-6])(?:\s*/\s*([1-6]))?", u)
    if m:
        values = [int(m.group(1))]
        if m.group(2):
            values.append(int(m.group(2)))
        return sum(values) / len(values), "GR " + "/".join(map(str, values))
    m = re.search(r"\bLS\s*([1-6])\b", u)
    if m:
        return float(m.group(1)) + 0.2, f"LS{m.group(1)}"
    m = re.search(r"\bMX\s*([1-6])\b", u)
    if m:
        return float(m.group(1)) + 0.2, f"MX {m.group(1)}"
    m = re.search(r"\b([1-6])(?:ST|ND|RD|TH)?\s*/\s*([1-6])(?:ST|ND|RD|TH)?\s+GRADE\b", u)
    if m:
        values = [int(m.group(1)), int(m.group(2))]
        return sum(values) / 2.0, f"{values[0]}/{values[1]} Grade"
    m = re.search(r"\b([1-6])(?:ST|ND|RD|TH)?\s+GRADE\b", u)
    if m:
        return float(m.group(1)), f"{m.group(1)} Grade"
    return None, _clean_md(value)


def _record(section: str, label: str) -> tuple[int, int, int, int]:
    m = re.search(
        rf"{re.escape(label)}\s*\**\s*(\d+)\s*:\s*(\d+)\s+(\d+)\s+(\d+)\s*\**",
        section,
        re.I,
    )
    return tuple(map(int, m.groups())) if m else (0, 0, 0, 0)


def _strip_cell(cell: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cell.strip())
    s = s.replace("**", "").replace("\xa0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", s).strip()


def _past_starts_markdown(section: str) -> list[GreyhoundStart]:
    starts: list[GreyhoundStart] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or not re.search(r"\d{2}-[A-Za-z]{3}-\d{4}", line):
            continue
        cells = [_strip_cell(c) for c in line.strip("|").split("|")]
        if len(cells) < 9:
            continue
        finish_pos = field_size = None
        finish_status = ""
        fm = re.search(r"(\d+)\s+of\s+(\d+)", cells[0], re.I)
        if fm:
            finish_pos, field_size = int(fm.group(1)), int(fm.group(2))
        elif re.search(r"\bFF\b", cells[0], re.I):
            finish_status = "FF"
        mm = re.search(r"([\d.]+)L", cells[1], re.I)
        margin = float(mm.group(1)) if mm else None
        date_raw = cells[2]
        try:
            parsed_date = datetime.strptime(date_raw, "%d-%b-%Y")
        except Exception:
            parsed_date = None
        track = cells[3].split()[0].upper() if cells[3] else ""
        grade_num, grade_label = grade_value(cells[4])
        prize = _money(cells[5])
        dm = re.search(r"(\d+)m", cells[6], re.I)
        distance_m = int(dm.group(1)) if dm else None
        surf_going = cells[7].upper().split()
        surface = surf_going[0] if surf_going else ""
        going = surf_going[1] if len(surf_going) > 1 else ""
        box = int(cells[8]) if cells[8].isdigit() and 1 <= int(cells[8]) <= 8 else None
        sp = None
        if len(cells) > 9:
            om = re.search(r"\$([\d.]+)", cells[9])
            if om:
                try:
                    sp = float(om.group(1))
                except ValueError:
                    pass
        sectional = None
        if len(cells) > 10:
            sm = re.search(r"(?<!\d)(\d+\.\d+)(?!\d)", cells[10])
            if sm:
                try:
                    sectional = float(sm.group(1))
                except ValueError:
                    pass
        winner = cells[11] if len(cells) > 11 else ""
        starts.append(GreyhoundStart(
            finish_pos=finish_pos, field_size=field_size, finish_status=finish_status,
            margin=margin, date_raw=date_raw, date=parsed_date, track=track,
            grade_label=grade_label, grade_num=grade_num, prize=prize,
            distance_m=distance_m, surface=surface, going=going, box=box,
            sp=sp, sectional=sectional, winner=winner, raw=raw_line,
        ))
    return starts


def _plain_flat(section: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", section)
    s = s.replace("**", " ").replace("#", " ").replace("|", " ")
    s = s.replace("\xa0", " ").replace("\u202f", " ").replace("\\:", ":")
    s = re.sub(r"(?m)^\s*[:\- ]{3,}\s*$", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _past_starts_plain(section: str) -> list[GreyhoundStart]:
    flat = _plain_flat(section)
    grade_pat = (
        r"(?:GR(?:ADE)?\s*[1-6](?:\s*/\s*[1-6])?|LS\s*[1-6]|MX\s*[1-6]|"
        r"FFA|OPEN|[1-6](?:ST|ND|RD|TH)?(?:\s*/\s*[1-6](?:ST|ND|RD|TH)?)?\s+GRADE)"
    )
    pattern = re.compile(
        rf"(?:(?P<pos>\d+)\s+of\s+(?P<field>\d+)|(?P<status>FF))\s+"
        rf"(?P<margin>\d+(?:\.\d+)?)L\s+"
        rf"(?P<date>\d{{2}}-[A-Za-z]{{3}}-\d{{4}})\s+"
        rf"(?P<track>[A-Za-z][A-Za-z .'-]{{1,24}}?)\s+"
        rf"(?P<grade>{grade_pat})\s+"
        rf"(?P<prize>AUD\s+\$[\d,.]+[kKmM]?|-)\s+"
        rf"(?P<dist>\d{{2,4}})m\s+"
        rf"(?P<surface>AW|ALL\s+WEATHER|TURF|T)\s*"
        rf"(?P<going>GOOD|SOFT|HEAVY|G|S|H)?\s+"
        rf"(?P<box>[1-8])\s+"
        rf"\$(?P<sp>\d+(?:\.\d+)?)"
        rf"(?:\s+(?P<sectional>\d+\.\d+))?",
        re.I,
    )
    starts: list[GreyhoundStart] = []
    for m in pattern.finditer(flat):
        finish_pos = int(m.group("pos")) if m.group("pos") else None
        field_size = int(m.group("field")) if m.group("field") else None
        finish_status = (m.group("status") or "").upper()
        date_raw = m.group("date")
        try:
            parsed_date = datetime.strptime(date_raw, "%d-%b-%Y")
        except Exception:
            parsed_date = None
        grade_num, grade_label = grade_value(m.group("grade"))
        surface_raw = _clean_md(m.group("surface")).upper()
        surface = "AW" if "AW" in surface_raw or "ALL WEATHER" in surface_raw else surface_raw
        going_raw = (m.group("going") or "").upper()
        going = {"GOOD": "G", "SOFT": "S", "HEAVY": "H"}.get(going_raw, going_raw)
        starts.append(GreyhoundStart(
            finish_pos=finish_pos,
            field_size=field_size,
            finish_status=finish_status,
            margin=float(m.group("margin")) if m.group("margin") else None,
            date_raw=date_raw,
            date=parsed_date,
            track=_clean_md(m.group("track")).upper(),
            grade_label=grade_label,
            grade_num=grade_num,
            prize=_money(m.group("prize")),
            distance_m=int(m.group("dist")),
            surface=surface,
            going=going,
            box=int(m.group("box")),
            sp=float(m.group("sp")),
            sectional=float(m.group("sectional")) if m.group("sectional") else None,
            raw=m.group(0),
        ))
    return starts


def _past_starts(section: str) -> list[GreyhoundStart]:
    starts = _past_starts_markdown(section)
    return starts if starts else _past_starts_plain(section)


def _form_before(text: str, position: int) -> str:
    pre = text[max(0, position - 600):position]
    values = re.findall(r"(?m)^\s*([0-9xX]{3,10})\s*$", pre)
    return values[-1] if values else ""


def _plain_lines_with_offsets(text: str) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    offset = 0
    for raw_line in text.splitlines(keepends=True):
        cleaned = _clean_md(raw_line).strip(" |\t")
        if cleaned and not re.fullmatch(r"[:\- ]{2,}", cleaned):
            rows.append((offset, cleaned))
        offset += len(raw_line)
    return rows


def _looks_runner_name(line: str) -> bool:
    s = line.strip()
    u = s.upper()
    if not (2 <= len(s) <= 60) or u in _STOP_LINES:
        return False
    if u.startswith(("TYPE:", "FASTEST TIME:", "AUD $", "CHART ", "THE CHART", "END OF ", "CAREER", "COURSE", "LAST 12M", "FIRST UP", "SECOND UP", "SEASON", "W%")):
        return False
    if re.search(r"\d", s) or "$" in s or ":" in s:
        return False
    if not re.search(r"[A-Z]", u):
        return False
    return s == u and len(re.findall(r"[A-Z]", u)) >= 3


def _plain_runner_starts(raw: str) -> list[tuple[int, int, str, str]]:
    rows = _plain_lines_with_offsets(raw)
    anchor_idx = 0
    for i, (_, line) in enumerate(rows):
        u = line.upper()
        if "RUNNER" in u and ("FORM" in u or "BOX" in u):
            anchor_idx = i + 1
            break
        if u == "BOOKMAKER":
            anchor_idx = i + 1
    found: list[tuple[int, int, str, str]] = []
    seen_names: set[str] = set()
    for i in range(anchor_idx, len(rows)):
        start_offset, form = rows[i]
        if not _FORM_LINE_RE.fullmatch(form):
            continue
        name = ""
        name_offset = -1
        for j in range(i + 1, min(len(rows), i + 14)):
            _, candidate = rows[j]
            if _FORM_LINE_RE.fullmatch(candidate):
                break
            if _looks_runner_name(candidate):
                name = candidate
                name_offset = rows[j][0]
                break
        if not name or name in seen_names:
            continue
        preview = raw[name_offset:min(len(raw), name_offset + 1800)]
        if not re.search(r"\b\d+yo\b|\bChart\b|\bCareer\b|\bScratched\b", preview, re.I):
            continue
        found.append((start_offset, name_offset, form, name))
        seen_names.add(name)
    return found


def _trainer_plain(segment: str, runner_name: str) -> str:
    prefix = re.split(r"(?i)\bChart|\bCareer", segment, maxsplit=1)[0]
    candidates = []
    for _, line in _plain_lines_with_offsets(prefix):
        if line == runner_name or line.upper() in _STOP_LINES or _FORM_LINE_RE.fullmatch(line):
            continue
        if re.fullmatch(r"\d+[A-Z](?:/[A-Z]+)?", line, re.I) or re.fullmatch(r"[1-8]", line):
            continue
        if _looks_runner_name(line) and " " in line:
            candidates.append(line)
    return candidates[-1] if candidates else ""


def _runner_from_segment(name: str, form: str, segment: str) -> GreyhoundRunner:
    trainer_match = re.search(
        r"\[([^\]]+)\]\(https?://www\.racingandsports\.com\.au/greyhound/trainer/",
        segment,
        re.I,
    )
    trainer = trainer_match.group(1).strip() if trainer_match else _trainer_plain(segment, _clean_md(name))
    before_chart = re.split(r"(?i)\bChart|\bCareer", segment, maxsplit=1)[0]
    box_values = re.findall(r"(?m)^\s*(?:\|\s*)?([1-8])(?:\s*\|)?\s*$", before_chart)
    box = int(box_values[-1]) if box_values else None
    prefix = re.split(r"(?i)\bCareer", segment, maxsplit=1)[0]
    odds_matches = re.findall(r"\$\s*(\d+(?:\.\d+)?)", prefix)
    odds = float(odds_matches[-1]) if odds_matches else None
    scratched = bool(re.search(r"\bScratched\b", prefix, re.I))
    detail = re.search(r"(?:######\s*)?(\d+)yo\s+(.+?)(?:\s*\||\s+Sire:|\n)", segment, re.I)
    age = int(detail.group(1)) if detail else None
    sex = _clean_md(detail.group(2)) if detail else ""
    career = _record(segment, "Career")
    course = _record(segment, "Course")
    dist = _record(segment, "Dist")
    wp = re.search(r"W%\s*-\s*P%\s*\**\s*(\d+)%\s*-\s*(\d+)%\s*\**", segment, re.I)
    win_pct = float(wp.group(1)) if wp else None
    place_pct = float(wp.group(2)) if wp else None
    return GreyhoundRunner(
        name=_clean_md(name),
        box=box,
        trainer=_clean_md(trainer),
        odds=odds,
        form=form,
        age=age,
        sex=sex,
        scratched=scratched,
        career_starts=career[0], career_wins=career[1], career_seconds=career[2], career_thirds=career[3],
        course_starts=course[0], course_wins=course[1], course_seconds=course[2], course_thirds=course[3],
        dist_starts=dist[0], dist_wins=dist[1], dist_seconds=dist[2], dist_thirds=dist[3],
        win_pct=win_pct, place_pct=place_pct,
        past_starts=_past_starts(segment),
        raw=segment,
    )


def _plain_header_name(raw: str) -> str:
    m = re.search(r"(?is)\(local\)\s*(?:\n|\r)+\s*([^\n\r]+?)\s*(?:\n|\r)+\s*Type\s*:", raw[:2000])
    if m:
        return _clean_md(m.group(1))
    m = re.search(r"(?im)^\s*([A-Z][A-Z0-9 &'./-]{5,})\s*$\s*^\s*Type\s*:", raw[:2000])
    return _clean_md(m.group(1)) if m else "Greyhound Race"


def parse_greyhound_race(text: str) -> GreyhoundRace:
    raw = (text or "").replace("\u202f", " ").replace("\xa0", " ")
    if len(raw.strip()) < 300:
        raise ValueError("Paste the complete Racing & Sports greyhound race page.")
    race_no_match = re.search(r"(?m)^\s*(?:\*\*)?(\d{1,2})(?:\*\*)?\s*$", raw[:1000])
    race_no = int(race_no_match.group(1)) if race_no_match else None
    time_match = re.search(r"(?m)^\s*(\d{1,2}:\d{2})\s*$", raw[:1000])
    race_time = time_match.group(1) if time_match else ""
    name_match = re.search(r"(?m)^##\s+(.+?)\s*$", raw)
    name = _clean_md(name_match.group(1)) if name_match else _plain_header_name(raw)
    type_match = re.search(r"Type\s*:\s*(?:\*\*)?(.+?)(?:\*\*)?\s+Fastest\s+Time\s*:", raw, re.I)
    grade_raw = _clean_md(type_match.group(1)) if type_match else ""
    grade_num, grade_label = grade_value(grade_raw)
    fastest_match = re.search(r"Fastest\s+Time\s*:\s*(?:\*\*)?([^\n\r*]+)", raw, re.I)
    fastest_time = _clean_md(fastest_match.group(1)) if fastest_match else ""
    prize_match = re.search(r"(?:\*\*)?AUD\s+\$([\d,]+(?:\.\d+)?)(?:\*\*)?", raw[:2000], re.I)
    prize = float(prize_match.group(1).replace(",", "")) if prize_match else None
    detail_match = re.search(
        r"(?m)^\s*(\d{2,4})m\s+([A-Z ]+?)\s+(GOOD|SOFT|HEAVY|FAST|SLOW)\s*$",
        raw,
        re.I,
    )
    distance_m = int(detail_match.group(1)) if detail_match else None
    surface = _clean_md(detail_match.group(2)).upper() if detail_match else ""
    going = detail_match.group(3).upper() if detail_match else ""
    runners: list[GreyhoundRunner] = []
    matches = list(_RUNNER_LINK_RE.finditer(raw))
    if matches:
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            segment = raw[match.start():end]
            form = _form_before(raw, match.start())
            runners.append(_runner_from_segment(match.group(1), form, segment))
    else:
        plain_starts = _plain_runner_starts(raw)
        for i, (start_offset, name_offset, form, runner_name) in enumerate(plain_starts):
            end = plain_starts[i + 1][0] if i + 1 < len(plain_starts) else len(raw)
            segment = raw[start_offset:end]
            runners.append(_runner_from_segment(runner_name, form, segment))
    if not runners:
        raise ValueError(
            "No greyhound runners were found. Paste from the R&S Full Fields page; normal browser text or markdown are both supported."
        )
    if not any(not r.scratched for r in runners):
        raise ValueError("All parsed runners are marked scratched.")
    return GreyhoundRace(
        race_no=race_no,
        time=race_time,
        name=name,
        grade_label=grade_label or _clean_md(grade_raw),
        grade_num=grade_num,
        prize=prize,
        distance_m=distance_m,
        surface=surface,
        going=going,
        fastest_time=fastest_time,
        runners=runners,
        source_text=raw,
    )
