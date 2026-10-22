# Rakshak Digital Twin

A lightweight browser-based 3D digital twin starter for Team Rakshak.

## Architecture
- `frontend/`: React + TypeScript + Vite + Three.js / React Three Fiber
- `backend/`: FastAPI grid simulator and WebSocket state stream
- `docs/`: architecture and implementation roadmap

This is a simulation-first starter. It does not switch real mains loads. Hardware integration should use low-voltage proxy loads and a clearly defined serial protocol.

## Requirements
- Node.js 20+
- Python 3.11+

## Run the backend
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Run the frontend
In another terminal:
```bash
cd frontend
npm install
npm run dev
```
Open the URL printed by Vite (usually http://localhost:5173).

## Initial features
- Browser 3D city with selectable buildings
- Simulated grid frequency, solar generation and demand
- Trigger solar-drop and demand-surge scenarios
- Automatic shedding in simulation mode
- WebSocket state stream from FastAPI to frontend
- Basic event log and live metrics

## Important modeling note
The grid dynamics here are intentionally simplified for a classroom prototype. It is not a validated power-system simulator and must not be used for real grid control. Thresholds and model parameters should be calibrated against the project's chosen scenarios and documented in the report.
