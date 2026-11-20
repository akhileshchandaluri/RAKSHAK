"""Generate paper figures and results.tex (LaTeX macros) from experiment outputs.

    python -B paper/figures.py [--results benchmarks/results/paper]

Every number quoted in main.tex comes from a macro written here, so the text cannot
drift from the data.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulation import ScenarioRequest, run_scenario

OUT = Path(__file__).resolve().parent / "figures"
POLICY = {"ufls": "AUFLS only", "rakshak": "Heuristic [orig.]", "edge": "Edge relays",
          "np_mrd": "NP-MRD", "hybrid": "Hybrid"}
COLORS = {"ufls": "#7f7f7f", "rakshak": "#c9a26b", "edge": "#9467bd", "np_mrd": "#1f77b4", "hybrid": "#2ca02c"}

plt.rcParams.update({"font.family": "serif", "font.size": 8, "axes.linewidth": 0.6, "lines.linewidth": 1.2,
                     "axes.grid": True, "grid.linewidth": 0.3, "grid.alpha": 0.5, "legend.frameon": False,
                     "figure.dpi": 200, "savefig.bbox": "tight"})
COL = 3.5  # IEEE single column width (in)


def macro(name, value):
    return f"\\newcommand{{\\{name}}}{{{value}}}\n"


def fig_trajectories(gain):
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    for policy in ("ufls", "rakshak", "np_mrd", "hybrid"):
        r = run_scenario(ScenarioRequest(mode=policy, grid_inertia_h=3, generation_loss=0.05, seed=0,
                                         mechanical_gain=gain))
        t, f = np.array(r["trace"]["time"]), np.array(r["trace"]["frequency"])
        keep = t <= 60
        ax.plot(t[keep], f[keep], color=COLORS[policy], label=POLICY[policy])
    for k, y in enumerate((49.4, 49.2)):
        ax.axhline(y, color="#d62728", lw=0.6, ls="--")
        ax.text(59, y + 0.01, f"AUFLS stage {k + 1}", ha="right", va="bottom", color="#d62728", fontsize=6)
    ax.set_xlabel("time (s)"); ax.set_ylabel("frequency (Hz)")
    ax.set_ylim(49.15, 50.2)
    ax.legend(ncol=2, fontsize=6.5, loc="lower left", bbox_to_anchor=(0.0, 0.08))
    fig.savefig(OUT / "trajectories.pdf"); fig.savefig(OUT / "trajectories.png")
    plt.close(fig)


def fig_customers(summary):
    rows = [r for r in summary["E1_means"] if r["enrollment"] == 1.0]
    cases = sorted({(r["H"], r["loss"]) for r in rows}, key=lambda k: (-k[0], k[1]))
    policies = list(POLICY)
    fig, ax = plt.subplots(figsize=(COL * 2, 2.0))
    width = 0.8 / len(policies)
    for j, p in enumerate(policies):
        vals = [next((r["customers_interrupted"] for r in rows if (r["H"], r["loss"]) == c and r["policy"] == p), 0) for c in cases]
        ax.bar(np.arange(len(cases)) + (j - (len(policies) - 1) / 2) * width, vals, width * 0.92,
               color=COLORS[p], label=POLICY[p])
    ax.set_xticks(range(len(cases)), [f"H={h:g} s\n{l * 100:g} %" for h, l in cases])
    ax.set_ylabel("customers interrupted")
    ax.legend(ncol=5, fontsize=6.5, loc="upper left")
    fig.savefig(OUT / "customers.pdf"); fig.savefig(OUT / "customers.png")
    plt.close(fig)


def fig_comm(summary):
    rows = summary["E2_means"]
    losses = sorted({r["comm_loss"] for r in rows})
    fig, axes = plt.subplots(1, 2, figsize=(COL * 2, 1.9))
    for metric, ax, label in (("customers_interrupted", axes[0], "customers interrupted"),
                              ("ufls_stages_tripped", axes[1], "AUFLS stages operated")):
        styles = ["-", "--", ":"]
        markers = ["o", "s", "^"]
        for p in ("np_mrd", "hybrid"):
            for k, loss in enumerate(losses):
                pts = sorted((r["comm_latency_s"], r[metric]) for r in rows if r["policy"] == p and r["comm_loss"] == loss)
                ax.plot(*zip(*pts), styles[k % 3], color=COLORS[p], marker=markers[k % 3], ms=2.5,
                        label=f"{POLICY[p]}, {loss * 100:g} % loss")
        ax.set_xlabel("command latency (s)"); ax.set_ylabel(label)
    axes[1].legend(fontsize=6, ncol=2)
    fig.savefig(OUT / "communication.pdf"); fig.savefig(OUT / "communication.png")
    plt.close(fig)


def fig_margin(summary):
    rows = sorted(summary["E3_means"], key=lambda r: r["margin_hz"])
    fig, ax = plt.subplots(figsize=(COL, 1.9))
    ax.plot([r["margin_hz"] for r in rows], [r["customers_interrupted"] for r in rows], "o-", ms=3, color=COLORS["np_mrd"])
    ax.set_xlabel("protection margin above 49.40 Hz (Hz)"); ax.set_ylabel("customers interrupted")
    ax2 = ax.twinx(); ax2.grid(False)
    ax2.plot([r["margin_hz"] for r in rows], [r["nadir"] for r in rows], "s--", ms=3, color="#d62728")
    ax2.set_ylabel("nadir (Hz)", color="#d62728")
    fig.savefig(OUT / "margin.pdf"); fig.savefig(OUT / "margin.png")
    plt.close(fig)


def write_macros(summary, calibration):
    e1 = summary["E1_means"]
    def mean_over(policy, metric):
        vals = [r[metric] for r in e1 if r["policy"] == policy]
        return float(np.mean(vals)) if vals else float("nan")
    names = {"ufls": "Aufls", "rakshak": "Heur", "edge": "Edge", "np_mrd": "Npmrd", "hybrid": "Hybrid"}
    text = "% Generated by paper/figures.py. Do not edit.\n"
    text += macro("RunsMain", sum(r["n"] for r in e1))
    text += macro("SeedsMain", max(r["n"] for r in e1))
    text += macro("CalibratedGain", summary["protocol"]["calibrated_mechanical_gain"])
    for p, n in names.items():
        text += macro(f"Cust{n}", f"{mean_over(p, 'customers_interrupted'):.1f}")
        text += macro(f"Stages{n}", f"{mean_over(p, 'ufls_stages_tripped'):.2f}")
        text += macro(f"Ens{n}", f"{mean_over(p, 'critical_energy_not_served_wh'):.2f}")
        text += macro(f"Unserved{n}", f"{mean_over(p, 'total_unserved_wh') / 1000:.2f}")
        text += macro(f"Nadir{n}", f"{mean_over(p, 'nadir'):.3f}")
    for name, key in (("NpVsAufls", "np_mrd_vs_ufls"), ("NpVsHeur", "np_mrd_vs_rakshak"),
                      ("HyVsAufls", "hybrid_vs_ufls"), ("HyVsHeur", "hybrid_vs_rakshak"), ("HyVsEdge", "hybrid_vs_edge")):
        r = summary["E1_paired"][key]["customers_interrupted"]
        if r:
            text += macro(f"Cust{name}", f"{r['mean_difference']:.1f}")
            text += macro(f"Cust{name}Lo", f"{r['ci95'][0]:.1f}")
            text += macro(f"Cust{name}Hi", f"{r['ci95'][1]:.1f}")
            text += macro(f"Cust{name}P", f"{r['wilcoxon_p']:.1e}" if r["wilcoxon_p"] is not None else "n/a")
    e2 = summary["E2_means"]
    worst = [r for r in e2 if r["comm_latency_s"] == max(x["comm_latency_s"] for x in e2) and r["comm_loss"] == max(x["comm_loss"] for x in e2)]
    for r in worst:
        n = "Np" if r["policy"] == "np_mrd" else "Hy"
        text += macro(f"WorstStages{n}", f"{r['ufls_stages_tripped']:.2f}")
        text += macro(f"WorstCust{n}", f"{r['customers_interrupted']:.1f}")
    text += macro("WorstLatency", max(x["comm_latency_s"] for x in e2))
    text += macro("WorstLoss", f"{max(x['comm_loss'] for x in e2) * 100:g}")
    test_errors = [abs(r["test_nadir_error_hz"]) for r in calibration]
    default_errors = [abs(r["default_gain_test_error_hz"]) for r in calibration]
    gains = [r["fitted_mechanical_gain"] for r in calibration]
    text += macro("CalTestErrMax", f"{max(test_errors):.3f}")
    text += macro("CalDefaultErrMin", f"{min(default_errors):.2f}")
    text += macro("CalDefaultErrMax", f"{max(default_errors):.2f}")
    text += macro("CalGainMax", f"{max(gains):.2f}")
    (Path(__file__).resolve().parent / "results.tex").write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(ROOT / "benchmarks" / "results" / "paper"))
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    summary = json.loads((Path(args.results) / "summary.json").read_text())
    calibration = json.loads((ROOT / "benchmarks" / "results" / "calibration.json").read_text())
    fig_trajectories(summary["protocol"]["calibrated_mechanical_gain"])
    fig_customers(summary)
    fig_comm(summary)
    fig_margin(summary)
    write_macros(summary, calibration)
    print("figures and results.tex written")


if __name__ == "__main__":
    main()
