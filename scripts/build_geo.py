"""Build static hydrography overlays for the dashboard map.

Downloads Natural Earth 1:10m rivers and lakes, keeps features whose
bounding box intersects a buffered Ohio extent, and writes compact GeoJSON:

    dashboard/geo/rivers.json
    dashboard/geo/lakes.json

Run once (or when tweaking the extent); outputs are committed.

    uv run python scripts/build_geo.py
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import requests
import shapefile  # pyshp

NE = "https://naciscdn.org/naturalearth/10m/physical"
SOURCES = {
    "rivers": f"{NE}/ne_10m_rivers_lake_centerlines.zip",
    "lakes": f"{NE}/ne_10m_lakes.zip",
}

# Ohio bbox (-84.82, 38.40, -80.52, 41.98) buffered ~1.5° so neighboring
# water (full Lake Erie shoreline, Ohio River context) renders at the edges.
WEST, SOUTH, EAST, NORTH = -86.4, 37.0, -79.0, 43.5

OUT_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "geo"
PRECISION = 4  # ~11 m; plenty for an overlay


def bbox_intersects(b: tuple[float, float, float, float]) -> bool:
    w, s, e, n = b
    return not (e < WEST or w > EAST or n < SOUTH or s > NORTH)


def round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], PRECISION), round(obj[1], PRECISION)]
        return [round_coords(x) for x in obj]
    return obj


def build(name: str, url: str, keep_fields: list[str]) -> None:
    print(f"{name}: downloading {url}")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(io.BytesIO(resp.content)).extractall(td)
        shp = next(Path(td).glob("*.shp"))
        reader = shapefile.Reader(str(shp))
        fields = [f[0] for f in reader.fields[1:]]

        features = []
        for sr in reader.iterShapeRecords():
            if not sr.shape.points or not bbox_intersects(sr.shape.bbox):
                continue
            props = dict(zip(fields, sr.record))
            geom = sr.shape.__geo_interface__
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        k: props.get(k) for k in keep_fields if props.get(k)
                    },
                    "geometry": {
                        "type": geom["type"],
                        "coordinates": round_coords(geom["coordinates"]),
                    },
                }
            )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}.json"
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   separators=(",", ":"))
    )
    print(f"  {len(features)} features → {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build("rivers", SOURCES["rivers"], ["name", "strokeweig"])
    build("lakes", SOURCES["lakes"], ["name"])
