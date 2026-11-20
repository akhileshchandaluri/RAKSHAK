"""FastAPI endpoints for the original Rakshak command center."""

import asyncio
import os
import secrets
from contextlib import suppress
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hil_bridge import HILBridge
from simulation import ScenarioRequest, SimulationController, compare_modes
from inventory import InventoryStore, ApplianceRequest, ReviewRequest
from field_check import compare_field_events

app = FastAPI(title="Project Rakshak — Grid Resilience Simulator")
default_scenario = ScenarioRequest()
hil_lock = asyncio.Lock()
inventory_store = InventoryStore()
reviewer_token = os.getenv("RAKSHAK_REVIEWER_TOKEN") or secrets.token_urlsafe(24)
if not os.getenv("RAKSHAK_REVIEWER_TOKEN"):
    print("Local reviewer credential (this server session): " + reviewer_token, flush=True)


def frozen_inventory(scenario):
    snapshot = inventory_store.snapshot()
    if scenario.inventory_revision is not None and scenario.inventory_revision != snapshot["revision"]:
        raise HTTPException(409, "Inventory changed. Reset the run to use the latest approved revision.")
    return snapshot


@app.get("/api/appliance-requests")
def list_requests():
    return {"requests": inventory_store.list(), "inventory_revision": inventory_store.snapshot()["revision"]}


@app.post("/api/appliance-requests", status_code=201)
def submit_request(request: ApplianceRequest):
    if request.appliance_id:
        fleet = SimulationController(inventory=inventory_store.snapshot()).fleet
        if request.appliance_id not in fleet.macro_fleet[request.building_id].devices:
            raise HTTPException(422, "Existing appliance ID is not installed in that building")
    return {"id": inventory_store.submit(request), "status": "pending"}


@app.post("/api/appliance-requests/{request_id}/review")
def review_request(request_id: str, review: ReviewRequest, authorization: str = Header(default="")):
    if not secrets.compare_digest(authorization.encode("utf-8"), ("Bearer " + reviewer_token).encode("utf-8")):
        raise HTTPException(401, "Reviewer credential required")
    try:
        return {"revision": inventory_store.review(request_id, review), "status": review.decision}
    except KeyError:
        raise HTTPException(404, "Request not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))



class PlaybackRequest(BaseModel):
    speed: int = Field(default=3, ge=1, le=10)
    playing: bool = True


class ConfigureRequest(PlaybackRequest):
    scenario: ScenarioRequest
    revision: int = Field(ge=0)
    selected: int = Field(default=1, ge=0, lt=12)


@app.get("/api/status")
async def get_status():
    return SimulationController(default_scenario, inventory_store.snapshot()).snapshot()


@app.post("/api/scenario")
async def set_scenario(req: ScenarioRequest):
    global default_scenario
    default_scenario = req
    return {"status": "ok", "mode": req.mode}


@app.post("/api/reset")
async def reset_simulation():
    global default_scenario
    default_scenario = ScenarioRequest()
    return {"status": "reset_complete"}


@app.post("/api/benchmark")
def benchmark(req: ScenarioRequest):
    return {"scenario": req.model_dump(), "results": compare_modes(req, frozen_inventory(req))}


@app.get("/api/replay/presets")
def replay_presets():
    from replay import PRESETS
    return {"presets": PRESETS}


@app.get("/api/replay")
def replay(preset: str):
    from replay import PRESETS, get_replay
    if preset not in PRESETS:
        raise HTTPException(404, "Unknown preset")
    return get_replay(PRESETS[preset], inventory_store.snapshot())


@app.post("/api/replay")
def replay_custom(req: ScenarioRequest):
    from replay import get_replay
    return get_replay(req.model_dump(), frozen_inventory(req))


@app.on_event("startup")
def warm_replays():
    if os.getenv("RAKSHAK_SKIP_PRECOMPUTE"):
        return
    import threading
    from replay import precompute
    threading.Thread(target=precompute, args=(inventory_store.snapshot(),), daemon=True).start()


@app.get("/api/campus")
def campus_model():
    from campus import load_campus
    data = load_campus()
    if data is None:
        raise HTTPException(404, "Campus model not built; run tools/build_campus.py")
    return data


@app.get("/api/paper-results")
def paper_results():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "results" / "paper" / "summary.json"
    if not path.exists():
        raise HTTPException(404, "Run benchmarks/paper_experiments.py first")
    import json as _json
    return _json.loads(path.read_text())


@app.get("/api/calibration")
def calibration_results():
    path = Path(__file__).resolve().parents[1] / "benchmarks" / "results" / "calibration.json"
    if not path.exists():
        raise HTTPException(404, "Run backend/calibration.py first")
    import json as _json
    return _json.loads(path.read_text())


@app.get("/api/field-check")
def field_check():
    return {"comparisons": compare_field_events()}


def board_arming(sim):
    """The bench board stands in for the appliance armed at the smallest contingency level
    (least negative RoCoF), so it reacts to the moderate demonstration events."""
    import math
    armed = getattr(sim.fleet._policy, "armed_rocof", None)
    if armed is None:
        return None
    values = sorted(float(v) for v in armed if math.isfinite(v))
    return values[-1] if values else None


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    sim = SimulationController(default_scenario, inventory_store.snapshot())
    playback = PlaybackRequest()
    revision = 0
    error = None
    hil = HILBridge()
    port = os.getenv("RAKSHAK_HIL_PORT")
    owns_serial = bool(port and not hil_lock.locked())
    if owns_serial:
        await hil_lock.acquire()
    elif port:
        hil.last_hardware_telemetry["state"] = "SERIAL_IN_USE"

    async def receive_controls():
        nonlocal playback, revision, error
        while True:
            try:
                data = await websocket.receive_json()
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                action = data.get("action")
                if action == "CONFIGURE":
                    config = ConfigureRequest.model_validate(data)
                    sim.inventory = frozen_inventory(config.scenario)
                    sim.reset(config.scenario)
                    sim.select(config.selected)
                    playback, revision = config, config.revision
                elif action == "PLAYBACK":
                    playback = PlaybackRequest.model_validate(data)
                elif action == "SELECT":
                    sim.select(int(data["selected"]))
                elif action == "RESET":
                    sim.inventory = inventory_store.snapshot()
                    sim.reset()
                elif action == "SET_MODE":
                    sim.reset(ScenarioRequest.model_validate({**sim.scenario.model_dump(), "mode": data["mode"]}))
                elif action == "SET_PARAMS":
                    mapping = {"loss": "generation_loss", "trec": "t_recover", "thr": "shed_threshold", "H": "grid_inertia_h"}
                    updates = {field: data[key] for key, field in mapping.items() if key in data}
                    sim.reset(ScenarioRequest.model_validate({**sim.scenario.model_dump(), **updates}))
                else:
                    raise ValueError("Unknown simulation action")
            except WebSocketDisconnect:
                return
            except (KeyError, TypeError, ValueError, HTTPException) as exc:
                error = str(exc)

    reader = asyncio.create_task(receive_controls())
    try:
        if owns_serial:
            await asyncio.to_thread(hil.connect, port)
        while not reader.done():
            if playback.playing:
                for _ in range(1 if hil.ser is not None else playback.speed):
                    sim.step()
            if hil.ser is not None:
                if playback.playing and not sim.complete:
                    await asyncio.to_thread(hil.send_grid_state, sim.grid.t, sim.grid.f, sim.grid.compute_rocof(),
                                            board_arming(sim))
                await asyncio.to_thread(hil.poll_hardware_response)
            await websocket.send_json({
                **sim.snapshot(), "revision": revision,
                "playing": playback.playing and not sim.complete, "error": error,
                "hil": {**hil.last_hardware_telemetry, "attached": hil.ser is not None},
            })
            error = None
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        try:
            with suppress(asyncio.CancelledError):
                await reader
        finally:
            if owns_serial:
                await asyncio.to_thread(hil.close)
                hil_lock.release()


app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend", html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000)
