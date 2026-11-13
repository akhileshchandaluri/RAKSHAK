"use strict";

const RakshakBenchmarks = (() => {
  const dash = "—";
  const rows = [
    ["Critical energy unserved", r => r.critical_energy_not_served_wh.toFixed(2) + " Wh", -1],
    ["Total service energy unserved", r => r.total_unserved_wh.toFixed(2) + " Wh", -1],
    ["Frequency nadir", r => r.nadir.toFixed(3) + " Hz", 1],
    ["Peak frequency", r => r.zenith.toFixed(3) + " Hz", -1],
    ["Maximum |RoCoF|", r => r.max_rocof.toFixed(3) + " Hz/s", -1],
    ["Settled frequency recovery", r => r.recovery_time === null ? dash : r.recovery_time.toFixed(1) + " s"],
    ["Energy served by protected-facility backup", r => r.backup_energy_wh.toFixed(2) + " Wh"],
    ["Largest unmet relief request", r => r.relief_shortfall_kw.toFixed(2) + " kW"],
    ["Longest appliance pause", r => r.longest_device_pause_s.toFixed(1) + " s"],
    ["Medical device-minutes offline", r => r.medical_minutes_lost.toFixed(2), -1],
    ["AUFLS block trips", r => String(r.feeder_trips), -1],
    ["Peak demand after reconnection", r => r.peak_post_shed_load ? (100 * r.peak_post_shed_load).toFixed(1) + "%" : dash],
    ["Modeled collapse", r => r.collapsed ? "Yes" : "No", -1],
  ];

  async function run(scenario, signal) {
    const response = await fetch("api/benchmark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(scenario),
      signal,
    });
    if (!response.ok) { const body = await response.json(); throw new Error(typeof body.detail === "string" ? body.detail : "Invalid benchmark request"); }
    return (await response.json()).results;
  }

  function render(tableBody, results) {
    const reference = results.find(result => result.mode === "ufls");
    const rakshak = results.find(result => result.mode === "rakshak");
    tableBody.replaceChildren(...rows.map(([label, format, direction]) => {
      const tr = document.createElement("tr");
      const heading = document.createElement("th");
      heading.scope = "row";
      heading.textContent = label;
      tr.append(heading);
      for (const result of results) {
        const td = tr.insertCell();
        const value = format(result);
        td.textContent = value;
        const comparator = result.mode === "rakshak" ? reference : rakshak;
        if (!direction || !comparator) continue;
        const score = formatted => formatted === "Yes" ? 1 : formatted === "No" ? 0 : Number.parseFloat(formatted);
        const delta = direction * (score(value) - score(format(comparator)));
        const improvement = result.mode === "rakshak";
        if (!Number.isFinite(delta) || (improvement ? delta <= 0 : delta >= 0)) continue;
        td.style.color = improvement ? "#86efac" : "#fda4af";
        td.style.fontWeight = "700";
        td.append(improvement ? " · Better" : " · Trails Rakshak");
      }
      return tr;
    }));
  }

  return { run, render };
})();
