import { CampusScene } from "./scene.js";
import { lineChart, palette } from "./charts.js";
import { renderLab } from "./lab.js";
import { renderMethods } from "./methods.js";

const $ = (id) => document.getElementById(id);
const AUFLS = [49.4, 49.2, 49.0, 48.8];

const PRESETS = {
  calibrated: { loss: 5, H: 3, km: "0.15", part: 100, lat: 0, pl: 0 },
  small: { loss: 2, H: 5, km: "0.15", part: 100, lat: 0, pl: 0 },
  low_inertia: { loss: 5, H: 2, km: "0.15", part: 100, lat: 0, pl: 0 },
  textbook: { loss: 18, H: 5, km: "0.95", part: 100, lat: 0, pl: 0 },
  comms: { loss: 5, H: 3, km: "0.15", part: 100, lat: 1, pl: 40 },
};

const S = {
  ws: null, revision: 0, playing: true, frame: null, campus: null, scene: null,
  history: [], selected: null, lastTime: -1,
};

// ---------------------------------------------------------------- controls
const outputs = {
  loss: (v) => `${(+v).toFixed(1)} %`, H: (v) => `${(+v).toFixed(1)} s`, part: (v) => `${v} %`,
  lat: (v) => `${(+v).toFixed(2)} s`, pl: (v) => `${v} %`, speed: (v) => `${v}×`, tod: (v) => clock(+v),
};
function clock(h) { const hh = Math.floor(h), mm = Math.round((h - hh) * 60); return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`; }
for (const [id, fmt] of Object.entries(outputs)) {
  const input = $(id), out = $("o-" + id);
  const sync = () => (out.textContent = fmt(input.value));
  input.addEventListener("input", sync); sync();
}
for (const id of ["loss", "H", "part", "lat", "pl"]) $(id).addEventListener("input", () => ($("preset").value = "custom"));
$("km").addEventListener("change", () => ($("preset").value = "custom"));
$("preset").addEventListener("change", () => {
  const p = PRESETS[$("preset").value];
  if (!p) return;
  for (const [k, v] of Object.entries(p)) { $(k).value = v; $(k).dispatchEvent(new Event("input")); }
  $("preset").value = Object.keys(PRESETS).find((k) => PRESETS[k] === p);
  configure();
});
$("mode").addEventListener("change", configure);
$("btn-apply").addEventListener("click", configure);
$("btn-play").addEventListener("click", () => {
  S.playing = !S.playing;
  $("btn-play").textContent = S.playing ? "Pause" : "Play";
  $("btn-play").setAttribute("aria-pressed", String(S.playing));
  send({ action: "PLAYBACK", playing: S.playing, speed: +$("speed").value });
});
$("speed").addEventListener("change", () => send({ action: "PLAYBACK", playing: S.playing, speed: +$("speed").value }));
$("tod").addEventListener("input", () => updateSun());
$("cam-reset").addEventListener("click", () => S.scene?.resetView(false));
$("cam-top").addEventListener("click", () => S.scene?.resetView(true));

function scenario() {
  return {
    mode: $("mode").value, generation_loss: +$("loss").value / 100, grid_inertia_h: +$("H").value,
    mechanical_gain: +$("km").value, participation: +$("part").value / 100,
    comm_latency_s: +$("lat").value, comm_jitter_s: +$("lat").value / 2, comm_loss: +$("pl").value / 100,
    campus: true, disturbance: "generation_loss", t_recover: 60,
  };
}

function configure() {
  S.revision += 1;
  S.history = [];
  S.lastTime = -1;
  send({ action: "CONFIGURE", revision: S.revision, scenario: scenario(), playing: S.playing,
         speed: +$("speed").value, selected: 1 });
}

function send(msg) { if (S.ws?.readyState === 1) S.ws.send(JSON.stringify(msg)); }

// ---------------------------------------------------------------- views
document.querySelectorAll(".tabs button").forEach((btn) => btn.addEventListener("click", () => {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b === btn)));
  document.querySelectorAll(".view").forEach((v) => (v.dataset.active = String(v.id === "view-" + btn.dataset.view)));
  try { localStorage.setItem("rakshak.view", btn.dataset.view); } catch (_) { /* storage unavailable */ }
  if (btn.dataset.view === "lab") renderLab($("lab"));
  drawCharts();
}));

// ---------------------------------------------------------------- connection
function connect() {
  const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/telemetry`;
  const ws = new WebSocket(url);
  S.ws = ws;
  ws.onopen = () => { setConn("live", "Live"); configure(); };
  ws.onclose = () => { setConn("lost", "Disconnected — telemetry frozen"); setTimeout(connect, 2000); };
  ws.onmessage = (e) => onFrame(JSON.parse(e.data));
}
function setConn(state, text) { $("conn").dataset.state = state; $("conn").textContent = text; }

function onFrame(frame) {
  if (frame.revision !== S.revision) return;           // ignore frames from a superseded run
  S.frame = frame;
  if (frame.time < S.lastTime) S.history = [];
  if (frame.time !== S.lastTime) {
    S.history.push({ t: frame.time, f: frame.frequency, load: frame.load_pu, gen: frame.generation_pu,
                     pred: frame.prediction?.predicted_min_hz });
    if (S.history.length > 6000) S.history.shift();
    S.lastTime = frame.time;
  }
  const f = frame.frequency;
  $("ro-freq").textContent = `${f.toFixed(3)} Hz`;
  $("ro-freq").parentElement.dataset.band = f <= AUFLS[0] ? "aufls" : f < 49.9 ? "alert" : "normal";
  $("ro-rocof").textContent = `${frame.rocof >= 0 ? "+" : ""}${frame.rocof.toFixed(3)} Hz/s`;
  $("ro-time").textContent = `${frame.time.toFixed(1)} s`;
  if (frame.error) setConn("lost", frame.error);
  S.scene?.update(frame.campus);
  renderLog(frame.events);
  renderAudit(frame);
  if (S.selected) renderInspector(S.selected);
  drawCharts();
}

// ---------------------------------------------------------------- panels
const ACTION = { shed: "Shed", restore: "Restore", feeder_trip: "AUFLS", feeder_restore: "Feeders", absorb: "Absorb",
                 absorption_end: "Release", fault: "Fault", repair: "Repair" };
function renderLog(events = []) {
  const items = [...events].reverse().map((e) =>
    `<li class="kind-${e.action}"><time>${e.time.toFixed(1)} s</time><span>${ACTION[e.action] || e.action}: ${escapeHtml(e.reason)}</span></li>`).join("");
  $("log").innerHTML = items || `<li><time></time><span class="fine">No dispatch actions yet.</span></li>`;
  $("log-mini").innerHTML = items || `<li><time></time><span class="fine">No dispatch actions yet.</span></li>`;
}

function renderAudit(frame) {
  const a = frame.dispatch || {}, p = frame.prediction || {}, m = frame.metrics || {};
  const rows = [
    ["Policy", modeLabel(frame.mode)],
    ["Decision", a.reason || "—"],
    ["Predicted minimum", p.predicted_min_hz ? `${p.predicted_min_hz.toFixed(3)} Hz` : "—"],
    ["Protection target", p.target_hz ? `${p.target_hz.toFixed(2)} Hz` : "—"],
    ["Estimated deficit", p.disturbance_estimate_pu != null ? `${(p.disturbance_estimate_pu * 100).toFixed(2)} %` : "—"],
    ["Relief requested", a.target_w ? `${(a.target_w / 1000).toFixed(1)} kW` : "0 kW"],
    ["Eligible flexible load", a.available_flexible_w ? `${(a.available_flexible_w / 1000).toFixed(0)} kW` : "—"],
  ];
  $("audit").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(String(v))}</dd>`).join("");
  const out = [
    ["Lowest frequency", `${m.nadir?.toFixed(3)} Hz`],
    ["AUFLS stages operated", m.ufls_stages_tripped],
    ["Customers interrupted", m.customers_interrupted],
    ["  by appliance dispatch", m.households_curtailed],
    ["  by feeder opening", m.households_disconnected],
    ["Protected sites interrupted", m.protected_sites_interrupted],
    ["Critical energy not served", `${m.critical_energy_not_served_wh?.toFixed(2)} Wh`],
    ["Deferred service energy", `${(m.total_unserved_wh / 1000).toFixed(2)} kWh`],
  ];
  $("outcomes").innerHTML = out.map(([k, v]) => `<dt>${k}</dt><dd>${v ?? "—"}</dd>`).join("");
  const nadir = m.nadir;
  $("nadir-meta").textContent = nadir ? `lowest ${nadir.toFixed(3)} Hz · AUFLS stage 1 at 49.40 Hz` : "";
}

function renderInspector(b) {
  const el = $("inspector");
  if (!b) { el.innerHTML = `<div class="empty">Select a campus building to inspect it.</div>`; el.dataset.open = "false"; return; }
  el.dataset.open = "true";
  const s = S.frame?.campus?.find((x) => x.id === b.id);
  const state = !s ? ["", "Waiting for telemetry"] : !s.energized ? ["crit", "Feeder opened by AUFLS"]
    : s.ac_curtailed ? ["warn", "AC curtailed by dispatch"] : ["", "Supplied"];
  el.innerHTML = `
    <h3>${escapeHtml(b.name || "Block " + b.id)}${b.verified ? "" : '<span class="badge warn">unverified</span>'}</h3>
    <div class="state-line"><span class="dot ${state[0]}"></span>${state[1]}</div>
    <dl class="kv">
      <dt>Use</dt><dd>${b.use}</dd>
      <dt>Floors</dt><dd>${b.floors} (${b.height_m} m)</dd>
      <dt>Footprint</dt><dd>${b.footprint_m2.toLocaleString()} m²</dd>
      <dt>Floor area</dt><dd>${b.floor_area_m2.toLocaleString()} m²</dd>
      <dt>EPI</dt><dd>${b.epi_kwh_m2_yr} kWh/m²/yr</dd>
      <dt>Annual energy</dt><dd>${(b.annual_kwh / 1000).toFixed(0)} MWh</dd>
      <dt>Average demand</dt><dd>${b.average_kw.toFixed(1)} kW</dd>
      <dt>Live demand</dt><dd>${s ? s.power_kw.toFixed(1) + " kW" : "—"}</dd>
      <dt>Room AC</dt><dd>${s ? `${s.ac_kw} kW · ${s.ac_on ? "on" : "off"}` : "—"}</dd>
      <dt>Room temperature</dt><dd>${s?.room_c != null ? s.room_c.toFixed(2) + " °C" : "—"}</dd>
      <dt>Participation</dt><dd>${s ? (s.enrolled ? "enrolled" : "not enrolled") : "—"}</dd>
    </dl>
    <p class="note">${escapeHtml(s?.reason || "")}</p>
    <p class="note">Footprint: Microsoft ML Building Footprints (ODbL). EPI source: ${escapeHtml(b.epi_source)}.
    Name, use and floor count are defaults until confirmed in <code>data/rvce/overrides.json</code>.</p>`;
}

// ---------------------------------------------------------------- charts
function drawCharts() {
  const c = palette();
  const h = S.history;
  const freq = h.map((p) => [p.t, p.f]);
  const refs = [
    { y: 49.9, label: "49.90 normal band", color: c.muted },
    ...AUFLS.map((y, i) => ({ y, label: `AUFLS stage ${i + 1}`, color: c.crit, dash: [6, 4] })),
  ];
  const fMin = Math.min(49.3, ...freq.map((p) => p[1])) - 0.05, fMax = Math.max(50.1, ...freq.map((p) => p[1])) + 0.02;
  if ($("view-grid").dataset.active === "true") {
    lineChart($("chart-freq"), { series: [{ points: freq, color: c.accent, label: "Frequency" },
      { points: h.filter((p) => p.pred).map((p) => [p.t, p.pred]), color: c.warn, label: "Predicted minimum", dash: [3, 3], width: 1.25 }],
      refs, xLabel: "time (s)", yLabel: "Hz", yMin: fMin, yMax: fMax });
    lineChart($("chart-load"), { series: [{ points: h.map((p) => [p.t, p.load]), color: c.accent, label: "Demand" },
      { points: h.map((p) => [p.t, p.gen]), color: c.ok, label: "Generation" }], xLabel: "time (s)", yLabel: "pu" });
  }
  lineChart($("chart-mini"), { series: [{ points: freq, color: c.accent, label: "Frequency" }],
    refs: refs.slice(0, 2), yMin: fMin, yMax: fMax, compact: true });
}

// ---------------------------------------------------------------- labels
function placeLabels() {
  if (!S.scene || !S.campus) return;
  const wrap = $("labels");
  const items = S.campus.buildings.filter((b) => b.campus && (b.id === S.selected?.id || b.id === S.scene.hovered));
  wrap.innerHTML = items.map((b) => {
    const p = S.scene.screenPosition(b);
    if (!p.visible) return "";
    return `<div class="tag ${b.id === S.selected?.id ? "sel" : ""}" style="left:${p.x}px;top:${p.y}px">${escapeHtml(b.name || "Block " + b.id)}</div>`;
  }).join("");
}

function updateSun() {
  const sp = S.scene?.setTimeOfDay(+$("tod").value);
  if (sp) $("sun-info").textContent = `Sun ${sp.elevationDeg.toFixed(1)}° elevation, ${sp.azimuthDeg.toFixed(0)}° azimuth · streetlights ${sp.elevationDeg < -6 ? "on" : "off"}. Lighting only; building demand uses annual averages.`;
}

function modeLabel(m) { return $("mode").querySelector(`option[value="${m}"]`)?.textContent || m; }
function escapeHtml(s) { return String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])); }

// ---------------------------------------------------------------- boot
async function boot() {
  renderMethods($("methods"));
  try {
    const res = await fetch("/api/campus");
    S.campus = await res.json();
    S.scene = new CampusScene($("scene"), S.campus, { onSelect: (b) => { S.selected = b; renderInspector(b); } });
    S.scene.onFrame = placeLabels;
    updateSun();
  } catch (err) {
    $("scene-wrap").insertAdjacentHTML("beforeend", `<p class="empty overlay">Campus model unavailable: ${escapeHtml(err.message)}</p>`);
  }
  let saved = null;
  try { saved = localStorage.getItem("rakshak.view"); } catch (_) { /* storage unavailable */ }
  if (saved) document.querySelector(`.tabs button[data-view="${saved}"]`)?.click();
  connect();
  window.addEventListener("resize", drawCharts);
}
boot();
