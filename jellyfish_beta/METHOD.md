# Method, beta v0.1

## Principle

Predict hazard from mechanisms that are known to transfer between regions,
with as few free parameters as the local event record can support. Fit only
what tens of events can constrain. Add machine learning later, once the
event table has hundreds of rows.

## Spatial and temporal unit

One row per beach per UTC day. Beaches are listed in `config/beaches.yaml`
with a shore-normal bearing `facing_deg` (direction from the beach out to
sea). Gridded forcing (winds, waves, currents, SST) is sampled at the nearest
cell, which for a lagoon beach is offshore of the reef. That is intentional:
the model treats it as the forcing that pushes material toward the reef, and
the last kilometre is handled by beach orientation and the lagoon flag.

## Onshore projection

For wind and waves (direction they come FROM):

    onshore = magnitude * cos(direction_from - facing_deg)

For currents (direction they flow TO), the direction is rotated by 180 first.
Positive means from the sea onto the beach. The wind-stress proxy is
`sign(onshore_wind) * onshore_wind^2`, averaged over 24, 48 and 72 hours.

## Physalia stranding index

    logit = bias + w24 * stress_24h + w72 * stress_72h + ws * max(onshore_swell_24h, 0)
    risk  = sigmoid(logit)

Priors: bias -3.0, w24 0.05, w72 0.03, ws 0.8. With these, a day of 6 m/s
onshore wind gives roughly 0.5 and a day of 10 m/s onshore wind gives above
0.95, while offshore trades give below 0.05. The mechanism is the one found
for Sydney beaches (BluebottleWatch) and Reunion's west coast. Weights are
the tuning targets.

## Cubozoan calm-window index

    calm_days = consecutive days with daily mean wind below calm_wind_ms (5 m/s), capped at 5
    logit     = bias + w_calm * calm_days + w_sst * (sst - 26) + w_rain * rain_3d_mm
    risk      = sigmoid(logit) * (1 if lagoon else 0.3)

Priors: bias -2.5, w_calm 0.8, w_sst 0.5, w_rain 0.02. Three calm days at
28 C give roughly 0.7; a windy 24 C day gives about 0.03. The trade-wind
relaxation mechanism comes from the Queensland Irukandji work. The
temperature threshold and the rain term are hypotheses for Mauritius.

## Species distribution prior

Presence-vs-background logistic classifier on global occurrence records
(GBIF, OBIS / JeDI) with environmental covariates, projected onto the waters
around Mauritius. Produces a monthly suitability surface per species group.
Not yet wired into the combined score: it needs an environmental extractor
(Bio-ORACLE or CMEMS climatologies) supplied by the user.

## Combination and tiers

    risk_score = max(w_physalia * physalia_risk, w_cubozoa * cubozoa_risk)

The max is deliberate: these are different hazards and an alert should fire
if either is likely. Tiers: moderate at 0.35, high at 0.60. Both thresholds
should be reset from the validated alert budget once real events exist.

## Known limitations

* ERA5 and Open-Meteo resolve wind at about 25 km; the island is 45 by 65 km.
  Beach-to-beach contrast comes almost entirely from orientation.
* Lagoon temperature is not observed by satellite SST. Add loggers.
* Reports are biased toward busy beaches in daylight. Validation treats
  unreported days as pseudo-absences and says so.
* Synthetic data is for plumbing only.
