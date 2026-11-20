import { lineChart } from "./svgcharts.js";

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const KIND_LABEL = {
  shed: "Appliance relief", restore: "Reconnection", aufls: "AUFLS feeder trip", local_trip: "Pre-armed local trip",
};

export function describeBuilding(replay, campus, index) {
  const meta = replay.data.buildings[index];
  if (meta?.campus_id != null) return `Campus block ${meta.campus_id}`;
  return `Home ${index}${meta && meta.type !== "house" ? ` (${meta.type.replace("_", " ")})` : ""}`;
}

/** Render one decision record into the explainer drawer. */
export function renderDecision(host, titleEl, d, replay, campus) {
  const step = (n, title, html) => `<div class="ex-step"><span class="n">${n}</span><div><h3>${title}</h3>${html}</div></div>`;
  titleEl.textContent = `${KIND_LABEL[d.kind] || d.kind} at ${d.t.toFixed(1)} s`;
  if (d.kind === "shed" && d.traj_without) {
    const rows = d.chosen.map((c) => `<tr><td>${esc(describeBuilding(replay, campus, c.building))}<br><span class="tagline">${esc(c.appliance)}</span></td>
      <td class="n">${c.kw.toFixed(1)}</td><td>${c.new_customer ? "new" : "already paused"}</td>
      <td class="n">${c.deferred_kwh_bound.toFixed(2)}</td><td class="n">${c.comfort_risk ?? "—"}</td></tr>`).join("");
    host.innerHTML = `
      <p class="ex-lede">${esc(d.summary)}</p>
      ${step(1, "Measure", `<p>Frequency ${d.f.toFixed(3)} Hz, falling at ${Math.abs(d.rocof).toFixed(3)} Hz/s.</p>`)}
      ${step(2, "Estimate the shortfall", `<p>The swing equation, solved for the power imbalance, gives a net deficit of
        <strong>${d.deficit_kw.toFixed(0)} kW</strong> (${(d.deficit_pu * 100).toFixed(2)} % of demand).</p>`)}
      ${step(3, "Predict the next 20 seconds", `<p>The frequency model (with governor limits) predicts a minimum of
        <strong>${d.predicted_min_without.toFixed(3)} Hz</strong> if nothing is done, and
        <strong>${d.predicted_min_with.toFixed(3)} Hz</strong> with the chosen relief.</p><div class="chart" id="ex-chart"></div>`)}
      ${step(4, "Ask for the minimum relief", `<p>Smallest relief keeping the predicted minimum at or above ${d.target_hz.toFixed(2)} Hz:
        <strong>${d.relief_requested_kw.toFixed(1)} kW</strong>; ${d.relief_delivered_kw.toFixed(1)} kW delivered.
        ${d.delay_s ? `Planned with a ${d.delay_s.toFixed(2)} s command delay.` : ""}</p>`)}
      ${step(5, "Choose who supplies it", `<p>${d.eligible_appliances} eligible appliances in ${d.eligible_customers} consenting homes
        (${d.eligible_kw.toFixed(0)} kW). Ranked by fewest new customers, then least guaranteed deferred energy
        (power × minimum off time), then most comfort slack. Critical and essential loads are never candidates.</p>
        <table class="picks"><thead><tr><th>Where</th><th>kW</th><th>Customer</th><th>kWh min.</th><th>Comfort</th></tr></thead><tbody>${rows}</tbody></table>`)}
      ${step(6, "What it avoided", `<p>${esc(d.counterfactual)}</p>`)}`;
    const c = { pred: css("--predict"), open: css("--open"), cur: css("--curtailed"), faint: css("--faint") };
    const sx = (arr) => arr.map((f, i) => [d.t + i * d.traj_step_s, f]);
    const actual = replay.frames.filter((f) => f.t >= d.t && f.t <= d.t + 20).map((f) => [f.t, f.f]);
    lineChart(host.querySelector("#ex-chart"), {
      series: [
        { points: sx(d.traj_without), color: c.open, label: "Predicted, no action", dash: "5 4" },
        { points: sx(d.traj_with), color: c.pred, label: "Predicted, with relief" },
        { points: actual, color: css("--text"), label: "What happened", width: 1.2 },
      ],
      refs: [{ y: 49.4, label: "AUFLS stage 1 · 49.40", color: c.open }, { y: d.target_hz, label: "", color: c.faint }],
      xLabel: "s", yLabel: "Hz", height: 190,
    });
    return;
  }
  if (d.kind === "local_trip") {
    const rows = d.chosen.map((c) => `<tr><td>${esc(describeBuilding(replay, campus, c.building))}<br><span class="tagline">${esc(c.appliance)}</span></td>
      <td class="n">${c.kw.toFixed(1)}</td><td class="n">${c.armed_rocof.toFixed(3)}</td></tr>`).join("");
    host.innerHTML = `
      <p class="ex-lede">${esc(d.summary)}</p>
      ${step(1, "Armed before the event", `<p>While the grid was normal, the controller computed, for each possible contingency size,
        the smallest set of appliances that keeps frequency above AUFLS, and sent each appliance the rate of fall it should react to.</p>`)}
      ${step(2, "Measured locally", `<p>Each appliance measured RoCoF itself: <strong>${d.rocof.toFixed(3)} Hz/s</strong>.</p>`)}
      ${step(3, "Acted without waiting", `<p>Appliances armed at a gentler rate switched off immediately. No message had to arrive, so
        a slow or lossy network could not delay them.</p>
        <table class="picks"><thead><tr><th>Where</th><th>kW</th><th>Armed at (Hz/s)</th></tr></thead><tbody>${rows}</tbody></table>`)}
      ${step(4, "Then refined centrally", `<p>The central predictor keeps watching and adds or returns relief as the event unfolds.</p>`)}`;
    return;
  }
  if (d.kind === "aufls") {
    const campusCut = d.buildings.filter((i) => replay.data.buildings[i]?.campus_id != null).length;
    host.innerHTML = `
      <p class="ex-lede">${esc(d.summary)}</p>
      ${step(1, "Fixed setting", `<p>Stage ${d.stage} relays trip when frequency is at or below ${d.threshold_hz.toFixed(1)} Hz
        (SRPC AUFLS settings). They do not know what is connected downstream.</p>`)}
      ${step(2, "Whole feeders open", `<p>${d.buildings.length} feeder blocks (${d.relief_kw.toFixed(0)} kW) disconnected${campusCut ? `, including ${campusCut} campus block(s)` : ""}.
        Everyone on them loses supply, whether they were running a geyser or a computer lab.</p>`)}
      ${step(3, "Restoration", `<p>Feeders return only after generation recovers and frequency is stable.</p>`)}`;
    return;
  }
  host.innerHTML = `<p class="ex-lede">${esc(d.summary || "")}</p>`;
}
