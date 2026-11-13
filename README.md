# Project Rakshak

A grid-resilience simulation testbed for consent-aware appliance control, protected electrical services and coordinated restoration alongside reference AUFLS protection. The original 3D dashboard shows 12 buildings from the same 500-building simulated fleet. This is not a calibrated physical-feeder digital twin.

See the [verification audit](docs/verification_audit.md) for software checks and the comparison with Indian grid event records.

## Run locally

```powershell
python -m pip install -r backend/requirements.txt
python run_sim.py
```

Open http://127.0.0.1:8000. The browser requires the Python server. Disconnection freezes telemetry and displays a warning. The analytics dashboard is at `/dashboard.html`, evidence register at `/evidence.html`, resident submissions at `/appliances.html`, and reviewer screen at `/reviewer.html`.

Select a showcase preset, then compare Reference AUFLS with AUFLS + Rakshak. Unmanaged and bulk-restoration modes are experimental controls. Normal operation, generation loss, demand surge, low enrollment, local feeder fault, backup exhaustion, restoration and solar surplus are available. Advanced settings expose assumptions with units. An electrical fault disconnects the selected feeder regardless of priority. Only explicitly modeled backup can continue supplying protected circuits.

## Appliance requests and review

The server prints a random reviewer credential on startup. Alternatively configure `RAKSHAK_REVIEWER_TOKEN` in the local process environment before launching. Do not put the credential into source control. The reviewer enters it at `/reviewer.html`; it is used as a Bearer credential and is not stored in the browser. This is a local demonstration service, not a deployed multi-tenant identity system.

Requests and decision history persist in ignored `var/inventory.sqlite3`. Override the path with `RAKSHAK_INVENTORY_DB` for isolated tests. New requests remain pending until approved or rejected with a reason. Existing configurations stay active while changes are pending. Approval does not grant control consent or install backup. Custom device types default to manual control. Every simulation freezes a revision and applies new approvals only on reset. Comparisons reject stale inventory revisions rather than silently changing the fleet.

Critical and essential service priorities are distinct from ordinary/flexible consumption, control consent, and current operating state. The inspector includes inactive appliances, quantities, unit and aggregate watts, evidence, priority and state. The critical-service panel displays electrical continuity only for buildings with protected loads. No ECG or patient-health inference is generated.

## Indian reference and limitations

Normal band: 49.90–50.05 Hz. The dated SRPC reference profile uses 49.4/49.2/49.0/48.8 Hz and 5/6/7/7% relief allocations, scaled here to initial scenario demand and fixed whole blocks. Actual regional allocations and feeder wiring differ. India also uses generation response, reserves, operator demand management, fault protection and restoration. The dashboard does not reproduce all those systems. See the linked evidence register for the dated ADMS example and model assumptions.

Experimental defaults include DR at 49.60 Hz, 100 ms AUFLS dwell, 180 s compressor lockout, and a 47.5 Hz study cutoff. These are not all national operating rules. The model has no voltage/power-flow, calibrated thermal comfort, clinical physiological model, black-start or measured device response. Backup is idealized and finite.

## Verify and reproduce results

```powershell
python -m pip install -r backend/requirements-dev.txt
python -B -m unittest discover -s tests -v
python -B benchmarks/benchmark_modes.py
python -B benchmarks/research_matrix.py --workers 8
```

The matrix runs 20 paired seeds, five enrollment levels and three loss magnitudes under two policies: 600 simulations, each 270 seconds. Results are in `benchmarks/results/paired_runs.csv` and `summary.json`. Intervals represent variability across modeled seeds, not field uncertainty. Earlier result tables from the quarter-fleet UFLS implementation are superseded.

Browser checks use Playwright, with `RAKSHAK_PLAYWRIGHT_MODULE` pointing to an installed Playwright module and `PLAYWRIGHT_BROWSERS_PATH` configured if needed. Run `node tests/browser_showcase.cjs` with the local server active.

- [Evidence, equations and assumptions](docs/model_evidence.md)
- [Feature transfer decisions](docs/feature_transfer.md)
- [Presentation guide](docs/presentation_guide.md)
- [Architecture](docs/architecture.md)
- [Optional hardware bridge](firmware/README.md)

## Alignment and credits

Project Rakshak explores energy flexibility and resilient infrastructure in the context of SDG 7 and SDG 11. The project was led by [Nagasathya](https://github.com/nagasathya-06) at RV College of Engineering, Bengaluru, for Experiential Learning in fifth-semester Computer Science.
