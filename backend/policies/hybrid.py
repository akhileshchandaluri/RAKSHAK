"""Hybrid policy: pre-armed graded appliance relief with local RoCoF triggering,
refined by central NP-MRD.

Structure follows special protection / remedial action schemes, in which the control
centre arms load-shedding actions in advance and local devices execute them on a
measured trigger without waiting for communication:
  P. M. Anderson and B. K. LeReverend, "Industry experience with special protection
  schemes," IEEE Trans. Power Syst., 11(3), pp. 1166-1179, 1996.

Arming (central, periodic, before any event, over the impaired channel):
  for a ladder of contingency sizes P_k the controller computes, with the same SFR
  predictor used by NP-MRD, the minimum relief R_k that keeps the predicted nadir at or
  above AUFLS stage 1 + margin when relief starts after the local detection delay. The
  appliance sets are nested (level k adds to level k-1) and chosen by the same covering
  knapsack. The set added at level k is needed for every contingency larger than
  P_(k-1), so each appliance stores the RoCoF the model predicts for P_(k-1),
  measured over the same first 0.2 s window the appliance uses.
Triggering (local): an armed appliance trips when its own RoCoF measurement is at or
  below its armed value, i.e. when the observed contingency is at least as large.
Refinement (central): NP-MRD continues as usual; it restores surplus relief and adds
  more if needed, subject to channel latency and loss.
"""

import numpy as np

from nadir_predictor import SFRObserver
from policies.np_mrd import NadirPredictivePolicy

LEVELS_PU = tuple(round(0.01 * k, 2) for k in range(1, 31))   # 0.01 ... 0.30


class HybridPolicy(NadirPredictivePolicy):
    name = "hybrid"

    def __init__(self, arm_period_s=30.0, resend_period_s=1.0, detection_s=0.25, **options):
        super().__init__(**options)
        self.arm_period_s, self.resend_period_s, self.detection_s = arm_period_s, resend_period_s, detection_s

    def reset(self, fleet, cfg):
        super().reset(fleet, cfg)
        self.cfg = cfg
        self.pairs = [(b, d) for b in fleet.macro_fleet if b.enrolled
                      for d in b.devices.values() if d.tier == 2 and d.control and d.consent]
        self.index = {id(d): i for i, (_, d) in enumerate(self.pairs)}
        self.armed_rocof = np.full(len(self.pairs), -np.inf)     # -inf = not armed
        self.offset = np.array([b.local_freq_offset for b, _ in self.pairs])
        self.history = []
        self.next_arm = 0.0
        self.next_resend = 0.0
        self.plan = {}
        self.local_trips = 0

    # ---------------------------------------------------------------- arming
    def _plan(self, fleet, now):
        observer = SFRObserver(self.cfg, inertia_error=self.inertia_error)
        observer.set_equilibrium(self.cfg.f0)
        observer.update(0.0, self.cfg.f0, 0.0)
        target = self.threshold_hz + self.margin_hz
        candidates = [(b, d) for b, d in self.pairs if b.energized and d.is_on and d.eligible(now)]
        chosen_ids, armed_w, plan = set(), 0.0, {}
        previous_rocof = 0.0
        for level in LEVELS_PU:
            max_pu = sum(d.base_w for _, d in candidates) / fleet.baseline_macro_w
            observer.p_net_history = [(0.0, level)]
            relief_pu, _, _ = observer.minimum_relief(target, max(max_pu, 1e-6), delay_s=self.detection_s)
            need_w = relief_pu * fleet.baseline_macro_w - armed_w
            trajectory = observer.trajectory(level, 0.25)
            rocof = (trajectory[4] - trajectory[0]) / 0.2   # first 0.2 s window, as measured locally
            trigger, previous_rocof = previous_rocof, rocof
            if need_w > 0:
                pool = [(b, d) for b, d in candidates if id(d) not in chosen_ids]
                if not pool:
                    break
                extra = pool if sum(d.base_w for _, d in pool) <= need_w else self._select(pool, need_w, now)
                for b, d in extra:
                    chosen_ids.add(id(d))
                    plan[id(d)] = (b, d, trigger)
                    armed_w += d.base_w
        return plan

    def _arm(self, fleet, now):
        """Broadcast the cached plan; lost messages are repaired by the next resend."""
        plan = self.plan
        for i, (b, d) in enumerate(self.pairs):
            entry = plan.get(id(d))
            self._send(fleet, now, "arm", b, d, entry[2] if entry else -np.inf)

    def _send(self, fleet, now, action, building, device, value=None):
        if action != "arm":
            return super()._send(fleet, now, action, building, device)
        if self.channel.ideal:
            self.armed_rocof[self.index[id(device)]] = value
        else:
            self.channel.send(now, ("arm", building, device, value))

    def on_step(self, fleet, now, frequency):
        self.observer.track(now, frequency)
        for payload in self.channel.due(now):
            if payload[0] == "arm":
                self.armed_rocof[self.index[id(payload[2])]] = payload[3]
            else:
                self._apply(fleet, now, *payload)
        # Local measurement: RoCoF over a 0.2 s window (five 50 ms samples).
        self.history.append(frequency)
        self.history = self.history[-5:]
        if len(self.history) < 5 or self.event_t is not None and now - self.event_t > 3.0:
            return
        local_rocof = (self.history[-1] - self.history[0]) / 0.2
        trip = np.nonzero(local_rocof < self.armed_rocof)[0]
        count = 0
        for i in trip:
            building, device = self.pairs[i]
            self.armed_rocof[i] = -np.inf
            if not (building.energized and device.is_on and device.eligible(now)):
                continue
            device.turn_off(now)
            device.absorbing = False
            if device.user_wants:
                device.shed_at = now
                device.restore_at = now + device.lockout_duration
            device.reason = "Hybrid: pre-armed local RoCoF trigger"
            self.event_households.add(building.idx)
            count += 1
        if count:
            self.local_trips += count
            fleet.shed_count += count
            fleet.power_dirty = True
            fleet.first_shed_at = now if fleet.first_shed_at is None else fleet.first_shed_at
            fleet._event(now, "shed", f"{count} pre-armed appliances tripped locally (RoCoF {local_rocof:.3f} Hz/s)",
                         trigger="pre-armed local")

    def dispatch(self, fleet, now, frequency, rocof, supply, available, load, allow_absorption):
        if self.event_t is None:
            if now + 1e-9 >= self.next_arm:
                self.next_arm = now + self.arm_period_s
                self.plan = self._plan(fleet, now)
            if now + 1e-9 >= self.next_resend:
                self.next_resend = now + self.resend_period_s
                self._arm(fleet, now)
        super().dispatch(fleet, now, frequency, rocof, supply, available, load, allow_absorption)
