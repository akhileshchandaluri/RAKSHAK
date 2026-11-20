import { barChart, lineChart, palette } from "./charts.js";

const POLICY = { ufls: "AUFLS only", rakshak: "Original heuristic", edge: "Edge relays", np_mrd: "NP-MRD", hybrid: "Hybrid" };
let cache = null;

export async function renderLab(root) {
  if (!cache) {
    try {
      const [res, cal] = await Promise.all([fetch("/api/paper-results"), fetch("/api/calibration")]);
      if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
      cache = { summary: await res.json(), calibration: cal.ok ? await cal.json() : [] };
    } catch (err) {
      root.innerHTML = `<p class="empty">Experiment results are not available yet (${err.message}). Run <code>python -B benchmarks/paper_experiments.py</code>.</p>`;
      return;
    }
  }
  const { summary, calibration } = cache;
  const c = palette();
  const keys = Object.keys(POLICY).map((k, i) => ({ key: k, label: POLICY[k], color: [c.muted, "#c9a26b", c.protected, c.accent, c.ok][i] }));
  root.innerHTML = `
    <p class="lede">Results from <code>benchmarks/paper_experiments.py</code>: ${summary.E1_means.reduce((n, r) => n + r.n, 0)} main-comparison runs,
      270 simulated seconds each, governor gain calibrated to Indian events (K<sub>m</sub> = ${summary.protocol.calibrated_mechanical_gain}).
      Means over seeds; seeds index modelled variation, not field uncertainty.</p>
    <article class="card wide"><header><h3>Customers interrupted, full enrollment</h3><span class="meta">mean per run · H (s) / contingency</span></header><canvas class="chart" id="lab-customers"></canvas></article>
    <article class="card"><header><h3>AUFLS stages operated</h3><span class="meta">mean per run, all cases</span></header><canvas class="chart" id="lab-aufls"></canvas></article>
    <article class="card"><header><h3>Critical energy not served</h3><span class="meta">Wh per run, all cases</span></header><canvas class="chart" id="lab-ens"></canvas></article>
    <article class="card"><header><h3>Communication latency, 40 % packet loss</h3><span class="meta">customers interrupted · H 3 s, 5 %</span></header><canvas class="chart" id="lab-comm"></canvas></article>
    <article class="card"><header><h3>Communication latency, 40 % packet loss</h3><span class="meta">AUFLS stages operated</span></header><canvas class="chart" id="lab-comm-aufls"></canvas></article>
    <article class="card"><header><h3>Protection margin trade-off (NP-MRD)</h3><span class="meta">margin above 49.40 Hz</span></header><canvas class="chart" id="lab-margin"></canvas></article>
    <article class="card"><header><h3>Inertia estimate error (NP-MRD)</h3><span class="meta">operator H error</span></header><canvas class="chart" id="lab-inertia"></canvas></article>
    <article class="card wide"><header><h3>Paired differences across all main-comparison cases</h3><span class="meta">challenger − baseline · 95 % t interval · Wilcoxon signed-rank p</span></header><div id="lab-paired"></div></article>
    <article class="card wide"><header><h3>Calibration to Indian events (leave one event out)</h3><span class="meta">reported nadirs: Rajasthan 49.40 Hz, Khavda 49.39 Hz</span></header><div id="lab-cal"></div></article>`;

  const e1 = summary.E1_means;
  const cases = [...new Set(e1.filter((r) => r.enrollment === 1).map((r) => `${r.H}|${r.loss}`))];
  barChart(document.getElementById("lab-customers"), {
    keys, yLabel: "customers",
    groups: cases.map((k) => { const [H, loss] = k.split("|"); return {
      label: `${H} s / ${(loss * 100).toFixed(1)} %`,
      values: e1.filter((r) => r.enrollment === 1 && r.H == H && r.loss == loss).map((r) => ({ key: r.policy, value: r.customers_interrupted })) }; }),
  });
  const overall = (metric) => [{ label: "all main-comparison cases", values: keys.map((k) => {
    const rows = e1.filter((r) => r.policy === k.key);
    return { key: k.key, value: rows.reduce((sum, r) => sum + r[metric], 0) / Math.max(rows.length, 1) };
  }) }];
  barChart(document.getElementById("lab-aufls"), { keys, groups: overall("ufls_stages_tripped"), yLabel: "stages" });
  barChart(document.getElementById("lab-ens"), { keys, groups: overall("critical_energy_not_served_wh"), yLabel: "Wh" });

  const e2 = summary.E2_means.filter((r) => r.comm_loss === 0.4);
  for (const [id, metric] of [["lab-comm", "customers_interrupted"], ["lab-comm-aufls", "ufls_stages_tripped"]]) {
    lineChart(document.getElementById(id), { xLabel: "latency (s)", yLabel: metric === "ufls_stages_tripped" ? "stages" : "customers",
      series: ["np_mrd", "hybrid"].map((p, i) => ({ label: POLICY[p], color: [c.accent, c.ok][i],
        points: e2.filter((r) => r.policy === p).map((r) => [r.comm_latency_s, r[metric]]).sort((a, b) => a[0] - b[0]) })) });
  }
  const e3 = summary.E3_means;
  lineChart(document.getElementById("lab-margin"), { xLabel: "margin (Hz)", yLabel: "customers / stages",
    series: [{ label: "Customers interrupted", color: c.accent, points: e3.map((r) => [r.margin_hz, r.customers_interrupted]) },
             { label: "AUFLS stages", color: c.crit, points: e3.map((r) => [r.margin_hz, r.ufls_stages_tripped]) }] });
  const e4 = summary.E4_means;
  lineChart(document.getElementById("lab-inertia"), { xLabel: "H error (fraction)", yLabel: "customers / stages",
    series: [{ label: "Customers interrupted", color: c.accent, points: e4.map((r) => [r.inertia_error, r.customers_interrupted]) },
             { label: "AUFLS stages", color: c.crit, points: e4.map((r) => [r.inertia_error, r.ufls_stages_tripped]) }] });

  const paired = summary.E1_paired;
  const metrics = ["customers_interrupted", "ufls_stages_tripped", "critical_energy_not_served_wh", "total_unserved_wh", "nadir"];
  document.getElementById("lab-paired").innerHTML = `<table class="data"><thead><tr><th>Comparison</th>${metrics.map((m) => `<th>${m.replaceAll("_", " ")}</th>`).join("")}</tr></thead><tbody>${
    Object.entries(paired).map(([name, row]) => `<tr><td>${name.replace("_vs_", " vs ").replaceAll("np_mrd", "NP-MRD").replaceAll("ufls", "AUFLS").replaceAll("rakshak", "heuristic")}</td>${
      metrics.map((m) => { const r = row[m]; return `<td>${r ? `${r.mean_difference}<br><span class="fine">[${r.ci95.join(", ")}]${r.wilcoxon_p != null ? ` p=${r.wilcoxon_p.toExponential(1)}` : ""}</span>` : "—"}</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;
  document.getElementById("lab-cal").innerHTML = calibration.length ? `<table class="data"><thead><tr><th>Base (GW)</th><th>H (s)</th><th>Fitted on</th><th>K<sub>m</sub></th><th>Fit error (Hz)</th><th>Tested on</th><th>Test error (Hz)</th><th>Textbook K<sub>m</sub> error (Hz)</th></tr></thead><tbody>${
    calibration.map((r) => `<tr><td>${r.assumed_base_mw / 1000}</td><td>${r.assumed_H_s}</td><td>${r.fit_event}</td><td>${r.fitted_mechanical_gain}</td><td>${r.fit_nadir_error_hz}</td><td>${r.test_event}</td><td>${r.test_nadir_error_hz}</td><td>${r.default_gain_test_error_hz}</td></tr>`).join("")}</tbody></table>
    <p class="fine">Both reported nadirs were arrested by AUFLS near 49.4 Hz, so the events bound the governor gain from above rather than identify it exactly. Fits at K<sub>m</sub> = 0.02 sit on the search bound.</p>` : "";
}

