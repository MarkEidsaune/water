"""Build the dashboard data files: site list + recent history per gage.

Usage:
    uv run python -m water.pipeline [--days 365]

Writes:
    dashboard/data/sites.json            all active Ohio stream gages
    dashboard/data/series/<site>.json    daily series for each gage
    data/raw/*.parquet                   cached raw pulls

Set USGS_API_KEY (optional) for higher API rate limits.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from water import api

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DATA = ROOT / "dashboard" / "data"
RAW_DIR = ROOT / "data" / "raw"


def cache_raw(daily: dict, name: str) -> None:
    """Flatten the nested daily dict to a tidy parquet for later modeling."""
    rows = [
        {"site_no": site, "date": day, **values}
        for site, days in daily.items()
        for day, values in days.items()
    ]
    df = pd.DataFrame(rows)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(RAW_DIR / f"{name}.parquet", index=False)


def build(days: int = 365) -> None:
    start = (date.today() - timedelta(days=days)).isoformat()

    print("Fetching Ohio site list…")
    sites = api.get_ohio_sites()
    print(f"  {len(sites)} active stream gages")

    print(f"Fetching daily values since {start}…")
    daily = api.get_ohio_daily(start)
    cache_raw(daily, f"ohio_dv_{start}_{date.today().isoformat()}")

    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)
    (DASHBOARD_DATA / "series").mkdir(exist_ok=True)

    site_records = []
    for site in sites:
        days_map = daily.get(site["site_no"])
        if not days_map:
            continue
        dates = sorted(days_map)
        params = sorted({p for v in days_map.values() for p in v})
        series = {"date": dates}
        for p in params:
            series[p] = [days_map[d].get(p) for d in dates]
        (DASHBOARD_DATA / "series" / f"{site['site_no']}.json").write_text(
            json.dumps(series)
        )
        site_records.append(
            {
                "id": site["site_no"],
                "name": site["name"],
                "lat": round(site["lat"], 5),
                "lon": round(site["lon"], 5),
                "params": params,
            }
        )

    (DASHBOARD_DATA / "sites.json").write_text(json.dumps(site_records))
    print(f"Wrote {len(site_records)} sites with data → {DASHBOARD_DATA}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    build(ap.parse_args().days)
