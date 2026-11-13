"use strict";

document.getElementById("run-field-check").addEventListener("click", async event => {
  const button = event.currentTarget;
  const status = document.getElementById("field-check-status");
  const body = document.getElementById("field-check-results");
  button.disabled = true;
  body.replaceChildren();
  status.textContent = "Running four simulations…";
  try {
    const response = await fetch("api/field-check");
    if (!response.ok) throw new Error("Could not run the historical comparison.");
    const { comparisons } = await response.json();
    for (const result of comparisons) {
      const row = body.insertRow();
      const source = document.createElement("a");
      source.href = result.source;
      source.textContent = result.name;
      row.insertCell().append(source);
      for (const value of [
        result.assumed_base_mw / 1000,
        result.initial_hz.toFixed(2),
        result.nadir_hz.toFixed(2),
        result.modeled_nadir_hz.toFixed(3),
        result.nadir_error_hz.toFixed(3),
        result.modeled_aufls_blocks,
      ]) {
        row.insertCell().textContent = value;
      }
    }
    status.textContent = "Positive error means the model predicted a shallower dip.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
