"""Client for the USGS Water Data OGC API.

https://api.waterdata.usgs.gov/docs/ogcapi/

Plain `requests` against /ogcapi/v0. An API key is optional; set the
USGS_API_KEY environment variable to raise rate limits (the key is sent
via the X-Api-Key header, never logged).
"""

from __future__ import annotations

import os
from typing import Iterator

import requests

BASE = "https://api.waterdata.usgs.gov/ogcapi/v0"
PAGE_LIMIT = 10_000
TIMEOUT = 180

# Parameters of interest for fisheries work
PARAMS = {
    "00060": "discharge_cfs",       # streamflow, ft³/s
    "00065": "gage_height_ft",      # gage height, ft
    "00010": "temperature_c",       # water temperature, °C
}
STATISTIC_MEAN = "00003"


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["Accept"] = "application/geo+json"
    key = os.environ.get("USGS_API_KEY")
    if key:
        s.headers["X-Api-Key"] = key
    return s


def iter_features(collection: str, params: dict) -> Iterator[dict]:
    """Yield all features from a collection query, following next-links."""
    s = _session()
    url = f"{BASE}/collections/{collection}/items"
    query = {"f": "json", "limit": str(PAGE_LIMIT), **params}
    while url:
        resp = s.get(url, params=query, timeout=TIMEOUT)
        resp.raise_for_status()
        page = resp.json()
        yield from page.get("features", [])
        nxt = [l["href"] for l in page.get("links", []) if l["rel"] == "next"]
        url = nxt[0] if nxt else None
        query = None  # next-link already carries the cursor and filters


def get_ohio_sites() -> list[dict]:
    """Active Ohio stream gages as a list of dicts.

    Keys: site_no, name, lat, lon.
    """
    sites = []
    for f in iter_features(
        "monitoring-locations",
        {"state_code": "39", "site_type_code": "ST"},
    ):
        if not f.get("geometry"):
            continue  # a handful of locations lack coordinates
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        sites.append(
            {
                "site_no": p["monitoring_location_number"],
                "name": p["monitoring_location_name"],
                "lat": lat,
                "lon": lon,
            }
        )
    return sites


def get_ohio_daily(start_date: str, end_date: str | None = None) -> dict:
    """Statewide daily mean values for our parameters.

    Returns {site_no: {date: {param_name: value}}} — nested dicts keyed by
    USGS site number, ISO date, and friendly parameter name.
    """
    interval = f"{start_date}T00:00:00Z/" + (
        f"{end_date}T23:59:59Z" if end_date else ".."
    )
    out: dict[str, dict[str, dict[str, float]]] = {}
    for code, name in PARAMS.items():
        n = 0
        for f in iter_features(
            "daily",
            {
                "state_code": "39",
                "site_type_code": "ST",
                "parameter_code": code,
                "statistic_id": STATISTIC_MEAN,
                "datetime": interval,
            },
        ):
            p = f["properties"]
            if p.get("value") is None:
                continue
            site = p["monitoring_location_id"].removeprefix("USGS-")
            out.setdefault(site, {}).setdefault(p["time"], {})[name] = float(
                p["value"]
            )
            n += 1
        print(f"    {name}: {n} records")
    return out
