"""Closed-form frequency-nadir prediction for the reheat System Frequency Response model.

All expressions are taken from

    P. M. Anderson and M. Mirheydar, "A low-order system frequency response model,"
    IEEE Transactions on Power Systems, vol. 5, no. 3, pp. 720-729, Aug. 1990.

For a step disturbance P (per unit, positive = generation deficit) the speed deviation is

    dw(t) = -(R P / (D R + K_m)) * [1 + alpha * exp(-zeta w_n t) * sin(w_r t + phi)]

with  w_n^2 = (D R + K_m) / (2 H R T_R)
      zeta  = w_n (2 H R + (D R + K_m F_H) T_R) / (2 (D R + K_m))
      w_r   = w_n sqrt(1 - zeta^2)
      alpha = sqrt((1 - 2 T_R zeta w_n + T_R^2 w_n^2) / (1 - zeta^2))
      phi   = atan2(w_r T_R, 1 - zeta w_n T_R) - atan2(sqrt(1 - zeta^2), -zeta)

The model is linear, so the response to several steps (the disturbance plus relief
actions applied later) is the superposition of individual step responses. That is
the only operation added here; no new frequency formula is introduced.

The initial rate of change of frequency follows the swing equation
df/dt(0+) = -f0 * P / (2 H) (P. Kundur, Power System Stability and Control, 1994,
eq. 3.208 in per-unit form), which gives the standard RoCoF-based disturbance
estimate P = -2 H (df/dt) / f0 used, e.g., by T. Inoue et al., "Estimation of power
system inertia constant and capacity of spinning-reserve support generators using
measured frequency transients," IEEE Trans. Power Syst., 12(1), 1997.
"""

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.linalg import expm


@dataclass(frozen=True)
class SFRParameters:
    H: float = 5.0          # inertia constant (s)
    D: float = 1.0          # load damping (pu/pu)
    R: float = 0.05         # droop (pu)
    T_R: float = 8.0        # reheat time constant (s)
    F_H: float = 0.3        # HP fraction
    K_m: float = 0.95       # mechanical gain
    f0: float = 50.0

    @classmethod
    def from_config(cls, cfg):
        return cls(H=cfg.H, D=cfg.D, R=cfg.governor_droop, T_R=cfg.reheat_time_constant,
                   F_H=cfg.hp_fraction, K_m=cfg.mechanical_gain, f0=cfg.f0)

    # Derived Anderson-Mirheydar quantities
    @property
    def wn(self):
        return math.sqrt((self.D * self.R + self.K_m) / (2 * self.H * self.R * self.T_R))

    @property
    def zeta(self):
        return self.wn * (2 * self.H * self.R + (self.D * self.R + self.K_m * self.F_H) * self.T_R) / (
            2 * (self.D * self.R + self.K_m))

    @property
    def wr(self):
        return self.wn * math.sqrt(1 - self.zeta ** 2)

    @property
    def alpha(self):
        z, wn, tr = self.zeta, self.wn, self.T_R
        return math.sqrt((1 - 2 * tr * z * wn + tr ** 2 * wn ** 2) / (1 - z ** 2))

    @property
    def phi(self):
        z, wn, tr = self.zeta, self.wn, self.T_R
        return math.atan2(self.wr * tr, 1 - z * wn * tr) - math.atan2(math.sqrt(1 - z ** 2), -z)

    @property
    def gain(self):
        return self.R / (self.D * self.R + self.K_m)


def step_response_pu(params, power_pu, t):
    """Speed deviation (pu) at time t after a step of ``power_pu`` (Anderson-Mirheydar eq.).

    Valid for the underdamped case (zeta < 1) treated in the paper."""
    if t <= 0:
        return 0.0
    p = params
    return -p.gain * power_pu * (1 + p.alpha * math.exp(-p.zeta * p.wn * t) * math.sin(p.wr * t + p.phi))


@lru_cache(maxsize=64)
def unit_step_table(params, horizon_s=120.0, dt=0.05):
    """Exact unit-step response of the same SFR transfer function
    G(s) = (R w_n^2 / (D R + K_m)) (1 + T_R s) / (s^2 + 2 zeta w_n s + w_n^2)
    sampled every ``dt`` using the state-space matrix exponential (valid for any zeta).
    Returns y with dw(k dt) = -P * y[k]."""
    p = params
    wn2 = (p.D * p.R + p.K_m) / (2 * p.H * p.R * p.T_R)
    two_zeta_wn = (2 * p.H * p.R + (p.D * p.R + p.K_m * p.F_H) * p.T_R) / (2 * p.H * p.R * p.T_R)
    K = p.R * wn2 / (p.D * p.R + p.K_m)
    A = np.array([[0.0, 1.0], [-wn2, -two_zeta_wn]])
    B = np.array([0.0, 1.0])
    C = np.array([K, K * p.T_R])
    Phi = expm(A * dt)
    Gamma = np.linalg.solve(A, (Phi - np.eye(2)) @ B)
    n = int(round(horizon_s / dt)) + 1
    y = np.empty(n)
    x = np.zeros(2)
    for k in range(n):
        y[k] = C @ x
        x = Phi @ x + Gamma
    y.setflags(write=False)
    return y


def response_series_hz(params, steps, t_from, horizon_s=40.0, dt=0.05, f_start=None):
    """Frequency trajectory (Hz) on [t_from, t_from + horizon] for (time, power_pu) steps,
    by linear superposition of the exact step response."""
    f_start = params.f0 if f_start is None else f_start
    table = unit_step_table(params, max(120.0, horizon_s + 60.0), dt)
    times = t_from + dt * np.arange(int(round(horizon_s / dt)) + 1)
    dw = np.zeros_like(times)
    for t0, power in steps:
        k = np.floor((times - t0) / dt + 1e-9).astype(int)
        valid = k >= 0
        dw[valid] -= power * table[np.minimum(k[valid], len(table) - 1)]
    return times, f_start + params.f0 * dw


def nadir_time_s(params):
    """Time of the first extremum: tan(w_r t_z) = w_r T_R / (zeta w_n T_R - 1)."""
    p = params
    t = math.atan2(p.wr * p.T_R, p.zeta * p.wn * p.T_R - 1) / p.wr
    return t if t > 0 else t + math.pi / p.wr


def nadir_hz(params, power_pu, f_start=None):
    """Nadir frequency (Hz) for a single step from equilibrium: Anderson-Mirheydar closed
    form when underdamped, otherwise the exact sampled response."""
    f_start = params.f0 if f_start is None else f_start
    if params.zeta < 1:
        return f_start + params.f0 * step_response_pu(params, power_pu, nadir_time_s(params))
    return predicted_minimum_hz(params, [(0.0, power_pu)], 0.0, horizon_s=120.0, f_start=f_start)


def predicted_minimum_hz(params, steps, t_from, horizon_s=40.0, resolution_s=0.05, f_start=None):
    """Minimum predicted frequency over [t_from, t_from + horizon]."""
    return float(response_series_hz(params, steps, t_from, horizon_s, resolution_s, f_start)[1].min())


def disturbance_from_rocof(params, rocof_hz_s):
    """RoCoF-based estimate of the step size (Kundur 1994; Inoue et al. 1997)."""
    return -2 * params.H * rocof_hz_s / params.f0


def minimum_relief_pu(params, steps, t_now, threshold_hz, margin_hz=0.05, delay_s=0.0,
                      max_relief_pu=0.5, tolerance_pu=1e-4, f_start=None):
    """Smallest additional relief applied at t_now + delay keeping the predicted minimum
    frequency at or above threshold + margin. Bisection on the monotone superposition.

    Returns (relief_pu, predicted_min_without, predicted_min_with).
    """
    target = threshold_hz + margin_hz
    base = predicted_minimum_hz(params, steps, t_now, f_start=f_start)
    if base >= target:
        return 0.0, base, base
    apply_at = t_now + delay_s

    def minimum_with(relief):
        return predicted_minimum_hz(params, steps + [(apply_at, -relief)], t_now, f_start=f_start)

    if minimum_with(max_relief_pu) < target:
        return max_relief_pu, base, minimum_with(max_relief_pu)
    lo, hi = 0.0, max_relief_pu
    while hi - lo > tolerance_pu:
        mid = (lo + hi) / 2
        if minimum_with(mid) >= target:
            hi = mid
        else:
            lo = mid
    return hi, base, minimum_with(hi)


class SFRObserver:
    """Operator-side copy of the plant used for prediction, including the governor
    dead band and reserve limits of ``GridEngine`` (standard limiters on the
    Anderson-Mirheydar SFR model, see Kundur 1994, ch. 9 and 11).

    * The frequency state is taken from measurement every tick; the unmeasured
      governor/reheat state is integrated with the measured frequency as input.
    * The net power deficit is obtained from the swing equation solved for the power
      imbalance, P_net = P_m - D*dw - 2H*(df/dt)/f0 (Kundur 1994, eq. 3.208), averaged
      over recent ticks.
    * ``predict_minimum`` integrates the same model forward for a vector of candidate
      extra relief values simultaneously (RK4, the integrator used by ``GridEngine``).
    """

    def __init__(self, cfg, inertia_error=0.0, dt=0.05):
        self.cfg = cfg
        self.H = cfg.H * (1 + inertia_error)
        self.dt = dt
        self.f0 = cfg.f0
        self.x0 = 0.0
        self.y = 0.0
        self.t = None
        self.x = 0.0
        self.p_net_history = []
        self.hold = False

    def _command(self, deviation):
        cfg = self.cfg
        error = np.where(np.abs(deviation * cfg.f0) > cfg.governor_deadband_hz, deviation, 0.0)
        return np.clip(-cfg.mechanical_gain * error / cfg.governor_droop, -cfg.down_reserve_pu, cfg.up_reserve_pu)

    def _pm(self, deviation, y):
        return y + self.cfg.hp_fraction * (self._command(deviation) - y)

    def set_equilibrium(self, frequency):
        self.x0 = (frequency - self.f0) / self.f0

    def update(self, now, frequency, rocof):
        x = (frequency - self.f0) / self.f0
        if self.t is not None:
            steps = max(1, int(round((now - self.t) / self.dt)))
            h = (now - self.t) / steps
            for k in range(steps):
                xi = self.x + (x - self.x) * (k + 0.5) / steps
                dev = xi - self.x0
                self.y = float(self.y + h * (self._command(dev) - self.y) / self.cfg.reheat_time_constant)
        self.t, self.x = now, x
        dev = x - self.x0
        p_net = float(self._pm(dev, self.y)) - self.cfg.D * dev - 2 * self.H * rocof / self.f0
        if not self.hold:
            self.p_net_history.append((now, p_net))
        self.hold = False
        return self.deficit()

    def reset_estimate(self, value):
        """Restart the averaging after a known change of the net deficit (an own relief
        or pickup action, or an observed AUFLS operation). The measured RoCoF window still
        straddles that change on the next tick, so that tick is not used."""
        self.p_net_history = [(self.t if self.t is not None else 0.0, value)]
        self.hold = True

    def deficit(self):
        return float(np.mean([p for _, p in self.p_net_history])) if self.p_net_history else 0.0

    def predict_minimum(self, extra_pu, horizon_s=20.0, delay_s=0.0, deficit=None, step_s=0.1):
        """Minimum frequency (Hz) over the horizon for each candidate extra deficit change
        (negative = relief, positive = pickup) applied after ``delay_s``. RK4, inlined."""
        extra = np.atleast_1d(np.asarray(extra_pu, dtype=float))
        p_net = self.deficit() if deficit is None else deficit
        cfg = self.cfg
        h = step_s
        x0, D, two_h = self.x0, cfg.D, 2 * self.H
        fh, tr = cfg.hp_fraction, cfg.reheat_time_constant
        gain = -cfg.mechanical_gain / cfg.governor_droop
        band = cfg.governor_deadband_hz / cfg.f0
        lo_lim, hi_lim = -cfg.down_reserve_pu, cfg.up_reserve_pu
        x = np.full_like(extra, self.x)
        y = np.full_like(extra, self.y)
        lowest = x.copy()

        def deriv(x, y, p):
            dev = x - x0
            command = np.minimum(np.maximum(gain * dev * (np.abs(dev) > band), lo_lim), hi_lim)
            return (y + fh * (command - y) - p - D * dev) / two_h, (command - y) / tr

        n = int(round(horizon_s / h))
        for k in range(n):
            p = p_net + extra if k * h >= delay_s else p_net
            a1, b1 = deriv(x, y, p)
            a2, b2 = deriv(x + 0.5 * h * a1, y + 0.5 * h * b1, p)
            a3, b3 = deriv(x + 0.5 * h * a2, y + 0.5 * h * b2, p)
            a4, b4 = deriv(x + h * a3, y + h * b3, p)
            x = x + (h / 6) * (a1 + 2 * a2 + 2 * a3 + a4)
            y = y + (h / 6) * (b1 + 2 * b2 + 2 * b3 + b4)
            np.minimum(lowest, x, out=lowest)
        return self.f0 * (1 + lowest)

    def minimum_relief(self, target_hz, max_relief_pu, delay_s=0.0, resolution_pu=2e-4):
        """Smallest relief (pu) whose predicted minimum frequency >= target_hz.
        Two vectorised passes over a relief grid (coarse, then fine)."""
        base = float(self.predict_minimum(0.0, delay_s=delay_s)[0])
        if base >= target_hz:
            return 0.0, base, base
        lo, hi = 0.0, max_relief_pu
        for _ in range(3):
            grid = np.linspace(lo, hi, 33)
            minima = self.predict_minimum(-grid, delay_s=delay_s)
            ok = np.nonzero(minima >= target_hz)[0]
            if len(ok) == 0:
                return max_relief_pu, base, float(minima[-1])
            j = ok[0]
            lo, hi = (grid[j - 1] if j > 0 else 0.0), grid[j]
            if hi - lo <= resolution_pu:
                break
        return float(hi), base, float(self.predict_minimum(-hi, delay_s=delay_s)[0])
