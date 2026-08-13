# Ohio Water

USGS water data for local fisheries: ingestion, a map-based dashboard, and
predictive modeling experiments.

## Layout

```
src/water/       Ingestion library (USGS NWIS via dataretrieval)
dashboard/       Static Leaflet + D3 dashboard (Tufte-inspired)
notebooks/       Modeling experiments
reports/         Write-ups (Tufte CSS articles)
data/            Raw and processed data (gitignored)
```

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Fetch data & build the dashboard

```bash
uv run python -m water.pipeline --days 365
```

This pulls all active Ohio stream gages reporting discharge, gage height, or
water temperature, caches raw pulls to `data/raw/`, and writes
`dashboard/data/` (site list + per-gage daily series).

## View the dashboard

```bash
python -m http.server -d dashboard 8000
```

Open http://localhost:8000 — click a gage to see sparklines of the trailing
year.

## Data sources

- **Gage observations:** USGS National Water Information System (NWIS),
  retrieved via [dataretrieval](https://github.com/DOI-USGS/dataretrieval-python).
- **Hydrography (rivers and inland lakes):** National Hydrography Dataset Plus
  (NHDPlus), queried from the NHDPlus V2 snapshot hosted by EPA WATERS
  GeoServices:

  > Moore, R.B., McKay, L.D., Rea, A.H., Bondelid, T.R., Price, C.V.,
  > Dewald, T.G., and Hayes, L., 2025, User’s guide for the National
  > Hydrography Dataset Plus High Resolution (NHDPlus HR): U.S. Geological
  > Survey Scientific Investigations Report 2025–5031, 78 p.,
  > https://doi.org/10.3133/sir20255031. [Supersedes USGS Open-File Report
  > 2019–1096.]

- **Great Lakes shorelines:** [Natural Earth](https://www.naturalearthdata.com/)
  1:10m physical vectors (public domain).

## Modeling

```bash
uv run jupyter lab
```

Notebooks live in `notebooks/`; write experiment results up as Tufte-style
articles in `reports/`.
