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


def _clean_md(value: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value or "")
    s = s.replace("**", "").replace("\xa0", " ").replace("\u202f", " ").replace("\\:", ":")
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
    """Map common Australian greyhound grades to an ordered axis (lower = stronger)."""
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
        rf"{re.escape(label)}\*\*(\d+):\s*(\d+)\s+(\d+)\s+(\d+)\*\*",
        section,
        re.I,
    )
    return tuple(map(int, m.groups())) if m else (0, 0, 0, 0)


def _strip_cell(cell: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cell.strip())
    s = s.replace("**", "").replace("\xa0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", s).strip()


def _past_starts(section: str) -> list[GreyhoundStart]:
    starts: list[GreyhoundStart] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        if not re.search(r"\d{2}-[A-Za-z]{3}-\d{4}", line):
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

        starts.append(
            GreyhoundStart(
                finish_pos=finish_pos,
                field_size=field_size,
                finish_status=finish_status,
                margin=margin,
                date_raw=date_raw,
                date=parsed_date,
                track=track,
                grade_label=grade_label,
                grade_num=grade_num,
                prize=prize,
                distance_m=distance_m,
                surface=surface,
                going=going,
                box=box,
                sp=sp,
                sectional=sectional,
                winner=winner,
                raw=raw_line,
            )
        )
    return starts


def _form_before(text: str, position: int) -> str:
    pre = text[max(0, position - 600):position]
    values = re.findall(r"(?m)^\s*([0-9xX]{2,10})\s*$", pre)
    return values[-1] if values else ""


def _runner_from_segment(name: str, form: str, segment: str) -> GreyhoundRunner:
    trainer_match = re.search(
        r"\[([^\]]+)\]\(https?://www\.racingandsports\.com\.au/greyhound/trainer/",
        segment,
        re.I,
    )
    trainer = trainer_match.group(1).strip() if trainer_match else ""

    before_trainer = segment[:trainer_match.start()] if trainer_match else segment[:1200]
    box_values = re.findall(r"(?m)^\s*([1-8])\s*$", before_trainer)
    box = int(box_values[-1]) if box_values else None

    odds_match = re.search(r"\*\*\$(\d+(?:\.\d+)?)\*\*", segment)
    odds = float(odds_match.group(1)) if odds_match else None
    scratched = bool(re.search(r"\*\*\s*Scratched\s*\*\*", segment, re.I))

    detail = re.search(r"######\s+(\d+)yo\s+(.+?)\s+\|", segment, re.I)
    age = int(detail.group(1)) if detail else None
    sex = detail.group(2).strip() if detail else ""

    career = _record(segment, "Career")
    course = _record(segment, "Course")
    dist = _record(segment, "Dist")

    wp = re.search(r"W%\s*-\s*P%\*\*(\d+)%\s*-\s*(\d+)%\*\*", segment, re.I)
    win_pct = float(wp.group(1)) if wp else None
    place_pct = float(wp.group(2)) if wp else None

    return GreyhoundRunner(
        name=_clean_md(name),
        box=box,
        trainer=trainer,
        odds=odds,
        form=form,
        age=age,
        sex=sex,
        scratched=scratched,
        career_starts=career[0],
        career_wins=career[1],
        career_seconds=career[2],
        career_thirds=career[3],
        course_starts=course[0],
        course_wins=course[1],
        course_seconds=course[2],
        course_thirds=course[3],
        dist_starts=dist[0],
        dist_wins=dist[1],
        dist_seconds=dist[2],
        dist_thirds=dist[3],
        win_pct=win_pct,
        place_pct=place_pct,
        past_starts=_past_starts(segment),
        raw=segment,
    )


def parse_greyhound_race(text: str) -> GreyhoundRace:
    raw = (text or "").replace("\u202f", " ")
    if len(raw.strip()) < 300:
        raise ValueError("Paste the complete Racing & Sports greyhound race page.")

    race_no_match = re.search(r"(?m)^\s*\*\*(\d{1,2})\*\*\s*$", raw[:1000])
    race_no = int(race_no_match.group(1)) if race_no_match else None

    time_match = re.search(r"(?m)^\s*(\d{1,2}:\d{2})\s*$", raw[:1000])
    race_time = time_match.group(1) if time_match else ""

    name_match = re.search(r"(?m)^##\s+(.+?)\s*$", raw)
    name = _clean_md(name_match.group(1)) if name_match else "Greyhound Race"

    type_match = re.search(r"Type:\s*\*\*(.+?)\*\*", raw, re.I)
    grade_raw = type_match.group(1) if type_match else ""
    grade_num, grade_label = grade_value(grade_raw)

    fastest_match = re.search(r"Fastest Time:\s*\*\*([^*]+)\*\*", raw, re.I)
    fastest_time = _clean_md(fastest_match.group(1)) if fastest_match else ""

    prize_match = re.search(r"\*\*AUD\s+\$([\d,]+(?:\.\d+)?)\*\*", raw, re.I)
    prize = float(prize_match.group(1).replace(",", "")) if prize_match else None

    detail_match = re.search(
        r"(?m)^\s*(\d{2,4})m\s+([A-Z ]+?)\s+(GOOD|SOFT|HEAVY|FAST|SLOW)\s*$",
        raw,
        re.I,
    )
    distance_m = int(detail_match.group(1)) if detail_match else None
    surface = _clean_md(detail_match.group(2)).upper() if detail_match else ""
    going = detail_match.group(3).upper() if detail_match else ""

    matches = list(_RUNNER_LINK_RE.finditer(raw))
    if not matches:
        raise ValueError("No greyhound runner links were found in the pasted Racing & Sports data.")

    runners: list[GreyhoundRunner] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        segment = raw[match.start():end]
        form = _form_before(raw, match.start())
        runner = _runner_from_segment(match.group(1), form, segment)
        runners.append(runner)

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
