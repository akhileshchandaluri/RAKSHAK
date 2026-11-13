import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from config import APPLIANCE_CATALOG
from fleet_simulator import FleetSimulator
from inventory import InventoryStore, ApplianceRequest, ReviewRequest
from simulation import SimulationController, ScenarioRequest, run_scenario


class ShowcaseTests(unittest.TestCase):
    def test_showcase_demand_starts_and_stops_in_unmanaged_mode(self):
        sim = SimulationController(ScenarioRequest(
            mode="none", generation_loss=0, dynamic_demand=True,
        ))
        washer = sim.fleet.micro_buildings[0].devices["washer"]
        states = {washer.is_on}
        while sim.grid.t < 270:
            sim.step(measure_nilm=False)
            states.add(washer.is_on)
        self.assertEqual(states, {False, True})
        self.assertFalse(sim.grid.collapsed)
        self.assertGreaterEqual(sim.grid.nadir, 49.90)

    def test_event_initial_frequency_is_in_equilibrium_before_trip(self):
        from grid_engine import GridEngine
        grid = GridEngine()
        grid.reset(initial_frequency_hz=49.95)
        for _ in range(100):
            grid.step(1.0)
        self.assertAlmostEqual(grid.f, 49.95)
        grid.step(1.0)
        self.assertLess(grid.f, 49.95)

    def test_ordinary_is_distinct_from_permission(self):
        for key in ('tv', 'washer', 'microwave', 'reception'):
            self.assertEqual(APPLIANCE_CATALOG[key]['tier'], 3)
        fleet = FleetSimulator()
        for b in fleet.macro_fleet:
            for d in b.devices.values():
                if d.tier in (0, 1, 3):
                    self.assertFalse(d.eligible(1000))

    def test_minimum_on_consent_and_budget(self):
        d = FleetSimulator().micro_buildings[1].devices['ac']
        d.turn_on(0)
        self.assertFalse(d.eligible(10))
        self.assertTrue(d.eligible(61))
        d.consent = False
        self.assertFalse(d.eligible(61))
        d.consent = True
        d.budget_exhausted = True
        self.assertFalse(d.eligible(1000))

    def test_ufls_reference_allocations_and_exclusions(self):
        fleet = FleetSimulator()
        self.assertEqual(fleet.cfg.ufls_stages, [49.4, 49.2, 49.0, 48.8])
        for fraction, group in zip(fleet.cfg.ufls_relief, fleet.stage_blocks):
            watts = sum(b.get_total_power_w(0) for b in group)
            self.assertGreaterEqual(watts, fraction * fleet.baseline_macro_w)
            self.assertLess(watts - fraction * fleet.baseline_macro_w, max(b.get_total_power_w(0) for b in group) + 1)
            self.assertTrue(all(b.b_type not in {'clinic','cold_chain','water_service'} for b in group))
        fleet._step_ufls(0, .05, 49.39, False)
        self.assertEqual(fleet.ufls_trips, 0)
        fleet._step_ufls(.05, .05, 49.39, False)
        self.assertEqual(fleet.ufls_trips, len(fleet.stage_blocks[0]))
        self.assertTrue(fleet.ufls_relief_w[0] > 0)

    def test_same_protection_for_rakshak(self):
        for mode in ('ufls', 'rakshak', 'rakshak_unstaggered'):
            fleet = FleetSimulator(participation=0)
            fleet.step(0, .05, 49.39, 0, mode)
            fleet.step(.05, .05, 49.39, 0, mode)
            self.assertGreater(fleet.ufls_trips, 0)

    def test_local_fault_and_energy_accounting(self):
        sim = SimulationController(ScenarioRequest(disturbance='feeder_fault', t_recover=20, clinical_backup_minutes=.01))
        for _ in range(140): sim.step(measure_nilm=False)
        house, clinic = sim.fleet.micro_buildings[0], sim.fleet.micro_buildings[2]
        self.assertFalse(house.energized)
        self.assertFalse(clinic.energized)
        self.assertFalse(clinic.on_backup)
        self.assertGreater(sim.total_unserved_wh, 0)
        self.assertAlmostEqual(sim.requested_energy_wh, sim.served_energy_wh + sim.total_unserved_wh, places=7)
        self.assertGreater(clinic.critical_unserved_wh, 0)
        self.assertEqual(sim.grid.f, 50.0)
        self.assertEqual(sim.grid.nadir, 50.0)

    def test_water_and_cold_chain_inventory(self):
        sim = SimulationController()
        self.assertEqual(sim.fleet.micro_buildings[8].b_type, 'cold_chain')
        self.assertGreater(sim.fleet.micro_buildings[8].backup_wh, 0)
        self.assertEqual(sim.fleet.micro_buildings[9].tank_l, 250)

    def test_backup_exhaustion_starts_critical_compressor_lockout(self):
        sim = SimulationController(ScenarioRequest(
            disturbance='feeder_fault', t_recover=10, clinical_backup_minutes=.01,
        ))
        clinic = sim.fleet.micro_buildings[2]
        fridge = clinic.devices['vaccine']
        initial_backup = clinic.backup_wh
        while sim.grid.t < 10.5:
            sim.step(measure_nilm=False)
        self.assertTrue(clinic.energized)
        self.assertFalse(fridge.is_on)
        self.assertGreater(fridge.t_off, 5)
        self.assertAlmostEqual(sim.backup_energy_wh, initial_backup - clinic.backup_wh)

    def test_review_orders_same_second_submissions_by_insertion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = InventoryStore(Path(directory) / 'ledger.db')
            request = ApplianceRequest(
                building_id=0, appliance_id='tv', catalog_key='tv', name='Television',
                quantity=1, power_w=100, tier=3, source='https://mepdcl.in/Pages/ConsumptionCalculator',
                justification='Representative utility example',
            )
            review = ReviewRequest(decision='approved', reason='Utility rating reviewed')
            older, newer = store.submit(request), store.submit(request)
            with store.connect() as db:
                db.execute("UPDATE requests SET created='2026-01-01 00:00:00'")
            store.review(older, review)
            store.review(newer, review)
            older, newer = store.submit(request), store.submit(request)
            store.review(newer, review)
            with self.assertRaisesRegex(ValueError, 'conflicting'):
                store.review(older, review)

    def test_cached_power_matches_device_sum(self):
        sim = SimulationController()
        for _ in range(250):
            sim.step(measure_nilm=False)
            now = sim.grid.t - sim.grid.dt
            self.assertAlmostEqual(sim.fleet.total_power(now), sum(b.get_total_power_w(now) for b in sim.fleet.macro_fleet), places=5)

    def test_pending_rejected_approved_and_frozen_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            store = InventoryStore(Path(directory) / 'ledger.db')
            request = ApplianceRequest(building_id=0, catalog_key='tv', name='Second television', quantity=1, power_w=100, tier=3, source='https://mepdcl.in/Pages/ConsumptionCalculator', justification='Utility example for a second television')
            frozen = store.snapshot()
            first = store.submit(request)
            self.assertEqual(store.snapshot(), frozen)
            store.review(first, ReviewRequest(decision='rejected', reason='Duplicate inventory entry'))
            self.assertEqual(store.snapshot(), frozen)
            second = store.submit(request)
            store.review(second, ReviewRequest(decision='approved', reason='Rating and ordinary use reviewed'))
            with self.assertRaises(ValueError): store.review(second, ReviewRequest(decision='approved', reason='Repeated approval attempt'))
            current = InventoryStore(Path(directory) / 'ledger.db').snapshot()
            before, after = SimulationController(inventory=frozen), SimulationController(inventory=current)
            self.assertEqual(len(after.fleet.micro_buildings[0].devices), len(before.fleet.micro_buildings[0].devices)+1)
            self.assertEqual(before.inventory['revision'], 0)

    def test_invalid_source_and_quantity(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApplianceRequest(building_id=0, catalog_key='tv', name='TV', quantity=0, power_w=100, tier=3, source='javascript:alert(1)', justification='Invalid values rejected')

    def test_api_review_permissions_and_stale_revision(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import main
        with tempfile.TemporaryDirectory() as directory:
            store = InventoryStore(Path(directory) / 'api.db')
            with patch.object(main, 'inventory_store', store), patch.object(main, 'reviewer_token', 'test-only-credential'):
                client = TestClient(main.app)
                payload = dict(building_id=0, catalog_key='tv', name='Test TV', quantity=1, power_w=100, tier=3, source='https://mepdcl.in/Pages/ConsumptionCalculator', justification='Test representative utility value')
                response = client.post('/api/appliance-requests', json=payload)
                self.assertEqual(response.status_code, 201)
                request_id = response.json()['id']
                url = '/api/appliance-requests/' + request_id + '/review'
                decision = dict(decision='approved', reason='Evidence and ordinary classification checked')
                self.assertEqual(client.post(url, json=decision).status_code, 401)
                self.assertEqual(store.snapshot()['revision'], 0)
                headers = {'Authorization': 'Bearer test-only-credential'}
                self.assertEqual(client.post(url, json=decision, headers=headers).status_code, 200)
                self.assertEqual(client.post(url, json=decision, headers=headers).status_code, 409)
                self.assertEqual(client.post('/api/benchmark', json={'inventory_revision':0}).status_code, 409)
                with client.websocket_connect('/ws/telemetry') as ws:
                    frame = ws.receive_json()
                    self.assertEqual(frame['inventory_revision'], 1)
                    ws.send_json({'action':'CONFIGURE','revision':8,'scenario':{'inventory_revision':0}})
                    for _ in range(10):
                        frame = ws.receive_json()
                        if frame['error']:
                            break
                    self.assertIsNotNone(frame['error'])

    def test_full_model_timestep_convergence(self):
        values = []
        for dt in (.05, .025):
            sim = SimulationController(ScenarioRequest(generation_loss=.18))
            sim.grid.dt = dt
            while sim.grid.t < 15:
                sim.step(measure_nilm=False)
            values.append(sim.grid.nadir)
        self.assertLess(abs(values[0]-values[1]), .03)


if __name__ == '__main__':
    unittest.main()
