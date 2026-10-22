from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Rakshak Digital Twin API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

NOMINAL_HZ = 50.0
SHED_THRESHOLD_HZ = 49.6
RESTORE_THRESHOLD_HZ = 50.0


def initial_state() -> dict[str, Any]:
    return {
        "timestamp": time.time(),
        "running": True,
        "mode": "simulation",
        "frequencyHz": NOMINAL_HZ,
        "solarKw": 8.0,
        "demandKw": 12.0,
        "generationKw": 12.0,
        "shedThresholdHz": SHED_THRESHOLD_HZ,
        "restoreThresholdHz": RESTORE_THRESHOLD_HZ,
        "balancingEnabled": True,
        "disturbance": "none",
        "disturbanceSeconds": 0,
        "events": ["Twin initialised. Simulation mode active."],
        "buildings": [
            {
                "id": "home-01", "name": "Residential Block A", "kind": "residential",
                "x": -5, "z": 0, "powerKw": 4.0, "status": "online",
                "appliances": [
                    {"id": "critical-light", "name": "Critical lighting", "tier": 1, "powerKw": 0.2, "status": "on"},
                    {"id": "fan-01", "name": "DC fan", "tier": 2, "powerKw": 0.5, "status": "on"},
                    {"id": "ac-01", "name": "Air conditioner (proxy)", "tier": 3, "powerKw": 1.5, "status": "on"},
                ],
            },
            {
                "id": "clinic-01", "name": "Community Clinic", "kind": "clinic",
                "x": 0, "z": -4, "powerKw": 3.0, "status": "online",
                "appliances": [
                    {"id": "medical-01", "name": "Critical medical proxy", "tier": 1, "powerKw": 0.3, "status": "on"},
                    {"id": "clinic-fan", "name": "Ventilation fan", "tier": 2, "powerKw": 0.4, "status": "on"},
                    {"id": "water-heater", "name": "Water heater (proxy)", "tier": 3, "powerKw": 1.0, "status": "on"},
                ],
            },
            {
                "id": "office-01", "name": "Office & EV Charging", "kind": "office",
                "x": 5, "z": 0, "powerKw": 5.0, "status": "online",
                "appliances": [
                    {"id": "security-01", "name": "Security / networking", "tier": 1, "powerKw": 0.2, "status": "on"},
                    {"id": "office-fan", "name": "Office fan", "tier": 2, "powerKw": 0.5, "status": "on"},
                    {"id": "ev-01", "name": "EV charger (proxy)", "tier": 3, "powerKw": 2.0, "status": "on"},
                ],
            },
        ],
        "metrics": {
            "frequencyNadirHz": NOMINAL_HZ,
            "recoverySeconds": None,
            "shedActions": 0,
            "energyNotServedCriticalKwh": 0.0,
            "reboundPeakKw": 0.0,
        },
    }


STATE = initial_state()
HISTORY: list[dict[str, float]] = []
LAST_TICK = time.monotonic()


class ScenarioRequest(BaseModel):
    scenario: str


class ControlRequest(BaseModel):
    balancingEnabled: bool


def log_event(message: str) -> None:
    STATE["events"].insert(0, message)
    STATE["events"] = STATE["events"][:12]


def all_appliances():
    for building in STATE["buildings"]:
        for appliance in building["appliances"]:
            yield appliance


def current_load_kw() -> float:
    return sum(a["powerKw"] for a in all_appliances() if a["status"] == "on")


def set_disturbance(scenario: str) -> None:
    allowed = {"solar_drop", "demand_surge", "none"}
    if scenario not in allowed:
        raise ValueError(f"Unknown scenario: {scenario}")
    STATE["disturbance"] = scenario
    STATE["disturbanceSeconds"] = 0
    if scenario == "solar_drop":
        STATE["solarKw"] = 2.0
        log_event("Solar-generation drop injected.")
    elif scenario == "demand_surge":
        STATE["demandKw"] = 16.0
        log_event("Demand surge injected.")
    else:
        STATE["solarKw"] = 8.0
        STATE["demandKw"] = 12.0
        for appliance in all_appliances():
            appliance["status"] = "on"
        STATE["metrics"]["recoverySeconds"] = None
        log_event("Scenario reset; proxy loads restored.")


def tick(dt: float = 0.1) -> None:
    # Simplified illustrative dynamics: frequency moves with generation-demand imbalance.
    # This is a demo model, not a grid-code or engineering-grade simulator.
    STATE["timestamp"] = time.time()
    STATE["disturbanceSeconds"] += dt
    active_load = current_load_kw()
    STATE["generationKw"] = 8.0 + STATE["solarKw"]
    imbalance = STATE["generationKw"] - active_load
    target_delta = max(-1.0, min(1.0, imbalance * 0.035))
    # Restore toward nominal when balance is near zero; clamp to plausible demo range.
    target = NOMINAL_HZ + target_delta
    if STATE["disturbance"] != "none":
        target -= min(0.9, STATE["disturbanceSeconds"] * 0.018)
    if STATE["disturbance"] == "none":
        target = NOMINAL_HZ
    STATE["frequencyHz"] += (target - STATE["frequencyHz"]) * min(1.0, dt * 1.6)
    STATE["frequencyHz"] = max(48.0, min(50.5, STATE["frequencyHz"]))

    metrics = STATE["metrics"]
    metrics["frequencyNadirHz"] = min(metrics["frequencyNadirHz"], STATE["frequencyHz"])

    if STATE["balancingEnabled"] and STATE["frequencyHz"] <= SHED_THRESHOLD_HZ:
        candidates = [a for a in all_appliances() if a["tier"] == 3 and a["status"] == "on"]
        if candidates:
            # Deterministic lowest-priority-first shedding for the starter implementation.
            candidate = max(candidates, key=lambda a: a["powerKw"])
            candidate["status"] = "off"
            metrics["shedActions"] += 1
            log_event(f"Shed {candidate['name']} at {STATE['frequencyHz']:.2f} Hz.")

    if STATE["disturbance"] == "none" and abs(STATE["frequencyHz"] - NOMINAL_HZ) < 0.03:
        metrics["frequencyNadirHz"] = NOMINAL_HZ

    HISTORY.append({
        "t": round(STATE["timestamp"], 2),
        "frequencyHz": round(STATE["frequencyHz"], 3),
        "demandKw": round(active_load, 2),
        "generationKw": round(STATE["generationKw"], 2),
    })
    if len(HISTORY) > 240:
        del HISTORY[:-240]


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "rakshak-digital-twin"}


@app.get("/api/state")
async def get_state():
    return copy.deepcopy(STATE)


@app.get("/api/history")
async def get_history():
    return HISTORY[-240:]


@app.post("/api/scenario")
async def scenario(request: ScenarioRequest):
    try:
        set_disturbance(request.scenario)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "state": copy.deepcopy(STATE)}


@app.post("/api/control")
async def control(request: ControlRequest):
    STATE["balancingEnabled"] = request.balancingEnabled
    log_event(f"Automatic balancing {'enabled' if request.balancingEnabled else 'disabled'}.")
    return {"ok": True, "state": copy.deepcopy(STATE)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            tick(0.1)
            await websocket.send_json({
                "state": copy.deepcopy(STATE),
                "history": HISTORY[-120:],
            })
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
