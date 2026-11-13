"""Explainable event detection from simulated aggregate active power."""

from config import APPLIANCE_CATALOG


class NILMDisaggregator:
    def __init__(self, sample_rate_hz=20.0):
        self.previous_w = None
        self.last_event_s = float("-inf")
        self.active_appliances = {key: False for key in APPLIANCE_CATALOG}

    def feed_sample(self, timestamp, aggregate_power_w, aggregate_current_a=None):
        previous = self.previous_w
        self.previous_w = aggregate_power_w
        if previous is None or timestamp - self.last_event_s < 0.25:
            return None
        delta = aggregate_power_w - previous
        if abs(delta) < 60:
            return None
        self.last_event_s = timestamp
        distances = []
        for key, spec in APPLIANCE_CATALOG.items():
            signature = spec["power_w"]
            if delta > 0:
                distance = min(abs(delta - signature), abs(delta - signature * spec["inrush_ratio"]))
            else:
                distance = abs(abs(delta) - signature)
            if distance <= max(20, 0.15 * signature):
                distances.append((distance / signature, key))
        distances.sort()
        match = distances[0][1] if distances else None
        classification = "matched" if match else "unknown"
        if len(distances) > 1 and distances[1][0] - distances[0][0] < 0.08:
            match, classification = None, "ambiguous"
        if match:
            self.active_appliances[match] = delta > 0
        return {
            "timestamp": round(timestamp, 2), "type": "LOAD_ON" if delta > 0 else "LOAD_OFF",
            "name": APPLIANCE_CATALOG[match]["name"] if match else None,
            "appliance": match, "classification": classification,
            "confidence": round(max(0, 1 - 4 * distances[0][0]), 2) if match else None,
            "delta_p": round(delta, 1),
        }

    def get_tier_breakdown_w(self):
        names = ("tier_0_critical", "tier_1_essential", "tier_2_deferrable", "tier_3_ordinary")
        totals = dict.fromkeys(names, 0.0)
        for key, active in self.active_appliances.items():
            spec = APPLIANCE_CATALOG[key]
            if active:
                totals[names[spec["tier"]]] += spec["power_w"]
        return totals
