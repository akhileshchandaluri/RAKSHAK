"""Decentralised (edge) under-frequency response of appliance controllers.

Each enrolled flexible appliance carries a local under-frequency relay. Trip thresholds
are spread uniformly across a band so that the aggregate response approximates a
droop characteristic, the decentralised scheme of
  A. Molina-Garcia, F. Bouffard, D. S. Kirschen, "Decentralized demand-side
  contribution to primary frequency control," IEEE Trans. Power Syst., 26(1), 2011,
building on the dynamic-demand concept of
  J. A. Short, D. G. Infield, L. L. Freris, "Stabilization of grid frequency through
  dynamic demand control," IEEE Trans. Power Syst., 22(3), 2007.
Reconnection waits for frequency to re-enter the IEGC normal band (>= 49.90 Hz, CERC
IEGC 2023) and then a randomised hold, the de-synchronisation remedy discussed by
  K. Sinitsyn, S. Kundu, S. Backhaus, "Safe protocols for generating power pulses
  with heterogeneous populations of thermostatically controlled loads," Energy
  Conversion and Management, 67, 2013.

Thresholds and holds are derived per device from a hash of its MAC and the seed, so
runs are reproducible. Local measurement differs from the area frequency by the
building's ``local_freq_offset`` (declared measurement error, +/- 15 mHz).
"""

import numpy as np

from fleet_simulator import pseudo_hash_mac
from policies.base import DispatchPolicy


class EdgeLayer:
    def __init__(self, band_hz=(49.45, 49.80), dwell_s=0.1, hold_s=(5.0, 40.0), reconnect_hz=49.90,
                 tag="edge"):
        self.band_hz, self.dwell_s, self.hold_s = band_hz, dwell_s, hold_s
        self.reconnect_hz, self.tag = reconnect_hz, tag

    def reset(self, fleet):
        self.pairs = [(b, d) for b in fleet.macro_fleet if b.enrolled
                      for d in b.devices.values() if d.tier == 2 and d.control and d.consent]
        lo, hi = self.band_hz
        self.threshold = np.array([lo + (hi - lo) * pseudo_hash_mac(b.mac, f"edge:{fleet.seed}:{d.key}")
                                   for b, d in self.pairs])
        self.hold = np.array([self.hold_s[0] + (self.hold_s[1] - self.hold_s[0]) *
                              pseudo_hash_mac(b.mac, f"hold:{fleet.seed}:{d.key}") for b, d in self.pairs])
        self.offset = np.array([b.local_freq_offset for b, _ in self.pairs])
        self.below = np.zeros(len(self.pairs))
        self.normal = np.zeros(len(self.pairs))
        self.tripped = np.zeros(len(self.pairs), dtype=bool)

    def step(self, fleet, now, frequency, dt, armed=None):
        if not self.pairs:
            return 0
        local = frequency + self.offset
        self.below = np.where(local <= self.threshold, self.below + dt, 0.0)
        self.normal = np.where(local >= self.reconnect_hz, self.normal + dt, 0.0)
        trips = 0
        for i in np.nonzero((self.below + 1e-9 >= self.dwell_s) & ~self.tripped)[0]:
            if armed is not None and not armed[i]:
                continue
            building, device = self.pairs[i]
            if not (building.energized and device.is_on and device.eligible(now)):
                continue
            device.turn_off(now)
            device.absorbing = False
            if device.user_wants:
                device.shed_at = now
                device.restore_at = now + device.lockout_duration
            device.reason = f"{self.tag}: local relay at {self.threshold[i]:.3f} Hz"
            device.edge_tripped = True
            self.tripped[i] = True
            trips += 1
        restored = 0
        for i in np.nonzero(self.tripped & (self.normal >= self.hold))[0]:
            building, device = self.pairs[i]
            if device.shed_at is None:
                self.tripped[i] = False
                continue
            if building.energized and now >= device.restore_at and device.can_turn_on(now) and device.turn_on(now):
                device.longest_pause_s = max(device.longest_pause_s, now - device.shed_at)
                device.shed_seconds += now - device.shed_at
                device.shed_at = None
                device.edge_tripped = False
                device.reason = f"{self.tag}: reconnected after randomised hold"
                self.tripped[i] = False
                restored += 1
        if trips:
            fleet.shed_count += trips
            fleet.first_shed_at = now if fleet.first_shed_at is None else fleet.first_shed_at
            fleet.power_dirty = True
            fleet._event(now, "shed", f"{trips} appliances opened local under-frequency relays at {frequency:.2f} Hz",
                         trigger=self.tag)
        if restored:
            fleet.restore_count += restored
            fleet.last_restore_at = now
            fleet.power_dirty = True
            fleet._event(now, "restore", f"{restored} appliances reconnected locally")
        return trips


class EdgePolicy(DispatchPolicy):
    """Every enrolled flexible appliance responds autonomously; no central dispatch."""
    name = "edge"
    uses_ufls = True
    dispatches = False

    def __init__(self, **options):
        self.layer = EdgeLayer(**options)
        self.last_t = None

    def reset(self, fleet, cfg):
        self.layer.reset(fleet)
        self.dt = 0.05

    def on_step(self, fleet, now, frequency):
        dt = 0.05 if self.last_t is None else now - self.last_t
        self.last_t = now
        self.layer.step(fleet, now, frequency, dt)
