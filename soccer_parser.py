from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


def _clean(value: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value or "")
    s = s.replace("**", "").replace("*", "").replace("\xa0", " ").replace("\u202f", " ")
    return re.sub(r"\s+", " ", s).strip()


def canonical_team(value: str) -> str:
    s = _clean(value).upper()
    s = re.sub(r"\b(FK|BK|FC)\b", "", s)
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


def _row_values(text: str, label: str, start_marker: str = "") -> list[Optional[float]]:
    section = text
    if start_marker:
        pos = section.lower().find(start_marker.lower())
        if pos >= 0:
            section = section[pos:]
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [_clean(c) for c in line.strip().strip("|").split("|")]
        if not cells or cells[0].strip().lower() != label.lower():
            continue
        values: list[Optional[float]] = []
        for cell in cells[1:4]:
            raw = cell.replace("%", "").replace(",", "").strip()
            try:
                values.append(float(raw))
            except Exception:
                values.append(None)
        while len(values) < 3:
            values.append(None)
        return values
    return [None, None, None]


def _ppg_block(text: str, label: str, next_label: str) -> Optional[float]:
    m = re.search(rf"\*\*{re.escape(label)}\*\*(.*?)(?=\*\*{re.escape(next_label)}\*\*)", text, flags=re.I | re.S)
    if not m:
        return None
    values = re.findall(r"\*\*([+-]?\d+(?:\.\d+)?)\*\*", m.group(1))
    if len(values) >= 8:
        try:
            return float(values[7])
        except ValueError:
            return None
    return None


def _overall_ppg(text: str) -> Optional[float]:
    m = re.search(r"\*\*Overall\*\*(.*?)(?=\*\*[\d.]+\*\*\s*\n\s*\*\*Points Per Game)", text, flags=re.I | re.S)
    if not m:
        return None
    values = re.findall(r"\*\*([+-]?\d+(?:\.\d+)?)\*\*", m.group(1))
    if len(values) >= 8:
        try:
            return float(values[7])
        except ValueError:
            return None
    return None


_DATE_RE = re.compile(r"^\s*-\s*\*\*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})\*\*\s*$", re.I)


def _recent_matches(text: str) -> list[MatchResult]:
    lines = text.splitlines()
    matches: list[MatchResult] = []
    i = 0
    while i < len(lines):
        dm = _DATE_RE.match(lines[i])
        if not dm:
            i += 1
            continue
        date_label = dm.group(1)
        j = i + 1
        chunk: list[str] = []
        while j < len(lines) and not _DATE_RE.match(lines[j]) and j < i + 26:
            chunk.append(lines[j])
            j += 1
        link_texts: list[str] = []
        for raw in chunk:
            for lm in re.finditer(r"\[([^\]]+)\]\([^)]+\)", raw):
                link_texts.append(_clean(lm.group(1)))
        score_idx = next((k for k, item in enumerate(link_texts) if re.fullmatch(r"\d+\s*-\s*\d+", item)), None)
        if score_idx is not None and score_idx >= 1 and score_idx + 1 < len(link_texts):
            home = link_texts[score_idx - 1]
            away = link_texts[score_idx + 1]
            hg, ag = map(int, re.findall(r"\d+", link_texts[score_idx]))
            matches.append(MatchResult(date_label, home, away, hg, ag))
        i = max(j, i + 1)
    seen = set()
    output: list[MatchResult] = []
    for m in matches:
        key = (m.date_label, canonical_team(m.home), canonical_team(m.away), m.home_goals, m.away_goals)
        if key in seen:
            continue
        seen.add(key)
        output.append(m)
    return output


def parse_team_page(text: str) -> TeamProfile:
    raw = (text or "").replace("\u202f", " ").replace("\xa0", " ")
    if len(raw.strip()) < 1000:
        raise ValueError("Paste the complete FootyStats team page.")
    h1 = re.search(r"(?m)^#\s+(.+?)\s*$", raw)
    if not h1:
        sm = re.search(r"(?mi)^\s*(?:\d{4}\s+)?(.+?)\s+Statistics\s*$", raw)
        name = _clean(sm.group(1)) if sm else "Team"
    else:
        name = _clean(h1.group(1))
    stats_name = re.search(r"(?m)^##\s+\d{4}\s+(.+?)\s+Statistics\s*$", raw)
    if stats_name:
        name = _clean(stats_name.group(1))
    season_match = re.search(r"\*\*(\d{4})\s*Season\*\*", raw, re.I)
    season = int(season_match.group(1)) if season_match else None
    league = ""
    league_match = re.search(r"(?m)^\*\*([^*\n]+)\*\*\s*\n\s*\*\*\d{4}\s*Season\*\*", raw)
    if league_match:
        league = _clean(league_match.group(1))
    basic = "| **StatsOverallAt HomeAt Away**"
    goals_table = "| **Team ShotsOverallAt HomeAt Away**"
    over_table = "| **Over 0.5\\~5.5 Full-TimeOverallAt HomeAt Away**"
    btts_table = "| **BTTS StatsOverallAt HomeAt Away**"
    return TeamProfile(
        name=name, league=league, season=season,
        ppg_overall=_overall_ppg(raw), ppg_home=_ppg_block(raw, "Home Form", "Away Form"), ppg_away=_ppg_block(raw, "Away Form", "Overall"),
        wins_pct=_row_values(raw, "Wins", basic), draws_pct=_row_values(raw, "Draws", basic), losses_pct=_row_values(raw, "Losses", basic),
        gf=_row_values(raw, "Scored / Match", basic), ga=_row_values(raw, "Conceded / Match", basic),
        xgf=_row_values(raw, "xG For / Match", basic), xga=_row_values(raw, "xG Against / Match", basic),
        avg_goals=_row_values(raw, "AVG (Match Goals Average)", basic), clean_sheets=_row_values(raw, "Clean Sheets %", basic), failed_to_score=_row_values(raw, "Failed to Score %", basic),
        shots=_row_values(raw, "Shots Taken / Match", basic), shots_on_target=_row_values(raw, "Shots On Target / Match", goals_table),
        over25=_row_values(raw, "Over 2.5", over_table), btts=_row_values(raw, "BTTS", btts_table),
        matches=_recent_matches(raw), source_text=raw,
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
