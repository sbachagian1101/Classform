from datetime import date

from jellymru.harvest import (candidate_from_item, candidate_years, find_beaches, parse_dates,
                              parse_rss, resolve_year, species_hint, stings_hint)


def test_find_beaches_handles_accents_hyphens_and_variants():
    text = ("La NCG signale des méduses à Mont-Choisy, Trou-aux-Biches, Péreybère, "
            "Bain-Bœuf, Belle-Mare et Trou-d'Eau-Douce (plage Le Maho).")
    assert find_beaches(text) == ["mont_choisy", "trou_aux_biches", "pereybere", "bain_boeuf", "belle_mare", "trou_deau_douce"]
    assert find_beaches("jellyfish at Mon Choisy and Blue Bay") == ["mont_choisy", "blue_bay"]


def test_find_beaches_respects_word_boundaries():
    # "Tamarind" must not match Tamarin; "Albionne" must not match Albion.
    assert find_beaches("tamarind trees near Albionne") == []


def test_parse_dates_french_and_english():
    d = parse_dates("La présence de méduses a été signalée ce jeudi 26 décembre dans le lagon.")
    assert d == [{"weekday": 3, "day": 26, "month": 12, "year": None}]
    d = parse_dates("reported on Saturday, January 29, 2022 near Shivala")
    # English month-first order is not parsed; day-first English is.
    d2 = parse_dates("on Tuesday 1st January the NCG confirmed")
    assert d2 == [{"weekday": 1, "day": 1, "month": 1, "year": None}]
    d3 = parse_dates("le 9 février 2016, la police")
    assert d3 == [{"weekday": None, "day": 9, "month": 2, "year": 2016}]


def test_candidate_years_matches_hand_check():
    assert candidate_years(3, 26, 12, 2013, 2025) == [2013, 2019, 2024]
    assert candidate_years(1, 1, 1, 2013, 2025) == [2013, 2019]


def test_resolve_year_anchors_on_publication_date():
    # Thursday 26 December, article published 27 Dec 2024 -> 2024
    assert resolve_year(3, 26, 12, date(2024, 12, 27)) == 2024
    # Published early January: event in previous year's December
    assert resolve_year(3, 26, 12, date(2025, 1, 3)) == 2024
    # Weekday mismatch -> None
    assert resolve_year(0, 26, 12, date(2024, 12, 27)) is None
    # Future date relative to publication is rejected
    assert resolve_year(None, 26, 12, date(2024, 12, 20)) == 2023


def test_species_and_sting_hints():
    assert species_hint("présence de méduses-boîtes confirmée") == "cubozoa"
    assert species_hint("des physalies échouées") == "physalia"
    assert species_hint("des méduses dans le lagon") == "unknown"
    assert stings_hint("32 personnes piquées ont été admises") == 32
    assert stings_hint("prudence dans le lagon") is None


def test_parse_rss_and_candidate_row():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>Trou-aux-Biches et Mon Choisy : présence de méduse signalée - Le Mauricien</title>
    <link>https://example.org/a</link><pubDate>Fri, 27 Dec 2024 08:00:00 GMT</pubDate>
    <source url="https://example.org">Le Mauricien</source>
    <description>&lt;p&gt;La NCG signale ce jeudi 26 décembre la présence de méduses. Plusieurs personnes piquées.&lt;/p&gt;</description>
    </item></channel></rss>"""
    items = parse_rss(xml)
    assert len(items) == 1 and items[0]["source"] == "Le Mauricien"
    cand = candidate_from_item(items[0])
    assert cand["beaches"] == "trou_aux_biches;mont_choisy"
    assert cand["dates_found"] == "2024-12-26"
    assert cand["relevant"] is True
