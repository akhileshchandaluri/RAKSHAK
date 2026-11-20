import { barChart, lineChart } from "./svgcharts.js";

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
export const POLICY = { ufls: "AUFLS only", rakshak: "Threshold rule", edge: "Local relays", np_mrd: "Rakshak predictive", hybrid: "Rakshak hybrid" };

export function policyColors() {
  return { ufls: css("--faint"), rakshak: "#c9a26b", edge: css("--protected"), np_mrd: css("--accent"), hybrid: css("--ok") };
}

export function overall(summary) {
  const out = {};
  for (const p of Object.keys(POLICY)) {
    const rows = summary.E1_means.filter((r) => r.policy === p);
    const mean = (m) => rows.reduce((s, r) => s + r[m], 0) / Math.max(rows.length, 1);
    out[p] = { customers: mean("customers_interrupted"), stages: mean("ufls_stages_tripped"),
               ens: mean("critical_energy_not_served_wh"), deferred: mean("total_unserved_wh") / 1000, nadir: mean("nadir") };
  }
  return out;
}

export function renderResults(host, summary, calibration) {
  if (!summary) { host.innerHTML = `<div class="wrap"><h1>Results</h1><p class="lede">Experiment results are not available yet. Run <code>python -B benchmarks/paper_experiments.py</code>.</p></div>`; return; }
  const o = overall(summary);
  const colors = policyColors();
  const keys = Object.keys(POLICY).map((k) => ({ key: k, label: POLICY[k], color: colors[k] }));
  const runs = summary.E1_means.reduce((s, r) => s + r.n, 0);
  const pairedNp = summary.E1_paired.np_mrd_vs_ufls.customers_interrupted;
  const calMax = calibration.length ? Math.max(...calibration.map((r) => Math.abs(r.test_nadir_error_hz))) : null;
  host.innerHTML = `<div class="wrap">
    <h1>Results</h1>
    <p class="lede">${runs} paired simulations of 270 s each, over grid inertia, event size, participation and random
      households, with the governor response calibrated to Indian events. Means across runs; the spread reflects modelled
      variation, not field uncertainty.</p>
    <div class="headline">
      <div class="box"><div class="v">${o.np_mrd.customers.toFixed(1)}</div><div class="k">customers affected per event with Rakshak, vs ${o.ufls.customers.toFixed(1)} with AUFLS alone</div></div>
      <div class="box"><div class="v">${o.np_mrd.stages.toFixed(2)}</div><div class="k">AUFLS stages per event with Rakshak, vs ${o.ufls.stages.toFixed(2)}</div></div>
      <div class="box"><div class="v">${o.np_mrd.ens.toFixed(1)} Wh</div><div class="k">critical energy lost with Rakshak, vs ${o.ufls.ens.toFixed(2)} Wh</div></div>
      <div class="box"><div class="v">${calMax != null ? calMax.toFixed(3) + " Hz" : "—"}</div><div class="k">largest error predicting the held-out Indian event's lowest frequency</div></div>
    </div>
    <div class="grid2">
      <div class="box wide"><h2>Customers affected per event</h2><div class="sub">Full participation; inertia H and event size on the axis</div><div class="chart" id="r-cust"></div></div>
      <div class="box"><h2>Slow and lossy networks</h2><div class="sub">AUFLS stages operated vs command delay, 40 % packet loss</div><div class="chart" id="r-comm"></div></div>
      <div class="box"><h2>Safety margin trade-off</h2><div class="sub">Rakshak predictive: margin above 49.40 Hz</div><div class="chart" id="r-margin"></div></div>
      <div class="box wide"><h2>Paired differences</h2><div class="sub">Challenger minus baseline over identical events · 95 % interval · Wilcoxon signed-rank p</div><div id="r-paired"></div></div>
      <div class="box wide"><h2>Calibration to Indian events</h2><div class="sub">Fit the governor gain on one event, test on the other</div><div id="r-cal"></div></div>
    </div>
    <p class="muted" style="margin-top:18px">Paired Rakshak − AUFLS difference in customers affected: ${pairedNp.mean_difference.toFixed(1)}
      [${pairedNp.ci95.map((v) => v.toFixed(1)).join(", ")}], p = ${pairedNp.wilcoxon_p?.toExponential(1)}.</p>
  </div>`;
  const rows = summary.E1_means.filter((r) => r.enrollment === 1);
  const cases = [...new Set(rows.map((r) => `${r.H}|${r.loss}`))].sort((a, b) => b.split("|")[0] - a.split("|")[0] || a.split("|")[1] - b.split("|")[1]);
  barChart(host.querySelector("#r-cust"), { keys, yLabel: "customers",
    groups: cases.map((c) => { const [H, loss] = c.split("|"); return { label: `H ${H} s\n${(loss * 100).toFixed(1)} %`,
      values: Object.fromEntries(rows.filter((r) => `${r.H}|${r.loss}` === c).map((r) => [r.policy, r.customers_interrupted])) }; }) });
  const e2 = summary.E2_means.filter((r) => r.comm_loss === Math.max(...summary.E2_means.map((x) => x.comm_loss)));
  lineChart(host.querySelector("#r-comm"), { xLabel: "delay (s)", yLabel: "stages", height: 220,
    series: ["np_mrd", "hybrid"].map((p) => ({ label: POLICY[p], color: colors[p],
      points: e2.filter((r) => r.policy === p).map((r) => [r.comm_latency_s, r.ufls_stages_tripped]).sort((a, b) => a[0] - b[0]) })) });
  const e3 = summary.E3_means.slice().sort((a, b) => a.margin_hz - b.margin_hz);
  lineChart(host.querySelector("#r-margin"), { xLabel: "margin (Hz)", yLabel: "customers", height: 220,
    series: [{ label: "Customers affected", color: colors.np_mrd, points: e3.map((r) => [r.margin_hz, r.customers_interrupted]) }] });
  const metrics = [["customers_interrupted", "Customers"], ["ufls_stages_tripped", "AUFLS stages"], ["critical_energy_not_served_wh", "Critical Wh"], ["total_unserved_wh", "Deferred Wh"]];
  const f = (v) => Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(3);
  host.querySelector("#r-paired").innerHTML = `<table class="data"><thead><tr><th>Comparison</th>${metrics.map((m) => `<th>${m[1]}</th>`).join("")}</tr></thead><tbody>${
    Object.entries(summary.E1_paired).map(([name, row]) => `<tr><td>${name.split("_vs_").map((p) => POLICY[p] || p).join(" vs ")}</td>${
      metrics.map(([m]) => { const r = row[m]; return `<td>${r ? `${f(r.mean_difference)} <span class="muted">[${r.ci95.map(f).join(", ")}]</span>` : "—"}</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;
  host.querySelector("#r-cal").innerHTML = calibration.length ? `<table class="data"><thead><tr><th>Fitted on</th><th>Base (GW)</th><th>H (s)</th><th>Gain</th><th>Tested on</th><th>Test error (Hz)</th><th>Textbook error (Hz)</th></tr></thead><tbody>${
    calibration.map((r) => `<tr><td>${r.fit_event}</td><td>${r.assumed_base_mw / 1000}</td><td>${r.assumed_H_s}</td><td>${r.fitted_mechanical_gain}</td><td>${r.test_event}</td><td>${r.test_nadir_error_hz}</td><td>${r.default_gain_test_error_hz}</td></tr>`).join("")}</tbody></table>
    <p class="muted">Both observed lowest frequencies were stopped by AUFLS near 49.4 Hz, so the events bound the governor gain from above rather than pin it down.</p>` : "";
}
