from pathlib import Path

from race_parser import parse_race
from class_model import analyse_race, _current_reference_level, _display_race_strength

ROOT = Path(__file__).resolve().parents[1]


def test_ballarat_bm62_header_and_prize():
    race = parse_race((ROOT / 'sample_data' / 'Ballarat_R7_BM62.md').read_text(encoding='utf-8'))
    assert race.country == 'AUSTRALIA'
    assert race.race_type == 'BM62'
    assert race.benchmark_rating == 62
    assert race.grade_label == 'BM62'
    assert race.prize_currency == 'AUD'
    assert race.prize_amount == 27000
    assert _current_reference_level(race) is not None
    assert len(race.runners) == 9  # runner 9 is scratched; runner 10 remains active


def test_australian_bm_races_are_scored_and_displayed():
    race = parse_race((ROOT / 'sample_data' / 'Ballarat_R7_BM62.md').read_text(encoding='utf-8'))
    results = analyse_race(race)
    scores = {a.horse: a.score for a in results}
    assert len(set(scores.values())) > 1
    assert scores['BRING ME POWER'] > scores['PRINCE MARIONETTE']
    assert scores['HELLUVA BARTY'] > 7.0
    assert 'BM62' in next(a for a in results if a.horse == 'HELLUVA BARTY').relevant_previous_class
    first_past = race.runners[0].past_races[0]
    assert _display_race_strength(first_past).startswith('BM62 AUD $')


def test_australian_cl1_is_not_french_cl1():
    race = parse_race((ROOT / 'sample_data' / 'Ballarat_R7_BM62.md').read_text(encoding='utf-8'))
    ourzac = next(r for r in race.runners if r.horse == 'OURZACRACKER')
    cl1 = next(pr for pr in ourzac.past_races if pr.race_desc.strip().upper() == 'CL1')
    from class_model import _effective_level
    # Australian CL1 is a lower restricted-win grade, not elite French CL1.
    assert _effective_level(cl1) > _current_reference_level(race)
