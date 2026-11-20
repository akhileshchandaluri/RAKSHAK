"""Baseline Rakshak heuristic (revision 2026-11-13), kept verbatim as a comparison policy.

The relief target ``(load - supply + max(0, 49.90 - f) * 0.08) * baseline`` is the
original project's heuristic. It is retained only as a baseline; it is not a
literature formula. See docs/methods.md for the policies used in the paper.
"""

from fleet_simulator import pseudo_hash_mac
from policies.base import DispatchPolicy


class HeuristicPolicy(DispatchPolicy):
    uses_ufls = True
    dispatches = True

    def __init__(self, staged=True):
        self.staged = staged
        self.name = "rakshak" if staged else "rakshak_unstaggered"

    def dispatch(self, fleet, now, frequency, rocof, supply, available, load, allow_absorption):
        cfg = fleet.cfg
        staged = self.staged
        trigger = frequency <= cfg.threshold_smart_shed or (
            rocof <= cfg.threshold_rocof_severe and frequency < 49.90
        )
        enrolled = [
            (building, device) for building in fleet.macro_fleet
            if building.enrolled and building.energized
            for device in building.devices.values() if device.tier == 2 and device.control and device.consent
        ]
        if trigger:
            budget_w = max(0.0, load - supply + max(0.0, 49.90 - frequency) * 0.08) * fleet.baseline_macro_w
            relief_w = 0.0
            shed = 0
            candidates = sorted(
                ((b, d) for b, d in enrolled if d.is_on and d.eligible(now)),
                key=lambda pair: (
                    -pair[1].absorbing, pair[1].shed_seconds,
                    pair[1].key == "ac", -pair[1].base_w,
                    pair[0].local_freq_offset,
                ),
            )
            fleet.audit = {
                "reason": "Frequency threshold" if frequency <= cfg.threshold_smart_shed else "Falling-frequency trigger",
                "target_w": round(budget_w),
                "available_flexible_w": round(sum(d.get_power_w(now) for _, d in candidates)),
            }
            for building, device in candidates:
                if relief_w >= budget_w:
                    break
                relief_w += device.get_power_w(now)
                device.turn_off(now)
                device.reason = fleet.audit["reason"]
                if device.user_wants:
                    device.shed_at = now
                    delay = (
                        2 + cfg.restore_spread * pseudo_hash_mac(building.mac, f"{fleet.seed}:{device.key}")
                        if staged else 0.0
                    )
                    # Staggering and minimum off time can elapse concurrently.
                    device.restore_at = now + max(device.lockout_duration, delay)
                device.absorbing = False
                shed += 1
            fleet.audit["actual_relief_w"] = round(relief_w)
            fleet.audit["excluded_devices"] = sum(1 for b in fleet.macro_fleet for d in b.devices.values() if not (b.enrolled and b.energized and d.eligible(now)))
            if shed:
                fleet.shed_count += shed
                if fleet.first_shed_at is None:
                    fleet.first_shed_at = now
                fleet._event(now, "shed", f"Shed {shed} enrolled loads ({relief_w / 1000:.1f} kW) at {frequency:.2f} Hz",
                            target_w=fleet.audit["target_w"], eligible_w=fleet.audit["available_flexible_w"],
                            delivered_w=round(relief_w), excluded_devices=fleet.audit["excluded_devices"], trigger=fleet.audit["reason"])
            fleet.largest_relief_shortfall_w = max(fleet.largest_relief_shortfall_w, budget_w - relief_w)
            fleet._update_recovery(now, [d for _, d in enrolled if d.shed_at is not None])
            return

        manage_absorption(fleet, now, frequency, supply, load, enrolled, allow_absorption)

        fleet.audit = {"reason": "Monitoring frequency", "target_w": 0, "available_flexible_w": 0}
        pending = [(b, d) for b, d in enrolled if d.shed_at is not None]
        fleet._update_recovery(now, [d for _, d in pending])
        if fleet.restore_stable_s < cfg.restore_hold_s:
            return
        waiting = sorted(
            ((b, d) for b, d in pending if now >= d.restore_at and d.can_turn_on(now)),
            key=lambda pair: (
                pair[1].shed_at + pair[1].max_pause_s, pair[1].shed_at, pair[0].idx, pair[1].key
            ),
        )
        headroom = max(0.0, available - load)
        restored = 0
        # Convert swing-equation RoCoF to Hz over one dispatch interval.
        response_time = cfg.dispatch_interval_s
        for _, device in waiting:
            pickup = device.base_w * device.inrush_ratio / fleet.baseline_macro_w
            projected = frequency + (supply - load - pickup) * cfg.f0 * response_time / (2 * cfg.H)
            if staged and (pickup > headroom or projected < cfg.restore_guard_hz):
                fleet.recovery["blocked"] += 1
                continue
            if device.turn_on(now):
                device.reason = "Restored after frequency, capacity and lockout checks"
                device.longest_pause_s = max(device.longest_pause_s, now - device.shed_at)
                device.shed_seconds += now - device.shed_at
                device.shed_at = None
                restored += 1
                if staged:
                    headroom -= pickup
                    load += pickup
        if restored:
            fleet.recovery["waiting"] -= restored
            fleet.restore_count += restored
            fleet.last_restore_at = now
            fleet._event(now, "restore", f"Reconnected {restored} eligible loads at {frequency:.2f} Hz")


def manage_absorption(fleet, now, frequency, supply, load, enrolled, allow_absorption):
    """Over-frequency handling shared by all dispatching policies (unchanged baseline logic)."""
    if frequency < 50.03 or not allow_absorption:
        stopped = 0
        for _, device in enrolled:
            if device.absorbing:
                device.turn_off(now)
                device.absorbing = False
                stopped += 1
        if stopped:
            fleet._event(now, "absorption_end", f"Released {stopped} flexible loads")
    if allow_absorption and frequency >= 50.05 and supply > load:
        absorbed = 0
        surplus_w = (supply - load) * fleet.baseline_macro_w
        for _, device in enrolled:
            if device.control == "shift" and not device.user_wants and not device.is_on and device.base_w <= surplus_w:
                if device.turn_on(now):
                    device.absorbing = True
                    surplus_w -= device.base_w
                    absorbed += 1
        if absorbed:
            fleet._event(now, "absorb", f"Started {absorbed} enrolled idle EV loads to absorb surplus")
