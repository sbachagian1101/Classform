import json
from pathlib import Path

from race_parser import parse_race
from class_model import analyse_race, _current_reference_level

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'sample_data'


def test_unlabelled_flat_claiming_uses_prize_proxy():
    race = parse_race((DATA / 'Deauville_R1.md').read_text(encoding='utf-8'))
    assert race.race_no == 1
    assert race.current_class is None
    assert race.race_type == 'CLM'
    assert _current_reference_level(race) is not None
    scores = [a.score for a in analyse_race(race)]
    assert len(set(scores)) > 1  # no all-5.0 failure


def test_scratched_runners_are_excluded():
    r2 = parse_race((DATA / 'Deauville_R2.md').read_text(encoding='utf-8'))
    assert 10 not in [r.number for r in r2.runners]  # FALABELLA scratched
    r7 = parse_race((DATA / 'Deauville_R7.md').read_text(encoding='utf-8'))
    nums = [r.number for r in r7.runners]
    assert 4 not in nums and 10 not in nums


def test_deauville_result_feedback_is_active_and_class_only():
    results = json.loads((DATA / 'training_results.json').read_text(encoding='utf-8'))
    overlap = 0
    for fn, actual_top4 in results.items():
        race = parse_race((DATA / fn).read_text(encoding='utf-8'))
        pred_top4 = [a.number for a in analyse_race(race)[:4]]
        overlap += len(set(actual_top4) & set(pred_top4))
    # Updated general class weighting improves the audit set over the previous app
    # while deliberately not attempting to reproduce non-class outcome factors.
    assert overlap >= 16


def test_odds_are_display_only():
    race = parse_race((DATA / 'Deauville_R3.md').read_text(encoding='utf-8'))
    base = {a.number: a.score for a in analyse_race(race)}
    for r in race.runners:
        r.odds = 9999.0 if r.number % 2 else 1.01
    changed = {a.number: a.score for a in analyse_race(race)}
    assert changed == base
