from pathlib import Path
from race_parser import parse_race
from class_model import analyse_race

ROOT = Path(__file__).resolve().parents[1]


def test_vittel_r4():
    text = (ROOT / 'sample_data' / 'Vittel_R4.md').read_text(encoding='utf-8')
    race = parse_race(text)
    assert race.current_class == 4
    assert race.discipline == 'FLAT'
    assert len(race.runners) >= 8
    names = [r.horse for r in race.runners]
    assert 'FANTASTIC STAR' in names
    fs = next(r for r in race.runners if r.horse == 'FANTASTIC STAR')
    assert fs.odds == 3.6
    assert any(x.class_no == 3 for x in fs.past_races)
    res = analyse_race(race)
    # Core worked-example requirement: Fantastic Star should be the strongest class horse.
    assert res[0].horse == 'FANTASTIC STAR'


def test_cl2_file():
    text = (ROOT / 'sample_data' / 'Race8_CL2.md').read_text(encoding='utf-8')
    race = parse_race(text)
    assert race.current_class == 2
    assert race.discipline == 'FLAT'
    assert len(race.runners) >= 14
    res = analyse_race(race)
    top_names = [x.horse for x in res[:6]]
    # Worked analysis identified these as the leading class group.
    assert 'DOUBLE UP' in top_names
    assert 'ZELORO' in top_names
    assert 'SEONA' in top_names
