# Build roadmap

## Milestone 1 — Running 3D twin
- Start FastAPI and Vite.
- Verify WebSocket connection.
- Orbit/zoom the city and select buildings.
- Trigger solar-drop and demand-surge scenarios.

## Milestone 2 — Correct simulation
- Replace the illustrative frequency equation with a documented, parameterised model.
- Make the OFF baseline genuinely disable automatic shedding.
- Add frequency hysteresis, recovery dwell time, and staggered restoration.
- Reset scenario metrics/history consistently.
- Add deterministic scenario replay and exportable CSV.

## Milestone 3 — Better twin fidelity
- Make feeder status depend on measured/simulated current flow.
- Add solar arrays, substation, transformers and animated flow particles.
- Show building demand and local generation.
- Add a scenario timeline and playback.

## Milestone 4 — Hardware-in-the-loop
- Implement a USB serial bridge on the backend.
- Add a clear mode switch: Simulation / ESP32 Hardware.
- Display hardware connection state and command acknowledgements.
- Keep physical loads low voltage only.

## Milestone 5 — Evaluation
Compare balancing OFF, fixed-threshold balancing, and the proposed controller under identical scenarios. Report nadir, recovery time, shed energy, critical-load energy not served, response latency and rebound peak.
