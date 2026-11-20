"""Shared simulation, scenario validation and benchmark runner."""

from typing import Literal
import numpy as np

from pydantic import BaseModel, Field

from config import GridConfig
from fleet_simulator import FleetSimulator
from grid_engine import GridEngine
from nilm_engine import NILMDisaggregator
from policies import make_policy
from thermal import THERMAL_SPECS, ThermalState

MODES = ("none", "ufls", "rakshak", "rakshak_unstaggered", "np_mrd", "edge", "hybrid")
PolicyName = Literal["none", "ufls", "rakshak", "rakshak_unstaggered", "np_mrd", "edge", "hybrid"]
DURATION = 270.0


class ScenarioRequest(BaseModel):
    mode: PolicyName = "np_mrd"
    disturbance: Literal["generation_loss", "solar_surplus", "demand_surge", "feeder_fault"] = "generation_loss"
    fault_feeder: int = Field(default=0, ge=0, le=3)
    inventory_revision: int | None = Field(default=None, ge=0)
    generation_loss: float = Field(default=0.18, ge=0.0, le=0.35)
    t_recover: float = Field(default=45.0, ge=10, le=180)
    shed_threshold: float = Field(default=49.60, ge=49.2, le=49.9)
    grid_inertia_h: float = Field(default=5.0, ge=3, le=8)
    participation: float = Field(default=1.0, ge=0, le=1)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
    clinical_backup_minutes: float = Field(default=2, ge=0, le=30)
    dynamic_demand: bool = False
    plant: Literal["sfr_reheat", "two_lag"] = "sfr_reheat"
    # NP-MRD settings (see policies/np_mrd.py)
    margin_hz: float = Field(default=0.05, ge=0.0, le=0.5)
    actuation_delay_s: float = Field(default=0.0, ge=0.0, le=5.0)
    inertia_error: float = Field(default=0.0, ge=-0.5, le=0.5)
    # Outdoor temperature for comfort accounting. 32 degC is close to the April mean
    # daily maximum for Bengaluru in IMD climatological normals.
    ambient_c: float = Field(default=32.0, ge=10, le=48)
    # Communication impairments for centrally dispatched policies (np_mrd, hybrid).
    comm_latency_s: float = Field(default=0.0, ge=0.0, le=10.0)
    comm_jitter_s: float = Field(default=0.0, ge=0.0, le=10.0)
    comm_loss: float = Field(default=0.0, ge=0.0, le=0.9)


class SimulationController:
    def __init__(self, scenario=None, inventory=None):
        self.inventory = inventory or {"revision": 0, "items": []}
        self.reset(scenario or ScenarioRequest())

    def reset(self, scenario=None):
        self.scenario = scenario or self.scenario
        cfg = GridConfig(H=self.scenario.grid_inertia_h, threshold_smart_shed=self.scenario.shed_threshold,
                         plant=self.scenario.plant)
        self.grid = GridEngine(cfg)
        self.grid.reset(
            loss=self.scenario.generation_loss, t_rec=self.scenario.t_recover,
            disturbance=self.scenario.disturbance,
        )
        self.fleet = FleetSimulator(cfg, self.scenario.participation, self.scenario.seed,
                                    clinical_backup_minutes=self.scenario.clinical_backup_minutes, inventory=self.inventory)
        if self.scenario.dynamic_demand:
            self.fleet.configure_demand_cycles()
        self.enrolled_count = sum(building.enrolled for building in self.fleet.macro_fleet)
        self.nilm = NILMDisaggregator()
        self.nilm_event = None
        self.selected = 1
        self.protected_buildings = [
            building for building in self.fleet.macro_fleet if building.critical_w > 0
        ]
        self.backup_energy_wh = 0.0
        self.total_unserved_wh = 0.0
        self.requested_energy_wh = 0.0
        self.served_energy_wh = 0.0
        self.fault_active = False
        self.water_buildings = [b for b in self.fleet.macro_fleet if b.tank_l is not None]
        self.fleet._policy = make_policy(self.scenario.mode, **self._policy_options())
        self.fleet._policy.reset(self.fleet, cfg)
        self.thermal_devices = []
        for building in self.fleet.macro_fleet:
            for device in building.devices.values():
                spec = THERMAL_SPECS.get(device.spec.get("catalog_key", device.key))
                device.thermal = ThermalState(spec, self.scenario.ambient_c, power_w=device.base_w) if spec else None
                if spec:
                    self.thermal_devices.append((building, device))
        self.next_thermal = 0.0
        self.curtailed_households = set()
        self.disconnected_households = set()

    def _policy_options(self):
        sc = self.scenario
        if sc.mode not in ("np_mrd", "hybrid"):
            return {}
        return {"margin_hz": sc.margin_hz, "actuation_delay_s": sc.actuation_delay_s,
                "inertia_error": sc.inertia_error, "comm_latency_s": sc.comm_latency_s,
                "comm_jitter_s": sc.comm_jitter_s, "comm_loss": sc.comm_loss, "seed": sc.seed}

    @property
    def complete(self):
        return self.grid.t >= DURATION

    def select(self, index):
        if 0 <= index < len(self.fleet.micro_buildings) and index != self.selected:
            self.selected = index
            self.nilm = NILMDisaggregator()
            self.nilm_event = None

    def step(self, *, measure_nilm=True):
        grid, fleet = self.grid, self.fleet
        if self.complete:
            return
        now = grid.t
        scheduled = grid.get_generation_supply(now)
        fault = self.scenario.disturbance == "feeder_fault" and grid.t_trip <= now < grid.t_rec
        if fault != self.fault_active:
            self.fault_active = fault
            fleet.power_dirty = True
            fleet.faulted_feeder = self.scenario.fault_feeder if fault else None
            blocked = {b.idx for i, group in enumerate(fleet.stage_blocks) if fleet.ufls_feeder_tripped[i] for b in group}
            for b in fleet.macro_fleet:
                if b.feeder_idx == self.scenario.fault_feeder:
                    b.energized = not fault and b.idx not in blocked
                    for d in b.devices.values():
                        if fault and d.is_on and not (d.tier == 0 and b.backup_wh > 0):
                            d.t_off = now
            fleet._event(now, "fault" if fault else "repair", "Local feeder fault isolated" if fault else "Fault repaired; shared restoration permission")
        for b in self.water_buildings:
            if b.tank_l is not None:
                pump = b.devices["water_service_pump"]
                if b.tank_l >= 450 and pump.is_on:
                    fleet.power_dirty = True
                    pump.user_wants = pump.is_on = False
                elif b.tank_l <= 150 and not pump.is_on:
                    fleet.power_dirty = True
                    pump.user_wants = pump.is_on = True
        load = 0.0
        if not grid.collapsed:
            load = fleet.step(
                now, grid.dt, grid.f, grid.compute_rocof(), self.scenario.mode,
                supply=scheduled + grid.pm, available=scheduled + grid.cfg.up_reserve_pu,
                external_demand=grid.demand_disturbance(now),
                recovery_started=now >= grid.t_rec,
                allow_absorption=self.scenario.disturbance == "solar_surplus",
            )
        grid.step(load)
        if fleet.last_restore_at is not None and not grid.collapsed:
            grid.post_shed_peak_load = max(grid.post_shed_peak_load, grid.load_pu)
        if fleet.power_dirty:
            fleet.refresh_power()
        backup = np.zeros(len(fleet.macro_fleet), dtype=bool)
        for building in self.protected_buildings:
            feeder_available = building.energized and not grid.collapsed
            was_on_backup = building.on_backup
            self.backup_energy_wh += building.update_backup(grid.dt, feeder_available)
            backup[building.idx] = building.on_backup
            if was_on_backup and not building.on_backup and not feeder_available:
                for device in building.devices.values():
                    if device.tier == 0 and device.is_on:
                        device.t_off = now
        available = (fleet.energized_array[fleet.device_building] & (not grid.collapsed)) | (fleet.critical_array & backup[fleet.device_building])
        requested = fleet.base_array * fleet.want_array
        supplied = requested * fleet.on_array * available
        missing = requested - supplied
        delta_wh = missing * (grid.dt / 3600)
        self.requested_energy_wh += float(requested.sum()) * grid.dt / 3600
        self.served_energy_wh += float(supplied.sum()) * grid.dt / 3600
        self.total_unserved_wh += float(delta_wh.sum())
        fleet.unserved_array += delta_wh
        fleet.interruption_array += (missing > 0) * grid.dt
        critical_missing = missing * fleet.critical_array
        grid.critical_energy_not_served_wh += float(critical_missing.sum()) * grid.dt / 3600
        grid.medical_minutes_lost += float(((missing > 0) * fleet.medical_quantity).sum()) * grid.dt / 60
        by_building = np.bincount(fleet.device_building, weights=critical_missing, minlength=len(fleet.macro_fleet))
        for building in self.protected_buildings:
            building.critical_unserved_wh += by_building[building.idx] * grid.dt / 3600
            if by_building[building.idx] > 0:
                building.critical_interruption_s += grid.dt
        for building in self.water_buildings:
            inflow = 1.0 if building.energized and not grid.collapsed and building.devices["water_service_pump"].is_on else 0.0
            available_l = building.tank_l + inflow * grid.dt
            delivery = min(available_l, .25 * grid.dt)
            building.tank_l = min(500.0, available_l - delivery)
            building.water_shortfall_l += .25 * grid.dt - delivery
        if now + 1e-9 >= self.next_thermal:
            interval = grid.cfg.dispatch_interval_s
            self.next_thermal = now + interval
            for building, device in self.thermal_devices:
                running = device.is_on and building.energized and not grid.collapsed
                if device.user_wants or device.shed_at is not None:
                    device.thermal.step(interval, running, now)
                if device.shed_at is not None and device.tier == 2 and building.energized:
                    self.curtailed_households.add(building.idx)
            for building in fleet.macro_fleet:
                if not building.energized or grid.collapsed:
                    self.disconnected_households.add(building.idx)
        if measure_nilm:
            building = fleet.micro_buildings[self.selected]
            watts = (building.critical_w if building.on_backup else
                     building.get_total_power_w(now) if not grid.collapsed else 0.0)
            event = self.nilm.feed_sample(grid.t, watts, watts / 230)
            if event is not None:
                self.nilm_event = event

    def service_metrics(self):
        """Customer, comfort and fairness outcomes.

        Customers interrupted follow the customer-count basis of SAIFI (IEEE Std 1366-2022).
        Fairness is Jain's index (Jain, Chiu, Hawe, DEC-TR-301, 1984) of curtailed flexible
        energy over enrolled households that own flexible appliances."""
        fleet = self.fleet
        fleet.sync_metrics()
        per_household = []
        for building in fleet.macro_fleet:
            flexible = [d for d in building.devices.values() if d.tier == 2 and d.control]
            if building.enrolled and flexible:
                per_household.append(sum(d.unserved_wh for d in flexible))
        x = np.array(per_household)
        jain = float(x.sum() ** 2 / (len(x) * (x ** 2).sum())) if len(x) and (x ** 2).sum() > 0 else 1.0
        flexible_unserved_wh = float(sum(d.unserved_wh for b in fleet.macro_fleet
                                         for d in b.devices.values() if d.tier == 2 and d.control))
        protected = [b for b in fleet.macro_fleet if b.critical_w > 0]
        return {
            "households_curtailed": len(self.curtailed_households - self.disconnected_households),
            "households_disconnected": len(self.disconnected_households),
            "customers_interrupted": len(self.curtailed_households | self.disconnected_households),
            "protected_sites_interrupted": sum(1 for b in protected if b.critical_interruption_s > 0),
            "comfort_violation_degmin": round(sum(d.thermal.violation_degmin for _, d in self.thermal_devices), 3),
            "flexible_unserved_wh": round(flexible_unserved_wh, 2),
            "jain_fairness": round(jain, 4),
            "ufls_stages_tripped": sum(1 for w in fleet.ufls_relief_w if w > 0),
        }

    def snapshot(self):
        grid, fleet = self.grid, self.fleet
        fleet.sync_metrics()
        snapshot = grid.get_state()
        snapshot["metrics"].update({
            "total_unserved_wh": round(self.total_unserved_wh, 3),
            "requested_energy_wh": round(self.requested_energy_wh, 3),
            "served_energy_wh": round(self.served_energy_wh, 3),
            "water_shortfall_l": round(sum(b.water_shortfall_l for b in fleet.macro_fleet), 3),
            "feeder_trips": fleet.ufls_trips, "shed_count": fleet.shed_count,
            "restore_count": fleet.restore_count,
            "backup_energy_wh": round(self.backup_energy_wh, 2),
            "relief_shortfall_kw": round(fleet.largest_relief_shortfall_w / 1000, 2),
            **self.service_metrics(),
        })
        headroom = grid.get_generation_supply(grid.t) + grid.cfg.up_reserve_pu - grid.load_pu
        snapshot.update(
            inventory_revision=self.inventory["revision"],
            protection={"profile": grid.cfg.reference_profile, "reference_demand_w": fleet.baseline_macro_w,
                        "stages_hz": grid.cfg.ufls_stages, "relief_fractions": grid.cfg.ufls_relief,
                        "achieved_relief_w": fleet.ufls_relief_w, "delay_s": grid.cfg.ufls_delay_s},
            mode=self.scenario.mode, disturbance=self.scenario.disturbance,
            fleet_size=len(fleet.macro_fleet), enrolled_count=self.enrolled_count, complete=self.complete,
            buildings=[b.snapshot(max(0.0, grid.t - grid.dt), grid.collapsed) for b in fleet.micro_buildings],
            events=list(fleet.events), selected=self.selected, nilm_event=self.nilm_event,
            nilm_breakdown=self.nilm.get_tier_breakdown_w(),
            headroom_pu=round(max(0.0, headroom), 3) if not grid.collapsed else 0.0,
            restoration_hold_s=round(fleet.restore_stable_s, 1),
            restoration=fleet.recovery, dispatch=fleet.audit,
            prediction=getattr(fleet._policy, "last_prediction", None),
        )
        return snapshot


def run_scenario(scenario, *, duration=DURATION, inventory=None, initial_frequency_hz=None):
    sim = SimulationController(scenario, inventory)
    if initial_frequency_hz is not None:
        sim.grid.reset(
            loss=scenario.generation_loss, t_rec=scenario.t_recover,
            disturbance=scenario.disturbance, initial_frequency_hz=initial_frequency_hz,
        )
    traces = {"time": [0.0], "frequency": [sim.grid.f], "load": [1.0]}
    horizon = min(duration, DURATION)
    while sim.grid.t < horizon:
        sim.step(measure_nilm=False)
        if sim.grid.steps % 10 == 0 or sim.grid.t >= horizon:
            traces["time"].append(sim.grid.t)
            traces["frequency"].append(round(sim.grid.f, 3))
            traces["load"].append(round(sim.grid.load_pu, 4))
    snapshot = sim.snapshot()
    pauses = [
        max(device.longest_pause_s, sim.grid.t - device.shed_at if device.shed_at is not None else 0)
        for building in sim.fleet.macro_fleet for device in building.devices.values()
    ]
    return {"mode": scenario.mode, "collapsed": snapshot["collapsed"], **snapshot["metrics"],
            "longest_device_pause_s": round(max(pauses, default=0.0), 2), "trace": traces}


def compare_modes(scenario, inventory=None):
    return [run_scenario(scenario.model_copy(update={"mode": mode}), inventory=inventory) for mode in MODES]
