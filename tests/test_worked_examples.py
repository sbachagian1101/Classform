from pathlib import Path
from race_parser import parse_race
from class_model import analyse_race

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
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
}


def test_all_worked_examples_reproduce_scores():
    for filename, expected in EXPECTED.items():
        race = parse_race((ROOT / 'sample_data' / filename).read_text(encoding='utf-8'))
        got = {a.horse: a.score for a in analyse_race(race)}
        for horse, score in expected.items():
            assert got[horse] == score
