"""Appliance and feeder state for the 500-building Rakshak simulation."""

import hashlib
import math
import numpy as np
from collections import deque

from config import APPLIANCE_CATALOG, GridConfig


def pseudo_hash_mac(mac, salt="rakshak"):
    digest = hashlib.sha256(f"{mac}:{salt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") / 2**32


class SimulatedDevice:
    def __init__(self, key, multiplier=1.0, has_device=True, user_wants=True, spec=None, consent=True):
        spec = spec or APPLIANCE_CATALOG[key]
        self.spec = spec
        self.consent = consent
        self.min_on_s = spec.get("min_on_s", 0)
        self.interruption_s = 0.0
        self.unserved_wh = 0.0
        self.budget_exhausted = False
        self.outage_pending = False
        self.reason = "User requested" if user_wants else "User idle"
        self.key, self.name, self.tier = key, spec["name"], spec["tier"]
        self.quantity = multiplier
        self.base_w = spec["power_w"] * multiplier
        self.control = spec["control"]
        self.medical = spec["medical"]
        self.shed_seconds = 0.0
        self.longest_pause_s = 0.0
        self.max_pause_s = spec.get("max_pause_s", 0)
        self.inrush_ratio, self.tau = spec["inrush_ratio"], spec["tau_inrush"]
        self.lockout_duration = spec["lockout_s"]
        self.has_device, self.user_wants = has_device, user_wants
        self.is_on = has_device and user_wants
        self.t_on = self.t_off = float("-inf")
        self.shed_at = None
        self.restore_at = 0.0
        self.absorbing = False

    def eligible(self, now):
        return (self.tier == 2 and bool(self.control) and self.consent and not self.budget_exhausted
                and now - self.t_on >= self.min_on_s)

    def turn_off(self, now):
        if self.tier in (0, 1):
            return False
        if self.is_on:
            self.is_on = False
            self.t_off = now

    def can_turn_on(self, now):
        return now - self.t_off >= self.lockout_duration

    def turn_on(self, now):
        if not self.can_turn_on(now):
            return False
        self.is_on = True
        self.t_on = now
        return True

    def get_power_w(self, now):
        if not self.is_on:
            return 0.0
        elapsed = now - self.t_on
        if elapsed > 12 * self.tau or self.inrush_ratio == 1.0:
            return self.base_w
        return self.base_w * (1 + (self.inrush_ratio - 1) * math.exp(-elapsed / self.tau))


class BuildingAgent:
    def __init__(self, idx, b_type, feeder_idx, is_medical=False, mult=1.0, seed=42, participation=1.0):
        self.idx, self.b_type, self.feeder_idx, self.is_medical = idx, b_type, feeder_idx, is_medical
        self.mac = f"A4:CF:12:{idx >> 16 & 255:02X}:{idx >> 8 & 255:02X}:{idx & 255:02X}"
        self.energized = True
        self.enrolled = pseudo_hash_mac(self.mac, str(seed)) < participation
        self.local_freq_offset = math.sin(idx * 1.7) * 0.015
        # Seeded urban stress-case inventories and coincident usage, not survey estimates.
        def owns(key, fraction):
            return pseudo_hash_mac(self.mac, f"inventory:{seed}:{key}") < fraction

        def requested(key, fraction):
            return pseudo_hash_mac(self.mac, f"usage:{seed}:{key}") < fraction

        if b_type == "cold_chain":
            inventory = {"vaccine": (3, True), "clinical_lights": (2, True), "reception": (1, True)}
        elif b_type == "water_service":
            inventory = {"water_service_pump": (1, True), "lights": (2, True)}
        elif b_type == "clinic":
            inventory = {"o2": (2, True), "monitor": (2, True), "ventilator": (1, True),
                         "vaccine": (1, True), "clinical_lights": (10, True),
                         "clinical_ventilation": (1, True), "reception": (1, True),
                         "staff_heater": (1, requested("staff_heater", 0.15))}
        elif b_type == "shop":
            inventory = {"lights": (6, True), "fan": (2, True), "fridge": (1, True),
                         "reception": (1, True), "ac": (1, requested("ac", 0.75))}
        else:
            units = int(mult)
            inventory = {"lights": (4 * units, True), "fan": (2 * units, True),
                         "fridge": (units, requested("fridge", 0.55)),
                         "tv": (units, requested("tv", 0.5)),
                         "washer": (units, requested("washer", 0.12)),
                         "microwave": (units, requested("microwave", 0.06)),
                         "pump": (1, requested("pump", 0.12))}
            for key, ownership, use in (("ac", 0.55, 0.65), ("heater", 0.50, 0.22), ("ev", 0.08, 0.35)):
                if owns(key, ownership) or idx == 1:
                    inventory[key] = (units if key != "ev" else 1, requested(key, use))
            if is_medical:
                inventory["o2"] = (1, True)
        self.devices = {
            key: SimulatedDevice(key, quantity, user_wants=on)
            for key, (quantity, on) in inventory.items()
        }
        self.tank_l = 250.0 if b_type == "water_service" else None
        self.water_shortfall_l = 0.0
        self.critical_unserved_wh = 0.0
        self.critical_interruption_s = 0.0
        self.backup_wh = 0.0
        self.on_backup = False
        self.critical_w = sum(d.base_w for d in self.devices.values() if d.tier == 0 and d.user_wants)

    def update_backup(self, dt, feeder_available):
        # Idealized no-break, protected-bus-only supply. Deduct energy on island.
        running_w = sum(d.base_w for d in self.devices.values() if d.tier == 0 and d.is_on)
        step_wh = running_w * dt / 3600
        self.on_backup = not feeder_available and step_wh > 0 and self.backup_wh + 1e-10 >= step_wh
        if self.on_backup:
            self.backup_wh = max(0.0, self.backup_wh - step_wh)
            return step_wh
        return 0.0

    def get_total_power_w(self, now):
        return sum(device.get_power_w(now) for device in self.devices.values()) if self.energized else 0.0

    def snapshot(self, now, collapsed):
        energized = self.energized and not collapsed
        appliances = {}
        for key, device in self.devices.items():
            spec = device.spec
            served = energized or (device.tier == 0 and self.on_backup)
            appliances[key] = {
                "on": device.is_on and served, "requested": device.user_wants or device.absorbing,
                "rated_w": device.base_w, "quantity": device.quantity,
                "power_w": round(device.get_power_w(now) if energized else device.base_w, 1)
                if device.is_on and served else 0.0,
                "lockout_s": round(max(0, device.lockout_duration - (now - device.t_off)), 1),
                "waiting": device.shed_at is not None, "tier": device.tier,
                "supply": "grid" if energized else "backup" if served else "unavailable",
                "eligible": bool(device.eligible(now) and self.enrolled and energized),
                "appliance_id": key, "consent": device.consent, "approval_state": "approved",
                "catalog_key": spec.get("catalog_key", key),
                "unit_power_w": spec["power_w"], "evidence_kind": spec.get("evidence_kind", "declared_assumption"),
                "reason": ("User idle" if not device.user_wants and not device.absorbing else
                           "Study frequency cutoff reached; grid unavailable" if collapsed and not served else
                           "Feeder disconnected; no local supply" if not served else
                           "Protected backup bus supplying requested load" if self.on_backup and device.tier == 0 else device.reason),
                "unserved_wh": device.unserved_wh,
                "interruption_s": device.interruption_s, "budget_exhausted": device.budget_exhausted,
                "name": device.name, "room": spec["room"], "basis": spec["basis"],
                "source": spec["source"],
            }
        return {
            "i": self.idx, "type": self.b_type, "energized": energized,
            "power_w": round(sum(a["power_w"] for a in appliances.values()), 1),
            "devices": {key: appliance["on"] for key, appliance in appliances.items()},
            "appliances": appliances, "feeder": self.feeder_idx, "mac": self.mac,
            "continuity": {"requested_w": self.critical_w, "supplied_w": sum(a["power_w"] for a in appliances.values() if a["tier"] == 0),
                           "unserved_wh": self.critical_unserved_wh, "interruption_s": self.critical_interruption_s,
                           "backup_remaining_wh": self.backup_wh},
            "tank_l": self.tank_l, "water_shortfall_l": self.water_shortfall_l,
            "is_med": self.is_medical, "enrolled": self.enrolled, "on_backup": self.on_backup,
        }



class FleetSimulator:
    def __init__(self, config=None, participation=1.0, seed=42, size=500, clinical_backup_minutes=0, inventory=None):
        self.cfg = config or GridConfig()
        self.participation, self.seed, self.size = participation, seed, size
        self.clinical_backup_minutes = clinical_backup_minutes
        self.inventory = inventory or {"revision": 0, "items": []}
        self.init_fleet()

    def configure_demand_cycles(self):
        # Short illustrative sessions for the showcase. Compressor sessions
        # still obey the catalog's minimum on/off times.
        periods = {
            "tv": (100, 90), "washer": (120, 100), "microwave": (35, 120),
            "ac": (180, 180), "heater": (75, 150), "ev": (210, 120),
        }
        self.demand_cycles = []
        # Animate the showcase street. The background fleet represents a
        # steady aggregate so accelerated schedules do not synchronize it.
        for building, device in self.device_pairs:
            if building.idx >= len(self.micro_buildings):
                continue
            if device.key not in periods or device.tier == 0 or device.spec.get("catalog_key"):
                continue
            on_s, idle_s = periods[device.key]
            first = 25 + 120 * pseudo_hash_mac(building.mac, f"demand:{self.seed}:{device.key}")
            self.demand_cycles.append([first, on_s, idle_s, building, device])

    def update_demand(self, now):
        for cycle in self.demand_cycles:
            next_change, on_s, idle_s, building, device = cycle
            if now < next_change:
                continue
            if device.user_wants and device.is_on and now - device.t_on < device.min_on_s:
                cycle[0] = device.t_on + device.min_on_s
                continue
            device.user_wants = not device.user_wants
            cycle[0] = now + (on_s if device.user_wants else idle_s)
            self.power_dirty = True
            if device.user_wants:
                device.absorbing = False
                device.reason = "Scheduled demand started"
                continue
            if device.is_on:
                device.is_on = False
                device.t_off = now
            if device.shed_at is not None:
                pause = now - device.shed_at
                device.longest_pause_s = max(device.longest_pause_s, pause)
                device.shed_seconds += pause
                device.shed_at = None
            device.absorbing = device.outage_pending = False
            device.reason = "Scheduled demand ended"

    def init_fleet(self):
        types = ["house", "house", "clinic", "house", "shop", "house",
                 "house", "apartment", "cold_chain", "water_service", "house", "house"]
        weights = {"house": 1.0, "clinic": 2.5, "shop": 1.5, "apartment": 4.0, "cold_chain": 1.0, "water_service": 1.0}
        self.micro_buildings = [
            BuildingAgent(i, kind, i // 3, kind in {"clinic", "cold_chain"} or i == 1,
                          weights[kind], self.seed, self.participation)
            for i, kind in enumerate(types)
        ]
        self.macro_fleet = list(self.micro_buildings)
        for i in range(len(types), self.size):
            kind = "apartment" if i % 20 == 0 else "clinic" if i % 50 == 0 else "house"
            self.macro_fleet.append(BuildingAgent(
                i, kind, i % 4, kind == "clinic" or i % 100 == 1,
                weights[kind], self.seed, self.participation,
            ))
        for item in self.inventory["items"]:
            if item["building_id"] >= len(self.macro_fleet):
                continue
            building = self.macro_fleet[item["building_id"]]
            key = item.get("appliance_id") or "custom_" + item["request_id"]
            spec = dict(APPLIANCE_CATALOG.get(item["catalog_key"], APPLIANCE_CATALOG["reception"]))
            spec.update(name=item["name"], power_w=item["power_w"], tier=item["tier"], source=item["source"],
                        basis=item["justification"], evidence_kind="reviewed_submission",
                        catalog_key=item["catalog_key"])
            if item["catalog_key"] == "custom":
                spec.update(control="", medical=False, lockout_s=0, inrush_ratio=1, min_on_s=0)
            building.devices[key] = SimulatedDevice(key, item["quantity"], user_wants=item["requested"], spec=spec, consent=item["consent"])
        for building in self.macro_fleet:
            building.critical_w = sum(d.base_w for d in building.devices.values() if d.tier == 0 and d.user_wants)
            building.is_medical = any(d.medical for d in building.devices.values())
            if building.b_type in {"clinic", "cold_chain"}:
                building.backup_wh = building.critical_w * self.clinical_backup_minutes / 60
        self.baseline_macro_w = sum(b.get_total_power_w(0.0) for b in self.macro_fleet)
        self.ufls_feeder_tripped = [False] * 4
        self.stage_blocks = []
        remaining = [b for b in self.macro_fleet if b.b_type not in {"clinic", "cold_chain", "water_service"}]
        for fraction in self.cfg.ufls_relief:
            group, watts = [], 0.0
            while remaining and watts < fraction * self.baseline_macro_w:
                b = remaining.pop(0)
                group.append(b)
                watts += b.get_total_power_w(0)
            self.stage_blocks.append(group)
        self.ufls_relief_w = [0.0] * 4
        self.faulted_feeder = None
        self.ufls_stage_timers = [0.0] * 4
        self.ufls_trips = 0
        self.restore_stable_s = 0.0
        self.next_dispatch = 0.0
        self.first_shed_at = None
        self.last_restore_at = None
        self.shed_count = self.restore_count = 0
        self.events = deque(maxlen=12)
        self.audit = {"reason": "Monitoring frequency", "target_w": 0, "available_flexible_w": 0}
        self.recovery = {"waiting": 0, "lockout": 0, "stagger": 0, "blocked": 0}
        self.largest_relief_shortfall_w = 0.0
        self.device_pairs = [(b, d) for b in self.macro_fleet for d in b.devices.values()]
        self.device_building = np.array([b.idx for b,d in self.device_pairs])
        self.base_array = np.array([d.base_w for b,d in self.device_pairs])
        self.critical_array = np.array([d.tier == 0 for b,d in self.device_pairs])
        self.medical_quantity = np.array([d.quantity if d.medical else 0 for b,d in self.device_pairs])
        self.unserved_array = np.zeros(len(self.device_pairs))
        self.interruption_array = np.zeros(len(self.device_pairs))
        self.next_maintenance = 0.0
        self.power_dirty = True
        self.demand_cycles = []

    def refresh_power(self):
        pairs = self.device_pairs
        self.on_array = np.array([d.is_on for b,d in pairs])
        self.want_array = np.array([d.user_wants for b,d in pairs])
        self.t_on_array = np.array([d.t_on for b,d in pairs])
        self.inrush_array = np.array([d.inrush_ratio - 1 for b,d in pairs])
        self.tau_array = np.array([d.tau for b,d in pairs])
        self.energized_array = np.array([b.energized for b in self.macro_fleet])
        self.power_dirty = False

    def total_power(self, now):
        if self.power_dirty:
            self.refresh_power()
        startup = np.exp(-np.minimum(100, np.maximum(0, now-self.t_on_array) / self.tau_array))
        return float(np.sum(self.base_array * self.on_array * self.energized_array[self.device_building] * (1+self.inrush_array*startup)))

    def sync_metrics(self):
        for i, (b,d) in enumerate(self.device_pairs):
            d.unserved_wh = float(self.unserved_array[i])
            d.interruption_s = float(self.interruption_array[i])

    def _event(self, now, action, reason, **details):
        self.events.append({"time": round(now, 2), "action": action, "reason": reason, **details})

    def _step_ufls(self, now, dt, frequency, recovery_started):
        for stage, threshold in enumerate(self.cfg.ufls_stages):
            if self.ufls_feeder_tripped[stage]:
                continue
            self.ufls_stage_timers[stage] = self.ufls_stage_timers[stage] + dt if frequency <= threshold else 0.0
            if self.ufls_stage_timers[stage] + 1e-9 >= self.cfg.ufls_delay_s:
                self.power_dirty = True
                self.ufls_feeder_tripped[stage] = True
                group = self.stage_blocks[stage]
                self.ufls_relief_w[stage] += sum(b.get_total_power_w(now) for b in group)
                self.ufls_trips += len(group)
                for building in group:
                    building.energized = False
                    for device in building.devices.values():
                        if device.is_on and not (device.tier == 0 and building.backup_wh > 0):
                            device.t_off = now
                self.first_shed_at = now if self.first_shed_at is None else self.first_shed_at
                self._event(now, "feeder_trip", f"AUFLS stage {stage+1}: {len(group)} modeled blocks opened at {frequency:.3f} Hz")
        if any(self.ufls_feeder_tripped) and recovery_started and self.restore_stable_s >= 10.0:
            # Shared illustrative operator permission after generation recovery and stability.
            for building in self.macro_fleet:
                if not building.energized and building.feeder_idx != self.faulted_feeder:
                    building.energized = True
                    for device in building.devices.values():
                        if device.is_on:
                            device.t_on = now
            self.power_dirty = True
            self.ufls_feeder_tripped = [False] * 4
            self.ufls_stage_timers = [0.0] * 4
            self.restore_stable_s = 0.0
            self.last_restore_at = now
            self._event(now, "feeder_restore", "Shared simulated operator permission: generation recovered and stable for 10 s")

    def _policy_for(self, mode):
        """Resolve a policy name once and keep its state for the whole run."""
        from policies import make_policy
        cached = getattr(self, "_policy", None)
        if cached is not None and (cached is mode or cached.name == mode):
            return cached
        self._policy = make_policy(mode)
        self._policy.reset(self, self.cfg)
        return self._policy

    def _dispatch(self, now, frequency, rocof, mode, supply, available, load, allow_absorption):
        """Backward-compatible entry point used by tests and older scripts."""
        self._policy_for(mode).dispatch(self, now, frequency, rocof, supply, available, load, allow_absorption)

    def _update_recovery(self, now, devices):
        self.recovery = {
            "waiting": len(devices),
            "lockout": sum(not d.can_turn_on(now) for d in devices),
            "stagger": sum(d.can_turn_on(now) and now < d.restore_at for d in devices),
            "blocked": 0,
        }

    def step(self, current_t, dt, grid_freq, rocof, mode, *, supply=1.0, available=1.0,
             external_demand=0.0, recovery_started=False, allow_absorption=False):
        policy = self._policy_for(mode)
        self.update_demand(current_t)
        if grid_freq >= self.cfg.threshold_recover and abs(rocof) < 0.10:
            self.restore_stable_s += dt
        else:
            self.restore_stable_s = 0.0
        if policy.uses_ufls:
            self._step_ufls(current_t, dt, grid_freq, recovery_started)
        if self.power_dirty or current_t + 1e-9 >= self.next_maintenance:
            self.next_maintenance = current_t + self.cfg.dispatch_interval_s
            self.power_dirty = True
            for b in self.macro_fleet:
                for d in b.devices.values():
                    if d.shed_at is not None and d.max_pause_s and current_t - d.shed_at >= d.max_pause_s:
                        d.budget_exhausted = True
                        d.reason = "Interruption budget exhausted; awaiting safe restoration"
                    if b.energized and d.is_on and not d.can_turn_on(current_t):
                        d.outage_pending = True
                        d.is_on = False
                        d.shed_at = current_t if d.shed_at is None else d.shed_at
                        d.restore_at = d.t_off + d.lockout_duration
                        d.reason = "Compressor restart lockout after supply interruption"
                    if b.energized and not d.is_on and d.user_wants and d.shed_at is not None and (d.tier != 2 or d.outage_pending) and d.can_turn_on(current_t):
                        d.turn_on(current_t)
                        d.longest_pause_s = max(d.longest_pause_s, current_t - d.shed_at)
                        d.outage_pending = False
                        d.shed_at = None
                    if b.energized and d.user_wants and not d.is_on and d.shed_at is None and d.can_turn_on(current_t):
                        d.turn_on(current_t)
                        d.reason = "Requested load started after supply and lockout checks"
        total_w = self.total_power(current_t)
        if policy.dispatches and current_t + 1e-9 >= self.next_dispatch:
            self.next_dispatch = current_t + self.cfg.dispatch_interval_s
            policy.dispatch(self, current_t, grid_freq, rocof, supply, available,
                            total_w / self.baseline_macro_w + external_demand, allow_absorption)
            self.power_dirty = True
            total_w = self.total_power(current_t)
        return total_w / self.baseline_macro_w
