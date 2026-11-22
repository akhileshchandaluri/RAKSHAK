// Guided demonstration. Each scene names the replay(s) it plays, the time window, the
// camera, and the caption. Numbers in captions are read from the replays at run time.

// Oblique, low views so heights read as 3D (a near-vertical view looks like a flat photo).
const CAMPUS_VIEW = { target: [60, -40], distance: 600, polar: 1.12, azimuth: -0.72 };
const CLOSE_VIEW = { target: [40, -10], distance: 400, polar: 1.12, azimuth: -0.5 };

export const SCENES = [
  {
    id: "campus", step: "The twin",
    title: "RV College of Engineering, as a living model",
    replay: "aufls", from: 0, to: 0,
    camera: CAMPUS_VIEW,
    body: () => `
      <p>The campus outline, building names, floor counts, roads, metro line and the Vrishabhavati river come from
      OpenStreetMap and agree with the architects' campus key plan. Energy is calibrated to RVCE's NAAC-reported
      built-up area (67,721 m²) and hostel area (38,659 m²); the 500 kW rooftop solar sits on the eight buildings named
      in RVCE's BESCOM report.</p>
      <p>The surrounding streets carry 500 simulated homes, shops and clinics sharing this part of the grid.
      Click any building to see where each number comes from.</p>`,
  },
  {
    id: "trip", step: "The event",
    title: "A large power plant trips",
    replay: "aufls", from: 4, to: 6.6,
    camera: CAMPUS_VIEW,
    kpis: (c) => [["Frequency now", `${c.f.toFixed(3)} Hz`, c.f < 49.6 ? "warn" : ""], ["Falling at", `${Math.abs(c.r).toFixed(2)} Hz/s`, "warn"]],
    body: () => `
      <p>At 5 s, <strong>5 % of the region's generation is lost</strong>, about the size of the Rajasthan (2023) and
      Khavda (2026) events. Supply is suddenly short of demand, so grid frequency starts falling from 50 Hz.</p>
      <p>The grid's emergency brake is <strong>AUFLS</strong>: relays that cut whole feeders when frequency reaches
      49.4 Hz, then 49.2, 49.0 and 48.8 Hz.</p>`,
  },
  {
    id: "aufls", step: "Today",
    title: "Under-frequency load shedding cuts whole feeders",
    replay: "aufls", from: 6.6, to: 30,
    camera: CLOSE_VIEW,
    kpis: (c) => [["Lowest frequency", `${c.fmin.toFixed(3)} Hz`, c.fmin <= 49.4 ? "bad" : ""],
      ["AUFLS stages", c.stages, c.stages ? "bad" : ""], ["Campus blocks cut", c.campusCut, c.campusCut ? "bad" : ""],
      ["Customers interrupted", c.affected, c.affected ? "bad" : ""]],
    body: () => `
      <p>Frequency touches 49.4 Hz and the stage-1 relays open. <strong>Every building on those feeders goes dark</strong>,
      whatever it was running: lecture halls, labs, a hostel kitchen.</p>
      <p>The relays only see frequency. They cannot tell a geyser from a server room.</p>`,
  },
  {
    id: "threshold", step: "A simple fix",
    title: "A fixed threshold rule overreacts",
    replay: "threshold", from: 4, to: 40,
    camera: CAMPUS_VIEW,
    kpis: (c) => [["Customers paused", c.affected, c.affected > 5 ? "warn" : ""], ["AUFLS stages", c.stages, c.stages ? "bad" : "good"],
      ["Lowest frequency", `${c.fmin.toFixed(3)} Hz`, ""]],
    body: () => `
      <p>The obvious alternative is to switch off flexible appliances (air conditioners, geysers, EV chargers) as soon as
      frequency drops below 49.6 Hz, in proportion to how far it has fallen.</p>
      <p>It does stop AUFLS, but it <strong>pauses far more homes than needed</strong>, because it never asks how much
      relief protection actually requires. Frequency even overshoots above 50 Hz.</p>`,
  },
  {
    id: "npmrd", step: "Rakshak",
    title: "Predict the dip, then act with the minimum",
    replay: "npmrd", from: 4, to: 7, openFirstDecision: true,
    camera: CLOSE_VIEW,
    kpis: (c) => [["Customers paused", c.affected, c.affected <= 2 ? "good" : "warn"], ["AUFLS stages", c.stages, c.stages ? "bad" : "good"],
      ["Lowest frequency", `${c.fmin.toFixed(3)} Hz`, ""]],
    body: () => `
      <p>Within half a second Rakshak <strong>estimates the shortfall</strong> from how fast frequency is falling,
      <strong>predicts</strong> the next 20 seconds with a frequency model calibrated to Indian events, and asks for the
      <strong>smallest relief</strong> that keeps frequency above the AUFLS line.</p>
      <p>It then picks who supplies it: fewest homes first, then appliances that defer the least energy, then those with
      the most comfort slack. Hospitals, fridges and pumps are never touched. The panel on the right shows its reasoning.</p>`,
  },
  {
    id: "comms", step: "Real networks",
    title: "When commands arrive late, pre-arming keeps it working",
    compare: ["npmrd_comms", "hybrid_comms"], from: 4, to: 30,
    camera: CAMPUS_VIEW,
    body: () => `
      <p>Real smart-home links are slow and lossy. Here every command takes about 1.5 s to arrive and <strong>40 % are lost</strong>.</p>
      <p><strong>Left:</strong> central control alone reacts too late: frequency reaches 49.4 Hz, AUFLS trips, and more homes are affected.
      <strong>Right:</strong> Rakshak's hybrid sends each appliance, in advance, the rate of fall it should react to.
      They switch off locally within 0.25 s, with no message needed, and the central predictor refines afterwards.</p>`,
  },
  {
    id: "results", step: "Evidence",
    title: "Across hundreds of simulated events",
    results: true,
    camera: CAMPUS_VIEW,
    body: (r) => r ? `
      <p>Paired simulations over inertia, event size, participation and random seeds, with the governor response
      calibrated to the Rajasthan and Khavda events.</p>` : `<p>Run the experiments to show results here.</p>`,
  },
];
