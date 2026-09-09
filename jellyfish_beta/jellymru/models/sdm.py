"""Species distribution model (SDM) skeleton.

Purpose: a habitat-suitability prior for scyphozoan and cubozoan species built
from global presence records (GBIF, OBIS / JeDI, iNaturalist) and gridded
environmental climatologies, projected onto the waters around Mauritius. It
needs no local labels, which is exactly why it belongs in the beta.

What is implemented
-------------------
* ``fetch_gbif_occurrences`` : paged pull from the public GBIF API (no key).
* ``sample_background``      : random background points inside a bounding box.
* ``train_sdm`` / ``predict_suitability`` : presence-vs-background classifier.

What you supply
---------------
A function that returns environmental covariates for a set of lat/lon points
(e.g. sampling Bio-ORACLE or CMEMS rasters with xarray). See
``extract_env_at_points`` for the expected signature.
"""
from __future__ import annotations

import time
from typing import Callable, Iterable

import numpy as np
import pandas as pd

GBIF_URL = "https://api.gbif.org/v1/occurrence/search"

# Species of interest for Mauritius, by hazard group. Extend as the local
# inventory is built.
SPECIES_OF_INTEREST = {
    "physalia": ["Physalia physalis", "Physalia utriculus"],
    "cubozoa": ["Carybdea", "Alatina alata", "Chironex", "Carukia barnesi"],
    "scyphozoa": ["Aurelia aurita", "Pelagia noctiluca", "Chrysaora", "Cassiopea andromeda",
                  "Rhizostoma", "Crambionella orsini"],
}


def fetch_gbif_occurrences(
    scientific_name: str,
    bbox: tuple[float, float, float, float] | None = None,
    max_records: int = 5000,
    page_size: int = 300,
    pause_s: float = 0.2,
    session=None,
) -> pd.DataFrame:
    """Pull georeferenced occurrences for a taxon from GBIF.

    bbox = (min_lon, min_lat, max_lon, max_lat). Returns lat, lon, date,
    species, basis_of_record, gbif_id.
    """
    import requests

    sess = session or requests.Session()
    rows: list[dict] = []
    offset = 0
    while offset < max_records:
        params = {
            "scientificName": scientific_name,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
            "limit": min(page_size, max_records - offset),
            "offset": offset,
        }
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            params["decimalLongitude"] = f"{min_lon},{max_lon}"
            params["decimalLatitude"] = f"{min_lat},{max_lat}"
        resp = sess.get(GBIF_URL, params=params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        for r in payload.get("results", []):
            rows.append({
                "gbif_id": r.get("key"),
                "species": r.get("species") or r.get("scientificName"),
                "lat": r.get("decimalLatitude"),
                "lon": r.get("decimalLongitude"),
                "date": r.get("eventDate"),
                "basis_of_record": r.get("basisOfRecord"),
            })
        if payload.get("endOfRecords", True):
            break
        offset += page_size
        time.sleep(pause_s)
    df = pd.DataFrame(rows, columns=["gbif_id", "species", "lat", "lon", "date", "basis_of_record"])
    return df.dropna(subset=["lat", "lon"]).reset_index(drop=True)


def sample_background(bbox: tuple[float, float, float, float], n: int, seed: int = 0) -> pd.DataFrame:
    """Uniform random background points in a bounding box (ocean mask is up to you)."""
    rng = np.random.default_rng(seed)
    min_lon, min_lat, max_lon, max_lat = bbox
    return pd.DataFrame({
        "lon": rng.uniform(min_lon, max_lon, n),
        "lat": rng.uniform(min_lat, max_lat, n),
    })


EnvExtractor = Callable[[pd.DataFrame], pd.DataFrame]


def extract_env_at_points(points: pd.DataFrame) -> pd.DataFrame:
    """Placeholder for the covariate sampler.

    Replace with a function that takes a DataFrame with ``lat`` and ``lon``
    and returns the same rows with numeric covariate columns (e.g. sst_mean,
    sst_range, chl_mean, salinity, depth, dist_coast_km).
    """
    raise NotImplementedError(
        "Provide an environmental extractor, e.g. sample Bio-ORACLE or CMEMS rasters with xarray."
    )


def train_sdm(presence: pd.DataFrame, background: pd.DataFrame, feature_cols: Iterable[str]):
    """Presence-vs-background classifier (a MaxEnt-style logistic baseline)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    cols = list(feature_cols)
    X = pd.concat([presence[cols], background[cols]], ignore_index=True).to_numpy(dtype=float)
    y = np.concatenate([np.ones(len(presence)), np.zeros(len(background))])
    model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000))
    model.fit(X, y)
    model.feature_cols_ = cols
    return model


def predict_suitability(model, env: pd.DataFrame) -> pd.Series:
    X = env[model.feature_cols_].to_numpy(dtype=float)
    return pd.Series(model.predict_proba(X)[:, 1], index=env.index, name="suitability")
