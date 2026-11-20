# Project Rakshak

Rakshak is a simulation-based digital twin of the RV College of Engineering campus inside a modelled grid area. It is also the research testbed for a paper on **nadir-predictive, consent-constrained appliance relief beneath under-frequency load shedding (AUFLS)** in the Indian grid.

When a large generator trips, AUFLS opens whole feeders and interrupts everyone on them. Rakshak asks a narrower question: what is the **smallest** set of consenting households' flexible appliances whose curtailment keeps frequency above the first AUFLS stage? And does the answer survive slow or lossy communication?

## Results at a glance

All numbers come from `benchmarks/results/paper/summary.json`. The main comparison is 540 paired runs with the governor gain calibrated to Indian events.

| Policy | Customers interrupted per event | AUFLS stages | Critical energy not served (Wh) |
|---|---|---|---|
| AUFLS only | 11.2 | 0.56 | 1.73 |
| Original heuristic | 13.5 | 0 | 0 |
| Edge relays | 12.3 | 0 | 0 |
| **NP-MRD** | **1.1** | **0** | **0** |
| **Hybrid (pre-armed)** | **1.3** | **0** | **0** |

- **NP-MRD against AUFLS only:** 10.1 fewer customers interrupted per event (95 % CI 8.3–12.0, Wilcoxon p ≈ 4 × 10⁻¹²).
- **Communication:** with 2 s command latency, central NP-MRD operates one AUFLS stage. The pre-armed hybrid operated none in any tested latency and loss combination.
- **Calibration:** the governor gain is fitted to the Rajasthan (2023) and Khavda (2026) events, leaving one event out each time. The test-event nadir error is at most 0.007 Hz; the textbook value is off by 0.32–0.43 Hz.
- **Trade-offs reported:** with textbook governor response at 18 % loss, NP-MRD defers more energy than the heuristic. With a 30 % underestimate of inertia, AUFLS occasionally operates.

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

Then open http://127.0.0.1:8000. The landing page is the campus twin, with four views:

- **Campus twin:** RVCE footprints in 3D, live building state, time-of-day sun and streetlights, and a building inspector.
- **Grid console:** frequency against the AUFLS thresholds, the predicted nadir, and an audit of every dispatch decision.
- **Experiment lab:** the paper's results and the calibration table.
- **Methods:** sources and assumptions.

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

- **Footprints:** Microsoft Global ML Building Footprints (ODbL), filtered around RVCE.
- **Energy:** floor area × BEE benchmark EPI for the Moderate climate zone.
- **Unverified defaults:** names, uses, floor counts and campus membership are marked "unverified" until confirmed in `data/rvce/overrides.json`. Then run `python tools/build_campus.py`.

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

Earlier documents in `docs/` (architecture, model evidence, verification audit) describe the first version and are kept for history.

## Credits

Experiential Learning project, RV College of Engineering, Bengaluru. Original project lead: [Nagasathya](https://github.com/nagasathya-06).
