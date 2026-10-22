# Architecture and data flow

```text
Scenario controls (React)
        |
        | POST /api/scenario
        v
FastAPI grid simulation ---- simplified frequency dynamics
        |                              |
        | WebSocket /ws                | control policy
        v                              v
React state store <------------- virtual appliance states
        |
        +--> Three.js city scene
        +--> frequency chart
        +--> asset inspector
        +--> event log

Future hardware mode:
FastAPI serial bridge <----USB serial----> ESP32
                                      |
                                      +--> INA219 / low-voltage proxy loads
```

## Planned hardware protocol (not implemented yet)
Use newline-delimited JSON over USB serial, with explicit message types. Example messages:
- Backend to ESP32: `{"type":"grid_frequency","hz":49.55}`
- ESP32 to backend: `{"type":"telemetry","measured_power_w":14.2,"relay_states":{"load3":false}}`
- ESP32 to backend: `{"type":"ack","action":"shed_load3","ok":true}`

The actual firmware and serial bridge must validate messages, handle disconnection, and fail safely. Never connect mains voltage to a breadboard or an unqualified prototype.
