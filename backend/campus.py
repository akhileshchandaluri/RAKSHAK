"""RVCE campus buildings as simulation agents (opt-in, ``ScenarioRequest.campus``).

Each campus footprint in data/rvce/campus.json becomes a BuildingAgent whose average
demand comes from floor area x BEE benchmark EPI (see tools/build_campus.py). The
average is split into
  * room air-conditioning, a declared share ``ac_share`` (default 30 %) of the average,
    represented as 2 kW catalog AC units (same MePDCL rating as the household model),
    which are flexible tier-2 appliances when the campus participates;
  * the remaining building base load (lighting, fans, computing, lifts), tier 3,
    not dispatchable;
  * buildings whose use is "health" carry their whole load on the protected tier-0 bus.
The AC share is an assumption pending RVCE sub-metering, and is swept in sensitivity.
"""

import json
from functools import lru_cache
from pathlib import Path

from config import APPLIANCE_CATALOG

CAMPUS_FILE = Path(__file__).resolve().parents[1] / "data" / "rvce" / "campus.json"


@lru_cache(maxsize=1)
def load_campus():
    return json.loads(CAMPUS_FILE.read_text()) if CAMPUS_FILE.exists() else None


def base_spec(name, watts, tier):
    spec = dict(APPLIANCE_CATALOG["reception"])
    spec.update(name=name, power_w=watts, tier=tier, control="", medical=False, lockout_s=0,
                inrush_ratio=1, min_on_s=0, room="Building",
                source="https://www.beeindia.gov.in/sites/default/files/Flyer_22nd%20Jan.pdf",
                basis="Floor area x BEE EPI (Moderate zone) / 8760 h; RVCE meter data pending",
                evidence_kind="declared_assumption", catalog_key="campus_base")
    return spec


def add_campus(fleet, BuildingAgent, SimulatedDevice, ac_share=0.30):
    data = load_campus()
    if not data:
        return []
    added = []
    start = len(fleet.macro_fleet)
    for k, b in enumerate(x for x in data["buildings"] if x["campus"]):
        idx = start + k
        agent = BuildingAgent(idx, "campus", idx % 4, False, 1.0, fleet.seed, fleet.participation)
        agent.campus = b
        average_w = b["average_kw"] * 1000
        if b["use"] == "health":
            agent.devices = {"campus_base": SimulatedDevice("campus_base", 1, spec=base_spec(b["name"] or "Health", average_w, 0))}
        else:
            ac_units = max(0, round(ac_share * average_w / APPLIANCE_CATALOG["ac"]["power_w"]))
            base_w = max(0.0, average_w - ac_units * APPLIANCE_CATALOG["ac"]["power_w"])
            agent.devices = {"campus_base": SimulatedDevice("campus_base", 1, spec=base_spec(b["name"] or "Block", base_w, 3))}
            if ac_units:
                agent.devices["ac"] = SimulatedDevice("ac", ac_units, user_wants=True)
        fleet.macro_fleet.append(agent)
        added.append(agent)
    return added
