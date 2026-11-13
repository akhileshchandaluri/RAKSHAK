import sys
import math
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fleet_simulator import FleetSimulator
from grid_engine import GridEngine
from config import APPLIANCE_CATALOG, GridConfig
from hil_bridge import HILBridge
from nilm_engine import NILMDisaggregator
from simulation import ScenarioRequest, SimulationController


class SimulationTests(unittest.TestCase):
    def test_swing_equation_against_closed_form(self):
        cfg = GridConfig(up_reserve_pu=0, down_reserve_pu=0)
        for dt in (0.05, 0.025):
            with self.subTest(dt=dt):
                grid = GridEngine(cfg)
                grid.reset(loss=0.1, t_trip=0)
                grid.dt = dt
                for _ in range(round(5 / dt)):
                    grid.step(1)
                expected = cfg.f0 * (1 - 0.1 / cfg.D * (1 - math.exp(-cfg.D * 5 / (2 * cfg.H))))
                self.assertAlmostEqual(grid.f, expected, places=8)

    def test_priorities_distinguish_food_and_vaccine_storage(self):
        sim = SimulationController()
        house = sim.fleet.micro_buildings[1]
        clinic = sim.fleet.micro_buildings[2]
        self.assertEqual(house.devices["fridge"].tier, 1)
        self.assertEqual(clinic.devices["vaccine"].tier, 0)
        self.assertFalse(house.devices["washer"].control)
        self.assertTrue(all(not device.control for device in clinic.devices.values() if device.tier == 0))
        self.assertEqual(clinic.devices["clinical_lights"].base_w, 150)
        self.assertTrue(all(spec["source"].startswith("https://") and spec["basis"]
                            for spec in APPLIANCE_CATALOG.values()))

    def test_clinical_backup_supplies_only_protected_loads_and_exhausts(self):
        sim = SimulationController(ScenarioRequest(clinical_backup_minutes=0.01))
        clinic = sim.fleet.micro_buildings[2]
        sim.grid.collapsed = True
        sim.step()
        snapshot = sim.snapshot()["buildings"][2]
        self.assertEqual(snapshot["appliances"]["o2"]["supply"], "backup")
        self.assertEqual(snapshot["appliances"]["reception"]["supply"], "unavailable")
        self.assertEqual(snapshot["power_w"], clinic.critical_w)
        self.assertEqual(sim.grid.load_pu, 0.0)
        for _ in range(20):
            sim.step()
        self.assertFalse(clinic.on_backup)
        self.assertEqual(clinic.backup_wh, 0)
        self.assertGreater(sim.grid.critical_energy_not_served_wh, 0)
    def test_held_reduction_continues_to_affect_frequency(self):
        unmanaged, reduced = GridEngine(), GridEngine()
        for grid in (unmanaged, reduced):
            grid.reset(t_trip=0, loss=0.1)
        for _ in range(600):
            unmanaged.step(1.0)
            reduced.step(0.95)
        self.assertEqual(reduced.load_pu, 0.95)
        self.assertGreater(reduced.f, unmanaged.f + 0.08)

    def test_macro_buildings_drive_grid_demand(self):
        fleet = FleetSimulator()
        self.assertEqual(len(fleet.macro_fleet), 500)
        self.assertIs(fleet.micro_buildings[0], fleet.macro_fleet[0])
        for building in fleet.macro_fleet[12:]:
            building.energized = False
        self.assertLess(fleet.step(0, 0.05, 50, 0, "none"), 0.08)

    def test_enrollment_and_reset(self):
        zero = SimulationController(ScenarioRequest(participation=0))
        enrolled = SimulationController()
        for _ in range(250):
            zero.step()
            enrolled.step()
        self.assertEqual(zero.fleet.shed_count, 0)
        self.assertGreater(enrolled.fleet.shed_count, 0)
        self.assertGreater(enrolled.grid.nadir, zero.grid.nadir)
        self.assertTrue(all(
            device.is_on for building in enrolled.fleet.macro_fleet
            for device in building.devices.values() if device.tier == 0
        ))
        enrolled.reset()
        self.assertEqual(enrolled.grid.t, 0)
        self.assertEqual(enrolled.fleet.shed_count, 0)
        self.assertFalse(enrolled.fleet.events)

    def test_restore_checks_frequency_capacity_and_lockout(self):
        fleet = FleetSimulator(size=12)
        device = fleet.micro_buildings[0].devices["ac"]
        device.turn_off(0)
        device.shed_at = 0
        device.restore_at = 190
        fleet.restore_stable_s = fleet.cfg.restore_hold_s
        for now, frequency, capacity in [(179, 50, 1.2), (189, 50, 1.2), (200, 50, 0.9), (200, 49.8, 1.2)]:
            fleet._dispatch(now, frequency, 0, "rakshak", 0.9, capacity, 0.9, False)
            self.assertFalse(device.is_on)
        fleet._dispatch(201, 50, 0, "rakshak", 1.0, 1.2, 0.9, False)
        self.assertTrue(device.is_on)
        self.assertEqual(fleet.restore_count, 1)

    def test_disturbance_components_have_expected_signs(self):
        for kind, expected in (("generation_loss", -1), ("demand_surge", -1), ("solar_surplus", 1)):
            with self.subTest(kind=kind):
                grid = GridEngine()
                grid.reset(t_trip=0, loss=0.1, disturbance=kind)
                grid.step(1.0)
                self.assertGreater((grid.f - 50) * expected, 0)

    def test_nilm_abstains_on_aggregate_step_without_matching_signature(self):
        detector = NILMDisaggregator()
        self.assertIsNone(detector.feed_sample(0, 1000))
        event = detector.feed_sample(0.05, 13000)
        self.assertEqual(event["classification"], "unknown")
        self.assertIsNone(event["appliance"])

    def test_serial_parser_keeps_partial_frames_and_reports_stale_heartbeat(self):
        class SerialInput:
            def __init__(self):
                self.chunks = iter((
                    b'{"node_id":"esp32_rakshak_01",',
                    b'"shed_l3":1,"input_fresh":true}\n',
                    b"",
                ))

            def read(self, size):
                return next(self.chunks)

        bridge = HILBridge()
        bridge.ser = SerialInput()
        self.assertFalse(bridge.poll_hardware_response()["connected"])
        with patch("hil_bridge.time.monotonic", return_value=5.0):
            heartbeat = bridge.poll_hardware_response()
        self.assertTrue(heartbeat["connected"])
        self.assertTrue(heartbeat["relay_l3_deferrable"])
        with patch("hil_bridge.time.monotonic", return_value=6.1):
            self.assertEqual(bridge.poll_hardware_response()["state"], "HEARTBEAT_LOST")


if __name__ == "__main__":
    unittest.main()
