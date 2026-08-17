from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


def _clean(value: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value or "")
    s = s.replace("**", "").replace("__", "").replace("`", "")
    s = s.replace("\xa0", " ").replace("\u202f", " ").replace("\\~", "~")
    s = re.sub(r"^\s*[#>*+-]+\s*", "", s)
    return re.sub(r"\s+", " ", s).strip()


def canonical_team(value: str) -> str:
    s = _clean(value).upper()
    s = re.sub(r"\b(FK|BK|FC)\b", "", s)
    s = re.sub(r"[^A-ZÀ-ÖØ-Þ0-9 ]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class MatchResult:
    date_label: str
    home: str
    away: str
    home_goals: int
    away_goals: int


@dataclass
class TeamProfile:
    name: str
    league: str = ""
    season: Optional[int] = None
    ppg_overall: Optional[float] = None
    ppg_home: Optional[float] = None
    ppg_away: Optional[float] = None
    wins_pct: list[Optional[float]] = field(default_factory=list)
    draws_pct: list[Optional[float]] = field(default_factory=list)
    losses_pct: list[Optional[float]] = field(default_factory=list)
    gf: list[Optional[float]] = field(default_factory=list)
    ga: list[Optional[float]] = field(default_factory=list)
    xgf: list[Optional[float]] = field(default_factory=list)
    xga: list[Optional[float]] = field(default_factory=list)
    avg_goals: list[Optional[float]] = field(default_factory=list)
    clean_sheets: list[Optional[float]] = field(default_factory=list)
    failed_to_score: list[Optional[float]] = field(default_factory=list)
    shots: list[Optional[float]] = field(default_factory=list)
    shots_on_target: list[Optional[float]] = field(default_factory=list)
    over25: list[Optional[float]] = field(default_factory=list)
    btts: list[Optional[float]] = field(default_factory=list)
    matches: list[MatchResult] = field(default_factory=list)
    source_text: str = ""


def _visible_lines(text: str) -> list[str]:
    out = []
    for raw in (text or "").splitlines():
        line = _clean(raw)
        if not line:
            continue
        if re.fullmatch(r"[:|\- ]+", line):
            continue
        out.append(line)
    return out


def _slice(text: str, start_pat: str | None = None, end_pats: tuple[str, ...] = ()) -> str:
    lo = 0
    if start_pat:
        m = re.search(start_pat, text, re.I | re.S)
        if m:
            lo = m.start()
    hi = len(text)
    for pat in end_pats:
        m = re.search(pat, text[lo + 1 :], re.I | re.S)
        if m:
            hi = min(hi, lo + 1 + m.start())
    return text[lo:hi]


def _num_token(s: str) -> Optional[float]:
    t = _clean(s).replace(",", "").strip()
    m = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*%?", t)
    return float(m.group(1)) if m else None


def _numbers_in_line_after_label(line: str, label: str) -> list[float]:
    c = _clean(line)
    idx = c.lower().find(label.lower())
    if idx < 0:
        return []
    tail = c[idx + len(label) :]
    return [float(x) for x in re.findall(r"([+-]?\d+(?:\.\d+)?)\s*%?", tail)]


def _metric_triplet(text: str, label: str, start_pat: str | None = None, end_pats: tuple[str, ...] = ()) -> list[Optional[float]]:
    section = _slice(text, start_pat, end_pats)

    # Markdown/table representation: label and three cells remain on one row.
    for raw in section.splitlines():
        if label.lower() not in _clean(raw).lower():
            continue
        c = _clean(raw.replace("|", " "))
        if not c.lower().startswith(label.lower()):
            continue
        vals = _numbers_in_line_after_label(c, label)
        if len(vals) >= 3:
            return vals[:3]

    # Browser-copy representation: table cells may be tabs or separate lines.
    lines = _visible_lines(section)
    for i, line in enumerate(lines):
        if line.lower() != label.lower() and not line.lower().startswith(label.lower() + " "):
            continue
        vals = _numbers_in_line_after_label(line, label)
        j = i + 1
        while len(vals) < 3 and j < len(lines) and j <= i + 8:
            n = _num_token(lines[j])
            if n is not None:
                vals.append(n)
            elif vals and re.search(r"[A-Za-z]", lines[j]):
                break
            j += 1
        if vals:
            return (vals + [None, None, None])[:3]
    return [None, None, None]


def _form_ppg(text: str, label: str, next_label: str) -> Optional[float]:
    lines = _visible_lines(text)
    start = next((i for i, x in enumerate(lines) if x.lower() == label.lower()), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lower() == next_label.lower()), len(lines))
    nums = []
    for x in lines[start + 1 : end]:
        n = _num_token(x)
        if n is not None:
            nums.append(n)
        if len(nums) >= 8:
            break
    return nums[7] if len(nums) >= 8 else None


def _overall_ppg(text: str) -> Optional[float]:
    lines = _visible_lines(text)
    away_i = next((i for i, x in enumerate(lines) if x.lower() == "away form"), 0)
    start = next((i for i in range(away_i + 1, len(lines)) if lines[i].lower() == "overall"), None)
    if start is None:
        return None
    nums = []
    for x in lines[start + 1 : start + 40]:
        if x.lower() == "points per game":
            break
        n = _num_token(x)
        if n is not None:
            nums.append(n)
        if len(nums) >= 8:
            break
    return nums[7] if len(nums) >= 8 else None


_DATE_ONLY = re.compile(r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}$", re.I)
_SCORE_ONLY = re.compile(r"^(\d+)\s*-\s*(\d+)$")
_EXCLUDE = {
    "HT", "FT", "STATS", "TOTAL", "HOME", "AWAY", "SHOW 5 MORE GAMES",
    "FIXTURES", "OVERALL", "GOALS", "CORNERS", "CARDS",
}


def _team_candidate(line: str) -> bool:
    u = line.upper().strip()
    if not u or u in _EXCLUDE:
        return False
    if _DATE_ONLY.fullmatch(line) or _SCORE_ONLY.fullmatch(line):
        return False
    if re.search(r"^(AVG|BTTS|OVER 2\.5|UNDER 2\.5|IN A FEW HOURS|GOAL TIMING)", u):
        return False
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?%?", line):
        return False
    return bool(re.search(r"[A-Za-zÀ-ÿ]", line)) and len(line) <= 80


def _recent_matches(text: str) -> list[MatchResult]:
    lines = _visible_lines(text)
    matches: list[MatchResult] = []
    i = 0
    while i < len(lines):
        if not _DATE_ONLY.fullmatch(lines[i]):
            i += 1
            continue
        date = lines[i]
        j = i + 1
        while j < len(lines) and not _DATE_ONLY.fullmatch(lines[j]) and j < i + 24:
            j += 1
        block = lines[i + 1 : j]
        score_idx = next((k for k, x in enumerate(block) if _SCORE_ONLY.fullmatch(x)), None)
        if score_idx is not None:
            sm = _SCORE_ONLY.fullmatch(block[score_idx])
            pre = [x for x in block[:score_idx] if _team_candidate(x)]
            post = [x for x in block[score_idx + 1 :] if _team_candidate(x)]
            if sm and pre and post:
                matches.append(MatchResult(date, pre[-1], post[0], int(sm.group(1)), int(sm.group(2))))
        i = max(j, i + 1)

    seen = set()
    out: list[MatchResult] = []
    for m in matches:
        key = (m.date_label, canonical_team(m.home), canonical_team(m.away), m.home_goals, m.away_goals)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def parse_team_page(text: str) -> TeamProfile:
    raw = (text or "").replace("\u202f", " ").replace("\xa0", " ")
    if len(raw.strip()) < 1000:
        raise ValueError("Paste the complete FootyStats team page.")

    # Prefer the Statistics heading: it normalises names such as Molde FK II -> Molde II.
    m = re.search(r"(?mi)^\s*#{0,2}\s*(\d{4})\s+(.+?)\s+Statistics\s*$", raw)
    if m:
        season = int(m.group(1))
        name = _clean(m.group(2))
    else:
        h1 = re.search(r"(?m)^#\s+(.+?)\s*$", raw)
        name = _clean(h1.group(1)) if h1 else "Team"
        sm = re.search(r"(?i)\b(\d{4})\s+Season\b", _clean(raw))
        season = int(sm.group(1)) if sm else None

    league = ""
    vis = _visible_lines(raw[:6000])
    sidx = next((i for i, x in enumerate(vis) if re.fullmatch(r"\d{4}\s+Season", x, re.I)), None)
    if sidx is not None:
        for x in reversed(vis[max(0, sidx - 5) : sidx]):
            if "Wins /" in x or x.lower().startswith("upcoming"):
                continue
            if re.search(r"division|league|liga|serie|premier|championship", x, re.I):
                league = x
                break

    basic_start = r"StatsOverallAt HomeAt Away|Stats\s+Overall\s+At Home\s+At Away"
    basic_end = (r"1st\s*/\s*2nd Half",)
    over_start = r"Over\s*/\s*Under Goals"
    over_end = (r"Both Teams To Score",)
    btts_start = r"Both Teams To Score"
    btts_end = (r"Corner Stats",)
    shots_start = r"Shots,?\s*xG\s*&\s*Offsides"
    shots_end = (r"Goal Kicks", r"Common Scorelines")

    return TeamProfile(
        name=name,
        league=league,
        season=season,
        ppg_overall=_overall_ppg(raw),
        ppg_home=_form_ppg(raw, "Home Form", "Away Form"),
        ppg_away=_form_ppg(raw, "Away Form", "Overall"),
        wins_pct=_metric_triplet(raw, "Wins", basic_start, basic_end),
        draws_pct=_metric_triplet(raw, "Draws", basic_start, basic_end),
        losses_pct=_metric_triplet(raw, "Losses", basic_start, basic_end),
        gf=_metric_triplet(raw, "Scored / Match", basic_start, basic_end),
        ga=_metric_triplet(raw, "Conceded / Match", basic_start, basic_end),
        xgf=_metric_triplet(raw, "xG For / Match", basic_start, basic_end),
        xga=_metric_triplet(raw, "xG Against / Match", basic_start, basic_end),
        avg_goals=_metric_triplet(raw, "AVG (Match Goals Average)", basic_start, basic_end),
        clean_sheets=_metric_triplet(raw, "Clean Sheets %", basic_start, basic_end),
        failed_to_score=_metric_triplet(raw, "Failed to Score %", basic_start, basic_end),
        shots=_metric_triplet(raw, "Shots Taken / Match", basic_start, basic_end),
        shots_on_target=_metric_triplet(raw, "Shots On Target / Match", shots_start, shots_end),
        over25=_metric_triplet(raw, "Over 2.5", over_start, over_end),
        btts=_metric_triplet(raw, "BTTS", btts_start, btts_end),
        matches=_recent_matches(raw),
        source_text=raw,
    )


def recent_summary(profile: TeamProfile, n: int = 10, venue: str = "") -> dict:
    team = canonical_team(profile.name)
    rows = []
    for match in profile.matches:
        is_home = canonical_team(match.home) == team
        is_away = canonical_team(match.away) == team
        if not (is_home or is_away):
            continue
        if venue == "home" and not is_home:
            continue
        if venue == "away" and not is_away:
            continue
        gf = match.home_goals if is_home else match.away_goals
        ga = match.away_goals if is_home else match.home_goals
        pts = 3 if gf > ga else 1 if gf == ga else 0
        rows.append((gf, ga, pts, match))
        if len(rows) >= n:
            break
    if not rows:
        return {"n": 0, "gf": None, "ga": None, "ppg": None, "btts": None, "over25": None, "matches": []}
    count = len(rows)
    return {
        "n": count,
        "gf": sum(x[0] for x in rows) / count,
        "ga": sum(x[1] for x in rows) / count,
        "ppg": sum(x[2] for x in rows) / count,
        "btts": 100.0 * sum(1 for x in rows if x[0] > 0 and x[1] > 0) / count,
        "over25": 100.0 * sum(1 for x in rows if x[0] + x[1] > 2) / count,
        "matches": [x[3] for x in rows],
    }


def h2h_matches(home: TeamProfile, away: TeamProfile, limit: int = 5) -> list[MatchResult]:
    home_key = canonical_team(home.name)
    away_key = canonical_team(away.name)
    pool = list(home.matches) + list(away.matches)
    out: list[MatchResult] = []
    seen = set()
    for match in pool:
        keys = {canonical_team(match.home), canonical_team(match.away)}
        if keys != {home_key, away_key}:
            continue
        key = (match.date_label, canonical_team(match.home), canonical_team(match.away), match.home_goals, match.away_goals)
        if key in seen:
            continue
        seen.add(key)
        out.append(match)
        if len(out) >= limit:
            break
    return out
