# Data sources

## Environmental forcing

| Variable | Source | Resolution | Access | Used by |
|---|---|---|---|---|
| Wind history | ERA5 (ECMWF) via Copernicus CDS; ARCO-ERA5 Zarr on Google Cloud for bulk | 0.25 deg, hourly, 1940 to present | Free account (CDS); none (ARCO) | `fetch/era5.py` |
| Wind and marine history, forecast | Open-Meteo archive, forecast and marine APIs | 0.25 deg weather; marine from global wave and ocean models | Keyless, rate limited | `fetch/openmeteo.py` (beta) |
| Wind forecast | ECMWF Open Data, NOAA GFS | 0.25 deg, 3 to 6 hourly | Open | operational |
| Station winds | NOAA Integrated Surface Database (Plaisance airport, Vacoas) | hourly | Open | bias correction |
| Surface currents, SST, salinity | Copernicus Marine global physics (analysis, forecast, reanalysis) | 1/12 deg, hourly to daily | Free account | `fetch/cmems.py` |
| Waves and swell | Copernicus Marine global waves; NOAA WaveWatch III | 1/12 deg, 3 hourly | Free account / open | `fetch/cmems.py` |
| SST | NOAA OISST; NASA MUR GHRSST | 0.25 deg / 1 km, daily | Open / free Earthdata login | operational |
| Chlorophyll-a | Copernicus Marine GlobColour; NASA Ocean Color | 4 km, daily and 8-day | Free account | SDM covariate |
| Rainfall | CHIRPS; NASA IMERG | 5 km / 10 km, daily | Open | cubozoa rain term |
| Tides and sea level | IOC Sea Level Station Monitoring (Port Louis); FES tidal model | minutes | Open | later |
| Bathymetry | GEBCO 2024 | 15 arc-second | Open | drift model, SDM |
| Reef and lagoon zones | Allen Coral Atlas | 5 m | Open | beach segmentation |
| Coastline | OpenStreetMap | vector | Open | beach bearings |
| Climate indices | Indian Ocean Dipole (DMI), Nino 3.4 from NOAA PSL | monthly | Open | interannual term |

## Occurrence records for the species distribution model

| Source | Notes |
|---|---|
| GBIF occurrence API | Keyless, paged; see `jellymru/models/sdm.py` |
| OBIS, including the Jellyfish Database Initiative (JeDI, about 476,000 records) | Open |
| iNaturalist research-grade | Open, via GBIF |
| Bio-ORACLE, World Ocean Atlas | Environmental climatologies for training covariates |

## Event sources for `data/events/mru_events.csv`

Ordered by value. Record the URL or archive reference for every row.

1. National Coast Guard sighting communiqués and Beach Authority warnings
   (request internal logs, not only press releases).
2. Ministry of Health, SAMU and private clinic sting records, by date and locality.
3. Lifeguard and hotel logs on the north, east and south-east coasts.
4. Press archives: Defimedia, L'Express, Le Mauricien, Le Matinal, ION News.
5. Tripadvisor Mauritius forum threads on jellyfish (dated first-hand reports).
6. Facebook groups for divers, kite-surfers and residents.
7. Mauritius Oceanography Institute and Albion Fisheries Research Centre
   (species inventory, any monitoring records, lagoon temperature loggers).
8. Reunion press (Linfo.re, Clicanoo, Zinfos974) for Physalia strandings,
   as a second validation set in the same climate.

## Reference projects

* BluebottleWatch, UNSW and Surf Life Saving Australia: wind-driven Physalia stranding forecast, Sydney.
* Bourg et al. 2022, "Driving the blue fleet": drivers of Physalia beachings off Sydney.
* Gershwin et al. 2014, "Dangerous jellyfish blooms are predictable": Irukandji and trade-wind relaxation.
* NOAA NCCOS Chesapeake Bay sea nettle forecast: temperature and salinity probability-of-encounter model.
* MED-JELLYRISK and the Mediterranean jellyfish citizen-science campaigns.
* Malta hydrodynamic modelling of bloom trajectories.
