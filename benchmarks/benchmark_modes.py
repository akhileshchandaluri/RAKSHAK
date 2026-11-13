"""Run the same paired benchmark used by the Rakshak dashboards."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from simulation import ScenarioRequest, compare_modes
from inventory import InventoryStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disturbance", choices=["generation_loss", "solar_surplus", "demand_surge", "feeder_fault"],
                        default="generation_loss")
    parser.add_argument("--magnitude", type=float, default=0.18)
    parser.add_argument("--participation", type=float, default=1.0)
    parser.add_argument("--recovery", type=float, default=45.0, help="Simulated seconds until the return ramp starts")
    parser.add_argument("--inertia", type=float, default=5.0)
    parser.add_argument("--threshold", type=float, default=49.60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clinical-backup", type=float, default=2, help="Minutes at modeled protected clinical load")
    args = parser.parse_args()
    scenario = ScenarioRequest(
        disturbance=args.disturbance, generation_loss=args.magnitude, participation=args.participation,
        t_recover=args.recovery, grid_inertia_h=args.inertia, shed_threshold=args.threshold, seed=args.seed,
        clinical_backup_minutes=args.clinical_backup,
    )
    print(f"{'Mode':24} {'Nadir':>7} {'Peak Hz':>7} {'RoCoF':>7} {'Recovery':>9} {'Critical Wh':>12} {'Peak p.u.':>10}")
    for row in compare_modes(scenario, InventoryStore().snapshot()):
        recovery = "-" if row["recovery_time"] is None else f'{row["recovery_time"]:.2f}s'
        rebound = "-" if not row["peak_post_shed_load"] else f'{row["peak_post_shed_load"]:.3f}'
        print(
            f'{row["mode"]:24} {row["nadir"]:7.3f} {row["zenith"]:7.3f} '
            f'{row["max_rocof"]:7.3f} {recovery:>9} {row["critical_energy_not_served_wh"]:12.2f} {rebound:>10}'
        )


if __name__ == "__main__":
    main()
