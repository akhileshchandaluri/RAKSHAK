import { World } from "./world.js";
import { Replay, Player } from "./player.js";
import { SCENES } from "./story.js";
import { renderDecision, KIND_LABEL, describeBuilding } from "./explain.js";
import { renderResults, overall } from "./results.js";
import { renderMethods } from "./methods.js";
import { lineChart, sparkline } from "./svgcharts.js";

const $ = (id) => document.getElementById(id);
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const PRESET_LABEL = {
  aufls: "AUFLS only", threshold: "Fixed threshold rule", npmrd: "Rakshak predictive", hybrid: "Rakshak hybrid",
  npmrd_comms: "Rakshak predictive · slow network", hybrid_comms: "Rakshak hybrid · slow network", none: "No protection",
};

const S = {
  mode: null, campus: null, world: null, replays: new Map(), current: [], sceneIndex: 0,
  selected: null, summary: null, calibration: [], decisionShown: null, cmp: ["aufls", "hybrid"],
};

// ---------------------------------------------------------------- data
async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

async function replay(preset) {
  if (!S.replays.has(preset)) {
    S.replays.set(preset, (async () => {
      busy(true, "Simulating " + (PRESET_LABEL[preset] || preset) + "…");
      try { return new Replay(await fetchJSON(`/api/replay?preset=${encodeURIComponent(preset)}`)); }
      finally { busy(false); }
    })());
  }
  return S.replays.get(preset);
}

function busy(on, text = "Simulating…") { $("loading").hidden = !on; $("loading-text").textContent = text; }

// ---------------------------------------------------------------- player
const player = new Player({ onFrame: (t, replays) => render(t, replays) });
player.onPlayState = (playing) => {
  $("tl-play-icon").setAttribute("d", playing ? "M7 5h4v14H7zM13 5h4v14h-4z" : "M8 5v14l11-7z");
  $("tl-play").setAttribute("aria-label", playing ? "Pause" : "Play");
};
$("tl-play").addEventListener("click", () => player.toggle());
$("tl-speed").addEventListener("change", () => (player.speed = +$("tl-speed").value));
$("tl-scrub").addEventListener("input", () => player.seek(+$("tl-scrub").value));

function load(replays) {
  S.current = replays;
  player.load(replays);
  const main = replays[0];
  $("tl-scrub").max = main.duration;
  const c = { pred: css("--accent"), open: css("--open") };
  sparkline($("tl-spark"), main.frames.map((f) => [f.t, f.f]), {
    x0: 0, x1: main.duration, y0: Math.min(49.3, ...main.frames.map((f) => f.f)) - 0.02,
    y1: Math.max(50.1, ...main.frames.map((f) => f.f)) + 0.02, color: c.pred,
    refs: [{ y: 49.4, color: c.open }] });
  $("tl-markers").innerHTML = main.data.decisions.map((d, k) =>
    `<button class="${d.kind}" style="left:${(d.t / main.duration) * 100}%" data-k="${k}" title="${KIND_LABEL[d.kind] || d.kind} at ${d.t.toFixed(1)} s"></button>`).join("");
  $("tl-markers").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    const d = main.data.decisions[+b.dataset.k];
    player.pause(); player.seek(d.t + 0.5); openDecision(d, main);
  }));
}

// ---------------------------------------------------------------- render
function render(t, replays) {
  if (!replays.length || !S.world) return;
  const main = replays[0];
  const frame = main.frameAt(t);
  $("tl-scrub").value = t;
  $("tl-time").textContent = `${t.toFixed(1)} s`;
  const hz = $("hz");
  hz.dataset.band = frame.f <= 49.4 ? "aufls" : frame.f < 49.9 ? "alert" : "normal";
  $("hz-value").textContent = frame.f.toFixed(3);
  if (replays.length === 2) {
    const [a, b] = replays;
    const sa = a.stateAt(t), sb = b.stateAt(t);
    S.world.split = { left: () => S.world.applyState(sa, a), right: () => S.world.applyState(sb, b) };
    renderCompare(t);
  } else {
    S.world.split = null;
    S.world.applyState(main.stateAt(t), main);
  }
  if (S.mode === "story") renderStoryKpis(t);
  if (S.mode === "explore") renderExploreKpis(t);
  if (S.selected) renderBuilding(S.selected);
}

function placeLabels() {
  const host = $("labels");
  if (!S.world || !S.current.length || S.current.length === 2) { host.innerHTML = ""; return; }
  const r = S.current[0];
  const state = r.stateAt(player.t);
  const frame = r.frameAt(player.t);
  const items = [];
  for (const b of S.campus.buildings) {
    if (!b.campus) continue;
    const meta = r.data.buildings.find((x) => x.campus_id === b.id);
    if (!meta) continue;
    const s = state[meta.i];
    const sel = S.selected?.kind === "campus" && S.selected.building.id === b.id;
    if (s === 0 && !sel) continue;
    const kw = frame.k[r.data.campus_ids.indexOf(b.id)] ?? 0;
    const text = s === 2 ? `<b>Feeder cut</b> · Block ${b.id}` : s === 1 ? `<b>AC paused</b> · Block ${b.id}` : `Block ${b.id} · ${kw.toFixed(0)} kW`;
    items.push({ b, cls: s === 2 ? "open" : s === 1 ? "curtailed" : "", sel, text });
  }
  host.innerHTML = items.slice(0, 14).map(({ b, cls, sel, text }) => {
    const p = S.world.screen(b.centroid[0], b.centroid[1], b.height_m + 4);
    if (!p.visible) return "";
    return `<div class="label ${cls} ${sel ? "selected" : ""}" data-id="${b.id}" style="left:${p.x}px;top:${p.y}px">${text}</div>`;
  }).join("");
  host.querySelectorAll(".label").forEach((el) => el.addEventListener("click", () => {
    const b = S.campus.buildings.find((x) => x.id === +el.dataset.id);
    selectBuilding({ kind: "campus", building: b });
  }));
}

// ---------------------------------------------------------------- building card
function selectBuilding(hit) {
  S.selected = hit;
  S.world.select(hit?.kind === "campus" ? hit.building.id : null);
  if (hit?.kind === "campus") S.world.flyTo({ target: hit.building.centroid, distance: 300, polar: 1.0, azimuth: -0.4, duration: 1.1 });
  renderBuilding(hit);
}

function renderBuilding(hit) {
  const card = $("building-card");
  if (!hit || !S.current.length || $("explainer").hidden === false) { card.hidden = true; return; }
  const r = S.current[0];
  const state = r.stateAt(player.t);
  let idx, title, rows, note;
  if (hit.kind === "campus") {
    const b = hit.building;
    const meta = r.data.buildings.find((x) => x.campus_id === b.id);
    idx = meta?.i;
    const kw = r.frameAt(player.t).k[r.data.campus_ids.indexOf(b.id)] ?? 0;
    title = `${esc(b.name || "Block " + b.id)}${b.verified ? "" : '<span class="badge">unverified</span>'}`;
    rows = [["Use", b.use], ["Floors", `${b.floors} · ${b.height_m} m`], ["Floor area", `${b.floor_area_m2.toLocaleString()} m²`],
      ["Benchmark", `${b.epi_kwh_m2_yr} kWh/m²/yr`], ["Annual energy", `${(b.annual_kwh / 1000).toFixed(0)} MWh`],
      ["Average demand", `${b.average_kw.toFixed(1)} kW`], ["Demand now", `${kw.toFixed(1)} kW`]];
    note = "Footprint from satellite imagery (Microsoft, ODbL). Energy from floor area × BEE benchmark. Name, use and floors are defaults until RVCE confirms them.";
  } else {
    idx = hit.fleetIndex;
    const meta = r.data.buildings[idx];
    title = esc(describeBuilding(r, S.campus, idx));
    rows = [["Type", meta.type.replace("_", " ")], ["Participates", meta.enrolled ? "yes" : "no"], ["Protected loads", meta.critical ? "yes" : "no"]];
    note = "A simulated household placed on a real footprint near the campus; its appliances are modelled, not surveyed.";
  }
  const s = idx != null ? state[idx] : 0;
  const status = [["", "Supplied"], ["curtailed", "Flexible appliance paused"], ["open", "Feeder cut by AUFLS"], ["protected", "Protected load on backup"]][s];
  card.innerHTML = `<button class="icon-btn close" aria-label="Close">✕</button><h3>${title}</h3>
    <div class="state"><span class="dot ${status[0]}"></span>${status[1]}</div>
    <dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl><p class="note">${note}</p>`;
  card.querySelector(".close").addEventListener("click", () => selectBuilding(null));
  card.hidden = false;
}

// ---------------------------------------------------------------- explainer
function openDecision(d, r) {
  S.decisionShown = d;
  $("building-card").hidden = true;
  $("explainer").hidden = false;
  renderDecision($("ex-body"), $("ex-title"), d, r, S.campus);
  const first = (d.chosen?.[0]?.building ?? d.buildings?.[0]);
  const meta = first != null ? r.data.buildings[first] : null;
  if (meta?.campus_id != null) {
    const b = S.campus.buildings.find((x) => x.id === meta.campus_id);
    if (b) S.world.flyTo({ target: b.centroid, distance: 340, polar: 0.98, azimuth: -0.35, duration: 1.2 });
  }
}
$("ex-close").addEventListener("click", () => { $("explainer").hidden = true; S.decisionShown = null; });

// ---------------------------------------------------------------- story
function kpiHtml(list) {
  return list.map(([k, v, cls]) => `<div class="kpi ${cls || ""}"><div class="v">${v}</div><div class="k">${k}</div></div>`).join("");
}

function renderStoryKpis(t) {
  const scene = SCENES[S.sceneIndex];
  if (scene.results || !scene.kpis || !S.current.length) return;
  const r = S.current[0];
  const c = { ...r.countersAt(t), f: r.frameAt(t).f, r: r.frameAt(t).r };
  $("story-kpis").innerHTML = kpiHtml(scene.kpis(c));
}

async function showScene(i) {
  S.sceneIndex = Math.max(0, Math.min(SCENES.length - 1, i));
  const scene = SCENES[S.sceneIndex];
  $("explainer").hidden = true;
  $("story-step").textContent = `${S.sceneIndex + 1} / ${SCENES.length} · ${scene.step}`;
  $("story-title").textContent = scene.title;
  $("story-prev").disabled = S.sceneIndex === 0;
  $("story-next").textContent = S.sceneIndex === SCENES.length - 1 ? "Explore yourself" : "Next";
  $("story-dots").innerHTML = SCENES.map((_, k) => `<button aria-label="Scene ${k + 1}" ${k === S.sceneIndex ? 'aria-current="true"' : ""} data-k="${k}"></button>`).join("");
  $("story-dots").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => showScene(+b.dataset.k)));
  $("story-kpis").innerHTML = "";
  $("story-body").innerHTML = scene.body(S.summary);
  S.world.flyTo(scene.camera);
  if (scene.results) {
    setSplit(null);
    if (S.summary) {
      const o = overall(S.summary);
      $("story-kpis").innerHTML = kpiHtml([
        ["customers affected per event, Rakshak", o.np_mrd.customers.toFixed(1), "good"],
        ["with AUFLS alone", o.ufls.customers.toFixed(1), "bad"],
        ["AUFLS stages per event, Rakshak", o.np_mrd.stages.toFixed(2), "good"],
        ["with a slow network, hybrid", (S.summary.E2_means.filter((r) => r.policy === "hybrid").reduce((m, r) => Math.max(m, r.ufls_stages_tripped), 0)).toFixed(2), "good"],
      ]);
    }
    return;
  }
  const replays = scene.compare ? await Promise.all(scene.compare.map(replay)) : [await replay(scene.replay)];
  if (SCENES[S.sceneIndex] !== scene) return;
  setSplit(scene.compare ? scene.compare : null);
  load(replays);
  player.seek(scene.from);
  if (scene.to > scene.from) {
    player.speed = scene.to - scene.from < 4 ? 1 : +$("tl-speed").value;
    player.onStop = () => {
      player.speed = +$("tl-speed").value;
      if (scene.openFirstDecision) {
        const d = replays[0].data.decisions.find((x) => x.kind === "shed");
        if (d) openDecision(d, replays[0]);
      }
    };
    setTimeout(() => player.play(scene.to), 900);
  }
}
$("story-prev").addEventListener("click", () => showScene(S.sceneIndex - 1));
$("story-next").addEventListener("click", () => (S.sceneIndex === SCENES.length - 1 ? (location.hash = "#explore") : showScene(S.sceneIndex + 1)));

function setSplit(presets) {
  const on = !!presets;
  $("split-divider").hidden = !on;
  if (on) { $("tag-left").textContent = PRESET_LABEL[presets[0]]; $("tag-right").textContent = PRESET_LABEL[presets[1]]; }
  S.world.setSplit(on ? {} : null);
}

// ---------------------------------------------------------------- compare
function fillCompare() {
  for (const [id, k] of [["cmp-left", 0], ["cmp-right", 1]]) {
    const sel = $(id);
    sel.innerHTML = Object.entries(PRESET_LABEL).map(([v, l]) => `<option value="${v}" ${S.cmp[k] === v ? "selected" : ""}>${l}</option>`).join("");
    sel.onchange = () => { S.cmp[k] = sel.value; startCompare(); };
  }
}

async function startCompare() {
  const replays = await Promise.all(S.cmp.map(replay));
  setSplit(S.cmp);
  load(replays);
  player.seek(4);
  player.play();
}

function renderCompare(t) {
  if (S.mode !== "compare" && !(S.mode === "story" && SCENES[S.sceneIndex].compare)) return;
  const [a, b] = S.current;
  const ca = a.countersAt(t), cb = b.countersAt(t);
  const rows = [["Customers affected", ca.affected, cb.affected, true], ["Feeder blocks cut now", ca.cut, cb.cut, true],
    ["AUFLS stages", ca.stages, cb.stages, true], ["Lowest frequency (Hz)", ca.fmin.toFixed(3), cb.fmin.toFixed(3), false]];
  const cls = (x, y, lower) => (+x === +y ? "" : (lower ? +x < +y : +x > +y) ? "better" : "worse");
  if (S.mode === "compare") {
    $("cmp-kpis").innerHTML = `<div class="h"></div><div class="h v">${esc(PRESET_LABEL[S.cmp[0]])}</div><div class="h v">${esc(PRESET_LABEL[S.cmp[1]])}</div>` +
      rows.map(([k, x, y, lower]) => `<div>${k}</div><div class="v ${cls(x, y, lower)}">${x}</div><div class="v ${cls(y, x, lower)}">${y}</div>`).join("");
    lineChart($("cmp-chart"), { height: 190, xLabel: "s", yLabel: "Hz", x0: 0, x1: Math.min(90, a.duration), cursor: t,
      series: [{ points: a.frames.filter((f) => f.t <= 90).map((f) => [f.t, f.f]), color: css("--faint"), label: "Left" },
               { points: b.frames.filter((f) => f.t <= 90).map((f) => [f.t, f.f]), color: css("--accent"), label: "Right" }],
      refs: [{ y: 49.4, label: "AUFLS", color: css("--open") }] });
  } else {
    $("story-kpis").innerHTML = kpiHtml([
      ["Left: customers affected", ca.affected, ca.stages ? "bad" : ""], ["Right: customers affected", cb.affected, "good"],
      ["Left: AUFLS stages", ca.stages, ca.stages ? "bad" : "good"], ["Right: AUFLS stages", cb.stages, cb.stages ? "bad" : "good"]]);
  }
}

// ---------------------------------------------------------------- explore
for (const [id, fmt] of Object.entries({ "x-loss": (v) => `${(+v).toFixed(1)} %`, "x-H": (v) => `${(+v).toFixed(1)} s`,
  "x-part": (v) => `${v} %`, "x-lat": (v) => `${(+v).toFixed(2)} s`, "x-pl": (v) => `${v} %` })) {
  const input = $(id), out = $("o-" + id);
  const sync = () => (out.textContent = fmt(input.value));
  input.addEventListener("input", sync); sync();
}
$("x-run").addEventListener("click", async () => {
  const lat = +$("x-lat").value;
  const scenario = { mode: $("x-mode").value, generation_loss: +$("x-loss").value / 100, grid_inertia_h: +$("x-H").value,
    mechanical_gain: +$("x-km").value, participation: +$("x-part").value / 100, comm_latency_s: lat, comm_jitter_s: lat / 2,
    comm_loss: +$("x-pl").value / 100, campus: true, campus_aufls_stage1: $("x-feeder").checked, t_recover: 60, seed: 42 };
  busy(true, "Simulating 270 s of grid time…");
  $("x-run").disabled = true;
  try {
    const r = new Replay(await fetchJSON("/api/replay", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(scenario) }));
    setSplit(null);
    load([r]);
    player.seek(4); player.play();
  } catch (err) {
    $("x-kpis").innerHTML = `<dt>Error</dt><dd>${esc(err.message)}</dd>`;
  } finally { busy(false); $("x-run").disabled = false; }
});

function renderExploreKpis(t) {
  const r = S.current[0];
  if (!r) return;
  const c = r.countersAt(t), m = r.data.metrics;
  $("x-kpis").innerHTML = [["Lowest frequency", `${c.fmin.toFixed(3)} Hz`], ["AUFLS stages", c.stages], ["Customers affected", c.affected],
    ["Feeder blocks cut now", c.cut], ["Appliances paused now", c.paused], ["Critical energy lost (run)", `${m.critical_energy_not_served_wh.toFixed(2)} Wh`],
    ["Deferred energy (run)", `${(m.total_unserved_wh / 1000).toFixed(2)} kWh`]].map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}

// ---------------------------------------------------------------- routing
async function route() {
  const mode = (location.hash || "#story").slice(1);
  S.mode = ["story", "compare", "explore", "results", "methods"].includes(mode) ? mode : "story";
  document.querySelectorAll(".modes a").forEach((a) => { if (a.dataset.mode === S.mode) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  const page = S.mode === "results" || S.mode === "methods";
  document.body.classList.toggle("page-mode", page);
  $("page-results").hidden = S.mode !== "results";
  $("page-methods").hidden = S.mode !== "methods";
  for (const p of ["story", "compare", "explore"]) $("panel-" + p).hidden = S.mode !== p;
  $("explainer").hidden = true;
  player.pause();
  if (S.mode === "results") renderResults($("page-results"), S.summary, S.calibration);
  if (S.mode === "methods") renderMethods($("page-methods"));
  if (!S.world) return;
  if (S.mode === "story") showScene(S.sceneIndex);
  if (S.mode === "compare") { fillCompare(); startCompare(); }
  if (S.mode === "explore") { setSplit(null); load([await replay("hybrid")]); }
}
window.addEventListener("hashchange", route);

// ---------------------------------------------------------------- theme
function applyTheme(mode) {
  if (mode === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = mode;
  try { localStorage.setItem("rakshak.theme", mode); } catch (_) { /* storage unavailable */ }
  $("theme").title = `Theme: ${mode}`;
  if (S.current.length) render(player.t, S.current);
  if (S.mode === "results") renderResults($("page-results"), S.summary, S.calibration);
}
$("theme").addEventListener("click", () => {
  let mode = "system";
  try { mode = localStorage.getItem("rakshak.theme") || "system"; } catch (_) { /* default */ }
  const order = ["system", "light", "dark"];
  applyTheme(order[(order.indexOf(mode) + 1) % order.length]);
});

// ---------------------------------------------------------------- tools
function clock(h) { const hh = Math.floor(h), mm = Math.round((h - hh) * 60); return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`; }
$("tod").addEventListener("input", () => { $("o-tod").textContent = clock(+$("tod").value); S.world?.setTimeOfDay(+$("tod").value); });
$("cam-orbit").addEventListener("click", () => S.world.flyTo({ target: [70, -20], distance: 760, polar: 0.92, azimuth: -0.72 }));
$("cam-plan").addEventListener("click", () => S.world.flyTo({ target: [70, -20], distance: 980, polar: 0.05, azimuth: 0 }));

// ---------------------------------------------------------------- boot
async function boot() {
  renderMethods($("page-methods"));
  [S.summary, S.calibration] = await Promise.all([
    fetchJSON("/api/paper-results").catch(() => null), fetchJSON("/api/calibration").catch(() => []),
  ]);
  S.campus = await fetchJSON("/api/campus");
  S.world = new World($("world"), S.campus);
  S.world.onPick = (hit) => selectBuilding(hit);
  S.world.onFrame = placeLabels;
  S.world.flyTo({ target: [70, -20], distance: 760, polar: 0.92, azimuth: -0.72, duration: 0.01 });
  await route();
}
boot().catch((err) => { busy(true, "Could not start: " + err.message); });
