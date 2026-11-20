"""First-order equivalent-thermal-parameter (ETP) states used for comfort accounting.

Model (first-order ETP, exact discretisation), as used for thermostatic loads by
  D. S. Callaway, "Tapping the energy storage potential in electric loads to deliver
  load following and regulation, with application to wind energy," Energy Conversion
  and Management, 50(5), 2009, and
  J. L. Mathieu, S. Koch, D. S. Callaway, "State estimation and control of electric
  loads to manage real-time energy imbalance," IEEE Trans. Power Syst., 28(1), 2013:

    theta[k+1] = a * theta[k] + (1 - a) * (theta_a - m * theta_g),   a = exp(-h / (C R))

where m = 1 while the appliance runs and 0 while it is curtailed, and theta_g is the
temperature gain of the running appliance. We take theta_g so that the running
steady state equals the user's set point (theta_a - theta_g = theta_set for cooling,
theta_a + theta_g = theta_set for heating), i.e. the appliance is assumed to hold its
set point when it is supplied, which matches the constant-power appliance load model.

Comfort is reported as degree-minutes outside the comfort band; ranking curtailment
candidates by their position in the band is the "priority stack" of
  N. Lu, "An evaluation of the HVAC load potential for providing load balancing
  service," IEEE Trans. Smart Grid, 3(3), 2012.

Electric vehicles use charging laxity (time slack before the requested energy can no
longer be delivered), as in least-laxity-first EV scheduling, e.g.
  Y. Xu, F. Pan, L. Tong, "Dynamic scheduling for charging electric vehicles: a
  priority rule," IEEE Trans. Automatic Control, 61(12), 2016.
"""

import math
from dataclasses import dataclass


@dataclass
class ThermalSpec:
    kind: str               # "cooling" | "heating" | "ev"
    tau_s: float            # C*R time constant (s)
    set_point_c: float
    band_c: float           # half-width of comfort band around the set point
    source: str


# Parameter values. Each entry states its basis; see docs/methods.md.
THERMAL_SPECS = {
    # Room AC. C = 10 kWh/degC and R = 2 degC/kW are the TCL parameters tabulated by
    # Mathieu, Koch and Callaway (2013) -> C*R = 20 h. Set point 24 degC is the BEE
    # default-temperature notification for room ACs (S.O. 4426(E), 2019/2020).
    # The 1 degC half band is the illustrative dead band of Mathieu et al. (0.5 degC)
    # widened to an occupant band; it is a declared assumption with sensitivity.
    "ac": ThermalSpec("cooling", 20 * 3600, 24.0, 1.0,
                      "Mathieu, Koch, Callaway, IEEE TPWRS 28(1) 2013 (C, R); BEE AC default 24 degC"),
    # Storage water heater (geyser), 25 L, one-node tank. Standby loss 0.75 kWh/24 h at
    # 45 K difference is of the order of the BEE star-label limits for storage water
    # heaters; UA = 0.75 kWh / 24 h / 45 K = 0.69 W/K, C = 25 kg * 4186 J/kgK.
    "heater": ThermalSpec("heating", 25 * 4186 / (750 / 24 / 45), 60.0, 5.0,
                          "One-node tank model (Dolan, Nehrir, Gerez, IEEE TEC 11(1) 1996); BEE storage water heater standby-loss schedule"),
    "staff_heater": ThermalSpec("heating", 25 * 4186 / (750 / 24 / 45), 60.0, 5.0,
                                "Same as heater"),
    "ev": ThermalSpec("ev", 0.0, 0.0, 0.0,
                      "Least-laxity priority, Xu, Pan, Tong, IEEE TAC 61(12) 2016"),
}


class ThermalState:
    """Temperature (or EV laxity) state of one appliance."""

    def __init__(self, spec, ambient_c, ev_energy_kwh=10.0, ev_deadline_s=4 * 3600, power_w=3300):
        self.spec = spec
        self.ambient_c = ambient_c
        self.temperature_c = spec.set_point_c
        self.violation_degmin = 0.0
        # EV: requested energy and departure deadline (declared scenario assumption).
        self.ev_remaining_kwh = ev_energy_kwh
        self.ev_deadline_s = ev_deadline_s
        self.ev_power_kw = power_w / 1000

    def step(self, dt, running, now):
        spec = self.spec
        if spec.kind == "ev":
            if running:
                self.ev_remaining_kwh = max(0.0, self.ev_remaining_kwh - self.ev_power_kw * dt / 3600)
            return
        a = math.exp(-dt / spec.tau_s)
        if spec.kind == "cooling":
            gain = self.ambient_c - spec.set_point_c
            target = self.ambient_c - (gain if running else 0.0)
        else:
            gain = spec.set_point_c - self.ambient_c
            target = self.ambient_c + (gain if running else 0.0)
        self.temperature_c = a * self.temperature_c + (1 - a) * target
        excess = self.outside_band_c()
        self.violation_degmin += excess * dt / 60

    def outside_band_c(self):
        spec = self.spec
        if spec.kind == "cooling":
            return max(0.0, self.temperature_c - (spec.set_point_c + spec.band_c))
        if spec.kind == "heating":
            return max(0.0, (spec.set_point_c - spec.band_c) - self.temperature_c)
        return 0.0

    def comfort_risk(self, now):
        """Normalised position in the band (0 = most slack, 1 = at the band edge).
        For EVs: 1 - laxity / deadline."""
        spec = self.spec
        if spec.kind == "ev":
            time_needed = self.ev_remaining_kwh / max(self.ev_power_kw, 1e-9) * 3600
            laxity = max(0.0, self.ev_deadline_s - now - time_needed)
            return 1.0 - min(1.0, laxity / max(self.ev_deadline_s, 1.0))
        if spec.kind == "cooling":
            position = (self.temperature_c - (spec.set_point_c - spec.band_c)) / (2 * spec.band_c)
        else:
            position = ((spec.set_point_c + spec.band_c) - self.temperature_c) / (2 * spec.band_c)
        return min(1.0, max(0.0, position))

    def must_restore(self):
        if self.spec.kind == "ev":
            return False
        return self.outside_band_c() > 0
