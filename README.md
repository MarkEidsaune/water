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

## Modeling

```bash
uv run jupyter lab
```

Notebooks live in `notebooks/`; write experiment results up as Tufte-style
articles in `reports/`.
