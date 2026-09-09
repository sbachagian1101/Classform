"""ERA5 hourly winds via the Copernicus Climate Data Store (CDS).

Primary-source replacement for the Open-Meteo weather history. Requires
``pip install cdsapi xarray netcdf4`` and a ~/.cdsapirc with your CDS key.
For bulk history the ARCO-ERA5 Zarr mirror on Google Cloud is faster:
    gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

# Bounding box covering Mauritius with a margin: N, W, S, E
MAURITIUS_AREA = [-19.5, 56.9, -20.9, 58.2]


def download_era5_winds(start: date, end: date, out_path: Path, area=MAURITIUS_AREA) -> Path:
    try:
        import cdsapi
    except ImportError as exc:  # pragma: no cover
        raise ImportError("pip install cdsapi to use ERA5 downloads") from exc

    years = sorted({str(y) for y in range(start.year, end.year + 1)})
    months = [f"{m:02d}" for m in range(1, 13)]
    days = [f"{d:02d}" for d in range(1, 32)]
    request = {
        "product_type": ["reanalysis"],
        "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind", "total_precipitation"],
        "year": years, "month": months, "day": days,
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": area,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    client = cdsapi.Client()
    client.retrieve("reanalysis-era5-single-levels", request, str(out_path))
    return out_path


def era5_to_hourly_rows(nc_path: Path, beaches) -> "pd.DataFrame":
    """Sample the nearest ERA5 cell for each beach and emit tidy hourly rows."""
    import numpy as np
    import pandas as pd
    import xarray as xr

    ds = xr.open_dataset(nc_path)
    frames = []
    for _, b in beaches.iterrows():
        pt = ds.sel(latitude=b["lat"], longitude=b["lon"], method="nearest")
        u = pt["u10"].to_series()
        v = pt["v10"].to_series()
        speed = np.sqrt(u**2 + v**2)
        direction_from = (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0
        df = pd.DataFrame({
            "beach_id": b["id"],
            "time": pd.to_datetime(u.index, utc=True),
            "wind_speed_ms": speed.to_numpy(),
            "wind_dir_from_deg": direction_from.to_numpy(),
        })
        if "tp" in pt:
            df["precip_mm"] = pt["tp"].to_series().to_numpy() * 1000.0
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
