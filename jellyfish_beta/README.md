# Mauritius Jellyfish Risk, beta

A beta predictive system for jellyfish hazard on Mauritian beaches. It is
built the way the Sydney bluebottle, Queensland Irukandji and Mediterranean
projects started: **mechanistic indices with a handful of tunable parameters,
validated against whatever local event record exists**, rather than a
black-box model that would need thousands of labels Mauritius does not have.

Three components, each independently testable:

| Component | Hazard | Mechanism | Needs local labels? |
|---|---|---|---|
| `jellymru/models/physalia.py` | Physalia (bluebottle) strandings | Onshore wind stress over 1 to 3 days plus onshore swell, per beach orientation | Only to tune 3 to 4 weights |
| `jellymru/models/cubozoa.py` | Box jellyfish in lagoons | Consecutive calm days after trade-wind relaxation, warm SST, recent rain, lagoon flag | Only to tune thresholds |
| `jellymru/models/sdm.py` | Scyphozoan / cubozoan habitat suitability | Species distribution model on global GBIF, OBIS and JeDI presence records | No |

Outputs are a per-beach, per-day risk score in [0, 1] and a tier
(low / moderate / high), served by a Streamlit dashboard.

**Status:** scaffold. Parameters in `config/model_params.yaml` are priors from
other regions and have not been fitted to Mauritian events. The event table
`data/events/mru_events.csv` is empty and is the first thing to fill.

## Layout

```
jellyfish_beta/
├── app.py                    Streamlit dashboard (reads data/outputs/latest_risk.csv)
├── config/
│   ├── beaches.yaml          beaches, positions, shore-normal bearings, lagoon flags
│   └── model_params.yaml     model priors, tier thresholds, validation settings
├── data/
│   ├── events/mru_events.csv the label set (empty template) and its README
│   ├── raw/                  hourly pulls (gitignored)
│   ├── features/             daily per-beach feature table (gitignored)
│   └── outputs/              latest_risk.csv, validation.csv (gitignored)
├── jellymru/
│   ├── config.py             loaders
│   ├── geo.py                bearings, onshore components
│   ├── features.py           hourly -> daily features (rolling windows, calm-day runs)
│   ├── risk.py               combine hazards into score and tier
│   ├── validate.py           sparse-label validation, climatology baseline, LOYO tuning
│   ├── synthetic.py          offline synthetic climate and events for dry runs
│   ├── fetch/
│   │   ├── openmeteo.py      keyless history and forecast (beta source)
│   │   ├── era5.py           ERA5 winds via CDS (operational source)
│   │   └── cmems.py          Copernicus Marine currents, waves, SST (operational source)
│   └── models/
│       ├── physalia.py
│       ├── cubozoa.py
│       └── sdm.py
├── scripts/
│   ├── make_synthetic.py     generate a synthetic dataset
│   ├── build_features.py     build the daily feature table from a source
│   ├── run_forecast.py       score the coming days and write latest_risk.csv
│   └── validate.py           metrics vs climatology, optional tuning
├── tests/                    pytest, fully offline
├── METHOD.md                 what each index computes and why
└── SOURCES.md                data sources, access, and where to mine events
```

## Quick start (offline dry run, no accounts needed)

```bash
cd jellyfish_beta
pip install -r requirements.txt
python -m pytest tests -q

python scripts/make_synthetic.py                      # 2 years of synthetic hourly data + events
python scripts/build_features.py --source synthetic
python scripts/run_forecast.py --source synthetic
python scripts/validate.py --events data/events/synthetic_events.csv --tune
streamlit run app.py
```

The synthetic run proves the plumbing, not the science: events are drawn
from the same mechanisms the models encode, so the model beats climatology
by construction.

## Real data

```bash
# 1. History for validation (Open-Meteo, keyless; marine archive starts around 2022)
python scripts/build_features.py --source openmeteo --start 2022-01-01 --end 2025-12-31

# 2. Fill data/events/mru_events.csv (see data/events/README.md and SOURCES.md)

# 3. Validate and tune
python scripts/validate.py --events data/events/mru_events.csv --tune

# 4. Daily forecast
python scripts/run_forecast.py --days 7
```

For the operational system replace Open-Meteo with ERA5 (`jellymru/fetch/era5.py`)
and Copernicus Marine (`jellymru/fetch/cmems.py`); both need a free account
and the packages in `requirements-optional.txt`. The workflow in
`.github/workflows/daily_forecast.yml` runs the forecast every morning once
this folder is its own repository.

## How validation works with very few events

* Unit is the beach-day. Label 1 on an event day at that beach.
* Score is the max risk over the previous `lead_days` (default 2), so early
  warnings count.
* Beach-days within `negative_buffer_days` of an event are not used as
  negatives, because "no report" next to an event is not a reliable absence.
* Every model is compared against a leave-one-year-out (beach, month)
  climatology. Beating that is the bar.
* Metrics: ROC AUC, average precision, and hit rate at a fixed alert budget
  (default: 10 percent of beach-days on alert).
* Tuning uses leave-one-year-out grid search over a few weights, so nothing
  is scored on events it was fitted to.

## What to do first

1. Verify beach positions and `facing_deg` bearings in `config/beaches.yaml`.
2. Mine events into `data/events/mru_events.csv` (Coast Guard, Beach Authority,
   press, Tripadvisor, hospital records). Target 50 to 150 dated events.
3. Run the Open-Meteo history and the validator. Expect the Physalia index to
   show skill first; the cubozoan index is the open question.
4. Start a reporting form so lifeguards and the public add presence and
   absence records from day one.
