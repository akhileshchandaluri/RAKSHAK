"""Tests for the research core: SFR prediction, NP-MRD selection, thermal states, parity."""

import hashlib
import itertools
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import numpy as np

from config import GridConfig
from grid_engine import GridEngine
from nadir_predictor import SFRObserver, SFRParameters, nadir_hz, predicted_minimum_hz
from policies.np_mrd import NadirPredictivePolicy
from simulation import ScenarioRequest, run_scenario
from thermal import THERMAL_SPECS, ThermalState

LEGACY = json.loads((Path(__file__).parent / "fixtures" / "legacy_parity.json").read_text())


def simulated_nadir(cfg, loss):
    grid = GridEngine(cfg)
    grid.reset(loss=loss, t_trip=0)
    lowest = grid.f
    while grid.t < 80:
        grid.step(1.0)
        lowest = min(lowest, grid.f)
    return lowest


class PredictorTests(unittest.TestCase):
    def test_anderson_mirheydar_closed_form_matches_integrated_plant(self):
        for H in (2.0, 3.0, 5.0):          # overdamped, near-critical and underdamped cases
            for loss in (0.05, 0.18):
                with self.subTest(H=H, loss=loss):
                    cfg = GridConfig(H=H, governor_deadband_hz=0, up_reserve_pu=10, down_reserve_pu=10, f_collapse=0)
                    params = SFRParameters.from_config(cfg)
                    self.assertAlmostEqual(nadir_hz(params, loss), simulated_nadir(cfg, loss), places=3)

    def test_superposition_of_relief_step(self):
        cfg = GridConfig(H=4, governor_deadband_hz=0, up_reserve_pu=10, down_reserve_pu=10, f_collapse=0)
        params = SFRParameters.from_config(cfg)
        grid = GridEngine(cfg)
        grid.reset(loss=0.15, t_trip=0)
        lowest = 50.0
        while grid.t < 60:
            grid.step(1.0 if grid.t < 1.0 - 1e-9 else 0.95)
            lowest = min(lowest, grid.f)
        predicted = predicted_minimum_hz(params, [(0.0, 0.15), (1.0, -0.05)], 0.0, horizon_s=60)
        self.assertAlmostEqual(predicted, lowest, delta=0.002)

    def test_observer_prediction_includes_reserve_limit(self):
        cfg = GridConfig(H=5)
        observer = SFRObserver(cfg)
        observer.set_equilibrium(50.0)
        grid = GridEngine(cfg)
        grid.reset(loss=0.10, t_trip=0)
        for _ in range(10):
            grid.step(1.0)
        observer.update(grid.t, grid.f, grid.compute_rocof())
        observer.y = grid.pg   # isolate prediction from estimation
        predicted = float(observer.predict_minimum(0.0, horizon_s=40, deficit=0.10)[0])
        lowest = grid.f
        while grid.t < 60:
            grid.step(1.0)
            lowest = min(lowest, grid.f)
        self.assertLess(abs(predicted - lowest), 0.01)


class SelectionTests(unittest.TestCase):
    def test_covering_knapsack_is_optimal_on_small_instance(self):
        class Device:
            def __init__(self, w):
                self.base_w, self.thermal, self.lockout_duration = w, None, 0

        class Building:
            def __init__(self, idx):
                self.idx = idx

        rng = np.random.default_rng(4)
        candidates = [(Building(int(rng.integers(0, 4))), Device(float(rng.choice([2000, 3300, 1500])))) for _ in range(9)]
        policy = NadirPredictivePolicy()
        policy.event_households = set()
        target = 6000.0
        chosen = policy._select(candidates, target, 0.0)
        self.assertGreaterEqual(sum(d.base_w for _, d in chosen), target)
        best = min(len({b.idx for b, _ in subset})
                   for r in range(1, len(candidates) + 1)
                   for subset in itertools.combinations(candidates, r)
                   if sum(d.base_w for _, d in subset) >= target)
        self.assertEqual(len({b.idx for b, _ in chosen}), best)


class ThermalTests(unittest.TestCase):
    def test_etp_curtailed_room_follows_exponential(self):
        spec = THERMAL_SPECS["ac"]
        state = ThermalState(spec, ambient_c=32.0)
        for _ in range(600):
            state.step(0.5, running=False, now=0)
        expected = 32.0 + (24.0 - 32.0) * math.exp(-300 / spec.tau_s)
        self.assertAlmostEqual(state.temperature_c, expected, places=9)


class OutcomeTests(unittest.TestCase):
    def test_np_mrd_prevents_aufls_with_fewer_customers(self):
        ufls = run_scenario(ScenarioRequest(mode="ufls", generation_loss=0.10))
        heuristic = run_scenario(ScenarioRequest(mode="rakshak", generation_loss=0.10))
        npmrd = run_scenario(ScenarioRequest(mode="np_mrd", generation_loss=0.10))
        self.assertGreater(ufls["ufls_stages_tripped"], 0)
        self.assertEqual(npmrd["ufls_stages_tripped"], 0)
        self.assertEqual(npmrd["critical_energy_not_served_wh"], 0)
        self.assertLess(npmrd["customers_interrupted"], heuristic["customers_interrupted"])
        self.assertLess(npmrd["customers_interrupted"], ufls["customers_interrupted"])

    def test_legacy_two_lag_heuristic_results_unchanged(self):
        cases = {"0.35-1.0-generation_loss-True": dict(generation_loss=0.35, participation=1.0,
                                                       disturbance="generation_loss", dynamic_demand=True),
                 "0.1-0.25-feeder_fault-False": dict(generation_loss=0.1, participation=0.25,
                                                     disturbance="feeder_fault", dynamic_demand=False)}
        for key, fields in cases.items():
            for expected in LEGACY[key]:
                with self.subTest(key=key, mode=expected["mode"]):
                    result = run_scenario(ScenarioRequest(mode=expected["mode"], plant="two_lag", seed=3, **fields))
                    trace = result.pop("trace")
                    self.assertEqual(hashlib.sha256(json.dumps(trace, sort_keys=True).encode()).hexdigest(),
                                     expected["trace_sha256"])
                    for metric, value in expected.items():
                        if metric not in ("trace_sha256",):
                            self.assertEqual(result[metric], value, metric)


if __name__ == "__main__":
    unittest.main()


class CampusTests(unittest.TestCase):
    def test_campus_agents_follow_benchmark_energy(self):
        from campus import load_campus
        from simulation import SimulationController
        data = load_campus()
        sim = SimulationController(ScenarioRequest(campus=True))
        campus = [b for b in data["buildings"] if b["campus"]]
        self.assertEqual(len(sim.fleet.campus_buildings), len(campus))
        for agent in sim.fleet.campus_buildings:
            b = agent.campus
            area = b.get("energy_floor_area_m2", b["floor_area_m2"])
            self.assertAlmostEqual(b["annual_kwh"], area * b["epi_kwh_m2_yr"], delta=1e-4 * b["annual_kwh"] + 10)
            total = sum(d.base_w for d in agent.devices.values())
            self.assertAlmostEqual(total / 1000, b["average_kw"], delta=0.01)
        # Energy-bearing area is calibrated to the documented RVCE totals (NAAC SSR).
        rvce = [b for b in campus if b.get("institution") == "RVCE"]
        self.assertAlmostEqual(sum(b.get("energy_floor_area_m2", 0) for b in rvce if b["use"] != "hostel"), 67721, delta=5)
        self.assertAlmostEqual(sum(b.get("energy_floor_area_m2", 0) for b in rvce if b["use"] == "hostel"), 38659, delta=5)
        # The 500 kW rooftop PV sits on the eight buildings named in the BESCOM report.
        hosts = [b for b in campus if b.get("solar_kwp")]
        self.assertEqual(len(hosts), 8)
        self.assertAlmostEqual(sum(b["solar_kwp"] for b in hosts), 500, delta=0.5)
