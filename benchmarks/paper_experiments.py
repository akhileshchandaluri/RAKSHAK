"""Experiments for the paper. Every run uses the shared simulation entry point.

E1  main comparison: policy x inertia x contingency x enrollment x seed
E2  communication robustness: latency x loss for central and hybrid control
E3  protection margin sweep (trade-off curve) for NP-MRD
E4  operator inertia-estimate error for NP-MRD
E5  sensitivity with the textbook governor gain (K_m = 0.95)

Outputs: benchmarks/results/paper/<experiment>.csv and summary.json with paired
statistics (mean difference, 95 % Student-t interval, Wilcoxon signed-rank p) across
seeds. Seeds index modelled scenario variation only; intervals are not field
uncertainty.

    python -B benchmarks/paper_experiments.py --workers 4           # full
    python -B benchmarks/paper_experiments.py --quick --workers 4   # smoke test
"""

import argparse
import csv
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np
from scipy import stats

from simulation import ScenarioRequest, run_scenario

CALIBRATED_GAIN = 0.15   # leave-one-event-out fit, benchmarks/results/calibration.json
METRICS = ("nadir", "ufls_stages_tripped", "feeder_trips", "critical_energy_not_served_wh",
           "protected_sites_interrupted", "customers_interrupted", "households_curtailed",
           "households_disconnected", "total_unserved_wh", "flexible_unserved_wh",
           "comfort_violation_degmin", "jain_fairness", "longest_device_pause_s", "peak_post_shed_load",
           "shed_count", "restore_count")


def plan(quick=False):
    seeds = range(3 if quick else 6)
    runs = []
    policies = ("ufls", "rakshak", "edge", "np_mrd", "hybrid")
    for H in ((3,) if quick else (5, 3, 2)):
        for loss in ((0.05,) if quick else (0.02, 0.035, 0.05)):
            for enrollment in ((1.0,) if quick else (0.5, 1.0)):
                for seed in seeds:
                    for policy in policies:
                        runs.append(("E1", dict(mode=policy, grid_inertia_h=H, generation_loss=loss,
                                                participation=enrollment, seed=seed,
                                                mechanical_gain=CALIBRATED_GAIN)))
    for latency in ((0.0, 1.0) if quick else (0.0, 0.25, 0.5, 1.0, 2.0)):
        for loss_p in ((0.0, 0.4) if quick else (0.0, 0.2, 0.4)):
            for seed in seeds:
                for policy in ("np_mrd", "hybrid"):
                    runs.append(("E2", dict(mode=policy, grid_inertia_h=3, generation_loss=0.05, seed=seed,
                                            mechanical_gain=CALIBRATED_GAIN, comm_latency_s=latency,
                                            comm_jitter_s=latency / 2, comm_loss=loss_p)))
    for margin in ((0.05, 0.2) if quick else (0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3)):
        for seed in seeds:
            runs.append(("E3", dict(mode="np_mrd", grid_inertia_h=3, generation_loss=0.05, seed=seed,
                                    mechanical_gain=CALIBRATED_GAIN, margin_hz=margin)))
    for error in ((-0.3, 0.3) if quick else (-0.3, -0.15, 0.0, 0.15, 0.3)):
        for seed in seeds:
            runs.append(("E4", dict(mode="np_mrd", grid_inertia_h=3, generation_loss=0.05, seed=seed,
                                    mechanical_gain=CALIBRATED_GAIN, inertia_error=error)))
    for H in ((5,) if quick else (5, 3)):
        for loss in ((0.18,) if quick else (0.10, 0.18)):
            for seed in (range(2) if quick else range(5)):
                for policy in policies:
                    runs.append(("E5", dict(mode=policy, grid_inertia_h=H, generation_loss=loss, seed=seed,
                                            mechanical_gain=0.95)))
    return runs


def execute(job):
    experiment, fields = job
    started = time.time()
    result = run_scenario(ScenarioRequest(**fields))
    row = {"experiment": experiment, **fields, **{m: result[m] for m in METRICS},
           "runtime_s": round(time.time() - started, 2)}
    return row


def paired(rows, keys, baseline, challenger, metric):
    """Paired differences challenger - baseline matched on all keys except the policy."""
    index = {}
    for r in rows:
        index[(r["mode"],) + tuple(r[k] for k in keys)] = r[metric]
    diffs = []
    for r in rows:
        if r["mode"] != baseline:
            continue
        key = tuple(r[k] for k in keys)
        if (challenger,) + key in index:
            diffs.append(index[(challenger,) + key] - r[metric])
    d = np.array(diffs, dtype=float)
    if len(d) < 2:
        return None
    half = stats.t.ppf(0.975, len(d) - 1) * d.std(ddof=1) / np.sqrt(len(d)) if d.std(ddof=1) > 0 else 0.0
    nonzero = d[d != 0]
    p = float(stats.wilcoxon(nonzero).pvalue) if len(nonzero) >= 6 else None
    return {"n": len(d), "mean_difference": round(float(d.mean()), 4),
            "ci95": [round(float(d.mean() - half), 4), round(float(d.mean() + half), 4)],
            "wilcoxon_p": p}


def summarise(rows):
    summary = {"protocol": {"duration_s": 270, "step_s": 0.05, "calibrated_mechanical_gain": CALIBRATED_GAIN,
                            "note": "Seeds index modelled variation only; intervals are not field uncertainty."}}
    e1 = [r for r in rows if r["experiment"] == "E1"]
    groups = {}
    for r in e1:
        groups.setdefault((r["grid_inertia_h"], r["generation_loss"], r["participation"], r["mode"]), []).append(r)
    summary["E1_means"] = [
        {"H": k[0], "loss": k[1], "enrollment": k[2], "policy": k[3], "n": len(v),
         **{m: round(float(np.mean([x[m] for x in v])), 4) for m in METRICS}}
        for k, v in sorted(groups.items())
    ]
    keys = ("grid_inertia_h", "generation_loss", "participation", "seed")
    summary["E1_paired"] = {
        f"{challenger}_vs_{baseline}": {m: paired(e1, keys, baseline, challenger, m)
                                        for m in ("customers_interrupted", "total_unserved_wh",
                                                  "critical_energy_not_served_wh", "ufls_stages_tripped", "nadir")}
        for baseline, challenger in (("ufls", "np_mrd"), ("rakshak", "np_mrd"), ("ufls", "hybrid"),
                                     ("rakshak", "hybrid"), ("edge", "hybrid"))
    }
    for experiment, factor in (("E2", ("comm_latency_s", "comm_loss")), ("E3", ("margin_hz",)),
                               ("E4", ("inertia_error",)), ("E5", ("grid_inertia_h", "generation_loss"))):
        part = [r for r in rows if r["experiment"] == experiment]
        g = {}
        for r in part:
            g.setdefault(tuple(r[f] for f in factor) + (r["mode"],), []).append(r)
        summary[f"{experiment}_means"] = [
            {**dict(zip(factor + ("policy",), k)), "n": len(v),
             **{m: round(float(np.mean([x[m] for x in v])), 4) for m in METRICS}}
            for k, v in sorted(g.items())
        ]
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", default=str(ROOT / "benchmarks" / "results" / "paper"))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = plan(args.quick)
    print(f"{len(jobs)} runs", flush=True)
    rows = []
    with Pool(args.workers) as pool:
        for i, row in enumerate(pool.imap_unordered(execute, jobs, chunksize=1), 1):
            rows.append(row)
            if i % 25 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)}", flush=True)
    rows.sort(key=lambda r: tuple(str(r.get(k)) for k in ("experiment", "mode", "grid_inertia_h", "generation_loss",
                                                           "participation", "comm_latency_s", "comm_loss",
                                                           "margin_hz", "inertia_error", "seed")))
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("experiment", "mode"), k))
    for experiment in sorted({r["experiment"] for r in rows}):
        with open(out / f"{experiment}.csv", "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(r for r in rows if r["experiment"] == experiment)
    (out / "summary.json").write_text(json.dumps(summarise(rows), indent=1))
    print("done", flush=True)


if __name__ == "__main__":
    main()
