"use strict";

const CATEGORY_COLORS = {
  clear: "#2ecc71",
  congestion: "#f1c40f",
  stalled_vehicle: "#e67e22",
  accident: "#e74c3c",
  hazard: "#d65cff",
  obscured: "#5b6b7b",
  unknown: "#3a4655",
};
const CATEGORY_LABELS = {
  clear: "Clear", congestion: "Congestion", stalled_vehicle: "Stalled vehicle",
  accident: "Accident", hazard: "Hazard", obscured: "Obscured", unknown: "Not yet scanned",
};

const state = { markers: new Map(), category: new Map(), seenIncidents: new Set() };

// --- map ---------------------------------------------------------------
const map = L.map("map", { preferCanvas: true, zoomControl: true }).setView([51.509, -0.118], 11);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution: "© OpenStreetMap, © CARTO", maxZoom: 19, subdomains: "abcd",
}).addTo(map);

function markerStyle(category) {
  const color = CATEGORY_COLORS[category] || CATEGORY_COLORS.unknown;
  const incident = category && category !== "clear" && category !== "obscured" && category !== "unknown";
  return {
    radius: incident ? 8 : 5,
    fillColor: color, color: incident ? "#fff" : color,
    weight: incident ? 2 : 1, opacity: 1, fillOpacity: 0.9,
  };
}

function popupHtml(cam, category) {
  const cat = category || "unknown";
  return `<div class="cam-popup">
    <div class="cam-name">${cam.name}</div>
    <div class="cam-cat" style="color:${CATEGORY_COLORS[cat]}">● ${CATEGORY_LABELS[cat] || cat}</div>
    <img loading="lazy" src="${cam.frame_url}?t=${Date.now()}" alt="camera frame"/>
  </div>`;
}

async function loadCameras() {
  const res = await fetch("/api/cameras");
  const cams = await res.json();
  cams.forEach((cam) => {
    const m = L.circleMarker([cam.lat, cam.lon], markerStyle("unknown"));
    m.bindPopup(() => popupHtml(cam, state.category.get(cam.id)), { maxWidth: 260 });
    m._cam = cam;
    m.addTo(map);
    state.markers.set(cam.id, m);
  });
  document.getElementById("status-text").textContent = `${cams.length} cameras live · scanning…`;
}

// --- incident log + recolor (populated once detector runs) -------------
function relTime(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function renderIncidents(incidents) {
  const list = document.getElementById("incident-list");
  document.getElementById("incident-count").textContent = incidents.length;
  if (!incidents.length) {
    list.innerHTML = '<li class="muted empty">No incidents detected yet.</li>';
    return;
  }
  list.innerHTML = "";
  incidents.forEach((inc) => {
    const li = document.createElement("li");
    li.className = "incident";
    li.style.borderLeftColor = CATEGORY_COLORS[inc.category] || CATEGORY_COLORS.unknown;
    const lead = inc.lead_time_seconds
      ? `<div class="lead">⏱ detected ${Math.round(inc.lead_time_seconds / 60)} min before official update</div>` : "";
    const tag = inc.matched_disruption_id
      ? `<span class="tag matched">✓ in official feed${inc.match_severity ? " · " + inc.match_severity : ""}</span>`
      : `<span class="tag ahead">⚡ not in official feed</span>`;
    li.innerHTML = `
      <img loading="lazy" src="${inc.image_thumb_url || inc.frame_url || ""}" alt=""/>
      <div class="meta">
        <div class="cat" style="color:${CATEGORY_COLORS[inc.category]}">${CATEGORY_LABELS[inc.category] || inc.category}
          <span class="ts">· ${relTime(inc.detected_at)}</span></div>
        <div class="loc">${inc.common_name}</div>
        <div class="desc">${inc.description || ""}</div>
        ${lead}
        <div class="tags">${tag}</div>
      </div>`;
    li.onclick = () => {
      map.setView([inc.lat, inc.lon], 15);
      const m = state.markers.get(inc.camera_id);
      if (m) m.openPopup();
    };
    list.appendChild(li);
  });
}

async function pollInsight() {
  try {
    const res = await fetch("/api/insight");
    if (!res.ok) return;
    const ins = await res.json();
    const banner = document.getElementById("leadbanner");
    const text = document.getElementById("leadbanner-text");
    if (ins.best_lead) {
      const b = ins.best_lead;
      text.textContent =
        `Detected "${CATEGORY_LABELS[b.category] || b.category}" at ${b.common_name} ` +
        `${Math.round(b.lead_time_seconds / 60)} min before the official TfL feed updated it.`;
      banner.classList.remove("hidden");
    } else if (ins.not_in_feed > 0) {
      text.textContent =
        `${ins.not_in_feed} live condition${ins.not_in_feed > 1 ? "s" : ""} detected that ` +
        `${ins.not_in_feed > 1 ? "are" : "is"} not yet in the official TfL disruption feed ` +
        `· ${ins.matched} corroborated · ${ins.official_count} official disruptions tracked.`;
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  } catch (e) { /* poller not up yet */ }
}

async function pollStates() {
  try {
    const res = await fetch("/api/states");
    if (!res.ok) return;
    const cats = await res.json(); // {camera_id: category}
    Object.entries(cats).forEach(([id, cat]) => {
      state.category.set(id, cat);
      const m = state.markers.get(id);
      if (m) m.setStyle(markerStyle(cat));
    });
  } catch (e) { /* detector not up yet */ }
}

async function pollIncidents() {
  try {
    const res = await fetch("/api/incidents");
    if (!res.ok) return;
    const incidents = await res.json();
    renderIncidents(incidents);
  } catch (e) { /* detector not up yet */ }
}

async function pollBriefing() {
  try {
    const res = await fetch("/api/briefing");
    if (!res.ok) return;
    const b = await res.json();
    if (b.text) {
      const el = document.getElementById("briefing-text");
      el.textContent = b.text;
      el.classList.remove("muted");
      if (b.generated_at)
        document.getElementById("briefing-time").textContent = "updated " + relTime(b.generated_at);
    }
  } catch (e) { /* briefing not up yet */ }
}

async function pollHealth() {
  try {
    const res = await fetch("/api/health");
    const h = await res.json();
    const dot = document.getElementById("health-dot");
    dot.className = "dot " + (h.status === "ok" ? "ok" : "bad");
    const scanned = h.scanned != null ? ` · ${h.scanned}/${h.cameras_monitored} scanned` : "";
    document.getElementById("status-text").textContent =
      `${h.model} · ${h.cameras_monitored} cameras${scanned}` + (h.replay_mode ? " · REPLAY" : "");
    // NVIDIA stack panel
    const beLabel = { openai: "vLLM", ollama: "Ollama" }[h.detector_backend] || h.detector_backend;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("nv-detector", `${h.model} · ${beLabel}`);
    set("nv-briefing", h.briefing_model || "—");
    set("nv-spatial", (h.spatial_backend || "—").replace(" (GPU)", " · GPU").replace(" (CPU)", " · CPU"));
  } catch (e) {
    document.getElementById("health-dot").className = "dot bad";
    document.getElementById("status-text").textContent = "backend offline";
  }
}

function buildLegend() {
  const ul = document.getElementById("legend-list");
  ["accident", "stalled_vehicle", "hazard", "congestion", "clear", "obscured"].forEach((c) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="swatch" style="background:${CATEGORY_COLORS[c]}"></span>${CATEGORY_LABELS[c]}`;
    ul.appendChild(li);
  });
}

// --- Ripple: causal cascade (planning mode) ----------------------------
const rippleLayer = L.layerGroup().addTo(map);

function renderCascadeImpact(r) {
  const el = document.getElementById("cascade-impact");
  if (!el) return;
  const deprivedNames = (r.most_deprived || []).map((m) => m.name).join(", ");
  el.innerHTML = `
    <div class="cascade-head"><b>${(r.est_daily_journeys || 0).toLocaleString()}</b> daily journeys affected</div>
    <div class="cascade-head"><b>${(r.affected_population || 0).toLocaleString()}</b> residents in catchment</div>
    <div class="cascade-row"><b>${r.deprived_lsoas || 0}</b> of ${r.affected_lsoas || 0} neighbourhoods in the most-deprived 20%</div>
    ${deprivedNames ? `<div class="cascade-row deprived">⚠ ${deprivedNames}</div>` : ""}
    <div class="cascade-row"><b>${(r.affected_nodes || 0).toLocaleString()}</b> junctions · <b>${r.affected_stops || 0}</b> stops · <b>${r.affected_routes || 0}</b> routes</div>
    ${r.engine ? `<div class="cascade-engine">⚡ BFS on ${r.engine}</div>` : ""}`;
}

async function runCascade(lat, lon) {
  const panel = document.getElementById("cascade-impact");
  if (panel) panel.innerHTML = '<span class="muted small">computing cascade…</span>';
  rippleLayer.clearLayers();
  try {
    const res = await fetch("/api/cascade", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon }),
    });
    if (!res.ok) { if (panel) panel.innerHTML = '<span class="muted small">cascade engine still loading…</span>'; return; }
    const r = await res.json();
    (r.ripple_points || []).forEach((p) =>
      L.circleMarker([p.lat, p.lon], { radius: 2.5, weight: 0, fillColor: "#4ea1ff", fillOpacity: 0.35 }).addTo(rippleLayer));
    L.circleMarker([lat, lon], { radius: 9, color: "#fff", weight: 2, fillColor: "#e74c3c", fillOpacity: 0.95 })
      .addTo(rippleLayer).bindPopup("Disruption epicentre").openPopup();
    renderCascadeImpact(r);
  } catch (e) {
    if (panel) panel.innerHTML = '<span class="muted small">cascade failed</span>';
    console.error(e);
  }
}

map.on("click", (e) => runCascade(e.latlng.lat, e.latlng.lng));

// --- boot --------------------------------------------------------------
buildLegend();
loadCameras().catch((e) => {
  document.getElementById("status-text").textContent = "failed to load cameras";
  console.error(e);
});
pollHealth();
setInterval(pollHealth, 5000);
setInterval(pollStates, 4000);
setInterval(pollIncidents, 4000);
setInterval(pollInsight, 5000);
setInterval(pollBriefing, 15000);
