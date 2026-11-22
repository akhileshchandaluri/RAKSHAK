# Project Rakshak

Rakshak is a simulation-based digital twin of the RV College of Engineering campus inside a modelled grid area. It is also the research testbed for a paper on **nadir-predictive, consent-constrained appliance relief beneath under-frequency load shedding (AUFLS)** in the Indian grid.

When a large generator trips, AUFLS opens whole feeders and interrupts everyone on them. Rakshak asks a narrower question: what is the **smallest** set of consenting households' flexible appliances whose curtailment keeps frequency above the first AUFLS stage? And does the answer survive slow or lossy communication?

## Results at a glance

All numbers come from `benchmarks/results/paper/summary.json`. The main comparison is 1,350 paired runs (10 seeds) with the governor gain calibrated to Indian events.

| Policy | Customers interrupted per event | AUFLS stages | Critical energy not served (Wh) |
|---|---|---|---|
| AUFLS only | 11.1 | 0.56 | 1.73 |
| Original heuristic | 12.8 | 0 | 0 |
| Edge relays | 11.6 | 0 | 0 |
| **NP-MRD** | **1.1** | **0** | **0** |
| **Hybrid (pre-armed)** | **1.4** | **0** | **0** |

- **NP-MRD against AUFLS only:** 10.0 fewer customers interrupted per event (95 % CI 8.8–11.1, Wilcoxon p ≈ 4 × 10⁻²⁸).
- **Communication:** with 2 s command latency, central NP-MRD operates one AUFLS stage. The pre-armed hybrid operated none in any tested latency and loss combination.
- **Calibration:** the governor gain is fitted to the Rajasthan (2023) and Khavda (2026) events, leaving one event out each time. The test-event nadir error is at most 0.007 Hz; the textbook value is off by 0.32–0.43 Hz.
- **Trade-offs reported:** with textbook governor response at 18 % loss, NP-MRD defers more energy than the heuristic. With a 30 % underestimate of inertia, AUFLS operated in 2 of 10 seeds.

## What is new, and what is not

**Established and cited:** frequency-responsive loads, staggered restoration, the SFR model, AUFLS, demand response programmes. Tata Power–AutoGrid, for example, does peak reduction over minutes to hours.

**Rakshak's contribution:**
1. **NP-MRD.** Minimum relief computed from a predicted nadir, including governor limits. Appliances are chosen by a lexicographic knapsack: customers interrupted first, then guaranteed deferred energy, then thermal slack.
2. **Hybrid.** Nested minimum-relief sets are pre-armed for a ladder of contingency sizes and triggered locally by RoCoF, in the style of a special protection scheme. Central refinement then works over an impaired channel.
3. **Calibration and experiments.** A calibrated Indian-event study with paired experiments, plus an open campus twin.

See [docs/literature_review.md](docs/literature_review.md) for what prior work already covers and [docs/methods.md](docs/methods.md) for every model's source, the declared assumptions, and the items still to verify before submission.

## Run

```bash
python -m pip install -r backend/requirements.txt
```

```bash
python run_sim.py
```

Then open http://127.0.0.1:8000. The app has five views:

- **Story:** a seven-step guided demonstration: the twin, a generator trip, AUFLS cutting feeders, the fixed-threshold rule, Rakshak's predictive relief, the pre-armed hybrid under bad communication, and the evidence.
- **Compare:** two policies replayed side by side on the same event, with a frequency chart and outcome table.
- **Explore:** run your own scenario (policy, event size, inertia, participation, latency, packet loss).
- **Results:** the paper's experiments and calibration.
- **Methods:** every model's source and assumptions.

Every replay records the controller's decisions. Click a marker on the timeline to open the decision explainer: what was measured, what was predicted, how much relief was needed, and why those appliances were chosen.

The 3D scene has two looks, switchable from the **Photoreal / Model** chip:

- **Photoreal:** Google Photorealistic 3D Tiles (via Cesium ion), with the simulation state drawn as translucent colours on the real buildings.
- **Model:** our own building models on Esri World Imagery, with roads, the metro viaduct and the Vrishabhavati river from OpenStreetMap. This view needs no 3D-tile access.

Both online layers need keys on the server, never in the browser bundle:

```bash
export RAKSHAK_CESIUM_TOKEN=...   # free Cesium ion Community token
export RAKSHAK_ARCGIS_KEY=...     # free ArcGIS Location Platform key (basemaps)
```

Without them, or offline, the twin falls back to the drawn model.

The original street view is at `/street.html`. The appliance request and review pages are at `/appliances.html` and `/reviewer.html`; the server prints the reviewer credential on start.

## Reproduce

```bash
python -m pip install -r backend/requirements-dev.txt
```

```bash
python -B -m unittest discover -s tests -v
```

```bash
python -B backend/calibration.py
```

```bash
python -B benchmarks/paper_experiments.py --workers 4
```

```bash
python -B paper/figures.py
```

`paper/figures.py` writes `paper/results.tex`, so every number in `paper/main.tex` comes from the data. Compile with `pdflatex main && bibtex main && pdflatex main && pdflatex main`, or upload `paper/` to Overleaf.

## Campus data

`python tools/build_campus.py` rebuilds `data/rvce/campus.json`. Sources, in precedence order:

1. `data/rvce/overrides.json`: corrections you confirm on campus.
2. **OpenStreetMap** (ODbL): the campus outline, 51 named buildings, floor counts where tagged, roads, the metro line and the river. This agrees with the architects' campus key plan in RVCE's NAAC submission, registered to satellite imagery (`data/rvce/source/keyplan_registration.json`).
3. **Microsoft Global ML Building Footprints** (ODbL): buildings that OSM does not map.

Documented facts in `data/rvce/facts.json`, each with its source URL:

- **Energy:** floor area × BEE benchmark EPI for the Moderate climate zone, scaled so RVCE totals match the NAAC-reported built-up area (67,721 m²) and hostel area (38,659 m²).
- **Solar:** the 500 kW rooftop PV is placed on the eight buildings named in the BESCOM commissioning report, shared by roof area.

The OSM outline covers the whole RV educational campus (about 49 acres, including RV University and other RV institutions). RVCE's own documents give 16.85 acres; each building carries its institution.

## Repository

| Path | Contents |
|---|---|
| `backend/grid_engine.py` | SFR plant (Anderson–Mirheydar), RK4 at 50 ms |
| `backend/nadir_predictor.py` | Closed-form and exact nadir, operator-side observer and predictor |
| `backend/policies/` | `np_mrd.py`, `hybrid.py`, `edge.py`, `heuristic.py` (original), `comms.py` |
| `backend/thermal.py` | ETP thermal states and EV laxity |
| `backend/campus.py`, `tools/build_campus.py`, `data/rvce/` | Campus model |
| `backend/calibration.py` | Leave-one-event-out calibration |
| `benchmarks/paper_experiments.py` | Experiments E1–E5 |
| `paper/` | IEEE conference draft, figures, generated results |
| `frontend/index.html`, `frontend/app/` | Twin application |
| `firmware/` | Optional ESP32 bench prototype (not part of the paper) |

## Limitations

- **Model scope:** single-area frequency, with no voltage or power-flow constraints.
- **Calibration:** only two field events, both arrested by AUFLS.
- **Simplified inputs:** communication is an abstraction, and campus loads are benchmark estimates.
- **No field trial.** Results describe the model, not RVCE or a utility network.

[docs/whats_new.md](docs/whats_new.md) explains what changed since Phase 2, the novelty, a demo talk track and likely evaluator questions. Earlier documents in `docs/` describe the first version and are kept for history.

## Credits

Experiential Learning project, RV College of Engineering, Bengaluru. Original project lead: [Nagasathya](https://github.com/nagasathya-06).
