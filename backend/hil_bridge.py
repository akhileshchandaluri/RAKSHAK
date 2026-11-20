"""Optional serial telemetry link for the low-voltage ESP32 reference demo."""

import json
import time

try:
    import serial
except ImportError:
    serial = None


class HILBridge:
    def __init__(self, port=None, baudrate=115200):
        self.ser = None
        self.baudrate = baudrate
        self.buffer = b""
        self.last_received = None
        self.last_hardware_telemetry = {"connected": False, "state": "SIMULATED"}
        if port:
            self.connect(port)

    def connect(self, port):
        if serial is None:
            self.last_hardware_telemetry["state"] = "SERIAL_DEPENDENCY_MISSING"
            return False
        try:
            self.ser = serial.Serial(port, self.baudrate, timeout=0, write_timeout=0.05)
        except serial.SerialException:
            self.last_hardware_telemetry["state"] = "SERIAL_UNAVAILABLE"
            return False
        self.last_hardware_telemetry["state"] = "WAITING_FOR_ESP32"
        return True

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except (OSError, serial.SerialException):
                pass
            self.ser = None
        self.last_hardware_telemetry["connected"] = False

    def send_grid_state(self, timestamp, frequency, rocof, armed_rocof=None):
        """Send the simulated measurement and, for the hybrid policy, the RoCoF value the
        board's deferrable channel is armed with (None = not armed)."""
        if self.ser is None:
            return
        packet = {"t": round(timestamp, 2), "f": round(frequency, 3), "df": round(rocof, 3),
                  "arm": None if armed_rocof is None else round(armed_rocof, 4)}
        try:
            self.ser.write((json.dumps(packet) + "\n").encode())
        except (OSError, serial.SerialException):
            self.close()
            self.last_hardware_telemetry["state"] = "SERIAL_UNAVAILABLE"

    def poll_hardware_response(self):
        if self.ser is None:
            return self.last_hardware_telemetry.copy()
        try:
            self.buffer += self.ser.read(4096)
        except (OSError, serial.SerialException):
            self.close()
            self.last_hardware_telemetry["state"] = "SERIAL_UNAVAILABLE"
            return self.last_hardware_telemetry.copy()
        *lines, self.buffer = self.buffer.split(b"\n")
        if len(self.buffer) > 4096:
            self.buffer = b""
        for line in lines:
            try:
                data = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if isinstance(data, dict) and data.get("node_id") == "esp32_rakshak_01":
                self.last_hardware_telemetry = {
                    "node_id": data["node_id"],
                    "relay_l1_critical": bool(data.get("shed_l1")),
                    "relay_l2_essential": bool(data.get("shed_l2")),
                    "relay_l3_deferrable": bool(data.get("shed_l3")),
                    "input_fresh": data.get("input_fresh"),
                    "armed": data.get("armed"), "local_trip": data.get("local_trip"),
                }
                self.last_received = time.monotonic()
        if self.last_received is not None:
            connected = time.monotonic() - self.last_received < 1.0
            self.last_hardware_telemetry.update(
                connected=connected, state="HARDWARE_ACTIVE" if connected else "HEARTBEAT_LOST"
            )
        return self.last_hardware_telemetry.copy()
