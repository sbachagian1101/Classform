# Event harvest log

## Round 1, 9 Sep 2026: press and forum snippets

**Method.** Direct page fetches (Tripadvisor, Defimedia, L'Express, Le
Mauricien, Linfo.re, Newsmoris, Inside News, expat.com) were all blocked by
the sandbox egress proxy, so every row was compiled from search-engine
snippets of those pages, one targeted query per article. Because the
Mauritian press usually prints a weekday and day-of-month without a year,
years were resolved by weekday arithmetic (`jellymru.harvest.candidate_years`)
and cross-checked against article id sequences and neighbouring alerts. The
same logic is packaged in `jellymru/harvest.py` for the next rounds.

**Confidence semantics.**
- `high`: year explicit in the snippet or article URL, or a second source agrees.
- `medium`: year inferred from weekday plus article id ordering or an adjacent alert.
- `low`: weekday inference with two plausible years, source URL not captured, or a
  non-official report. Filter with `--min-confidence medium` for scoring.

**What was found.** 91 rows: 66 with day precision (59 at medium confidence or better), 15 week, 1 month, 9 undated leads. Dated rows span 2012 to 2026 across 23 beaches.
Undated leads are kept at the bottom of the table with empty dates so the
loader drops them but the URLs stay on record.

**Clusters worth noting for the models.**
- Aug 2013: four west and north beaches on alert the same morning as a 4 m
  swell warning. A stranding-type signal.
- Jan 2016: 32 people hospitalised in one night, north-west beaches
  (Baie du Tombeau, Le Goulet, Bain Boeuf); swimming banned. Bad weather
  and flooding at Belle Mare a month later.
- Jan 2019: box jellyfish confirmed at ten or more beaches within a week,
  starting east (Roches Noires, Poste Lafayette) on 1 Jan; press cites high
  heat and heavy rain. The clearest cubozoan episode in the record.
- Nov 2019: coin-sized dark-blue surface drifters in the north, at least 18
  sting cases over two days, attributed by the NCG officer and a skipper to
  wind from the north; chondrophores on beaches the next day. The clearest
  Physalia-type (wind-driven) episode.
- Aug to Nov 2022: Belle Mare repeatedly (14 Aug, 23 Aug, 23 Oct), then
  La Preneuse (26 Sep) and the north (6 Nov).
- Dec 2024 to Jan 2025: north (25 Dec stings, 26 Dec, 3 to 4 Jan), then west
  (Flic en Flac 7 Jan), east and south-east (Belle Mare, Blue Bay), Belle Mare
  again 14 Jan.
- Nothing found for 2017, 2021 (beyond two items) or 2023. Treat those as
  gaps in indexing, not as absence.

**Seasonality in the record (day-precision rows).** Events cluster in
austral summer (Dec to Mar) and again Aug to Nov. Winter trade-wind months
(May to Jul) are sparse.

**Beaches added to `config/beaches.yaml`** because reports name them:
La Cuvette, Bain Boeuf, Grand Gaube, Pointe aux Piments, Baie du Tombeau,
Le Goulet, Roches Noires, Bras d'Eau, Ile aux Cerfs, Albion, La Preneuse,
Riviere Noire, La Prairie, Ile aux Benitiers, La Cambuse. Coordinates and
bearings are approximate.

## Next rounds

1. Open each `source_url` from a machine with normal network access and
   confirm the date on the page (the `article:published_time` meta tag is
   enough). Upgrade `low` and `medium` rows to `high` as they are confirmed,
   and resolve the undated leads at the bottom of the table.
2. Run `python scripts/harvest_press.py` monthly for new alerts.
3. Search Facebook pages of Defimedia, L'Express and the Mauritius Police
   Force for communiqués that never became articles.
4. Ask the NCG Operations Room and the Beach Authority for their alert log;
   that will multiply this table.
5. Réunion press (Linfo.re, Clicanoo, Zinfos974) for a parallel Physalia set.

## Queries used

Site-scoped searches on defimedia.info, lexpress.mu, lemauricien.com,
zinfos-moris.com, ionnews.mu, inside.news, newsmoris.com, linfo.re and
tripadvisor.com with the terms: méduses, méduses-boîtes, physalies, lagon,
National Coast Guard, garde-côtes, plage, piqûres, and each beach name.
