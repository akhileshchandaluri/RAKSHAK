// Methods page: every model, the source it comes from, and what is assumed.
export function renderMethods(root) {
  root.innerHTML = `
  <h2>What this twin is</h2>
  <p>A <strong>simulation-based digital twin</strong> of the RVCE campus inside a grid area of 500 modelled buildings.
  The physics, the controller and the campus loads run in the same Python engine used for the paper's experiments.
  It is not connected to RVCE meters yet: verified names, uses and floor counts go in
  <code>data/rvce/overrides.json</code>, and metered energy can replace the benchmark estimates. It does not claim to be a
  validated physical twin.</p>

  <h2>Grid frequency</h2>
  <p>Low-order System Frequency Response model with a reheat steam unit: P. M. Anderson and M. Mirheydar,
  “A low-order system frequency response model,” <em>IEEE Trans. Power Systems</em>, 5(3), 1990. Governor dead band
  and reserve limits are standard limiters. Integration: RK4, 50 ms. The closed-form nadir of that paper is checked
  against the integrated plant in <code>tests/test_research_core.py</code> to 0.001 Hz.</p>
  <p>Governor gain K<sub>m</sub> is fitted to two published Indian events (Rajasthan, 15 May 2023; Khavda, 13 May 2026)
  by leave-one-event-out calibration; textbook K<sub>m</sub> = 0.95 misses the reported nadirs by 0.32–0.43 Hz.</p>

  <h2>Reference protection</h2>
  <p>AUFLS stages 49.4/49.2/49.0/48.8 Hz with 5/6/7/7 % relief, from the SRPC task-force report of 27 March 2024,
  scaled to the modelled demand. Protected facilities are on exempt feeders. All policies share it.</p>

  <h2>Controllers compared</h2>
  <h3>NP-MRD (this work)</h3>
  <p>Estimates the net power deficit from the swing equation solved for imbalance (P. Kundur, <em>Power System Stability
  and Control</em>, 1994; T. Inoue et al., IEEE TPWRS 12(1), 1997), predicts the frequency trajectory with the same SFR
  model including limiters, and finds the smallest relief keeping the predicted minimum at or above AUFLS stage 1 plus a
  margin. Appliances are chosen by a covering 0/1 knapsack (HiGHS) with a lexicographic objective: fewest customers
  interrupted (the customer count of SAIFI, IEEE Std 1366-2022), then the least guaranteed deferred energy (power ×
  compressor lockout), then the most thermal or charging slack (priority stack, N. Lu, IEEE TSG 2012; least laxity,
  Xu, Pan, Tong, IEEE TAC 2016).</p>
  <h3>Hybrid (this work)</h3>
  <p>Arms nested minimum-relief sets for a ladder of contingency sizes in advance and lets each appliance trip locally on
  its own RoCoF measurement, as in special protection schemes (P. M. Anderson and B. K. LeReverend, IEEE TPWRS 11(3),
  1996). Central NP-MRD then refines over the impaired channel.</p>
  <h3>Baselines</h3>
  <p>AUFLS only; the original Rakshak heuristic; decentralised relays with distributed thresholds (A. Molina-García,
  F. Bouffard, D. S. Kirschen, IEEE TPWRS 26(1), 2011) with randomised reconnection.</p>

  <h2>Appliances and comfort</h2>
  <p>Ratings from the MePDCL consumption calculator and manufacturer data (see the evidence register). Thermal states
  use the first-order equivalent-thermal-parameter model with parameters of J. L. Mathieu, S. Koch, D. S. Callaway,
  IEEE TPWRS 28(1), 2013. Comfort is reported in degree-minutes outside the band. Fairness is Jain's index.</p>

  <h2>Campus model</h2>
  <ul>
    <li>Footprints: Microsoft Global ML Building Footprints, release 2026-02-03, ODbL 1.0. Machine-detected; no heights for this region.</li>
    <li>Campus membership, names, uses and floor counts are defaults until verified. Floors: 3 for footprints ≥ 300 m², else 2; 3.5 m per floor.</li>
    <li>Energy: floor area × BEE/UNDP-GEF benchmark EPI, Moderate zone (Institutes 129, Hospitals 247, Offices &lt;50 % AC 94 kWh/m²/yr), divided by 8760 h.</li>
    <li>Room AC is a declared 30 % of each block's average demand, as 2 kW units. Replace with RVCE sub-metering when available.</li>
    <li>Road corridor alignment is inferred from the elongated structure in the footprint data; carriageway width and streetlight spacing are illustrative.</li>
    <li>Sun position: NOAA GML general solar position equations; azimuth by Meeus (eq. 13.5). Streetlights switch at civil twilight.</li>
  </ul>

  <h2>Limits</h2>
  <p class="muted">Single-area frequency, no voltage or power flow. Two field events only, both arrested by AUFLS, so the
  governor gain is bounded rather than identified. Communication is a latency/loss abstraction. Campus loads are
  benchmark estimates. Results describe the model, not RVCE or a utility network.</p>

  <p><a href="evidence.html">Evidence register</a> · <a href="street.html">Original street view</a> ·
  <a href="appliances.html">Appliance requests</a> · <a href="reviewer.html">Reviewer</a></p>`;
}
