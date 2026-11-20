# ESP32 reference controller

This Arduino ESP32 sketch is a reference for a **low-voltage bench demo**. It receives simulated frequency and RoCoF over USB serial at 115200 baud, applies the three-tier relay policy, and reports relay states back to the dashboard. The reference uses a scaled 15-second lockout. A stale serial input holds the relay states and cancels pending restoration until fresh measurements return.

Use isolated 5 V or 12 V proxy loads on a bench. The sketch uses GPIO 18 for the critical-channel proxy, GPIO 19 for the essential channel, and GPIO 23 for the deferrable channel. Outputs are active-low. The sketch uses the simulator as its frequency source. Physical grid-frequency and aggregate appliance measurements remain outside this reference sketch.

To enable optional serial telemetry, configure the port before running the launcher.

```powershell
$env:RAKSHAK_HIL_PORT = 'COM3'
python run_sim.py
```

The first live dashboard session owns the serial port and plays at approximately real time. The UI reports the observed ESP32 heartbeat. Relay telemetry appears alongside the simulation. The virtual fleet continues to drive the simulated frequency independently of the board. Verify the sketch and the relay interface on a bench before using physical outputs.

## Hybrid demonstration (pre-armed local trigger)

With the twin's control policy set to **Hybrid**, the server sends the board, with every frequency sample, the RoCoF value its deferrable channel is armed with (`"arm"` in the serial packet). The board represents the appliance armed for the smallest contingency level. When the board's own RoCoF reading falls below that value, it opens the deferrable relay locally and reports `"local_trip": true`, without waiting for any command.

To show that arming survives a lost command link, fit a zero-crossing detector on `PIN_ZERO_CROSS_INT` fed from an **isolated low-voltage AC source** (for example a 9 V AC wall transformer through an optocoupled zero-cross module). Never connect mains to the board. When the serial stream stops, the board measures frequency and RoCoF from the zero crossings over the same 0.2 s window and the armed trigger still works. This path has not been tested on hardware in this repository; verify it on the bench first.
