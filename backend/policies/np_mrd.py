"""Nadir-Predictive Minimum-Relief Dispatch (NP-MRD).

Decision rule, every dispatch interval:

1. Detect the contingency and estimate the net power deficit from the swing equation
   solved for the imbalance, P = P_m - D*dw - 2H (df/dt)/f0 (Kundur 1994, eq. 3.208;
   the RoCoF-based estimate of Inoue et al. 1997), using an operator-side copy of the
   plant (``nadir_predictor.SFRObserver``) for the unmeasured governor state.
2. Predict the frequency trajectory by integrating the Anderson-Mirheydar (1990) SFR
   model with the same governor dead band and reserve limits as the plant.
3. Find, by a vectorised grid refinement, the smallest additional relief that keeps the
   predicted minimum frequency at or above the first AUFLS stage plus a margin. AUFLS is therefore not triggered when the
   eligible flexible load is sufficient.
4. Choose which appliances supply that relief with a covering 0/1 knapsack
   (Kellerer, Pferschy, Pisinger, "Knapsack Problems", Springer 2004) solved by
   HiGHS through ``scipy.optimize.milp``. The objective is lexicographic:
   first minimise the number of customers newly interrupted (the customer count
   underlying SAIFI, IEEE Std 1366-2022), then prefer appliances with the most
   thermal or charging slack (priority stack, Lu 2012; least laxity, Xu et al. 2016).
5. Restore curtailed appliances when the predicted minimum frequency including the
   restart pickup (rated power x inrush ratio, conservatively held) stays above the
   protection target plus a hysteresis. Appliances that have left their comfort
   band are considered first.

Critical (tier 0) and essential (tier 1) loads are never candidates; only enrolled,
consenting, supported flexible (tier 2) appliances can be curtailed.
"""

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from nadir_predictor import SFRObserver
from policies.base import DispatchPolicy
from policies.heuristic import manage_absorption


class NadirPredictivePolicy(DispatchPolicy):
    name = "np_mrd"
    uses_ufls = True
    dispatches = True

    def __init__(self, margin_hz=0.05, restore_hysteresis_hz=0.05, actuation_delay_s=0.0,
                 inertia_error=0.0, detect_hz=0.02):
        self.margin_hz = margin_hz
        self.restore_hysteresis_hz = restore_hysteresis_hz
        self.actuation_delay_s = actuation_delay_s
        self.inertia_error = inertia_error      # fractional error in the operator's H estimate
        self.detect_hz = detect_hz

    # ------------------------------------------------------------------ state
    def reset(self, fleet, cfg):
        self.observer = SFRObserver(cfg, inertia_error=self.inertia_error)
        self.threshold_hz = cfg.ufls_stages[0]
        self.event_t = None
        self.f_start = None
        self.in_flight = []          # (effective time, deficit change pu) not yet applied
        self.event_households = set()
        self.last_prediction = None
        self.seen_ufls_w = 0.0

    def _pending(self, now):
        self.in_flight = [(t, p) for t, p in self.in_flight if t > now]
        return sum(p for _, p in self.in_flight)

    # ----------------------------------------------------------------- policy
    def dispatch(self, fleet, now, frequency, rocof, supply, available, load, allow_absorption):
        observer = self.observer
        if self.event_t is None:
            if self.f_start is None:
                self.f_start = frequency
                observer.set_equilibrium(frequency)
            if frequency < self.f_start - self.detect_hz or rocof < -0.05:
                self.event_t = now
                observer.p_net_history = []
        ufls_w = sum(fleet.ufls_relief_w)
        if ufls_w > self.seen_ufls_w + 1e-9:
            # AUFLS operated since the last tick: subtract its known relief.
            observer.update(now, frequency, rocof)
            observer.reset_estimate(observer.deficit() - (ufls_w - self.seen_ufls_w) / fleet.baseline_macro_w)
            self.seen_ufls_w = ufls_w
        observer.update(now, frequency, rocof)

        enrolled = [
            (building, device) for building in fleet.macro_fleet
            if building.enrolled and building.energized
            for device in building.devices.values() if device.tier == 2 and device.control and device.consent
        ]
        if self.event_t is None:
            manage_absorption(fleet, now, frequency, supply, load, enrolled, allow_absorption)
            fleet.audit = {"reason": "Monitoring frequency", "target_w": 0, "available_flexible_w": 0,
                           "policy": self.name}
            return

        candidates = [(b, d) for b, d in enrolled if d.is_on and d.eligible(now) and not d.absorbing]
        available_w = sum(d.base_w for _, d in candidates)
        deficit = observer.deficit() + self._pending(now)
        target = self.threshold_hz + self.margin_hz
        # If frequency is already below the target, the best achievable objective is to
        # arrest the decline at the present value.
        effective_target = min(target, frequency - 0.01)
        base = float(observer.predict_minimum(0.0, delay_s=self.actuation_delay_s, deficit=deficit)[0])
        relief_pu = 0.0
        if base < effective_target:
            # Relief beyond the estimated deficit cannot raise the nadir further without
            # creating a surplus (swing-equation balance), so it is capped there.
            max_pu = max(min(available_w / fleet.baseline_macro_w, max(deficit, 0.0) + 0.01), 1e-6)
            relief_pu, _, _ = self._relief(effective_target, max_pu, deficit)
        self.last_prediction = {"time": round(now, 2), "predicted_min_hz": round(base, 3),
                                "target_hz": round(target, 3),
                                "disturbance_estimate_pu": round(deficit, 4)}
        fleet.audit = {
            "reason": "Predicted nadir below AUFLS stage 1 + margin" if relief_pu > 0 else "Prediction within limits",
            "policy": self.name, "target_w": round(relief_pu * fleet.baseline_macro_w),
            "available_flexible_w": round(available_w), **self.last_prediction,
        }
        if relief_pu > 1e-6:
            delivered = self._shed(fleet, now, frequency, candidates, relief_pu * fleet.baseline_macro_w)
            if self.actuation_delay_s == 0:
                observer.reset_estimate(observer.deficit() - delivered / fleet.baseline_macro_w)
        elif base >= target + self.restore_hysteresis_hz:
            picked = self._restore(fleet, now, frequency, enrolled, deficit)
            if picked and self.actuation_delay_s == 0:
                observer.reset_estimate(observer.deficit() + picked / fleet.baseline_macro_w)
        if (frequency >= 49.9 and abs(rocof) < 0.01 and not self.in_flight
                and not any(d.shed_at is not None for _, d in enrolled)):
            self.event_t = None   # event over; resume monitoring
            self.f_start = None
        fleet._update_recovery(now, [d for _, d in enrolled if d.shed_at is not None])

    def _relief(self, target, max_pu, deficit):
        lo, hi = 0.0, max_pu
        for _ in range(3):
            grid = np.linspace(lo, hi, 33)
            minima = self.observer.predict_minimum(-grid, delay_s=self.actuation_delay_s, deficit=deficit)
            ok = np.nonzero(minima >= target)[0]
            if len(ok) == 0:
                return max_pu, None, float(minima[-1])
            j = ok[0]
            lo, hi = (grid[j - 1] if j > 0 else 0.0), grid[j]
            if hi - lo <= 2e-4:
                break
        return float(hi), None, None

    def _select(self, candidates, target_w, now):
        """Covering knapsack: min new customers interrupted, then thermal/charging slack."""
        n = len(candidates)
        households = sorted({b.idx for b, _ in candidates})
        index = {h: j for j, h in enumerate(households)}
        m = len(households)
        risk = np.array([d.thermal.comfort_risk(now) if getattr(d, "thermal", None) else 0.5
                         for _, d in candidates])
        epsilon = 1.0 / (n + 1)
        household_cost = np.array([0.0 if h in self.event_households else 1.0 for h in households])
        c = np.concatenate([epsilon * risk, household_cost])
        power = np.array([d.base_w for _, d in candidates])
        rows = [np.concatenate([power, np.zeros(m)])]
        lower, upper = [target_w], [np.inf]
        link = np.zeros((n, n + m))
        for i, (b, _) in enumerate(candidates):
            link[i, i] = 1.0
            link[i, n + index[b.idx]] = -1.0
        constraints = [LinearConstraint(np.array(rows), lower, upper),
                       LinearConstraint(link, -np.inf, 0.0)]
        result = milp(c, constraints=constraints, integrality=np.ones(n + m),
                      bounds=Bounds(0, 1), options={"time_limit": 0.5})
        if result.x is not None and result.status in (0, 1):
            return [candidates[i] for i in range(n) if result.x[i] > 0.5]
        # Fallback: greedy by power density then slack.
        chosen, total = [], 0.0
        for i in sorted(range(n), key=lambda i: (-power[i], risk[i])):
            if total >= target_w:
                break
            chosen.append(candidates[i])
            total += power[i]
        return chosen

    def _shed(self, fleet, now, frequency, candidates, target_w):
        if not candidates:
            return 0.0
        if sum(d.base_w for _, d in candidates) <= target_w:
            chosen = candidates
        else:
            chosen = self._select(candidates, target_w, now)
        relief_w = 0.0
        for building, device in chosen:
            relief_w += device.base_w
            device.turn_off(now)
            device.reason = "NP-MRD: minimum relief to keep predicted nadir above AUFLS stage 1"
            if device.user_wants:
                device.shed_at = now
                device.restore_at = now + device.lockout_duration
            self.event_households.add(building.idx)
        if self.actuation_delay_s > 0:
            self.in_flight.append((now + self.actuation_delay_s, -relief_w / fleet.baseline_macro_w))
        fleet.shed_count += len(chosen)
        if fleet.first_shed_at is None:
            fleet.first_shed_at = now
        fleet.audit["actual_relief_w"] = round(relief_w)
        fleet.largest_relief_shortfall_w = max(fleet.largest_relief_shortfall_w, target_w - relief_w)
        fleet._event(now, "shed",
                     f"NP-MRD shed {len(chosen)} loads in {len({b.idx for b, _ in chosen})} homes "
                     f"({relief_w / 1000:.1f} kW) at {frequency:.2f} Hz; predicted nadir "
                     f"{self.last_prediction['predicted_min_hz']:.3f} Hz",
                     target_w=round(target_w), delivered_w=round(relief_w), trigger="predicted nadir")
        return relief_w

    def _restore(self, fleet, now, frequency, enrolled, deficit):
        pending = [(b, d) for b, d in enrolled if d.shed_at is not None]
        if not pending:
            return 0.0
        ready = [(b, d) for b, d in pending if now >= d.restore_at and d.can_turn_on(now)]
        if not ready:
            return 0.0
        ready.sort(key=lambda pair: (
            -(pair[1].thermal.must_restore() if getattr(pair[1], "thermal", None) else False),
            -(pair[1].thermal.comfort_risk(now) if getattr(pair[1], "thermal", None) else 0.5),
            pair[1].shed_at, pair[0].idx))
        # Restart pickup held at rated power x inrush ratio (conservative).
        pickups = np.cumsum([d.base_w * d.inrush_ratio for _, d in ready]) / fleet.baseline_macro_w
        minima = self.observer.predict_minimum(pickups, delay_s=self.actuation_delay_s, deficit=deficit)
        floor = self.threshold_hz + self.margin_hz + self.restore_hysteresis_hz
        count = int(np.argmin(minima >= floor)) if not np.all(minima >= floor) else len(ready)
        if count == 0:
            fleet.recovery["blocked"] = len(ready)
            return 0.0
        restored = 0
        picked_w = 0.0
        for _, device in ready[:count]:
            if device.turn_on(now):
                self.in_flight.append((now + self.actuation_delay_s, device.base_w / fleet.baseline_macro_w))
                device.reason = "NP-MRD: restored; predicted frequency stays above protection target"
                device.longest_pause_s = max(device.longest_pause_s, now - device.shed_at)
                device.shed_seconds += now - device.shed_at
                device.shed_at = None
                restored += 1
                picked_w += device.base_w
        if restored:
            fleet.restore_count += restored
            fleet.last_restore_at = now
            fleet._event(now, "restore", f"NP-MRD reconnected {restored} loads at {frequency:.2f} Hz")
        return picked_w
