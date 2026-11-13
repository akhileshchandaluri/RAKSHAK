/**
 * Project Rakshak: Edge-Intelligent Grid Resilience Controller
 * Platform: ESP32 DevKit V1 (FreeRTOS Native)
 * Aligned with SDG 11: Sustainable Cities & Communities
 *
 * Features:
 * 1. Dual-Core architecture (Core 0: Telemetry; Core 1: Real-time relay FSM & RoCoF)
 * 2. Hardware MAC-hash decentralized staggered restoration (Anti-Rebound)
 * 3. Compressor lockout timer against short-cycling (Oyefeso et al., IEEE 2024)
 * 4. Priority-tiered load shedding:
 *    - Tier 0: Critical proxy (LED) -> never commanded off by the firmware
 *    - Tier 1: Essential (Fan) -> Shed on extreme dip
 *    - Tier 2: Deferrable (Heater / AC) -> First to shed
 */

#include <Arduino.h>
#include <atomic>
#if __has_include(<esp_mac.h>)
#include <esp_mac.h>
#else
#include <esp_system.h>
#endif
#include "config.h"

// State Machine Definitions
enum GridState {
    GRID_NORMAL,
    UNDER_FREQUENCY_TRIP,
    LOCKOUT_HOLD,
    STAGGERED_RESTORING
};

std::atomic<GridState> currentState{GRID_NORMAL};

// Edge Telemetry Variables
std::atomic<float> currentFrequency{50.00f};
std::atomic<float> currentRoCoF{0.00f};
std::atomic<unsigned long> lastInputTime{0};
std::atomic<bool> haveInput{false};

// Timing & Timers
unsigned long lastShedTimestamp = 0;
unsigned long recoveryStartTime = 0;
unsigned long calculatedStaggerDelayMs = 0;
uint32_t deviceMacHash = 0;

// FreeRTOS Task Handles
TaskHandle_t TaskTelemetryHandle;
TaskHandle_t TaskRelayLogicHandle;

// Function to calculate deterministic CRC32 hash from hardware MAC address
uint32_t computeMacHash() {
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    uint32_t crc = 0xFFFFFFFF;
    for (int i = 0; i < 6; i++) {
        crc ^= mac[i];
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(crc & 1)));
        }
    }
    return ~crc;
}

bool readNumber(const String &line, const char *field, float &value) {
    const int start = line.indexOf(field);
    if (start < 0) return false;
    const int colon = line.indexOf(':', start);
    if (colon < 0) return false;
    const char *number = line.c_str() + colon + 1;
    char *end = nullptr;
    value = strtof(number, &end);
    if (number == end || !isfinite(value)) return false;
    while (*end == ' ' || *end == '\t') ++end;
    return *end == ',' || *end == '}';
}

// ----------------------------------------------------
// CORE 1: High-Speed Protection & Relay FSM Task
// ----------------------------------------------------
void TaskRelayLogic(void *) {
    for (;;) {
        // 1. Check for incoming Serial frequency packets from HIL simulation
        // Packet format: {"f": 49.52, "df": -0.35}
        if (Serial.available() > 0) {
            String line = Serial.readStringUntil('\n');
            line.trim();
            float frequency, rocof;
            if (line.startsWith("{") && line.endsWith("}") &&
                readNumber(line, "\"f\"", frequency) && readNumber(line, "\"df\"", rocof) &&
                frequency > 40.0f && frequency < 60.0f) {
                currentFrequency = frequency;
                currentRoCoF = rocof;
                lastInputTime = millis();
                haveInput = true;
            }
        }

        const unsigned long now = millis();
        if (!haveInput || now - lastInputTime > INPUT_TIMEOUT_MS) {
            // Hold the existing relay states until simulated measurements resume.
            if (currentState == LOCKOUT_HOLD || currentState == STAGGERED_RESTORING) {
                currentState = UNDER_FREQUENCY_TRIP;
            }
            vTaskDelay(pdMS_TO_TICKS(20));
            continue;
        }

        // 2. Evaluate Protection Rules
        bool severeRoCoF = (currentRoCoF <= SEVERE_ROCOF_HZ_S);
        bool underFreq = (currentFrequency <= SHED_THRESHOLD_HZ);
        const bool canRecover = currentFrequency >= RECOVERY_THRESHOLD_HZ && !severeRoCoF;
        if (currentState != GRID_NORMAL && currentFrequency <= SHED_THRESHOLD_HZ - 0.40) {
            digitalWrite(PIN_RELAY_ESSENTIAL, HIGH);
        }
        if (!canRecover && (currentState == LOCKOUT_HOLD || currentState == STAGGERED_RESTORING)) {
            currentState = UNDER_FREQUENCY_TRIP;
        }

        switch (currentState.load()) {
            case GRID_NORMAL:
                // Grid is healthy
                digitalWrite(PIN_RELAY_CRITICAL, LOW);    // Power ON (Active LOW)
                digitalWrite(PIN_RELAY_ESSENTIAL, LOW);   // Power ON
                digitalWrite(PIN_RELAY_DEFERRABLE, LOW);  // Power ON
                digitalWrite(PIN_LED_GRID_HEALTHY, HIGH);
                digitalWrite(PIN_LED_SHED_ACTIVE, LOW);

                if (underFreq || (severeRoCoF && currentFrequency < 49.80)) {
                    // Trigger Immediate Level 2 (Deferrable) Shedding
                    digitalWrite(PIN_RELAY_DEFERRABLE, HIGH); // Cut Deferrable Relay
                    digitalWrite(PIN_LED_SHED_ACTIVE, HIGH);
                    lastShedTimestamp = now;

                    // If frequency is severely low, shed Level 1 (Essential) as well
                    if (currentFrequency <= (SHED_THRESHOLD_HZ - 0.40)) {
                        digitalWrite(PIN_RELAY_ESSENTIAL, HIGH);
                    }

                    // Keep the critical proxy output in its commanded-on state.
                    digitalWrite(PIN_RELAY_CRITICAL, LOW);

                    currentState = UNDER_FREQUENCY_TRIP;
                }
                break;

            case UNDER_FREQUENCY_TRIP:
                // Check if grid has recovered above hysteresis boundary
                if (canRecover) {
                    recoveryStartTime = now;
                    // Calculate decentralized staggered restoration delay
                    // Start at 2 s and add up to MAX_STAGGER_SPREAD_MS - 1 ms.
                    calculatedStaggerDelayMs = 2000 + (deviceMacHash % MAX_STAGGER_SPREAD_MS);
                    currentState = LOCKOUT_HOLD;
                }
                break;

            case LOCKOUT_HOLD:
                // Enforce compressor lockout protection (Oyefeso et al., IEEE 2024)
                if (now - lastShedTimestamp < COMPRESSOR_LOCKOUT_MS) {
                    // Still in thermal cooldown; keep deferrable relay open
                    digitalWrite(PIN_RELAY_DEFERRABLE, HIGH);
                } else {
                    currentState = STAGGERED_RESTORING;
                }
                break;

            case STAGGERED_RESTORING:
                // Staggered reconnection timer
                if (now - recoveryStartTime >= calculatedStaggerDelayMs) {
                    // Restore both channels in the same control cycle.
                    digitalWrite(PIN_RELAY_ESSENTIAL, LOW);
                    digitalWrite(PIN_RELAY_DEFERRABLE, LOW);
                    digitalWrite(PIN_LED_SHED_ACTIVE, LOW);
                    currentState = GRID_NORMAL;
                }
                break;
        }

        vTaskDelay(pdMS_TO_TICKS(20)); // Run at 50 Hz
    }
}

// ----------------------------------------------------
// CORE 0: Network & Telemetry Reporting Task
// ----------------------------------------------------
void TaskTelemetry(void *) {
    for (;;) {
        // Construct JSON telemetry packet for Python Backend and Digital Twin
        // Format: {"node_id": "esp32_rakshak_01", "f": 49.65, "shed_l3": 1, "state": "NORMAL"}
        String statusJson = "{";
        statusJson += "\"node_id\":\"esp32_rakshak_01\",";
        statusJson += "\"f\":" + String(currentFrequency.load(), 2) + ",";
        statusJson += "\"rocof\":" + String(currentRoCoF.load(), 2) + ",";
        statusJson += "\"shed_l3\":" + String(digitalRead(PIN_RELAY_DEFERRABLE) == HIGH ? 1 : 0) + ",";
        statusJson += "\"shed_l2\":" + String(digitalRead(PIN_RELAY_ESSENTIAL) == HIGH ? 1 : 0) + ",";
        statusJson += "\"shed_l1\":0,"; // Always protected
        statusJson += "\"input_fresh\":" + String(haveInput && millis() - lastInputTime <= INPUT_TIMEOUT_MS ? "true" : "false") + ",";
        statusJson += "\"state\":" + String(static_cast<int>(currentState.load()));
        statusJson += "}";

        Serial.println(statusJson);
        vTaskDelay(pdMS_TO_TICKS(100)); // 10 Hz telemetry
    }
}

void setup() {
    Serial.begin(115200);
    Serial.setTimeout(30);

    // Initialize Relay Pins
    pinMode(PIN_RELAY_CRITICAL, OUTPUT);
    pinMode(PIN_RELAY_ESSENTIAL, OUTPUT);
    pinMode(PIN_RELAY_DEFERRABLE, OUTPUT);
    pinMode(PIN_LED_GRID_HEALTHY, OUTPUT);
    pinMode(PIN_LED_SHED_ACTIVE, OUTPUT);

    // Initial Relay States: Powered ON (Active LOW relays)
    digitalWrite(PIN_RELAY_CRITICAL, LOW);
    digitalWrite(PIN_RELAY_ESSENTIAL, LOW);
    digitalWrite(PIN_RELAY_DEFERRABLE, LOW);
    digitalWrite(PIN_LED_GRID_HEALTHY, HIGH);
    digitalWrite(PIN_LED_SHED_ACTIVE, LOW);

    // Compute Hardware MAC Address Hash
    deviceMacHash = computeMacHash();

    // Pin FreeRTOS tasks to respective ESP32 cores
    xTaskCreatePinnedToCore(TaskRelayLogic, "RelayFSM", 4096, NULL, 2, &TaskRelayLogicHandle, 1);
    xTaskCreatePinnedToCore(TaskTelemetry,  "Telemetry", 4096, NULL, 1, &TaskTelemetryHandle,  0);
}

void loop() {
    // Empty; FreeRTOS tasks manage execution
    vTaskDelay(pdMS_TO_TICKS(1000));
}
