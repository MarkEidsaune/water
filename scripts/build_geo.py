"""Build static hydrography overlays for the dashboard map.

Two sources, complementary scales:

  Natural Earth 1:10m lakes  → dashboard/geo/lakes.json      (Great Lakes)
  NHDPlus V2 (EPA WATERS)    → dashboard/geo/rivers.json     (named rivers)
                             → dashboard/geo/lakes-inland.json (lakes > 1 km²)

NHDPlus medium resolution carries every named stream; we keep features whose
GNIS name ends in " River" (a practical size proxy — this service does not
expose stream order). Segments are merged per river into one MultiLineString,
with total length (km) retained for line-weight scaling.

Run once, commit the outputs:

    uv run python scripts/build_geo.py

NHDPlus citation:
    Moore, R.B., McKay, L.D., Rea, A.H., Bondelid, T.R., Price, C.V.,
    Dewald, T.G., and Hayes, L., 2025, User's guide for the National
    Hydrography Dataset Plus High Resolution (NHDPlus HR): U.S. Geological
    Survey Scientific Investigations Report 2025-5031, 78 p.,
    https://doi.org/10.3133/sir20255031. [Supersedes USGS Open-File Report
    2019-1096.]
"""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

import requests
import shapefile  # pyshp

OUT_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "geo"
PRECISION = 4  # ~11 m

# Ohio bbox buffered so Lake Erie and Ohio River context render at the edges
WEST, SOUTH, EAST, NORTH = -86.4, 37.0, -79.0, 43.5
NHD_BBOX = "-84.9,38.3,-80.4,42.1"  # tighter box for NHD (state focus)

NE_LAKES = (
    "https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip"
)
NHD = (
    "https://watersgeo.epa.gov/arcgis/rest/services/"
    "NHDPlus_NP21/NHDSnapshot_NP21/MapServer"
)


def rnd(x: float) -> float:
    return round(x, PRECISION)


def round_coords(obj):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [rnd(obj[0]), rnd(obj[1])]
        return [round_coords(x) for x in obj]
    return obj


def write(name: str, features: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}.json"
    out.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   separators=(",", ":"))
    )
    print(f"  {len(features)} features → {out} ({out.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------- Natural Earth

def build_ne_lakes() -> None:
    print(f"Great Lakes: {NE_LAKES}")
    resp = requests.get(NE_LAKES, timeout=120)
    resp.raise_for_status()
    features = []
    with tempfile.TemporaryDirectory() as td:
        zipfile.ZipFile(io.BytesIO(resp.content)).extractall(td)
        reader = shapefile.Reader(str(next(Path(td).glob("*.shp"))))
        fields = [f[0] for f in reader.fields[1:]]
        for sr in reader.iterShapeRecords():
            if not sr.shape.points:
                continue
            w, s, e, n = sr.shape.bbox
            if e < WEST or w > EAST or n < SOUTH or s > NORTH:
                continue
            props = dict(zip(fields, sr.record))
            geom = sr.shape.__geo_interface__
            features.append({
                "type": "Feature",
                "properties": {"name": props.get("name") or None},
                "geometry": {
                    "type": geom["type"],
                    "coordinates": round_coords(geom["coordinates"]),
                },
            })
    write("lakes", features)


# ---------------------------------------------------------------- NHDPlus V2

def nhd_query(layer: int, where: str, out_fields: str) -> list[dict]:
    """Paginated GeoJSON query against the EPA WATERS NHD snapshot."""
    features, offset = [], 0
    while True:
        resp = requests.post(
            f"{NHD}/{layer}/query",
            data={
                "where": where,
                "geometry": NHD_BBOX,
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": out_fields,
                "outSR": "4326",
                "maxAllowableOffset": "0.001",
                "resultOffset": str(offset),
                "resultRecordCount": "1000",
                "f": "geojson",
            },
            timeout=180,
        )
        resp.raise_for_status()
        page = resp.json()
        if "error" in page:
            raise RuntimeError(page["error"])
        batch = page.get("features", [])
        features.extend(batch)
        print(f"    …{len(features)}")
        if not page.get("exceededTransferLimit") or not batch:
            return features
        offset += len(batch)


def build_nhd_rivers() -> None:
    print("Rivers: NHDPlus V2 named '% River' flowlines")
    raw = nhd_query(0, "GNIS_NAME LIKE '% River'", "GNIS_NAME,LENGTHKM")

    lines = defaultdict(list)
    length = defaultdict(float)
    for f in raw:
        name = f["properties"]["GNIS_NAME"]
        geom = f["geometry"]
        if geom is None:
            continue
        coords = (
            [geom["coordinates"]]
            if geom["type"] == "LineString"
            else geom["coordinates"]
        )
        lines[name].extend(round_coords(coords))
        length[name] += f["properties"].get("LENGTHKM") or 0.0

    features = [
        {
            "type": "Feature",
            "properties": {"name": name, "km": round(length[name], 1)},
            "geometry": {"type": "MultiLineString", "coordinates": parts},
        }
        for name, parts in sorted(lines.items())
    ]
    write("rivers", features)


def build_nhd_lakes() -> None:
    print("Inland lakes: NHDPlus V2 waterbodies > 1 km²")
    raw = nhd_query(1, "AREASQKM > 1", "GNIS_NAME,AREASQKM")
    features = []
    for f in raw:
        if f["geometry"] is None:
            continue
        p = f["properties"]
        if p.get("GNIS_NAME") in ("Lake Erie", "Lake Saint Clair"):
            continue  # Great Lakes come from the Natural Earth layer
        features.append({
            "type": "Feature",
            "properties": {
                "name": p.get("GNIS_NAME") or None,
                "km2": round(p.get("AREASQKM") or 0.0, 2),
            },
            "geometry": {
                "type": f["geometry"]["type"],
                "coordinates": round_coords(f["geometry"]["coordinates"]),
            },
        })
    write("lakes-inland", features)


if __name__ == "__main__":
    build_ne_lakes()
    build_nhd_rivers()
    build_nhd_lakes()
