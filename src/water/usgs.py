"""Fetch USGS NWIS water data for Ohio stream gages.

Thin wrappers around the official `dataretrieval` client, returning tidy
pandas DataFrames and caching raw pulls under data/raw/.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from dataretrieval import nwis

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Parameters of interest for fisheries work
PARAMS = {
    "00060": "discharge_cfs",       # streamflow, ft³/s
    "00065": "gage_height_ft",      # gage height, ft
    "00010": "temperature_c",       # water temperature, °C
}


def get_ohio_sites(parameter_codes: list[str] | None = None) -> pd.DataFrame:
    """Active Ohio stream-gage sites with daily values for our parameters.

    Returns a DataFrame with site_no, station_nm, dec_lat_va, dec_long_va,
    and the parameters each site reports.
    """
    codes = parameter_codes or list(PARAMS)
    sites, _ = nwis.what_sites(
        stateCd="OH",
        siteType="ST",              # streams only
        parameterCd=",".join(codes),
        hasDataTypeCd="dv",         # has daily values
        siteStatus="active",
    )
    cols = ["site_no", "station_nm", "dec_lat_va", "dec_long_va"]
    keep = sites[cols].drop_duplicates("site_no").reset_index(drop=True)
    return keep


def get_daily_values(
    site_no: str | list[str],
    start: str,
    end: str | None = None,
    parameter_codes: list[str] | None = None,
) -> pd.DataFrame:
    """Daily mean values for one or more sites, tidy format.

    Columns: site_no, date, <parameter columns from PARAMS>.
    """
    codes = parameter_codes or list(PARAMS)
    df, _ = nwis.get_dv(
        sites=site_no,
        parameterCd=codes,
        start=start,
        end=end,
    )
    if df.empty:
        return pd.DataFrame()

    df = df.reset_index()
    # dataretrieval names columns like "00060_Mean"; map to friendly names
    rename = {}
    for code, name in PARAMS.items():
        col = f"{code}_Mean"
        if col in df.columns:
            rename[col] = name
    df = df.rename(columns={"datetime": "date", **rename})
    keep = ["site_no", "date"] + [c for c in PARAMS.values() if c in df.columns]
    if "site_no" not in df.columns:  # single-site responses omit it
        df["site_no"] = site_no if isinstance(site_no, str) else site_no[0]
    df = df[keep]
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    return df


def cache_daily_values(df: pd.DataFrame, name: str) -> Path:
    """Write a raw pull to data/raw/<name>.parquet and return the path."""
    out = DATA_DIR / "raw" / f"{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out
