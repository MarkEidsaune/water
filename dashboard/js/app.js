// Ohio Water — map of USGS gages with sparkline detail panel.

const PARAM_LABELS = {
  discharge_cfs: "Discharge, ft³/s",
  gage_height_ft: "Gage height, ft",
  temperature_c: "Water temperature, °C",
};

// Live conditions via the USGS OGC API (CORS-open, keyless in-browser)
const OGC = "https://api.waterdata.usgs.gov/ogcapi/v0/collections";
const NIMS = "https://api.waterdata.usgs.gov/nims/v0";
const NIMS_IMG = "https://usgs-nims-images.s3.amazonaws.com";
const LIVE_PARAMS = { "00060": "discharge_cfs", "00065": "gage_height_ft", "00010": "temperature_c" };
const STALE_MS = 24 * 3600 * 1000; // ignore "latest" readings older than 24 h

// Percentile grid — must match PCT_GRID in src/water/pipeline.py
const PCT_GRID = [0, 5, 10, 25, 50, 75, 90, 95, 100];

// Current flow vs. the gage's own trailing year:
// dry amber → normal blue → high dark navy
const flowColor = d3
  .scaleLinear()
  .domain([0, 25, 50, 90, 100])
  .range(["#c08a3e", "#9db8a5", "#7fb2d6", "#1b6ca8", "#08306b"])
  .clamp(true);
const NO_DATA = "#999";

// Piecewise-linear percentile of v against quantile values q (on PCT_GRID)
function percentile(v, q) {
  if (v <= q[0]) return 0;
  for (let i = 1; i < q.length; i++) {
    if (v <= q[i]) {
      const span = q[i] - q[i - 1];
      const frac = span > 0 ? (v - q[i - 1]) / span : 1;
      return PCT_GRID[i - 1] + frac * (PCT_GRID[i] - PCT_GRID[i - 1]);
    }
  }
  return 100;
}

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

// One statewide request for current discharge at every Ohio stream gage
async function fetchLiveFlows() {
  try {
    const url = `${OGC}/latest-continuous/items?f=json&state_code=39&site_type_code=ST&parameter_code=00060&limit=10000`;
    const d = await fetch(url).then((r) => r.json());
    const now = Date.now();
    const flows = new Map();
    for (const f of d.features ?? []) {
      const p = f.properties;
      const t = Date.parse(p.time);
      if (p.value == null || now - t > STALE_MS) continue;
      flows.set(p.monitoring_location_id.replace("USGS-", ""), {
        value: +p.value,
        time: t,
      });
    }
    return flows;
  } catch {
    return new Map(); // offline/API down → neutral markers
  }
}

Promise.all([fetch("data/sites.json").then((r) => r.json()), fetchLiveFlows()])
  .then(([sites, flows]) => {
    let live = 0;
    for (const site of sites) {
      const flow = flows.get(site.id);
      let color = NO_DATA;
      let pct = null;
      if (flow && site.q) {
        pct = percentile(flow.value, site.q);
        color = flowColor(pct);
        live++;
      }
      const m = L.circleMarker([site.lat, site.lon], {
        radius: pct == null ? 3 : 4.5,
        className: "gage-marker",
        color,
        fillColor: color,
        fillOpacity: pct == null ? 0.25 : 0.75,
        weight: 1,
      }).addTo(map);
      let tip =
        pct == null
          ? site.name
          : `${site.name} — ${Math.round(pct)}th pctile flow`;
      if (site.cam) tip += " · camera";
      m.bindTooltip(tip, { direction: "top", offset: [0, -4] });
      m.on("click", () => {
        selectMarker(m);
        showSite(site);
      });
    }
    document.getElementById("legend").classList.toggle("hidden", live === 0);
  });

// Latest camera image: fetch fresh metadata so newestImageDT is current,
// then construct the S3 URL from the NIMS filename convention.
async function fetchCameraImage(camId) {
  try {
    const cams = await fetch(`${NIMS}/cameras?camId=${camId}`).then((r) => r.json());
    const dt = cams?.[0]?.newestImageDT;
    if (!dt) return null;
    const stamp = dt.replace(/\.\d+Z$/, "Z").replaceAll(":", "-");
    return {
      url: `${NIMS_IMG}/720/${camId}/${camId}___${stamp}.jpg`,
      time: new Date(dt),
      hivis: `https://apps.usgs.gov/hivis/camera/${camId}`,
    };
  } catch {
    return null;
  }
}

function renderCamera(img) {
  const el = document.getElementById("camera");
  el.innerHTML = "";
  if (!img) return;
  const when = img.time.toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
  el.innerHTML =
    `<a href="${img.hivis}" target="_blank" rel="noopener">` +
    `<img src="${img.url}" alt="Latest gage camera image"/></a>` +
    `<span class="asof">camera · ${when} · <a href="${img.hivis}" target="_blank" rel="noopener">timelapse</a></span>`;
}

// Current readings for one site, for the panel header
async function fetchSiteLatest(siteId) {
  try {
    const url = `${OGC}/latest-continuous/items?f=json&monitoring_location_id=USGS-${siteId}&limit=50`;
    const d = await fetch(url).then((r) => r.json());
    const now = Date.now();
    const out = [];
    for (const f of d.features ?? []) {
      const p = f.properties;
      const name = LIVE_PARAMS[p.parameter_code];
      const t = Date.parse(p.time);
      if (!name || p.value == null || now - t > STALE_MS) continue;
      out.push({ name, value: +p.value, time: t });
    }
    return out;
  } catch {
    return [];
  }
}

function renderNow(readings) {
  const el = document.getElementById("now");
  if (!readings.length) {
    el.innerHTML = "";
    return;
  }
  const asOf = new Date(Math.max(...readings.map((r) => r.time)));
  const parts = readings
    .map((r) => `${PARAM_LABELS[r.name]}: <strong>${r.value}</strong>`)
    .join(" · ");
  el.innerHTML = `${parts}<br/><span class="asof">as of ${asOf.toLocaleString([], {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  })}</span>`;
}

async function showSite(site) {
  document.getElementById("site-name").textContent = site.name;
  document.getElementById("site-meta").textContent =
    `USGS ${site.id} · ${site.lat.toFixed(3)}, ${(-site.lon).toFixed(3)} W`;
  document.getElementById("now").innerHTML = "";
  document.getElementById("camera").innerHTML = "";

  const [series, latest, camImg] = await Promise.all([
    fetch(`data/series/${site.id}.json`).then((r) => r.json()),
    fetchSiteLatest(site.id),
    site.cam ? fetchCameraImage(site.cam) : Promise.resolve(null),
  ]);
  renderNow(latest);
  renderCamera(camImg);

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

  // Hover: crosshair + dot + tooltip
  const bisect = d3.bisector((p) => p[0]).center;

  const vline = svg.append("line")
    .attr("class", "spark-crosshair")
    .attr("y1", m.top).attr("y2", height - m.bottom)
    .attr("visibility", "hidden");

  const dot = svg.append("circle")
    .attr("class", "spark-dot")
    .attr("r", 3)
    .attr("visibility", "hidden");

  const TW = 70, TH = 28;
  const tip = svg.append("g").attr("class", "spark-tip").attr("visibility", "hidden");
  tip.append("rect").attr("width", TW).attr("height", TH).attr("rx", 2);
  const tipDate = tip.append("text").attr("class", "spark-tip-date").attr("x", 5).attr("y", 10);
  const tipVal = tip.append("text").attr("class", "spark-tip-val").attr("x", 5).attr("y", 22);

  svg.append("rect")
    .attr("class", "spark-overlay")
    .attr("x", m.left).attr("y", m.top)
    .attr("width", width - m.left - m.right)
    .attr("height", height - m.top - m.bottom)
    .on("pointermove", (event) => {
      const [mx] = d3.pointer(event);
      const i = Math.min(bisect(pts, x.invert(mx)), pts.length - 1);
      const [date, val] = pts[i];
      const cx = x(date);
      const cy = y(val);

      vline.attr("x1", cx).attr("x2", cx).attr("visibility", "visible");
      dot.attr("cx", cx).attr("cy", cy).attr("visibility", "visible");

      tipDate.text(date.toLocaleDateString([], { month: "short", day: "numeric" }));
      tipVal.text(d3.format(".4~g")(val));

      const tx = cx + 8 + TW > width - m.right ? cx - TW - 8 : cx + 8;
      const ty = Math.min(Math.max(cy - TH / 2, m.top), height - m.bottom - TH);
      tip.attr("transform", `translate(${tx},${ty})`).attr("visibility", "visible");
    })
    .on("pointerleave", () => {
      vline.attr("visibility", "hidden");
      dot.attr("visibility", "hidden");
      tip.attr("visibility", "hidden");
    });

  div.appendChild(svg.node());
  return div;
}
