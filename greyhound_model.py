from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from greyhound_parser import GreyhoundRace, GreyhoundRunner, GreyhoundStart


@dataclass
class GreyhoundAnalysis:
    rank: int
    box: int
    runner: str
    odds: Optional[float]
    form_score: float
    form_prob: float
    market_prob: float
    final_prob: float
    top2_prob: float
    top3_prob: float
    value_edge: Optional[float]
    value_label: str
    confidence: str
    components: dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    evidence: list[str] = field(default_factory=list)


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(x)))


def _weighted_average(values: list[float], weights: list[float]) -> Optional[float]:
    pairs = [(v, w) for v, w in zip(values, weights) if v is not None and w > 0]
    if not pairs:
        return None
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def _finish_performance(start: GreyhoundStart) -> float:
    if start.finish_pos is None or not start.field_size or start.field_size <= 1:
        return 0.0 if start.finish_status else 0.5
    rank_component = (start.field_size - start.finish_pos) / (start.field_size - 1)
    margin = max(0.0, float(start.margin or 0.0))
    margin_component = 1.0 / (1.0 + margin / 5.0)
    return _clip(100.0 * (0.75 * rank_component + 0.25 * margin_component)) / 100.0


def _recent_form(runner: GreyhoundRunner) -> float:
    starts = runner.past_starts[:5]
    if not starts:
        return 50.0
    values = [_finish_performance(s) for s in starts]
    weights = [1.00, 0.82, 0.67, 0.55, 0.45][: len(values)]
    return _clip(100.0 * (_weighted_average(values, weights) or 0.5), 5, 95)


def _class_strength(race: GreyhoundRace, runner: GreyhoundRunner) -> float:
    current = race.grade_num
    if current is None:
        return 50.0
    values, weights = [], []
    for i, start in enumerate(runner.past_starts[:8]):
        if start.grade_num is None:
            continue
        advantage = current - start.grade_num
        perf = _finish_performance(start)
        value = 50.0 + 12.0 * advantage + 25.0 * (perf - 0.5)
        values.append(_clip(value, 5, 95))
        weights.append(0.85**i)
    return _weighted_average(values, weights) or 50.0


def _record_score(starts: int, wins: int, seconds: int, thirds: int) -> float:
    if not starts:
        return 50.0
    win_rate = wins / starts
    place_rate = (wins + seconds + thirds) / starts
    return _clip(50.0 + 140.0 * (win_rate - 0.15) + 45.0 * (place_rate - 0.45), 5, 95)


def _course_score(runner: GreyhoundRunner) -> float:
    return _record_score(runner.course_starts, runner.course_wins, runner.course_seconds, runner.course_thirds)


def _distance_score(runner: GreyhoundRunner) -> float:
    return _record_score(runner.dist_starts, runner.dist_wins, runner.dist_seconds, runner.dist_thirds)


def _box_zone(box: Optional[int]) -> Optional[int]:
    if box is None:
        return None
    if box <= 2:
        return 0
    if box <= 5:
        return 1
    return 2


def _box_score(runner: GreyhoundRunner) -> float:
    if runner.box is None:
        return 50.0
    same = [s for s in runner.past_starts if s.box == runner.box and s.finish_pos is not None]
    if len(same) >= 2:
        return _clip(100.0 * sum(_finish_performance(s) for s in same) / len(same), 5, 95)
    zone = _box_zone(runner.box)
    similar = [
        s for s in runner.past_starts
        if s.box is not None and _box_zone(s.box) == zone and s.finish_pos is not None
    ]
    if similar:
        return _clip(100.0 * sum(_finish_performance(s) for s in similar) / len(similar), 5, 95)
    return 50.0


def _consistency_score(runner: GreyhoundRunner) -> float:
    if runner.win_pct is None or runner.place_pct is None:
        return 50.0
    return _clip(50.0 + 1.2 * (runner.win_pct - 15.0) + 0.45 * (runner.place_pct - 45.0), 5, 95)


def _trend_score(runner: GreyhoundRunner) -> float:
    if len(runner.past_starts) < 4:
        return 50.0
    recent = runner.past_starts[:3]
    previous = runner.past_starts[3:6]
    recent_avg = sum(_finish_performance(s) for s in recent) / len(recent)
    previous_avg = sum(_finish_performance(s) for s in previous) / len(previous)
    return _clip(50.0 + 80.0 * (recent_avg - previous_avg), 10, 90)


def _sectional_medians(race: GreyhoundRace) -> dict[str, float]:
    medians: dict[str, float] = {}
    target = race.distance_m
    if not target:
        return medians
    for runner in race.runners:
        if runner.scratched:
            continue
        vals = [
            s.sectional
            for s in runner.past_starts
            if s.sectional is not None and s.distance_m is not None and abs(s.distance_m - target) <= 10
        ]
        if vals:
            vals = sorted(vals[:6])
            n = len(vals)
            medians[runner.name] = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    return medians


def _sectional_scores(race: GreyhoundRace) -> dict[str, float]:
    meds = _sectional_medians(race)
    if len(meds) < 2:
        return {r.name: 50.0 for r in race.runners if not r.scratched}
    vals = list(meds.values())
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / max(1, len(vals) - 1)
    sd = math.sqrt(variance)
    if sd < 1e-6:
        return {r.name: 50.0 for r in race.runners if not r.scratched}
    out = {}
    for runner in race.runners:
        if runner.scratched:
            continue
        if runner.name not in meds:
            out[runner.name] = 50.0
        else:
            z = (mean - meds[runner.name]) / sd
            out[runner.name] = _clip(50.0 + 18.0 * z, 15, 85)
    return out


def _form_scores(race: GreyhoundRace) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    sectional = _sectional_scores(race)
    components: dict[str, dict[str, float]] = {}
    scores: dict[str, float] = {}
    weights = {
        "Recent form": 0.25,
        "Class/grade": 0.18,
        "Course": 0.12,
        "Distance": 0.12,
        "Box suitability": 0.10,
        "Consistency": 0.08,
        "Sectional speed": 0.08,
        "Trend": 0.07,
    }
    for runner in race.runners:
        if runner.scratched:
            continue
        c = {
            "Recent form": _recent_form(runner),
            "Class/grade": _class_strength(race, runner),
            "Course": _course_score(runner),
            "Distance": _distance_score(runner),
            "Box suitability": _box_score(runner),
            "Consistency": _consistency_score(runner),
            "Sectional speed": sectional.get(runner.name, 50.0),
            "Trend": _trend_score(runner),
        }
        components[runner.name] = c
        scores[runner.name] = sum(c[k] * w for k, w in weights.items())
    return scores, components


def _softmax(scores: dict[str, float], temperature: float = 10.0) -> dict[str, float]:
    if not scores:
        return {}
    top = max(scores.values())
    raw = {k: math.exp((v - top) / temperature) for k, v in scores.items()}
    total = sum(raw.values()) or 1.0
    return {k: v / total for k, v in raw.items()}


def _market_probabilities(race: GreyhoundRace, form_prob: dict[str, float]) -> tuple[dict[str, float], int]:
    odds = {
        r.name: r.odds for r in race.runners
        if not r.scratched and r.name in form_prob and r.odds is not None and r.odds > 1.0
    }
    if len(odds) < 2:
        return dict(form_prob), len(odds)
    raw = {name: 1.0 / price for name, price in odds.items()}
    total_raw = sum(raw.values()) or 1.0
    base_market = {name: value / total_raw for name, value in raw.items()}
    market = {name: base_market.get(name, form_prob[name]) for name in form_prob}
    total = sum(market.values()) or 1.0
    market = {name: value / total for name, value in market.items()}
    return market, len(odds)


def _simulate_places(final_prob: dict[str, float], simulations: int = 8000) -> tuple[dict[str, float], dict[str, float]]:
    names = list(final_prob)
    top2 = {n: 0 for n in names}
    top3 = {n: 0 for n in names}
    rng = random.Random(8172026)
    for _ in range(simulations):
        remaining = names[:]
        weights = [max(final_prob[n], 1e-9) for n in remaining]
        order = []
        for _place in range(min(3, len(remaining))):
            total = sum(weights)
            pick = rng.random() * total
            cum = 0.0
            idx = 0
            for idx, w in enumerate(weights):
                cum += w
                if pick <= cum:
                    break
            order.append(remaining.pop(idx))
            weights.pop(idx)
        for n in order[:2]:
            top2[n] += 1
        for n in order[:3]:
            top3[n] += 1
    return ({n: top2[n] / simulations for n in names}, {n: top3[n] / simulations for n in names})


def analyse_greyhound_race(race: GreyhoundRace, market_weight: float = 0.35) -> list[GreyhoundAnalysis]:
    market_weight = max(0.0, min(0.40, float(market_weight)))
    form_weight = 1.0 - market_weight
    form_scores, components = _form_scores(race)
    form_prob = _softmax(form_scores)
    market_prob, priced_count = _market_probabilities(race, form_prob)
    use_market = priced_count >= 2 and market_weight > 0
    final_prob = {
        name: (form_weight * form_prob[name] + market_weight * market_prob[name]) if use_market else form_prob[name]
        for name in form_prob
    }
    total = sum(final_prob.values()) or 1.0
    final_prob = {name: p / total for name, p in final_prob.items()}
    top2, top3 = _simulate_places(final_prob)
    runner_by_name = {r.name: r for r in race.runners if not r.scratched}
    ordered = sorted(final_prob, key=lambda n: (-final_prob[n], runner_by_name[n].box or 99))
    gap = final_prob[ordered[0]] - final_prob[ordered[1]] if len(ordered) >= 2 else 1.0
    results = []
    for rank, name in enumerate(ordered, start=1):
        runner = runner_by_name[name]
        raw_implied = (1.0 / runner.odds) if runner.odds and runner.odds > 1.0 else None
        edge = final_prob[name] - raw_implied if raw_implied is not None else None
        if edge is None:
            value = "No price"
        elif edge >= 0.05:
            value = "Strong value"
        elif edge >= 0.02:
            value = "Possible value"
        elif edge > -0.02:
            value = "Fair price"
        else:
            value = "Underpriced"
        completeness = sum(1 for v in components[name].values() if abs(v - 50.0) > 0.1) / len(components[name])
        if rank == 1 and gap >= 0.07 and completeness >= 0.6:
            confidence = "High"
        elif (rank <= 2 and gap >= 0.035) or completeness >= 0.55:
            confidence = "Medium"
        else:
            confidence = "Low"
        c = components[name]
        top_factors = sorted(c.items(), key=lambda kv: kv[1], reverse=True)[:3]
        weak_factors = sorted(c.items(), key=lambda kv: kv[1])[:2]
        evidence = [
            f"Recent form score {c['Recent form']:.0f}/100 from up to the last 5 starts.",
            f"Class/grade score {c['Class/grade']:.0f}/100 against today's {race.grade_label or 'grade'}.",
            f"Course {c['Course']:.0f}/100 · Distance {c['Distance']:.0f}/100 · Box {c['Box suitability']:.0f}/100.",
        ]
        if runner.odds:
            evidence.append(f"Current R&S odds {runner.odds:.2f}; market contributes {market_weight*100:.0f}% when enough prices are available.")
        if runner.past_starts:
            last = runner.past_starts[0]
            if last.finish_pos and last.field_size:
                evidence.append(f"Latest start: {last.finish_pos}/{last.field_size} at {last.track or 'track'} in {last.grade_label or 'unclassified grade'}.")
        explanation = (
            f"{name} rates best through "
            + ", ".join(f"{k.lower()} ({v:.0f})" for k, v in top_factors)
            + ". Main negatives are "
            + ", ".join(f"{k.lower()} ({v:.0f})" for k, v in weak_factors)
            + f". Final win probability is {final_prob[name]*100:.1f}%"
            + (f" after blending {form_weight*100:.0f}% Form and {market_weight*100:.0f}% Market." if use_market else " from the Form model because sufficient market prices were unavailable.")
        )
        results.append(GreyhoundAnalysis(
            rank=rank,
            box=runner.box or 0,
            runner=name,
            odds=runner.odds,
            form_score=form_scores[name],
            form_prob=form_prob[name],
            market_prob=market_prob[name],
            final_prob=final_prob[name],
            top2_prob=top2[name],
            top3_prob=top3[name],
            value_edge=edge,
            value_label=value,
            confidence=confidence,
            components=c,
            explanation=explanation,
            evidence=evidence,
        ))
    return results
