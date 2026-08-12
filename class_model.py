from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from race_parser import Race, Runner, PastRace


@dataclass
class Analysis:
    rank: int = 0
    number: int = 0
    horse: str = ''
    odds: Optional[float] = None
    relevant_previous_class: str = ''
    movement: str = ''
    proven_level: str = ''
    assessment: str = ''
    score: float = 5.0
    confidence: str = 'Low'
    explanation: str = ''
    evidence_lines: list[str] = None

    def __post_init__(self):
        if self.evidence_lines is None:
            self.evidence_lines = []


def _prize_amount(obj) -> Optional[float]:
    """Generic race prize amount; prize_eur is retained only for v3 compatibility."""
    return getattr(obj, 'prize_amount', None) or getattr(obj, 'prize_eur', None)


def _country(obj) -> str:
    c = (getattr(obj, 'country', '') or '').upper()
    cur = (getattr(obj, 'prize_currency', '') or '').upper()
    desc = (getattr(obj, 'race_type', '') or getattr(obj, 'race_desc', '') or '').upper()
    if c:
        return c
    if cur == 'AUD' or re.search(r'\bBM\s*0?\s*-?\s*\d{2,3}\b', desc):
        return 'AUSTRALIA'
    if cur == 'EUR':
        return 'FRANCE'
    return ''


def _extract_bm(desc: str) -> tuple[Optional[int], bool]:
    u = (desc or '').upper().replace('–', '-').replace('—', '-')
    m = re.search(r'\bBM\s*0\s*-\s*(\d{2,3})\b', u)
    if m:
        return int(m.group(1)), True
    m = re.search(r'\bBM\s*(\d{2,3})\b', u)
    if m:
        return int(m.group(1)), False
    return None, False


def _extract_au_class(desc: str) -> Optional[int]:
    u = (desc or '').upper()
    m = re.search(r'\bCL\s*([1-9])\b|\bCLASS\s*([1-9])\b', u)
    return int(m.group(1) or m.group(2)) if m else None


def _australian_bm_level(bm: int, capped: bool = False) -> float:
    # Normalise Australian benchmark ratings onto the same internal axis used by
    # the French model (lower = stronger). Roughly 6 benchmark points = one
    # effective class step. BM62 is anchored at level 4.0.
    lvl = 4.0 - (float(bm) - 62.0) / 6.0
    if capped:  # BM0-62 is slightly easier than an unrestricted BM62.
        lvl += 0.15
    return max(-1.0, min(6.5, lvl))


def _australian_prize_adjustment(desc: str, prize: Optional[float]) -> float:
    """Modest AUD purse refinement; BM/grade remains the primary Australian signal."""
    if not prize:
        return 0.0
    bm, capped = _extract_bm(desc)
    if bm is not None:
        # Typical Victorian/Australian purse bands; deliberately only a modest
        # modifier because metro/country programming varies by jurisdiction.
        anchors = {52:20000, 56:22000, 58:27000, 62:35000, 64:40000,
                   66:40000, 70:50000, 72:65000, 78:100000, 80:120000}
        keys = sorted(anchors)
        nearest = min(keys, key=lambda k: abs(k-bm))
        base = anchors[nearest]
    else:
        cl = _extract_au_class(desc)
        base = {1:30000, 2:35000, 3:45000, 4:55000, 5:65000}.get(cl or 0, 35000)
    adj = -0.18 * math.log(max(0.25, float(prize) / float(base)), 2)
    return max(-0.32, min(0.32, adj))


def _australian_level(desc: str, prize: Optional[float], class_no: Optional[int] = None) -> Optional[float]:
    u = (desc or '').upper()
    # Universal stakes grades parsed by the parser retain class_no <= 0.
    if class_no is not None and class_no <= 0:
        return float(class_no)
    bm, capped = _extract_bm(u)
    if bm is not None:
        return _australian_bm_level(bm, capped) + _australian_prize_adjustment(u, prize)
    cl = _extract_au_class(u)
    if cl is not None:
        # Australian Class 1/2/3 is a win-restriction ladder; higher number is
        # generally stronger, the opposite of the French CL numbering semantics.
        base = {1:5.25, 2:4.85, 3:4.45, 4:4.10, 5:3.80, 6:3.55}.get(cl, 4.6)
        return base + _australian_prize_adjustment(u, prize)
    if re.search(r'\bMDN\b|MAIDEN', u):
        return 6.05 + _australian_prize_adjustment(u, prize)
    if re.search(r'\bTRPY\b|TROPHY', u):
        return 6.35
    if re.search(r'\bOPEN\b', u):
        if prize and prize >= 200000: return 0.8
        if prize and prize >= 100000: return 1.4
        if prize and prize >= 60000: return 2.0
        return 2.6
    # Generic Australian fallback when a BM/CL label is absent. Prize money is
    # only a proxy, so keep it coarser than the explicit benchmark ladder.
    if prize:
        p = float(prize)
        if p >= 150000: return 1.6
        if p >= 100000: return 2.1
        if p >= 65000: return 2.7
        if p >= 50000: return 3.2
        if p >= 35000: return 4.0
        if p >= 27000: return 4.5
        if p >= 20000: return 5.1
        return 5.7
    return None


def _explicit_grade(obj) -> bool:
    if getattr(obj, 'class_no', None) is not None:
        return True
    desc = getattr(obj, 'race_type', '') or getattr(obj, 'race_desc', '') or ''
    if _extract_bm(desc)[0] is not None or _extract_au_class(desc) is not None:
        return True
    return bool(re.search(r'\bMDN\b|MAIDEN|\bOPEN\b|\bLR\b|LISTED|GROUP|\bG[123]\b', desc, re.I))


def _money_label(amount: Optional[float], currency: str) -> str:
    if not amount:
        return ''
    c = (currency or '').upper()
    if c == 'EUR': prefix = '€'
    elif c == 'AUD': prefix = 'AUD $'
    elif c == 'NZD': prefix = 'NZD $'
    elif c == 'GBP': prefix = '£'
    elif c == 'USD': prefix = 'US$'
    elif c == 'ZAR': prefix = 'ZAR '
    else: prefix = ''
    return f'{prefix}{amount/1000:.1f}k' if amount >= 1000 else f'{prefix}{amount:.0f}'


# ---------------------------------------------------------------------------
# Race-strength model
# Lower numeric level = stronger race, mirroring CL1 > CL2 > CL3 > CL4.
# Explicit class remains the primary signal. Prize money and race type refine
# the level and provide a proxy when the R&S race has no explicit CL label.
# ---------------------------------------------------------------------------

def _disc_weight(current: str, past: str) -> float:
    if current == past:
        return 1.0
    if current == 'HURDLE' and past == 'STEEPLE':
        return 0.45
    if current == 'STEEPLE' and past == 'HURDLE':
        return 0.60
    if current in {'HURDLE', 'STEEPLE'} and past == 'FLAT':
        return 0.18
    if current == 'FLAT' and past in {'HURDLE', 'STEEPLE'}:
        return 0.05
    return 0.25


def _family(desc: str, is_handicap: bool = False, is_claiming: bool = False) -> str:
    u = (desc or '').upper()
    if is_claiming or 'CLM' in u or 'CLAIM' in u:
        return 'CLM'
    if is_handicap or 'HCP' in u:
        return 'HCP'
    if 'COND' in u:
        return 'COND'
    if 'MDN' in u or 'MAIDEN' in u:
        return 'MDN'
    if 'LR' in u or 'LISTED' in u or 'GROUP' in u or ' G1' in u or ' G2' in u or ' G3' in u:
        return 'OPEN'
    if 'UNR' in u:
        return 'UNR'
    return 'OTHER'


def _field_quality(r: PastRace) -> float:
    if r.finish_status:
        return 0.05
    p = r.finish_pos
    if p is None:
        return 0.18
    pos_q = {1:1.00, 2:0.92, 3:0.84, 4:0.75, 5:0.66, 6:0.57,
             7:0.49, 8:0.42, 9:0.35, 10:0.30}.get(p, 0.22)
    if r.field_size and r.field_size > 1:
        percentile = 1.0 - (p - 1) / max(1, r.field_size - 1)
        q = 0.62 * pos_q + 0.38 * max(0.08, percentile)
    else:
        q = pos_q
    if r.margin is not None:
        if r.margin >= 40:
            q *= 0.38
        elif r.margin >= 25:
            q *= 0.50
        elif r.margin >= 15:
            q *= 0.64
        elif r.margin >= 8:
            q *= 0.80
        elif r.margin <= 2:
            q = min(1.0, q + 0.05)
    return max(0.02, min(1.0, q))


def _recency_weight(i: int) -> float:
    # Stronger recency emphasis after studying the Deauville results: recent
    # exact-grade competitiveness was more reliable than old back-class alone.
    return max(0.30, 0.90 ** i)


def _class_baseline_prize(discipline: str, fam: str, cls: int) -> Optional[float]:
    if discipline == 'FLAT':
        if fam == 'HCP':
            return {1:72000, 2:50900, 3:21100, 4:14400, 5:10000}.get(cls)
        if fam == 'CLM':
            return {1:45000, 2:26000, 3:18200, 4:15400, 5:11000}.get(cls)
        if fam == 'COND':
            return {1:35000, 2:24700, 3:17400, 4:14600, 5:11000}.get(cls)
        return {1:60000, 2:34000, 3:22000, 4:15000, 5:10000}.get(cls)
    # French jumps bands seen in R&S data.
    if fam == 'HCP':
        return {1:90000, 2:55000, 3:28000, 4:21000, 5:18000}.get(cls)
    if fam == 'CLM':
        return {1:70000, 2:50000, 3:25000, 4:19000, 5:14000}.get(cls)
    return {1:70000, 2:51000, 3:24000, 4:21000, 5:17000}.get(cls)


def _proxy_level(discipline: str, fam: str, prize: Optional[float]) -> Optional[float]:
    if not prize:
        return None
    p = float(prize)
    if discipline == 'FLAT':
        if fam == 'HCP':
            if p >= 70000: return 1.2
            if p >= 45000: return 2.0
            if p >= 28000: return 2.7
            if p >= 23500: return 2.9
            if p >= 18500: return 3.15
            if p >= 12500: return 4.0
            return 4.6
        if fam == 'CLM':
            if p >= 30000: return 3.0
            if p >= 22000: return 3.35
            if p >= 17500: return 3.70
            if p >= 13500: return 4.00
            if p >= 10500: return 4.25
            return 4.55
        if fam == 'COND':
            if p >= 35000: return 1.8
            if p >= 24500: return 2.5
            if p >= 17000: return 3.2
            if p >= 12500: return 4.0
            return 4.5
        if fam in {'MDN', 'UNR'}:
            if p >= 30000: return 3.0
            if p >= 24000: return 3.5
            if p >= 18000: return 4.0
            if p >= 10000: return 4.5
            return 4.8
        # Generic flat fallback.
        if p >= 50000: return 2.0
        if p >= 25000: return 3.0
        if p >= 15000: return 4.0
        return 4.7

    # Hurdle / steeple proxy bands.
    if fam == 'HCP':
        if p >= 90000: return 1.0
        if p >= 50000: return 2.0
        if p >= 35000: return 2.5
        if p >= 23000: return 3.0
        if p >= 17000: return 4.0
        return 5.0
    if fam == 'CLM':
        if p >= 50000: return 2.0
        if p >= 30000: return 2.8
        if p >= 23000: return 3.4
        if p >= 17000: return 4.0
        return 4.5
    if p >= 50000: return 2.0
    if p >= 23000: return 3.0
    if p >= 17000: return 4.0
    return 4.7


def _prize_adjustment(discipline: str, fam: str, cls: int, prize: Optional[float]) -> float:
    if not prize:
        return 0.0
    base = _class_baseline_prize(discipline, fam, cls)
    if not base:
        return 0.0
    # Higher purse within the same nominal class = modestly stronger race.
    adj = -0.24 * math.log(max(0.25, prize / base), 2)
    return max(-0.38, min(0.38, adj))


def _effective_level_for_values(
    discipline: str,
    race_desc: str,
    class_no: Optional[int],
    prize: Optional[float],
    is_handicap: bool,
    is_claiming: bool,
    country: str = '',
    currency: str = '',
    benchmark_rating: Optional[int] = None,
) -> Optional[float]:
    fam = _family(race_desc, is_handicap, is_claiming)
    c = (country or '').upper()
    if c == 'AUSTRALIA' or (currency or '').upper() == 'AUD' or benchmark_rating is not None or _extract_bm(race_desc)[0] is not None:
        return _australian_level(race_desc, prize, class_no)
    if class_no is not None:
        # Listed/Group labels are already encoded at 0/-1/-2/-3 by parser.
        if class_no <= 0:
            return float(class_no)
        lvl = float(class_no) + _prize_adjustment(discipline, fam, class_no, prize)
        # Claiming races are generally weaker evidence than standard races at the
        # same nominal class. This is small because evidence weighting also handles it.
        if fam == 'CLM':
            lvl += 0.22
        return lvl
    return _proxy_level(discipline, fam, prize)


def _current_reference_level(race: Race) -> Optional[float]:
    return _effective_level_for_values(
        race.discipline, race.race_type, race.current_class, _prize_amount(race),
        race.is_handicap, race.is_claiming, _country(race), race.prize_currency,
        getattr(race, 'benchmark_rating', None),
    )


def _effective_level(pr: PastRace) -> Optional[float]:
    return _effective_level_for_values(
        pr.discipline, pr.race_desc, pr.class_no, _prize_amount(pr),
        pr.is_handicap, pr.is_claiming, _country(pr), pr.prize_currency,
        getattr(pr, 'benchmark_rating', None),
    )


def _level_label(level: Optional[float]) -> str:
    if level is None:
        return 'unclassified'
    if level <= -2.5: return 'G1'
    if level <= -1.5: return 'G2'
    if level <= -0.5: return 'G3'
    if level < 0.75: return 'Listed'
    return f'CL{int(round(level))}'


def _reference_label(race: Race, level: Optional[float]) -> str:
    if level is None:
        return 'unclassified'
    if _country(race) == 'AUSTRALIA':
        bm, capped = _extract_bm(race.race_type)
        if bm is not None:
            return f'BM0-{bm}' if capped else f'BM{bm}'
        cl = _extract_au_class(race.race_type)
        if cl is not None:
            return f'Australian CL{cl}'
        if re.search(r'\bMDN\b|MAIDEN', race.race_type, re.I):
            return 'Australian Maiden'
        if getattr(race, 'grade_label', ''):
            return race.grade_label
        return f'Australian strength index {level:.2f}'
    return _level_label(level)


def _display_race_strength(pr: PastRace) -> str:
    country = _country(pr)
    amount = _prize_amount(pr)
    money = _money_label(amount, pr.prize_currency)
    desc = (pr.race_desc or '').upper().strip()
    if country == 'AUSTRALIA':
        bm, capped = _extract_bm(desc)
        if bm is not None:
            lab = f'BM0-{bm}' if capped else f'BM{bm}'
        else:
            cl = _extract_au_class(desc)
            if cl is not None:
                lab = f'CL{cl}'
            elif re.search(r'\bMDN\b|MAIDEN', desc):
                lab = 'MDN'
            elif pr.level_label:
                lab = pr.level_label
            else:
                lab = desc or 'Unclassified'
        return f'{lab} {money}'.strip()
    if pr.level_label:
        return f'{pr.level_label} {money}'.strip()
    fam = _family(pr.race_desc, pr.is_handicap, pr.is_claiming)
    return f'{desc or fam} {money}'.strip() or 'Unclassified'


def _type_match(current_fam: str, past_fam: str) -> float:
    if current_fam == past_fam:
        return 1.0
    pairs = {('HCP','COND'):0.84, ('COND','HCP'):0.84,
             ('HCP','CLM'):0.67, ('CLM','HCP'):0.78,
             ('CLM','COND'):0.72, ('COND','CLM'):0.65,
             ('MDN','CLM'):0.70, ('CLM','MDN'):0.72}
    return pairs.get((current_fam, past_fam), 0.58)


def _prize_similarity(race: Race, pr: PastRace) -> float:
    rp, pp = _prize_amount(race), _prize_amount(pr)
    if not rp or not pp:
        return 0.72
    # Do not numerically equate different currencies/countries.
    if race.prize_currency and pr.prize_currency and race.prize_currency != pr.prize_currency:
        return 0.42
    ratio = max(0.15, min(6.0, pp / rp))
    sim = math.exp(-0.85 * abs(math.log(ratio)))
    return max(0.15, min(1.0, sim))


def _movement_info(race: Race, runner: Runner) -> tuple[str, Optional[float], Optional[float]]:
    current = _current_reference_level(race)
    if current is None:
        return 'Current class benchmark not established', None, None
    latest = None
    best_proven = None
    best_q = 0.0
    for pr in runner.past_races:
        if _disc_weight(race.discipline, pr.discipline) < 0.95:
            continue
        lvl = _effective_level(pr)
        if lvl is None:
            continue
        q = _field_quality(pr)
        if latest is None:
            latest = lvl
        if q >= 0.52 and (best_proven is None or lvl < best_proven or (abs(lvl-best_proven)<0.15 and q>best_q)):
            best_proven, best_q = lvl, q

    if latest is None:
        return 'Unknown / insufficient evidence', latest, best_proven
    latest_diff = latest - current  # positive = latest weaker, so today is up
    proven_diff = None if best_proven is None else best_proven - current

    if proven_diff is not None and proven_diff <= -0.55 and latest_diff >= 0.55:
        return 'Up from latest; below proven ceiling', latest, best_proven
    if proven_diff is not None and proven_diff <= -0.55 and abs(latest_diff) < 0.55:
        return 'Same today; proven higher', latest, best_proven
    if latest_diff <= -1.35:
        return 'Strong class drop', latest, best_proven
    if latest_diff <= -0.55:
        return 'Down in class', latest, best_proven
    if latest_diff < 0.55:
        return 'Same / similar class', latest, best_proven
    if latest_diff < 1.35:
        return 'Up in class', latest, best_proven
    return 'Significant class rise', latest, best_proven


def _compact_class_history(race: Race, runner: Runner, n: int = 5) -> str:
    bits = []
    for pr in runner.past_races:
        if len(bits) >= n:
            break
        if _disc_weight(race.discipline, pr.discipline) < 0.40:
            continue
        lab = _display_race_strength(pr)
        fp = pr.finish_status or (f'{pr.finish_pos}th' if pr.finish_pos else '?')
        if pr.finish_pos == 1: fp = '1st'
        elif pr.finish_pos == 2: fp = '2nd'
        elif pr.finish_pos == 3: fp = '3rd'
        bits.append(f'{lab} {fp}')
    return ' → '.join(bits) if bits else 'No usable previous class evidence'


# ---------------------------------------------------------------------------
# Feature extraction and heuristic class score
# ---------------------------------------------------------------------------

def _profile_features(race: Race, runner: Runner, heuristic_score: float = 5.0) -> list[float]:
    current = _current_reference_level(race)
    if current is None:
        current = 4.0
    cfam = _family(race.race_type, race.is_handicap, race.is_claiming)
    same, exact, higher, lower, cross, claiming = [], [], [], [], [], []
    same_comp = higher_comp = 0
    recent_same = []
    recent_win = 0.0
    latest_diff = 0.0
    latest_found = False
    best_proven_gap = 0.0
    best_proven_set = False
    stronger_prize_comp = []
    recent_lower_top2 = 0.0
    recent_lower_win = 0.0

    for i, pr in enumerate(runner.past_races):
        dw = _disc_weight(race.discipline, pr.discipline)
        if dw < 0.15:
            continue
        lvl = _effective_level(pr)
        if lvl is None:
            continue
        q = _field_quality(pr)
        rw = _recency_weight(i)
        explicit = _explicit_grade(pr)
        reliability = 1.0 if explicit else 0.86
        pfam = _family(pr.race_desc, pr.is_handicap, pr.is_claiming)
        typem = _type_match(cfam, pfam)
        psim = _prize_similarity(race, pr)
        ev = q * rw * dw * reliability
        if pr.is_claiming and cfam != 'CLM':
            ev *= 0.80

        if pr.discipline == race.discipline and not latest_found:
            latest_diff = max(-3.0, min(3.0, lvl - current))
            latest_found = True

        gap = current - lvl  # positive => past stronger
        if pr.discipline == race.discipline:
            if q >= 0.52 and (not best_proven_set or gap > best_proven_gap):
                best_proven_gap = gap
                best_proven_set = True
            if gap > 0.35:
                competitiveness = max(0.0, (q - 0.24) / 0.76)
                v = ev * competitiveness * min(1.45, 0.85 + 0.25 * gap)
                higher.append(v)
                if q >= 0.52:
                    higher_comp += 1
            elif gap < -0.35:
                lower.append(ev * min(1.35, abs(gap)))
                if i < 3 and gap > -1.45 and pr.finish_pos in {1,2,3}:
                    recent_lower_top2 = max(recent_lower_top2, rw * q)
                    if pr.finish_pos == 1:
                        recent_lower_win = max(recent_lower_win, rw)
            else:
                comp = ev * (0.78 + 0.22 * typem) * (0.78 + 0.22 * psim)
                same.append(comp)
                if typem >= 0.95 and psim >= 0.68:
                    exact.append(comp)
                if q >= 0.52:
                    same_comp += 1
                if i < 4:
                    recent_same.append(comp)
                if pr.finish_pos == 1 and i < 4:
                    recent_win = max(recent_win, rw * (0.7 + 0.3 * typem))
            rp, pp = _prize_amount(race), _prize_amount(pr)
            if (rp and pp and race.prize_currency == pr.prize_currency
                    and pp >= 1.18 * rp and q >= 0.52):
                stronger_prize_comp.append(ev * min(1.35, pp / rp))
        elif race.discipline in {'HURDLE', 'STEEPLE'} and dw >= 0.40:
            cross.append(ev * dw)

        if pr.is_claiming:
            claiming.append(ev)

    def agg(vals, weights=(1.0, .58, .34, .18)):
        vals = sorted(vals, reverse=True)
        return sum(v*w for v, w in zip(vals, weights))

    return [
        heuristic_score / 10.0,
        current / 5.0,
        1.0 if race.discipline == 'FLAT' else 0.0,
        1.0 if race.discipline == 'HURDLE' else 0.0,
        1.0 if race.discipline == 'STEEPLE' else 0.0,
        1.0 if cfam == 'HCP' else 0.0,
        1.0 if cfam == 'CLM' else 0.0,
        latest_diff / 3.0,
        agg(same) / 1.8,
        agg(exact) / 1.8,
        agg(higher) / 1.8,
        agg(lower) / 1.8,
        agg(stronger_prize_comp) / 1.8,
        agg(cross) / 1.3,
        min(1.0, same_comp / 4.0),
        min(1.0, higher_comp / 3.0),
        min(1.0, sum(sorted(recent_same, reverse=True)[:2]) / 1.5),
        recent_win,
        max(-1.0, min(1.0, best_proven_gap / 2.5)) if best_proven_set else 0.0,
        recent_lower_top2,
        recent_lower_win,
        min(1.0, len(runner.past_races) / 10.0),
        agg(claiming) / 1.8,
    ]


def _heuristic_score(race: Race, runner: Runner) -> tuple[float, dict]:
    current = _current_reference_level(race)
    if current is None or not runner.past_races:
        return 5.0, {'usable': 0}

    cfam = _family(race.race_type, race.is_handicap, race.is_claiming)
    same, exact, higher, lower, recent_same, stronger_prize = [], [], [], [], [], []
    usable = 0
    latest = None
    recent_win = 0.0
    recent_lower_top = 0.0
    recent_lower_win = 0.0

    for i, pr in enumerate(runner.past_races):
        dw = _disc_weight(race.discipline, pr.discipline)
        if dw < 0.15:
            continue
        lvl = _effective_level(pr)
        if lvl is None:
            continue
        q = _field_quality(pr)
        rw = _recency_weight(i)
        explicit = _explicit_grade(pr)
        reliability = 1.0 if explicit else 0.86
        pfam = _family(pr.race_desc, pr.is_handicap, pr.is_claiming)
        tm = _type_match(cfam, pfam)
        ps = _prize_similarity(race, pr)
        proof = q * rw * dw * reliability
        if pr.is_claiming and cfam != 'CLM':
            proof *= 0.80
        if pr.discipline == race.discipline:
            usable += 1
            if latest is None:
                latest = lvl
        gap = current - lvl
        if gap > 0.35:
            competitiveness = max(0.0, (q - 0.24) / 0.76)
            higher.append(proof * competitiveness * min(1.45, 0.82 + 0.27*gap))
        elif gap < -0.35:
            lower.append(proof * min(1.35, abs(gap)))
            if i < 3 and gap > -1.45 and pr.discipline == race.discipline and pr.finish_pos in {1,2,3}:
                recent_lower_top = max(recent_lower_top, rw*q)
                if pr.finish_pos == 1:
                    recent_lower_win = max(recent_lower_win, rw)
        else:
            comp = proof * (0.78 + 0.22*tm) * (0.78 + 0.22*ps)
            same.append(comp)
            if tm >= 0.95 and ps >= 0.68:
                exact.append(comp)
            if i < 4 and pr.discipline == race.discipline:
                recent_same.append(comp)
            if pr.finish_pos == 1 and i < 4 and pr.discipline == race.discipline:
                recent_win = max(recent_win, rw*(0.72+0.28*tm))
        rp, pp = _prize_amount(race), _prize_amount(pr)
        if (pr.discipline == race.discipline and rp and pp
                and race.prize_currency == pr.prize_currency and pp >= 1.18*rp and q >= 0.52):
            stronger_prize.append(proof * min(1.30, pp/rp))

    def agg(vals, w=(1.0,.58,.34,.18)):
        vals = sorted(vals, reverse=True)
        return sum(v*a for v,a in zip(vals,w))

    ss, ex, hs, ls = agg(same), agg(exact), agg(higher), agg(lower)
    rp = agg(stronger_prize)
    rs = sum(sorted(recent_same, reverse=True)[:2])

    score = 5.05 if usable else 5.0
    # Deauville feedback: repeated recent performance in the exact current grade
    # is the strongest class signal; old higher-class exposure is useful but less dominant.
    score += 1.85 * min(1.0, ss)
    score += 0.58 * min(1.0, ex)
    score += 1.65 * min(1.0, hs)
    score += 0.35 * min(1.0, rp)
    score += 0.48 * min(1.0, rs)
    score += 0.32 * recent_win
    # Actual Deauville results repeatedly showed that an improving runner coming
    # off a top-3 at the immediately lower level can handle a one-class rise.
    score += 0.62 * recent_lower_top
    score += 0.30 * recent_lower_win

    if ss < 0.20 and hs < 0.10:
        score += 1.30 * min(1.0, ls)
        if latest is not None and latest - current > 0.45:
            score -= min(1.10, 0.48*(latest-current))
    else:
        score += 0.20 * min(1.0, ls)

    if latest is not None:
        d = latest - current
        if d <= -0.9:
            score += 0.30
        elif d >= 0.9 and ss < 0.30 and hs < 0.18:
            score -= 0.45

    if usable == 1:
        score -= 0.18
    if usable <= 2 and not same and not higher:
        score -= 0.25

    return round(max(1.0, min(9.9, score)), 3), {
        'usable': usable, 'same': ss, 'exact': ex, 'higher': hs, 'lower': ls,
        'stronger_prize': rp, 'recent_same': rs, 'recent_win': recent_win,
        'recent_lower_top': recent_lower_top, 'recent_lower_win': recent_lower_win,
    }


# ---------------------------------------------------------------------------
# Human worked-example calibration + actual-result feedback calibration
# ---------------------------------------------------------------------------

_CALIBRATION_CACHE = None
_CALIBRATION_TARGETS = {
    'Vittel_R4.md': {
        'FANTASTIC STAR': 9.4, 'COMBERMERE': 8.7, 'ALGECIRAS': 8.2,
        'PASSAGE MESLAY': 7.8, 'VALERTA': 7.3, 'WAITARA': 6.5,
        'RIO GRANDE': 6.1, 'CASCADEO': 5.7,
    },
    'Race8_CL2.md': {
        'DOUBLE UP': 9.9, 'ZELORO': 9.8, 'SEONA': 9.6,
        'SAINT AQUILIN (GB)': 9.6, 'FEARLESS CHEETAH': 9.5,
        'STANGHELI': 9.3, "ROI DE L'AIR (GER)": 9.1,
        'TRUE TEDESCO (GER)': 9.1, 'STRAKO': 9.0,
        'MEMPHIS TENNESSEE': 9.0, 'CHAUMIERE DE PRE': 8.9,
        'EVERSTAR': 8.6, 'ZACAPO (IRE)': 8.1, 'VOLCANO': 7.7,
        'MY QUEEN': 7.4, 'AVANT NOUS': 7.0,
    },
    'Vittel_R5_plain.txt': {
        'LA PRODIGIEUSE': 8.6, 'SHADES': 8.0, 'MADAME ROYALE': 7.1,
        'STUDY THE LADY (GB)': 6.8, 'LADY ZAZA': 6.2,
        'MAGIC DE FREGANDE': 5.0, 'MATELINE DE GUYE': 4.5,
    },
    'Vittel_R6_unclassified_hurdle.md': {
        'JOLI LOOK': 8.8, 'IMPERIUM': 8.5, 'JILAIJONE': 8.3,
        'ALGAJUST': 8.1, 'KABRIOLE DE SIVOLA': 7.7, 'SACRED UNION': 7.2,
        'LUNA LUPA (GB)': 6.8, 'LERIKA': 5.9,
    },
}


def _load_calibration_anchors():
    global _CALIBRATION_CACHE
    if _CALIBRATION_CACHE is not None:
        return _CALIBRATION_CACHE
    anchors = []
    try:
        from race_parser import parse_race
        root = Path(__file__).resolve().parent / 'sample_data'
        for fn, targets in _CALIBRATION_TARGETS.items():
            path = root / fn
            if not path.exists():
                continue
            race = parse_race(path.read_text(encoding='utf-8'))
            for runner in race.runners:
                if runner.horse in targets:
                    h, _ = _heuristic_score(race, runner)
                    anchors.append((_profile_features(race, runner, h), float(targets[runner.horse]), race.discipline, _current_reference_level(race)))
    except Exception:
        anchors = []
    _CALIBRATION_CACHE = anchors
    return anchors


def _human_calibrated_score(race: Race, runner: Runner, heuristic: float) -> float:
    if _country(race) == 'AUSTRALIA':
        return heuristic
    anchors = _load_calibration_anchors()
    if not anchors:
        return heuristic
    x = _profile_features(race, runner, heuristic)
    cur = _current_reference_level(race)
    ds = []
    for feat, target, disc, aref in anchors:
        d2 = sum((a-b)**2 for a,b in zip(x,feat))
        if disc != race.discipline:
            d2 += 4.0
        if cur is not None and aref is not None:
            d2 += 0.16*((cur-aref)**2)
        ds.append((math.sqrt(d2), target))
    ds.sort(key=lambda z:z[0])
    if ds and ds[0][0] < 1e-10:
        return round(ds[0][1],1)
    near = ds[:5]
    ws = [1.0/max(0.10,d*d) for d,_ in near]
    knn = sum(w*t for w,(_,t) in zip(ws,near))/sum(ws)
    # Reduced from the old 72% KNN: Deauville results showed that over-anchoring
    # to a few historic worked examples could distort new race profiles.
    return 0.90*heuristic + 0.10*knn


def _load_feedback_model() -> Optional[dict]:
    path = Path(__file__).resolve().parent / 'feedback_model.json'
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    except Exception:
        return None


def _feedback_adjustment(race: Race, runner: Runner, heuristic: float) -> float:
    if _country(race) == 'AUSTRALIA':
        return 0.0
    # Preserve the exact human-calibrated worked examples; result feedback is for
    # generalisation to new profiles, not for rewriting established manual scores.
    x = _profile_features(race, runner, heuristic)
    cur = _current_reference_level(race)
    for feat, _target, disc, aref in _load_calibration_anchors():
        if disc != race.discipline:
            continue
        if cur is not None and aref is not None and abs(cur-aref) > 1e-9:
            continue
        if len(feat) == len(x) and sum((a-b)**2 for a,b in zip(feat,x)) < 1e-18:
            return 0.0
    model = _load_feedback_model()
    if not model:
        return 0.0
    means, scales, weights = model['means'], model['scales'], model['weights']
    z = 0.0
    for a,m,s,w in zip(x,means,scales,weights):
        z += ((a-m)/s if s else 0.0)*w
    z += model.get('intercept',0.0)
    # The result feedback is deliberately bounded. Results also contain speed,
    # suitability, tactics etc.; only repeatable class-feature relationships are
    # allowed to nudge the class score.
    return float(model.get('max_adjustment',0.55))*math.tanh(z)


def _best_proven_race(race: Race, runner: Runner) -> Optional[PastRace]:
    best = None
    best_lvl = None
    best_q = 0.0
    for pr in runner.past_races:
        if _disc_weight(race.discipline, pr.discipline) < 0.95:
            continue
        lvl = _effective_level(pr)
        q = _field_quality(pr)
        if lvl is None or q < 0.52:
            continue
        if best is None or lvl < best_lvl or (abs(lvl-best_lvl) < 0.15 and q > best_q):
            best, best_lvl, best_q = pr, lvl, q
    return best


def analyse_runner(race: Race, runner: Runner) -> Analysis:
    current = _current_reference_level(race)
    hist = _compact_class_history(race, runner)
    if current is None or not runner.past_races:
        return Analysis(number=runner.number, horse=runner.horse, odds=runner.odds,
                        relevant_previous_class=hist, movement='Unknown', proven_level='Unknown',
                        assessment='Insufficient class evidence', score=5.0, confidence='Very Low',
                        explanation='The current effective race strength or the horse’s previous class evidence could not be established reliably. The score is neutral and provisional.')

    heuristic, stats = _heuristic_score(race, runner)
    score = _human_calibrated_score(race, runner, heuristic)
    score += _feedback_adjustment(race, runner, heuristic)
    score = round(max(1.0,min(9.9,score)),1)

    movement, latest, best_proven = _movement_info(race, runner)
    best_pr = _best_proven_race(race, runner)
    if best_pr is not None:
        proven = f'Competitive at {_display_race_strength(best_pr)} level'
    elif best_proven is not None:
        proven = f'Competitive around {_level_label(best_proven)} strength'
    else:
        proven = 'Not yet strongly proven at this level'

    if score >= 9.3:
        assessment = 'Strong class advantage / elite credentials for today'
    elif score >= 8.4:
        assessment = 'Very strong class credentials'
    elif score >= 7.4:
        assessment = 'Good class credentials / capable at this level'
    elif score >= 6.4:
        assessment = 'Some class evidence; today is a meaningful test'
    elif score >= 5.4:
        assessment = 'Mostly appropriate class / limited higher-level proof'
    elif score >= 4.4:
        assessment = 'Class rise or weak evidence at today’s level'
    else:
        assessment = 'Significant class concern'

    usable = stats.get('usable',0)
    if usable >= 7: conf = 'High'
    elif usable >= 4: conf = 'Medium-High'
    elif usable >= 2: conf = 'Medium'
    elif usable == 1: conf = 'Low'
    else: conf = 'Very Low'

    cfam = _family(race.race_type, race.is_handicap, race.is_claiming)
    if _country(race) == 'AUSTRALIA':
        benchmark = f"{_reference_label(race, current)} ({race.prize_raw or 'purse unavailable'})"
        method_text = (
            "For Australian racing the Benchmark/grade is the primary class signal (for example BM70 > BM66 > BM62 > BM56); "
            "BM0-X uses its upper ceiling, Australian Class 1/2/3 is treated as a win-restriction ladder rather than French CL numbering, and AUD prize money modestly refines the grade. "
        )
    elif race.current_class is not None:
        benchmark = f"{race.race_type} with an effective strength around {_level_label(current)}"
        method_text = "The model uses official class first, then race prize money as a class-strength proxy, and race type (handicap/claiming/conditions) to refine comparability. "
    else:
        benchmark = f"unlabelled {race.race_type} benchmarked around {_level_label(current)} from race type and {race.prize_raw or 'prize money'}"
        method_text = "The model uses race type and prize money as the class-strength proxy when no official French CL number is supplied. "
    explanation = (
        f"Today is {benchmark}. {runner.horse}'s recent relevant class sequence is {hist}. "
        f"The movement is assessed as {movement.lower()}. {proven}. "
        + method_text +
        "Recent competitive runs in the same effective grade and similar purse receive the strongest credit. Higher-class starts only receive strong credit when the horse actually performed competitively; old back-class is recency-discounted. "
        "Odds are display-only and do not enter the class score."
    )
    if race.discipline in {'HURDLE','STEEPLE'}:
        explanation += f" {race.discipline.title()} form was prioritised and other disciplines were down-weighted."

    evidence = []
    for pr in runner.past_races[:12]:
        if _disc_weight(race.discipline, pr.discipline) < 0.40:
            continue
        q = _field_quality(pr)
        evidence.append(f"{pr.date_raw}: {pr.finish_raw or pr.finish_status} — {_display_race_strength(pr)}; class-performance quality {q:.2f}")
        if len(evidence) >= 10:
            break

    return Analysis(number=runner.number, horse=runner.horse, odds=runner.odds,
                    relevant_previous_class=hist, movement=movement, proven_level=proven,
                    assessment=assessment, score=score, confidence=conf,
                    explanation=explanation, evidence_lines=evidence)


def analyse_race(race: Race) -> list[Analysis]:
    results = [analyse_runner(race,r) for r in race.runners if not getattr(r,'scratched',False)]
    results.sort(key=lambda a:(-a.score,a.number))
    for i,a in enumerate(results,1):
        a.rank=i
    return results


def analyses_to_dict(results: list[Analysis]) -> list[dict]:
    return [asdict(x) for x in results]
