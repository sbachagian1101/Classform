"""Copernicus Marine (CMEMS) subsets for currents, waves, SST, salinity.

Primary-source replacement for the Open-Meteo marine product. Requires
``pip install copernicusmarine`` and a free Copernicus Marine account
(``copernicusmarine login`` once).

Dataset ids (global, 1/12 deg) worth starting from:
    physics analysis/forecast : cmems_mod_glo_phy_anfc_0.083deg_PT1H-m  (hourly surface)
    physics reanalysis        : cmems_mod_glo_phy_my_0.083deg_P1D-m
    waves analysis/forecast   : cmems_mod_glo_wav_anfc_0.083deg_PT3H-i
    waves reanalysis          : cmems_mod_glo_wav_my_0.2deg_PT3H-i
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

MAURITIUS_BBOX = {"minimum_longitude": 56.9, "maximum_longitude": 58.2,
                  "minimum_latitude": -20.9, "maximum_latitude": -19.5}


def subset(dataset_id: str, variables: list[str], start: date, end: date, out_path: Path) -> Path:
    try:
        import copernicusmarine
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pip install copernicusmarine to use CMEMS subsets") from exc

    copernicusmarine.subset(
        dataset_id=dataset_id,
        variables=variables,
        start_datetime=start.isoformat(),
        end_datetime=end.isoformat(),
        output_filename=str(out_path),
        **MAURITIUS_BBOX,
    )
    return out_path


def cmems_physics_to_hourly_rows(nc_path: Path, beaches) -> "pd.DataFrame":
    """Nearest-cell surface currents and SST per beach as tidy hourly rows.

    Note: the nearest ocean cell to a lagoon beach is outside the reef. The
    features layer treats these as the offshore forcing, which is the intent.
    """
    import numpy as np
    import pandas as pd
    import xarray as xr

    ds = xr.open_dataset(nc_path)
    if "depth" in ds.dims:
        ds = ds.isel(depth=0)
    frames = []
    for _, b in beaches.iterrows():
        pt = ds.sel(latitude=b["lat"], longitude=b["lon"], method="nearest")
        uo = pt["uo"].to_series()
        vo = pt["vo"].to_series()
        speed = np.sqrt(uo**2 + vo**2)
        direction_to = (np.degrees(np.arctan2(uo, vo)) + 360.0) % 360.0
        df = pd.DataFrame({
            "beach_id": b["id"],
            "time": pd.to_datetime(uo.index, utc=True),
            "current_speed_ms": speed.to_numpy(),
            "current_dir_to_deg": direction_to.to_numpy(),
        })
        if "thetao" in pt:
            df["sst_c"] = pt["thetao"].to_series().to_numpy()
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
