from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_ROOT / "config"
DATA_DIR = PACKAGE_ROOT / "data"


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_beaches(path: Path | None = None) -> pd.DataFrame:
    """Return the beach table with one row per beach.

    Columns: id, name, lat, lon, facing_deg, lagoon, region.
    """
    cfg = load_yaml(path or CONFIG_DIR / "beaches.yaml")
    df = pd.DataFrame(cfg["beaches"])
    required = {"id", "name", "lat", "lon", "facing_deg", "lagoon"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"beaches.yaml missing columns: {sorted(missing)}")
    if df["id"].duplicated().any():
        raise ValueError("beaches.yaml has duplicate ids")
    df["facing_deg"] = df["facing_deg"].astype(float) % 360.0
    df["lagoon"] = df["lagoon"].astype(bool)
    return df.set_index("id", drop=False)


def load_params(path: Path | None = None) -> dict[str, Any]:
    return load_yaml(path or CONFIG_DIR / "model_params.yaml")
