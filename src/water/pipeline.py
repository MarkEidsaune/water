"""Build the dashboard data files: site list + recent history per gage.

Usage:
    uv run python -m water.pipeline [--days 365]

Writes:
    dashboard/data/sites.json            all active Ohio stream gages
    dashboard/data/series/<site>.json    daily series for each gage
    data/raw/*.parquet                   cached raw pulls
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

from water import usgs

DASHBOARD_DATA = Path(__file__).resolve().parents[2] / "dashboard" / "data"


def build(days: int = 365) -> None:
    start = (date.today() - timedelta(days=days)).isoformat()

    print("Fetching Ohio site list…")
    sites = usgs.get_ohio_sites()
    print(f"  {len(sites)} active stream gages")

    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)
    (DASHBOARD_DATA / "series").mkdir(exist_ok=True)

    site_records = []
    site_ids = sites["site_no"].tolist()

    print(f"Fetching daily values since {start}…")
    dv = usgs.get_daily_values(site_ids, start=start)
    usgs.cache_daily_values(dv, f"ohio_dv_{start}_{date.today().isoformat()}")

    for _, row in sites.iterrows():
        sid = row["site_no"]
        d = dv[dv["site_no"] == sid]
        if d.empty:
            continue
        series = {"date": d["date"].dt.strftime("%Y-%m-%d").tolist()}
        params = []
        for col in usgs.PARAMS.values():
            if col in d.columns and d[col].notna().any():
                series[col] = [
                    None if v != v else round(float(v), 2) for v in d[col]
                ]
                params.append(col)
        if not params:
            continue
        (DASHBOARD_DATA / "series" / f"{sid}.json").write_text(
            json.dumps(series)
        )
        site_records.append(
            {
                "id": sid,
                "name": row["station_nm"].title(),
                "lat": float(row["dec_lat_va"]),
                "lon": float(row["dec_long_va"]),
                "params": params,
            }
        )

    (DASHBOARD_DATA / "sites.json").write_text(json.dumps(site_records))
    print(f"Wrote {len(site_records)} sites with data → {DASHBOARD_DATA}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365)
    build(ap.parse_args().days)
