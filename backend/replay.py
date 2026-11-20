"""Deterministic, scrubbable replays of a scenario for the story, compare and explainer views.

A replay runs the same ``SimulationController`` as the live view and the experiments and
records, every 0.5 s of simulated time:
  t, frequency, RoCoF, demand, generation, the controller's predicted minimum (if any),
  campus building demand (kW), and building state changes, encoded as
  0 supplied, 1 flexible appliance curtailed, 2 feeder open, 3 protected load on backup.
It also returns the complete event log, the decision records written by the policies and
AUFLS, and the final service metrics. Results are cached in var/replays.
"""

import hashlib
import json
import threading
from pathlib import Path

from simulation import DURATION, ScenarioRequest, SimulationController

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "var" / "replays"
FRAME_DT = 0.5

STORY_BASE = dict(campus=True, campus_aufls_stage1=True, generation_loss=0.05, grid_inertia_h=3.0,
                  mechanical_gain=0.15, t_recover=60.0, seed=42)
COMM = dict(comm_latency_s=1.0, comm_jitter_s=0.5, comm_loss=0.4)
PRESETS = {
    "aufls": dict(STORY_BASE, mode="ufls"),
    "threshold": dict(STORY_BASE, mode="rakshak"),
    "npmrd": dict(STORY_BASE, mode="np_mrd"),
    "hybrid": dict(STORY_BASE, mode="hybrid"),
    "npmrd_comms": dict(STORY_BASE, mode="np_mrd", **COMM),
    "hybrid_comms": dict(STORY_BASE, mode="hybrid", **COMM),
    "none": dict(STORY_BASE, mode="none"),
}

_locks = {}
_guard = threading.Lock()


def code_version():
    """Changes whenever model or policy code changes, so stale replays are never served."""
    digest = hashlib.sha256()
    for path in sorted((ROOT / "backend").rglob("*.py")):
        digest.update(path.read_bytes())
    digest.update((ROOT / "data" / "rvce" / "campus.json").read_bytes())
    return digest.hexdigest()[:12]


def _state(building, collapsed):
    if building.on_backup:
        return 3
    if not building.energized or collapsed:
        return 2
    for device in building.devices.values():
        if device.tier == 2 and device.shed_at is not None:
            return 1
    return 0


def build_replay(scenario, inventory=None):
    sim = SimulationController(scenario, inventory)
    fleet, grid = sim.fleet, sim.grid
    previous = [None] * len(fleet.macro_fleet)
    frames = []
    next_frame = 0.0
    while True:
        if grid.t + 1e-9 >= next_frame:
            changes = []
            for i, building in enumerate(fleet.macro_fleet):
                code = _state(building, grid.collapsed)
                if code != previous[i]:
                    changes.append([i, code])
                    previous[i] = code
            now = max(0.0, grid.t - grid.dt)
            prediction = getattr(fleet._policy, "last_prediction", None)
            frames.append({
                "t": round(grid.t, 2), "f": round(grid.f, 4), "r": round(grid.compute_rocof(), 3),
                "l": round(grid.load_pu, 4), "g": round(grid.generation_pu, 4),
                "p": prediction["predicted_min_hz"] if prediction and abs(prediction["time"] - grid.t) <= FRAME_DT else None,
                "k": [round(b.get_total_power_w(now) / 1000 if b.energized and not grid.collapsed else
                            (b.critical_w / 1000 if b.on_backup else 0.0), 1) for b in fleet.campus_buildings],
                "c": changes,
            })
            next_frame += FRAME_DT
        if sim.complete:
            break
        sim.step(measure_nilm=False)
    snapshot = sim.snapshot()
    index = []
    for b in fleet.macro_fleet:
        entry = {"i": b.idx, "type": b.b_type, "critical": b.critical_w > 0, "enrolled": b.enrolled}
        if getattr(b, "campus", None):
            entry["campus_id"] = b.campus["id"]
        index.append(entry)
    return {
        "scenario": scenario.model_dump(), "frame_dt": FRAME_DT, "duration": DURATION,
        "frames": frames, "events": fleet.event_log, "decisions": fleet.decisions,
        "metrics": snapshot["metrics"], "nadir": snapshot["metrics"]["nadir"],
        "buildings": index, "campus_ids": [b.campus["id"] for b in fleet.campus_buildings],
        "aufls_stages_hz": grid.cfg.ufls_stages, "baseline_kw": round(fleet.baseline_macro_w / 1000, 1),
    }


def get_replay(fields, inventory=None):
    scenario = ScenarioRequest.model_validate(fields)
    payload = {"scenario": scenario.model_dump(), "inventory": inventory or {"revision": 0, "items": []}}
    key = hashlib.sha256((json.dumps(payload, sort_keys=True) + code_version()).encode()).hexdigest()[:20]
    path = CACHE / f"{key}.json"
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        if path.exists():
            return json.loads(path.read_text())
        data = build_replay(scenario, inventory)
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")))
        tmp.replace(path)
        return data


def precompute(inventory=None):
    for fields in PRESETS.values():
        get_replay(fields, inventory)
