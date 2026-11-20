"""
Project Rakshak - Global Configuration & Simulation Constants
Aligned with SDG 11: Sustainable Cities and Communities
"""

import json
from pathlib import Path

from pydantic import BaseModel


class GridConfig(BaseModel):
    # Nominal Grid Parameters
    f0: float = 50.0                # Nominal frequency (Hz)
    H: float = 5.0                  # Grid inertia constant (seconds)
    D: float = 1.0                  # Load damping factor
    # Plant model. "sfr_reheat" is the low-order System Frequency Response model of
    # P. M. Anderson and M. Mirheydar, "A low-order system frequency response model,"
    # IEEE Trans. Power Syst., vol. 5, no. 3, pp. 720-729, 1990. Defaults for T_R,
    # F_H and K_m are the typical reheat-unit values reported in that paper.
    # "two_lag" is the earlier Rakshak governor + turbine lag model, kept for parity.
    plant: str = "sfr_reheat"
    reheat_time_constant: float = 8.0   # T_R (s), Anderson & Mirheydar 1990
    hp_fraction: float = 0.3            # F_H, high-pressure turbine power fraction
    mechanical_gain: float = 0.95       # K_m, mechanical power gain factor
    governor_droop: float = 0.05    # Governor speed regulation (5%)
    governor_time_constant: float = 0.5  # Governor valve lag (s)
    turbine_time_constant: float = 0.4
    governor_deadband_hz: float = 0.03
    up_reserve_pu: float = 0.15
    down_reserve_pu: float = 0.30
    f_collapse: float = 47.5        # Numerical study cutoff; not a universal generator trip setting

    # Protection & Shedding Thresholds
    threshold_smart_shed: float = 49.60   # Rakshak primary shedding threshold (Hz)
    threshold_rocof_severe: float = -0.50 # RoCoF (Hz/s) for predictive early trip
    threshold_recover: float = 49.90      # Grid frequency considered recovered (Hz)

    # UFLS (Under-Frequency Load Shedding) Feeder Stages
    ufls_stages: list[float] = [49.4, 49.2, 49.0, 48.8]

    ufls_relief: list[float] = [0.05, 0.06, 0.07, 0.07]
    ufls_delay_s: float = 0.10  # Illustrative relay dwell
    reference_profile: str = "SRPC task force 2024-03-27, scaled reference-demand emulator"

    # Staggered Restoration Parameters
    restore_spread: float = 40.0   # Max delay spread (seconds) for randomized MAC hashing
    restore_hold_s: float = 3.0
    restore_guard_hz: float = 49.85
    dispatch_interval_s: float = 0.5


# Canonical catalog used by Python and the standalone browser demo.
_catalog = Path(__file__).resolve().parents[1] / "frontend" / "appliance-catalog.js"
APPLIANCE_CATALOG = json.loads(
    _catalog.read_text(encoding="utf-8-sig").strip()
    .removeprefix("const APPLIANCE_CATALOG = ").removesuffix(";")
)
