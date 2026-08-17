from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from harness_parser import HarnessRace, HarnessRunner, HarnessStart


@dataclass
class HarnessAnalysis:
    rank: int
    form_rank: int
    market_rank: int
    number: int
    runner: str
    draw: str
    driver: str
    odds: Optional[float]
    form_score: float
    form_prob: float
    market_prob: float
    final_prob: float
    class_movement: str
    proven_level: str
    confidence: str
    value_edge: Optional[float]
    value_label: str
    components: dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    evidence: list[str] = field(default_factory=list)


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(x)))


def _weighted(values, weights, default=50.0):
    pairs = [(v, w) for v, w in zip(values, weights) if v is not None and w > 0]
    if not pairs:
        return default
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def _start_perf(s: HarnessStart) -> float:
    if s.finish_status:
        return 0.04
    if s.finish_pos is None or not s.field_size or s.field_size <= 1:
        return 0.35
    rank = (s.field_size - s.finish_pos) / (s.field_size - 1)
    margin = max(0.0, float(s.margin_m or 0.0))
    margin_comp = math.exp(-margin / 28.0)
    return max(0.0, min(1.0, 0.72 * rank + 0.28 * margin_comp))


def _recent_form(r: HarnessRunner) -> float:
    starts = r.past_starts[:5]
    if not starts:
        return 50.0
    weights = [1.0, 0.82, 0.68, 0.56, 0.46][:len(starts)]
    return _clip(_weighted([100 * _start_perf(s) for s in starts], weights), 5, 95)


def _record_score(starts, wins, seconds, thirds, baseline_win=0.10, baseline_place=0.30):
    if not starts:
        return 50.0
    win = wins / starts
    place = (wins + seconds + thirds) / starts
    return _clip(50 + 170 * (win - baseline_win) + 65 * (place - baseline_place), 5, 95)


def _course(r):
    return _record_score(r.course_starts, r.course_wins, r.course_seconds, r.course_thirds)


def _distance(r):
    return _record_score(r.dist_starts, r.dist_wins, r.dist_seconds, r.dist_thirds)


def _consistency(r):
    if r.last12_starts:
        return _record_score(r.last12_starts, r.last12_wins, r.last12_seconds, r.last12_thirds, 0.10, 0.30)
    return _record_score(r.career_starts, r.career_wins, r.career_seconds, r.career_thirds, 0.10, 0.30)


def _reliability(r):
    starts = r.past_starts[:8]
    if not starts:
        return 50.0
    bad = 0.0
    for i, s in enumerate(starts):
        if s.finish_status:
            bad += 1.0 * (0.9 ** i)
        elif s.margin_m is not None and s.margin_m >= 60:
            bad += 0.35 * (0.9 ** i)
    den = sum(0.9 ** i for i in range(len(starts))) or 1
    return _clip(88 - 95 * (bad / den), 8, 92)


def _draw_score(race: HarnessRace, r: HarnessRunner):
    import re
    d = (r.draw or "").upper().replace(" ", "")
    if not d:
        return 50.0
    if race.country == "AUSTRALIA":
        m = re.fullmatch(r"FR(\d+)", d)
        if m:
            return _clip(92 - 6.5 * (int(m.group(1)) - 1), 42, 92)
        m = re.fullmatch(r"SR(\d+)", d)
        if m:
            return _clip(68 - 4.5 * (int(m.group(1)) - 1), 40, 68)
        if d == "FT":
            return 63.0
        m = re.match(r"(\d+)M", d)
        if m:
            return _clip(58 - 1.1 * int(m.group(1)), 15, 58)
    m = re.match(r"(\d+)M", d)
    if m:
        return _clip(58 - 1.2 * int(m.group(1)), 15, 58)
    return 50.0


def _driver_score(r: HarnessRunner):
    current = (r.driver or "").strip().upper()
    if not current:
        return 50.0
    starts = [s for s in r.past_starts[:8] if (s.driver or "").strip().upper() == current]
    if not starts:
        return 48.0
    perf = sum(_start_perf(s) for s in starts) / len(starts)
    share = len(starts) / max(1, min(8, len(r.past_starts)))
    return _clip(42 + 48 * perf + 12 * share, 15, 92)


def _trend(r: HarnessRunner):
    if len(r.past_starts) < 4:
        return 50.0
    recent = r.past_starts[:3]
    previous = r.past_starts[3:6]
    if not previous:
        return 50.0
    ra = sum(_start_perf(s) for s in recent) / len(recent)
    rb = sum(_start_perf(s) for s in previous) / len(previous)
    return _clip(50 + 90 * (ra - rb), 10, 90)


def _class_context(race: HarnessRace, r: HarnessRunner):
    current = race.current_class_score
    past = [s for s in r.past_starts[:8] if s.class_score is not None]
    if current is None or not past:
        return 50.0, "Class unclear", "No comparable historical level"
    weights = [0.9 ** i for i in range(len(past))]
    avg = sum(s.class_score * w for s, w in zip(past, weights)) / sum(weights)
    delta = current - avg
    comparable = [s for s in past if abs((s.class_score or current) - current) <= 8]
    perf = sum(_start_perf(s) for s in comparable) / len(comparable) if comparable else 0.45
    score = _clip(50 - 3.2 * delta + 34 * (perf - 0.5), 8, 94)
    movement = "Rises in class" if delta >= 4.0 else ("Drops in class" if delta <= -4.0 else "Similar class")
    proven = [s.class_score for s in past if s.finish_pos is not None and s.finish_pos <= 3 and s.class_score is not None]
    level = max(proven) if proven else max(s.class_score for s in past if s.class_score is not None)
    return score, movement, f"Historical strength {level:.1f} vs current {current:.1f}"


def _form_scores(race: HarnessRace):
    scores, comps, movements, proven = {}, {}, {}, {}
    weights = {
        "Recent form": 0.26,
        "Class fit": 0.20,
        "Distance": 0.10,
        "Course": 0.08,
        "Draw/handicap": 0.09,
        "Reliability": 0.09,
        "Consistency": 0.07,
        "Driver": 0.05,
        "Trend": 0.06,
    }
    for r in race.runners:
        if r.scratched:
            continue
        cls, mov, prv = _class_context(race, r)
        c = {
            "Recent form": _recent_form(r),
            "Class fit": cls,
            "Distance": _distance(r),
            "Course": _course(r),
            "Draw/handicap": _draw_score(race, r),
            "Reliability": _reliability(r),
            "Consistency": _consistency(r),
            "Driver": _driver_score(r),
            "Trend": _trend(r),
        }
        comps[r.name] = c
        movements[r.name] = mov
        proven[r.name] = prv
        scores[r.name] = sum(c[k] * w for k, w in weights.items())
    return scores, comps, movements, proven


def _softmax(scores, temperature=11.5):
    if not scores:
        return {}
    top = max(scores.values())
    raw = {k: math.exp((v - top) / temperature) for k, v in scores.items()}
    total = sum(raw.values()) or 1
    return {k: v / total for k, v in raw.items()}


def _market(race: HarnessRace, form_prob):
    raw = {}
    for r in race.runners:
        if not r.scratched and r.name in form_prob and r.odds is not None and r.odds > 1:
            raw[r.name] = 1 / r.odds
    if len(raw) < 2:
        return dict(form_prob), len(raw)
    market = dict(form_prob)
    priced_mass = sum(form_prob[h] for h in raw)
    den = sum(raw.values()) or 1
    for h, v in raw.items():
        market[h] = priced_mass * v / den
    return market, len(raw)


def _value(final_prob, odds):
    if odds is None or odds <= 1:
        return None, "No price"
    edge = final_prob - 1 / odds
    if edge >= 0.05:
        return edge, "Strong value"
    if edge >= 0.02:
        return edge, "Possible value"
    if edge > -0.02:
        return edge, "Fair price"
    return edge, "Underpriced"


def analyse_harness_race(race: HarnessRace, market_weight_pct: int = 35) -> list[HarnessAnalysis]:
    market_weight = max(0, min(40, int(market_weight_pct))) / 100.0
    scores, components, movements, proven = _form_scores(race)
    form_prob = _softmax(scores)
    market_prob, priced_count = _market(race, form_prob)
    use_market = priced_count >= 2 and market_weight > 0
    final = {
        h: ((1 - market_weight) * form_prob[h] + market_weight * market_prob[h]) if use_market else form_prob[h]
        for h in form_prob
    }
    order = sorted(final, key=lambda h: (-final[h], h))
    form_order = sorted(form_prob, key=lambda h: (-form_prob[h], h))
    market_order = sorted(market_prob, key=lambda h: (-market_prob[h], h))
    form_rank = {h: i + 1 for i, h in enumerate(form_order)}
    market_rank = {h: i + 1 for i, h in enumerate(market_order)}
    runner_by = {r.name: r for r in race.runners if not r.scratched}
    out = []
    for rank, h in enumerate(order, 1):
        r = runner_by[h]
        edge, label = _value(final[h], r.odds)
        nstarts = len(r.past_starts)
        confidence = "High" if nstarts >= 6 and scores[h] >= 62 else ("Medium" if nstarts >= 3 else "Low")
        c = components[h]
        positives = sorted(c.items(), key=lambda kv: -kv[1])[:3]
        negatives = sorted(c.items(), key=lambda kv: kv[1])[:2]
        explanation = (
            f"{h} ranks #{rank} overall. The strongest factors are "
            + ", ".join(f"{k} ({v:.0f}/100)" for k, v in positives)
            + ". "
            + ("Main weaknesses are " + ", ".join(f"{k} ({v:.0f}/100)" for k, v in negatives) + ". " if negatives else "")
            + f"Class movement: {movements[h]}. "
            + (f"Current market odds {r.odds:.2f} are included at {int(market_weight * 100)}% weight." if use_market and r.odds else "The final ranking is driven mainly by form evidence.")
        )
        evidence = []
        for s in r.past_starts[:3]:
            fin = s.finish_status or (f"{s.finish_pos}/{s.field_size}" if s.finish_pos and s.field_size else "?")
            evidence.append(f"{s.date_raw}: {fin}, {s.track} {s.race_desc}, margin {s.margin_m if s.margin_m is not None else '—'}m")
        out.append(HarnessAnalysis(
            rank=rank, form_rank=form_rank[h], market_rank=market_rank[h], number=r.number,
            runner=h, draw=r.draw, driver=r.driver, odds=r.odds,
            form_score=scores[h], form_prob=form_prob[h], market_prob=market_prob[h], final_prob=final[h],
            class_movement=movements[h], proven_level=proven[h], confidence=confidence,
            value_edge=edge, value_label=label, components=c, explanation=explanation, evidence=evidence,
        ))
    return out
