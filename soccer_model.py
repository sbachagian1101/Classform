from __future__ import annotations

import math
from dataclasses import dataclass, field

from soccer_parser import TeamProfile, MatchResult, recent_summary, h2h_matches, canonical_team


@dataclass
class SoccerPrediction:
    home: str
    away: str
    home_xg: float
    away_xg: float
    home_win: float
    draw: float
    away_win: float
    btts_yes: float
    btts_no: float
    over25: float
    under25: float
    home_attack_index: float
    home_def_weakness: float
    away_attack_index: float
    away_def_weakness: float
    confidence: str
    likely_scores: list[tuple[str, float]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    diagnostics: dict[str, float] = field(default_factory=dict)
    h2h: list[MatchResult] = field(default_factory=list)
    data_quality: str = ""


def _clip(x, lo, hi):
    return max(lo, min(hi, float(x)))


def _mean(*values, default=None):
    xs = [float(x) for x in values if x is not None]
    if xs:
        return sum(xs) / len(xs)
    if default is None:
        return None
    return float(default)


def _at(values, idx):
    return values[idx] if values and len(values) > idx else None


def _poisson(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _score_matrix(lh, la, rho=-0.055, max_goals=10):
    matrix = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson(h, lh) * _poisson(a, la)
            if h == 0 and a == 0:
                p *= max(0.01, 1 - lh * la * rho)
            elif h == 0 and a == 1:
                p *= max(0.01, 1 + lh * rho)
            elif h == 1 and a == 0:
                p *= max(0.01, 1 + la * rho)
            elif h == 1 and a == 1:
                p *= max(0.01, 1 - rho)
            matrix[(h, a)] = p
    total = sum(matrix.values()) or 1.0
    return {k: v / total for k, v in matrix.items()}


def _three_way(matrix):
    return (
        sum(p for (h, a), p in matrix.items() if h > a),
        sum(p for (h, a), p in matrix.items() if h == a),
        sum(p for (h, a), p in matrix.items() if h < a),
    )


def _norm3(values):
    values = [max(1e-9, float(v)) for v in values]
    total = sum(values) or 1.0
    return tuple(v / total for v in values)


def _binary_calibrate(p, strength=0.84):
    p = _clip(p, 0.01, 0.99)
    logit = math.log(p / (1 - p))
    return 1 / (1 + math.exp(-strength * logit))


def _calibrate3(values, power=0.93):
    return _norm3([max(v, 1e-9) ** power for v in values])


def _shrink_rate(rate_pct, n, prior_pct, k=8.0):
    if rate_pct is None:
        return prior_pct
    n = max(0.0, float(n or 0))
    prior_pct = 50.0 if prior_pct is None else float(prior_pct)
    return (n * float(rate_pct) + k * prior_pct) / (n + k)


def _shrink_avg(value, n, prior, k=6.0):
    if value is None:
        return prior
    n = max(0.0, float(n or 0))
    if prior is None:
        return float(value)
    return (n * float(value) + k * float(prior)) / (n + k)


def _ppg_component(home_ppg, away_ppg, home_gd=0.0, away_gd=0.0):
    hp = float(home_ppg)
    ap = float(away_ppg)
    diff = _clip((hp - ap) + 0.12 * (home_gd - away_gd), -2.2, 2.2)
    home = math.exp(0.58 * diff)
    away = math.exp(-0.58 * diff)
    draw = _clip(0.98 - 0.07 * abs(diff), 0.62, 1.00)
    return _norm3((home, draw, away))


def _venue_wdl_component(home, away, hv_n, av_n):
    hw = _shrink_rate(_at(home.wins_pct, 1), hv_n, _at(home.wins_pct, 0), 6)
    hd = _shrink_rate(_at(home.draws_pct, 1), hv_n, _at(home.draws_pct, 0), 6)
    hl = _shrink_rate(_at(home.losses_pct, 1), hv_n, _at(home.losses_pct, 0), 6)
    aw = _shrink_rate(_at(away.wins_pct, 2), av_n, _at(away.wins_pct, 0), 6)
    ad = _shrink_rate(_at(away.draws_pct, 2), av_n, _at(away.draws_pct, 0), 6)
    al = _shrink_rate(_at(away.losses_pct, 2), av_n, _at(away.losses_pct, 0), 6)
    base = _norm3(((hw + al) / 2, (hd + ad) / 2, (aw + hl) / 2))
    ppg_diff = _clip(float(home.ppg_home) - float(away.ppg_away), -2, 2)
    tilted = (base[0] * math.exp(0.18 * ppg_diff), base[1], base[2] * math.exp(-0.18 * ppg_diff))
    return _norm3(tilted)


def _h2h_component(home, matches):
    if not matches:
        return (1 / 3, 1 / 3, 1 / 3)
    hk = canonical_team(home.name)
    home_s = draw_s = away_s = 1.8
    weights = [0.70, 0.50, 0.35, 0.25, 0.18]
    for w, m in zip(weights, matches):
        if canonical_team(m.home) == hk:
            hg, ag = m.home_goals, m.away_goals
        else:
            hg, ag = m.away_goals, m.home_goals
        if hg > ag:
            home_s += 2.2 * w
        elif hg == ag:
            draw_s += 2.2 * w
        else:
            away_s += 2.2 * w
    return _norm3((home_s, draw_s, away_s))


def _h2h_binary(home, matches, kind):
    if not matches:
        return None
    hk = canonical_team(home.name)
    weights = [1.0, 0.75, 0.55, 0.40, 0.30]
    yes = den = 0.0
    for w, m in zip(weights, matches):
        if canonical_team(m.home) == hk:
            hg, ag = m.home_goals, m.away_goals
        else:
            hg, ag = m.away_goals, m.home_goals
        if kind == "btts":
            hit = hg > 0 and ag > 0
        else:
            hit = hg + ag > 2
        yes += w * int(hit)
        den += w
    return yes / den if den else None


def _actual_goal_lambda(home, away, hv_n, av_n):
    hgf = _shrink_avg(_at(home.gf, 1), hv_n, _at(home.gf, 0), 6)
    aga = _shrink_avg(_at(away.ga, 2), av_n, _at(away.ga, 0), 6)
    agf = _shrink_avg(_at(away.gf, 2), av_n, _at(away.gf, 0), 6)
    hga = _shrink_avg(_at(home.ga, 1), hv_n, _at(home.ga, 0), 6)
    return _mean(hgf, aga), _mean(agf, hga)


def _xg_goal_lambda(home, away):
    return (
        _mean(_at(home.xgf, 1), _at(away.xga, 2)),
        _mean(_at(away.xgf, 2), _at(home.xga, 1)),
    )


def _expected_goals(home, away, hr10, ar10, hrv, arv):
    hv_n, av_n = hrv["n"], arv["n"]
    hxg, axg = _xg_goal_lambda(home, away)
    hact, aact = _actual_goal_lambda(home, away, hv_n, av_n)
    hre = _mean(hr10.get("gf"), ar10.get("ga"), default=hact)
    are = _mean(ar10.get("gf"), hr10.get("ga"), default=aact)
    hvr = _mean(hrv.get("gf"), arv.get("ga"), default=hact)
    avr = _mean(arv.get("gf"), hrv.get("ga"), default=aact)
    lh = 0.50 * hxg + 0.20 * hact + 0.20 * hre + 0.10 * hvr
    la = 0.50 * axg + 0.20 * aact + 0.20 * are + 0.10 * avr
    lh = 0.94 * lh + 0.06 * 1.35
    la = 0.94 * la + 0.06 * 1.35
    return _clip(lh, 0.25, 4.2), _clip(la, 0.25, 4.2), hxg, axg, hact, aact


def _score_probability(lam):
    return 1.0 - math.exp(-max(0.01, lam))


def _attack_index(profile, venue_idx, recent):
    xg = _at(profile.xgf, venue_idx)
    gf = _at(profile.gf, venue_idx)
    shots = _at(profile.shots, venue_idx)
    sot = _at(profile.shots_on_target, venue_idx)
    recent_gf = recent.get("gf")
    signal = 0.52 * xg + 0.23 * gf + 0.15 * (recent_gf if recent_gf is not None else gf) + 0.10 * 1.5
    score = 50 + 18 * (signal - 1.5)
    if shots is not None:
        score += 0.65 * (shots - 12.0)
    if sot is not None:
        score += 0.85 * (sot - 4.8)
    return _clip(score, 5, 95)


def _def_weakness_index(profile, venue_idx, recent, venue_n):
    xga = _at(profile.xga, venue_idx)
    ga = _at(profile.ga, venue_idx)
    rga = recent.get("ga")
    cs = _shrink_rate(_at(profile.clean_sheets, venue_idx), venue_n, _at(profile.clean_sheets, 0), 8)
    signal = 0.55 * xga + 0.25 * ga + 0.20 * (rga if rga is not None else ga)
    score = 50 + 18 * (signal - 1.5) + 0.16 * (35 - cs)
    return _clip(score, 5, 95)


def validate_match_inputs(home: TeamProfile, away: TeamProfile):
    errors = []
    warnings = []
    required = [
        (home.name, "home GF", _at(home.gf, 1)),
        (home.name, "home GA", _at(home.ga, 1)),
        (home.name, "home xG", _at(home.xgf, 1)),
        (home.name, "home xGA", _at(home.xga, 1)),
        (home.name, "home PPG", home.ppg_home),
        (home.name, "home W/D/L", None if any(_at(x, 1) is None for x in (home.wins_pct, home.draws_pct, home.losses_pct)) else 1),
        (away.name, "away GF", _at(away.gf, 2)),
        (away.name, "away GA", _at(away.ga, 2)),
        (away.name, "away xG", _at(away.xgf, 2)),
        (away.name, "away xGA", _at(away.xga, 2)),
        (away.name, "away PPG", away.ppg_away),
        (away.name, "away W/D/L", None if any(_at(x, 2) is None for x in (away.wins_pct, away.draws_pct, away.losses_pct)) else 1),
    ]
    for team, label, value in required:
        if value is None:
            errors.append(f"{team}: missing {label}")
    for team, profile, idx in ((home.name, home, 1), (away.name, away, 2)):
        if _at(profile.btts, idx) is None:
            warnings.append(f"{team}: venue BTTS rate missing")
        if _at(profile.over25, idx) is None:
            warnings.append(f"{team}: venue Over 2.5 rate missing")
        if len(profile.matches) < 5:
            errors.append(f"{team}: fewer than 5 completed matches were parsed")
        elif len(profile.matches) < 10:
            warnings.append(f"{team}: only {len(profile.matches)} completed matches parsed")
    return errors, warnings


def analyse_match(home: TeamProfile, away: TeamProfile) -> SoccerPrediction:
    errors, warnings = validate_match_inputs(home, away)
    if errors:
        raise ValueError("Prediction blocked — insufficient parsed data: " + "; ".join(errors))

    hr10 = recent_summary(home, 10)
    ar10 = recent_summary(away, 10)
    hrv = recent_summary(home, 10, "home")
    arv = recent_summary(away, 10, "away")
    h2h = h2h_matches(home, away, 5)

    lh, la, hxg, axg, hact, aact = _expected_goals(home, away, hr10, ar10, hrv, arv)

    venue = _venue_wdl_component(home, away, hrv["n"], arv["n"])
    xg_component = _three_way(_score_matrix(_clip(hxg, 0.2, 3.8), _clip(axg, 0.2, 3.8)))
    poisson = _three_way(_score_matrix(lh, la))
    hr_gd = (hr10.get("gf") or 0) - (hr10.get("ga") or 0)
    ar_gd = (ar10.get("gf") or 0) - (ar10.get("ga") or 0)
    recent = _ppg_component(hr10["ppg"], ar10["ppg"], hr_gd, ar_gd)
    hv_ppg = hrv.get("ppg") if hrv.get("ppg") is not None else home.ppg_home
    av_ppg = arv.get("ppg") if arv.get("ppg") is not None else away.ppg_away
    hv_gd = (hrv.get("gf") or _at(home.gf, 1)) - (hrv.get("ga") or _at(home.ga, 1))
    av_gd = (arv.get("gf") or _at(away.gf, 2)) - (arv.get("ga") or _at(away.ga, 2))
    venue_recent = _ppg_component(hv_ppg, av_ppg, hv_gd, av_gd)
    h2h3 = _h2h_component(home, h2h)
    one_x_two = _calibrate3(_norm3(tuple(
        0.25 * venue[i]
        + 0.25 * xg_component[i]
        + 0.20 * poisson[i]
        + 0.12 * recent[i]
        + 0.13 * venue_recent[i]
        + 0.05 * h2h3[i]
        for i in range(3)
    )))

    xg_btts = _score_probability(hxg) * _score_probability(axg)
    home_btts_prior = _at(home.btts, 0) if _at(home.btts, 0) is not None else 55.0
    away_btts_prior = _at(away.btts, 0) if _at(away.btts, 0) is not None else 55.0
    home_btts_shr = _shrink_rate(_at(home.btts, 1), hrv["n"], home_btts_prior, 8)
    away_btts_shr = _shrink_rate(_at(away.btts, 2), arv["n"], away_btts_prior, 8)
    venue_btts = (home_btts_shr + away_btts_shr) / 200.0
    h_fts = _shrink_rate(_at(home.failed_to_score, 1), hrv["n"], _at(home.failed_to_score, 0), 8)
    a_fts = _shrink_rate(_at(away.failed_to_score, 2), arv["n"], _at(away.failed_to_score, 0), 8)
    h_cs = _shrink_rate(_at(home.clean_sheets, 1), hrv["n"], _at(home.clean_sheets, 0), 8)
    a_cs = _shrink_rate(_at(away.clean_sheets, 2), arv["n"], _at(away.clean_sheets, 0), 8)
    h_score = ((100 - h_fts) + (100 - a_cs)) / 200.0
    a_score = ((100 - a_fts) + (100 - h_cs)) / 200.0
    reliability_btts = h_score * a_score
    recent_btts = _mean(hr10.get("btts"), ar10.get("btts"), default=55.0) / 100.0
    actual_btts = _score_probability(hact) * _score_probability(aact)
    h2h_btts = _h2h_binary(home, h2h, "btts")
    if h2h_btts is None:
        h2h_btts = recent_btts
    btts_raw = 0.35*xg_btts + 0.20*venue_btts + 0.15*reliability_btts + 0.15*recent_btts + 0.10*actual_btts + 0.05*h2h_btts
    btts = _clip(_binary_calibrate(btts_raw, 0.82), 0.06, 0.94)

    xg_over = 1 - sum(_poisson(t, hxg + axg) for t in range(3))
    poisson_over = 1 - sum(_poisson(t, lh + la) for t in range(3))
    home_o_prior = _at(home.over25, 0) if _at(home.over25, 0) is not None else 52.0
    away_o_prior = _at(away.over25, 0) if _at(away.over25, 0) is not None else 52.0
    home_o_shr = _shrink_rate(_at(home.over25, 1), hrv["n"], home_o_prior, 8)
    away_o_shr = _shrink_rate(_at(away.over25, 2), arv["n"], away_o_prior, 8)
    venue_over = (home_o_shr + away_o_shr) / 200.0
    recent_over = _mean(hr10.get("over25"), ar10.get("over25"), default=52.0) / 100.0
    actual_over = 1 - sum(_poisson(t, hact + aact) for t in range(3))
    h2h_over = _h2h_binary(home, h2h, "over")
    if h2h_over is None:
        h2h_over = recent_over
    over_raw = 0.35*xg_over + 0.25*poisson_over + 0.15*venue_over + 0.15*recent_over + 0.05*actual_over + 0.05*h2h_over
    over = _clip(_binary_calibrate(over_raw, 0.84), 0.06, 0.94)

    h_attack = _attack_index(home, 1, hr10)
    a_attack = _attack_index(away, 2, ar10)
    h_weak = _def_weakness_index(home, 1, hr10, hrv["n"])
    a_weak = _def_weakness_index(away, 2, ar10, arv["n"])

    matrix = _score_matrix(lh, la)
    scores = sorted(((f"{h}-{a}", p) for (h, a), p in matrix.items()), key=lambda x: x[1], reverse=True)[:6]
    quality = "Good"
    if warnings:
        quality = "Usable with warnings"
    if len(home.matches) >= 10 and len(away.matches) >= 10 and not warnings:
        quality = "Strong"

    evidence = [
        f"Expected goals (xG-led): {home.name} {lh:.2f} - {la:.2f} {away.name}.",
        f"Underlying xG matchup: {home.name} {hxg:.2f}; {away.name} {axg:.2f}.",
        f"Shrunk actual scoring matchup: {home.name} {hact:.2f}; {away.name} {aact:.2f}.",
        f"Relevant venue PPG: {home.name} {home.ppg_home:.2f}; {away.name} {away.ppg_away:.2f}.",
        f"Last 10 PPG: {home.name} {hr10['ppg']:.2f}; {away.name} {ar10['ppg']:.2f}.",
        f"Shrunk venue BTTS: {home_btts_shr:.0f}% / {away_btts_shr:.0f}%; combined {venue_btts*100:.0f}%.",
        f"Shrunk venue Over 2.5: {home_o_shr:.0f}% / {away_o_shr:.0f}%; combined {venue_over*100:.0f}%.",
        "Extreme home/away percentages are regressed toward broader team rates before use.",
    ]
    if h2h:
        m = h2h[0]
        evidence.append(f"H2H is included at low weight: {m.home} {m.home_goals}-{m.away_goals} {m.away}.")
    if warnings:
        evidence.append("Data warnings: " + "; ".join(warnings))

    ordered = sorted(one_x_two, reverse=True)
    gap = ordered[0] - ordered[1]
    confidence = "High" if quality == "Strong" and gap >= 0.13 else ("Medium" if gap >= 0.07 else "Cautious")
    diagnostics = {
        "Venue 1": venue[0], "Venue X": venue[1], "Venue 2": venue[2],
        "xG 1": xg_component[0], "xG X": xg_component[1], "xG 2": xg_component[2],
        "Poisson 1": poisson[0], "Poisson X": poisson[1], "Poisson 2": poisson[2],
        "Last10 1": recent[0], "Last10 X": recent[1], "Last10 2": recent[2],
        "VenueRecent 1": venue_recent[0], "VenueRecent X": venue_recent[1], "VenueRecent 2": venue_recent[2],
        "xG BTTS": xg_btts, "Venue BTTS": venue_btts, "Reliability BTTS": reliability_btts,
        "Recent BTTS": recent_btts, "Actual BTTS": actual_btts, "H2H BTTS": h2h_btts,
        "xG O2.5": xg_over, "Poisson O2.5": poisson_over, "Venue O2.5": venue_over,
        "Recent O2.5": recent_over, "Actual O2.5": actual_over, "H2H O2.5": h2h_over,
    }

    return SoccerPrediction(
        home=home.name, away=away.name,
        home_xg=lh, away_xg=la,
        home_win=one_x_two[0], draw=one_x_two[1], away_win=one_x_two[2],
        btts_yes=btts, btts_no=1-btts,
        over25=over, under25=1-over,
        home_attack_index=h_attack, home_def_weakness=h_weak,
        away_attack_index=a_attack, away_def_weakness=a_weak,
        confidence=confidence, likely_scores=scores, evidence=evidence,
        diagnostics=diagnostics, h2h=h2h, data_quality=quality,
    )
