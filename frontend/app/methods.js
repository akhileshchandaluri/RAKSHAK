// Methods page: what is new, every model and its source, and the assumptions.
export function renderMethods(root) {
  root.innerHTML = `<div class="wrap prose">
  <h1>Methods</h1>
  <p class="lede">A simulation-based digital twin of the RVCE campus and the grid area around it. The physics, the
  controllers and the campus loads run in the same Python engine used for the published experiments.</p>

  <h2>What is new in this work</h2>
  <ol>
    <li><strong>Minimum relief from a predicted dip.</strong> Every half second the controller estimates the power shortfall,
    predicts frequency for the next 20 s with a governor-limited frequency model, and asks for the smallest appliance
    relief that keeps frequency above the first AUFLS stage.</li>
    <li><strong>Customer-first choice of appliances.</strong> A covering knapsack picks who supplies that relief: fewest
    newly affected customers, then least guaranteed deferred energy (power × minimum off time), then most comfort slack.</li>
    <li><strong>Pre-armed, locally triggered relief.</strong> Before any event, nested appliance sets are computed for a
    ladder of contingency sizes; each appliance trips on its own rate-of-fall measurement, so slow or lossy networks
    do not delay the first response.</li>
    <li><strong>Calibrated to Indian events.</strong> The governor response is fitted to the Rajasthan (2023) and Khavda
    (2026) events and tested on the event it was not fitted to.</li>
  </ol>
  <p>Using appliances to avoid load shedding has been proposed before (e.g. Wang et al., <em>Energies</em> 2016); the
  contribution is the combination above. See <code>docs/literature_review.md</code>.</p>

  <h2>Models and sources</h2>
  <ul>
    <li>Grid frequency: reheat System Frequency Response model, P. M. Anderson and M. Mirheydar, IEEE TPWRS 5(3), 1990, with governor dead band and reserve limits; RK4 at 50 ms.</li>
    <li>Shortfall estimate: swing equation solved for imbalance (Kundur 1994; Terzija, IEEE TPWRS 2006).</li>
    <li>AUFLS reference: 49.4 / 49.2 / 49.0 / 48.8 Hz with 5 / 6 / 7 / 7 % relief, SRPC task force, 27 March 2024.</li>
    <li>Appliance selection: covering 0/1 knapsack (HiGHS); customers counted as in SAIFI, IEEE Std 1366-2022; comfort ordering by priority stack (N. Lu, IEEE TSG 2012) and EV laxity (Xu, Pan, Tong, IEEE TAC 2016).</li>
    <li>Pre-arming: structure of special protection schemes (Anderson and LeReverend, IEEE TPWRS 1996).</li>
    <li>Local relays baseline: Molina-García, Bouffard, Kirschen, IEEE TPWRS 2011.</li>
    <li>Room temperature: first-order thermal model with parameters of Mathieu, Koch, Callaway, IEEE TPWRS 2013.</li>
    <li>Campus outline, building names, floor counts, roads, metro line and river: OpenStreetMap contributors (ODbL). Checked against the ACE Group Architects campus key plan in RVCE's NAAC submission (Criterion 4.1.1), registered to satellite imagery.</li>
    <li>Buildings OpenStreetMap does not map: Microsoft Global ML Building Footprints (ODbL).</li>
    <li>Building energy: BEE/UNDP-GEF benchmarks, Moderate zone (Institutes 129, Hospitals 247 kWh/m²/yr), scaled so RVCE totals match the NAAC-reported built-up area (67,721 m²) and hostel area (38,659 m²).</li>
    <li>Rooftop solar: 500 kW on the eight buildings named in RVCE's BESCOM SRTPV commissioning report, shared by roof area.</li>
    <li>Photoreal view: Google Photorealistic 3D Tiles through Cesium ion. Model view ground: Esri World Imagery (Maxar, Earthstar Geographics).</li>
    <li>Sun position: NOAA Global Monitoring Laboratory equations; streetlights switch at civil twilight.</li>
  </ul>

  <h2>Assumptions</h2>
  <ul>
    <li>Floor counts not tagged in OpenStreetMap use a default per building type; floors are 3.5 m. Building use is read from the name.</li>
    <li>The OpenStreetMap outline covers the whole RV educational campus (about 49 acres); RVCE's own documents give 16.85 acres. Each building records its institution.</li>
    <li>Room AC is 30 % of each block's average demand. Demand uses annual averages; time of day changes lighting only.</li>
    <li>The 500 households are simulated and placed on the nearest real footprints.</li>
    <li>The option "campus on the AUFLS stage-1 feeder" is an assumption for the demonstration.</li>
    <li>In the model view, trees are placed where the satellite image is green; streetlights are drawn every 25 m along campus roads (spacing illustrative).</li>
    <li>Single-area frequency; no voltage or power-flow constraints. No field trial.</li>
  </ul>
  <p><a href="evidence.html">Evidence register</a> · <a href="appliances.html">Appliance requests</a> · <a href="reviewer.html">Reviewer</a> · <a href="street.html">Original street view</a></p>
  </div>`;
}
