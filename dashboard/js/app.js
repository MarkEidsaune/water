// Ohio Water — map of USGS gages with sparkline detail panel.

const PARAM_LABELS = {
  discharge_cfs: "Discharge, ft³/s",
  gage_height_ft: "Gage height, ft",
  temperature_c: "Water temperature, °C",
};

const map = L.map("map", { zoomControl: true }).setView([40.2, -82.7], 8);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
  attribution:
    '© OpenStreetMap, © CARTO · Data: USGS NWIS · Hydrography: <a href="https://doi.org/10.3133/sir20255031">USGS NHDPlus</a>, Natural Earth',
  maxZoom: 18,
}).addTo(map);

// Hydrography overlays: water is the only colored geography, drawn beneath
// the gage markers. Panes keep z-order explicit (lakes < rivers < markers).
map.createPane("lakes").style.zIndex = 390;
map.createPane("rivers").style.zIndex = 395;

const LAKE_STYLE = {
  color: "#c3dbe8",
  weight: 1,
  fillColor: "#d7e8f2",
  fillOpacity: 1,
};

for (const src of ["geo/lakes.json", "geo/lakes-inland.json"]) {
  fetch(src)
    .then((r) => r.json())
    .then((geo) =>
      L.geoJSON(geo, {
        pane: "lakes",
        interactive: false,
        style: LAKE_STYLE,
      }).addTo(map)
    );
}

fetch("geo/rivers.json")
  .then((r) => r.json())
  .then((geo) =>
    L.geoJSON(geo, {
      pane: "rivers",
      interactive: false,
      style: (f) => ({
        color: "#a3c6dd",
        // Weight by total river length (km) as a proxy for size:
        // ~1px for short rivers up to ~3px for the Ohio (799 km)
        weight: Math.min(3, 0.8 + Math.sqrt(f.properties.km ?? 50) / 12),
        opacity: 0.9,
      }),
    }).addTo(map)
  );

const panel = document.getElementById("panel");
document.getElementById("close").addEventListener("click", () => {
  panel.classList.add("hidden");
  selectMarker(null);
});

let selected = null;
function selectMarker(marker) {
  if (selected) selected.getElement()?.classList.remove("selected");
  selected = marker;
  if (selected) selected.getElement()?.classList.add("selected");
}

fetch("data/sites.json")
  .then((r) => r.json())
  .then((sites) => {
    for (const site of sites) {
      const m = L.circleMarker([site.lat, site.lon], {
        radius: 4,
        className: "gage-marker",
      }).addTo(map);
      m.bindTooltip(site.name, { direction: "top", offset: [0, -4] });
      m.on("click", () => {
        selectMarker(m);
        showSite(site);
      });
    }
  });

async function showSite(site) {
  const series = await fetch(`data/series/${site.id}.json`).then((r) => r.json());
  document.getElementById("site-name").textContent = site.name;
  document.getElementById("site-meta").textContent =
    `USGS ${site.id} · ${site.lat.toFixed(3)}, ${(-site.lon).toFixed(3)} W`;

  const charts = document.getElementById("charts");
  charts.innerHTML = "";
  const dates = series.date.map((d) => new Date(d));

  for (const param of site.params) {
    const values = series[param];
    if (!values) continue;
    charts.appendChild(sparkline(PARAM_LABELS[param] ?? param, dates, values));
  }
  panel.classList.remove("hidden");
}

function sparkline(title, dates, values, width = 320, height = 60) {
  const div = document.createElement("div");
  div.className = "chart";

  const pts = dates
    .map((d, i) => [d, values[i]])
    .filter(([, v]) => v !== null && v !== undefined);
  const latest = pts.length ? pts[pts.length - 1][1] : null;

  const h = document.createElement("h3");
  h.innerHTML = `${title}<span class="latest">${latest ?? "—"}</span>`;
  div.appendChild(h);
  if (!pts.length) return div;

  const m = { top: 4, right: 6, bottom: 16, left: 38 };
  const x = d3.scaleTime().domain(d3.extent(pts, (p) => p[0])).range([m.left, width - m.right]);
  const y = d3.scaleLinear().domain(d3.extent(pts, (p) => p[1])).nice().range([height - m.bottom, m.top]);

  const svg = d3.create("svg").attr("width", width).attr("height", height);

  svg.append("g")
    .attr("class", "spark-axis")
    .attr("transform", `translate(0,${height - m.bottom})`)
    .call(d3.axisBottom(x).ticks(4).tickSize(3))
    .call((g) => g.select(".domain").remove());

  svg.append("g")
    .attr("class", "spark-axis")
    .attr("transform", `translate(${m.left},0)`)
    .call(d3.axisLeft(y).ticks(3).tickSize(3))
    .call((g) => g.select(".domain").remove());

  svg.append("path")
    .datum(pts)
    .attr("class", "spark")
    .attr("d", d3.line().defined(([, v]) => v != null).x(([d]) => x(d)).y(([, v]) => y(v)));

  div.appendChild(svg.node());
  return div;
}
