"""Reduced-order single-area frequency model for the Rakshak simulator."""

from collections import deque

from config import GridConfig


class GridEngine:
    def __init__(self, config: GridConfig | None = None):
        self.cfg = config or GridConfig()
        self.reset()

    def reset(
        self, loss=0.18, t_trip=5.0, t_rec=45.0, ramp=30.0,
        disturbance="generation_loss", initial_frequency_hz=None,
    ):
        self.steps = 0
        self.t = 0.0
        self.dt = 0.05
        self.x = self.pg = self.pm = 0.0
        self.f = self.cfg.f0 if initial_frequency_hz is None else initial_frequency_hz
        self.x = self.initial_x = (self.f - self.cfg.f0) / self.cfg.f0
        self.loss, self.t_trip, self.t_rec, self.ramp = loss, t_trip, t_rec, ramp
        self.disturbance = disturbance
        self.collapsed = False
        self.history_f = deque([self.f], maxlen=5)
        self.nadir = self.zenith = self.f
        self.max_rocof = 0.0
        self.recovery_time = self.recovery_start = None
        self.out_of_band = False
        self.blackout_events = 0
        self.critical_energy_not_served_wh = 0.0
        self.medical_minutes_lost = 0.0
        self.post_shed_peak_load = 0.0
        self.generation_pu = self.load_pu = 1.0

    def compute_rocof(self, window_points=5):
        window = min(window_points, len(self.history_f))
        return (
            (self.history_f[-1] - self.history_f[-window]) / ((window - 1) * self.dt)
            if window > 1 else 0.0
        )

    def disturbance_magnitude(self, time_s):
        if time_s < self.t_trip:
            return 0.0
        return self.loss * max(0.0, 1.0 - max(0.0, time_s - self.t_rec) / self.ramp)

    def get_generation_supply(self, time_s):
        magnitude = self.disturbance_magnitude(time_s)
        if self.disturbance == "solar_surplus":
            return 1.0 + magnitude
        return 1.0 - magnitude if self.disturbance == "generation_loss" else 1.0

    def demand_disturbance(self, time_s):
        return self.disturbance_magnitude(time_s) if self.disturbance == "demand_surge" else 0.0

    def step(self, total_load_pu):
        """Integrate frequency, governor and turbine state using held absolute demand."""
        cfg = self.cfg
        supply = self.get_generation_supply(self.t)
        demand = total_load_pu + self.demand_disturbance(self.t)
        if not self.collapsed and self.disturbance == "feeder_fault":
            # Local distribution fault against an ideal stiff upstream grid.
            # This scenario studies continuity, not island frequency dynamics.
            self.x = self.pg = self.pm = 0.0
            self.f = cfg.f0
        elif not self.collapsed:
            def derivatives(state):
                x, governor, turbine = state
                # Model incremental governor and demand response around the
                # pre-disturbance operating point.
                deviation = x - self.initial_x
                error = deviation if abs(deviation * cfg.f0) > cfg.governor_deadband_hz else 0.0
                target = max(-cfg.down_reserve_pu, min(cfg.up_reserve_pu, -error / cfg.governor_droop))
                return (
                    (supply + turbine - demand - cfg.D * deviation) / (2.0 * cfg.H),
                    (target - governor) / cfg.governor_time_constant,
                    (governor - turbine) / cfg.turbine_time_constant,
                )

            state = (self.x, self.pg, self.pm)
            a = derivatives(state)
            b = derivatives(tuple(y + self.dt * dy / 2 for y, dy in zip(state, a)))
            c = derivatives(tuple(y + self.dt * dy / 2 for y, dy in zip(state, b)))
            d = derivatives(tuple(y + self.dt * dy for y, dy in zip(state, c)))
            self.x, self.pg, self.pm = (
                y + self.dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
                for y, k1, k2, k3, k4 in zip(state, a, b, c, d)
            )
            self.f = cfg.f0 * (1.0 + self.x)
            if self.f <= cfg.f_collapse:
                self.collapsed = True
                self.blackout_events += 1
                self.f = cfg.f_collapse

        self.generation_pu = 0.0 if self.collapsed else demand if self.disturbance == "feeder_fault" else supply + self.pm
        self.load_pu = 0.0 if self.collapsed else demand
        self.history_f.append(self.f)
        self.steps += 1
        self.t = self.steps * self.dt
        if self.t > self.t_trip:
            self.nadir = min(self.nadir, self.f)
            self.zenith = max(self.zenith, self.f)
            self.max_rocof = max(self.max_rocof, abs(self.compute_rocof()))
            if not self.collapsed and cfg.threshold_recover <= self.f <= 50.05:
                if self.out_of_band and self.recovery_start is None:
                    self.recovery_start = self.t
                if self.recovery_start is not None and self.t - self.recovery_start >= cfg.restore_hold_s:
                    self.recovery_time = self.recovery_start - self.t_trip
            else:
                self.out_of_band = True
                self.recovery_start = self.recovery_time = None
        return self.get_state()

    def get_state(self, total_load_pu=None):
        return {
            "time": round(self.t, 2),
            "frequency": round(self.f, 3),
            "rocof": round(self.compute_rocof(), 3),
            "generation_pu": round(self.generation_pu, 3),
            "load_pu": round(self.load_pu if total_load_pu is None else total_load_pu, 3),
            "collapsed": self.collapsed,
            "metrics": {
                "nadir": round(self.nadir, 3),
                "zenith": round(self.zenith, 3),
                "max_rocof": round(self.max_rocof, 3),
                "recovery_time": round(self.recovery_time, 2) if self.recovery_time is not None else None,
                "critical_energy_not_served_wh": round(self.critical_energy_not_served_wh, 2),
                "medical_minutes_lost": round(self.medical_minutes_lost, 3),
                "peak_post_shed_load": round(self.post_shed_peak_load, 3),
                "blackout_events": self.blackout_events,
            },
        }
