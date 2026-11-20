"""Leave-one-event-out calibration of the effective primary-response gain.

Observations are the two published Indian events in ``field_check.EVENTS``
(loss MW, pre-event frequency, nadir). Unknowns that the public reports do not give
(the system base in MW at the event instant and the inertia constant) are held as
declared assumptions and swept. One parameter is fitted: the SFR mechanical power gain
K_m of Anderson & Mirheydar (1990), which scales the aggregate governor response
(the effective frequency-response characteristic). Grid-India publishes
frequency-response-characteristic (FRC) assessments for large events, and the
reported nadirs are deeper than a full 5 % droop response would allow; the specific
FRC report used in the paper must be cited there (see docs/methods.md, "To verify").

Protocol: fit K_m on event A by bisection on the simulated nadir (reference AUFLS
active, 40 s, initial frequency = reported pre-event frequency), then report the
nadir error on event B with the fitted value. With two events this is a consistency
check, not a validation.
"""

import json
import sys
from pathlib import Path

from scipy.optimize import brentq

from field_check import EVENTS
from simulation import ScenarioRequest, run_scenario

BASES_MW = (200_000, 250_000)
INERTIA_S = (4.0, 5.0)


def simulated_nadir(event, base_mw, H, km):
    scenario = ScenarioRequest(mode="ufls", generation_loss=event["loss_mw"] / base_mw,
                               grid_inertia_h=H, mechanical_gain=km)
    return run_scenario(scenario, duration=40, initial_frequency_hz=event["initial_hz"])["nadir"]


def fit_gain(event, base_mw, H):
    """K_m in [0.02, 0.95] matching the reported nadir, or the nearer bound."""
    error = lambda km: simulated_nadir(event, base_mw, H, km) - event["nadir_hz"]
    lo, hi = 0.02, 0.95
    e_lo, e_hi = error(lo), error(hi)
    if e_lo * e_hi > 0:
        return lo if abs(e_lo) < abs(e_hi) else hi
    return brentq(error, lo, hi, xtol=1e-3)


def calibrate():
    rows = []
    for base in BASES_MW:
        for H in INERTIA_S:
            for i, train in enumerate(EVENTS):
                test = EVENTS[1 - i]
                km = fit_gain(train, base, H)
                rows.append({
                    "assumed_base_mw": base, "assumed_H_s": H,
                    "fit_event": train["name"], "test_event": test["name"],
                    "fitted_mechanical_gain": round(km, 3),
                    "fit_nadir_error_hz": round(simulated_nadir(train, base, H, km) - train["nadir_hz"], 3),
                    "test_nadir_error_hz": round(simulated_nadir(test, base, H, km) - test["nadir_hz"], 3),
                    "default_gain_test_error_hz": round(simulated_nadir(test, base, H, 0.95) - test["nadir_hz"], 3),
                })
    return rows


if __name__ == "__main__":
    out = calibrate()
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "benchmarks" / "results" / "calibration.json"
    target.write_text(json.dumps(out, indent=2))
    for row in out:
        print(row)
