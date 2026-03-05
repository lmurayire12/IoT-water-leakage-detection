# Water Leak Detection — Node.js MQTT Backend

Part of: **Smart IoT & AI-Driven Water Monitoring for Sustainable Resource Management**
BSc. Software Engineering Capstone | Lievin Murayire | Supervisor: Kevin Sebineza

---

## Folder Structure

```
backend/
├── index.js          ← Main MQTT server + Express dashboard
├── inference.py      ← Python: loads RF model, returns prediction via stdin/stdout
├── simulator.js      ← Fake ESP32 for testing without hardware
├── package.json
├── .env              ← MQTT broker URL, topics, threshold
├── public/
│   └── index.html    ← Real-time dashboard (Socket.io)
└── alerts.log        ← Auto-created: JSON log of all leak alerts
```

Model files expected one directory up (`D:\Leak\`):
- `rf_leak_detector.pkl`
- `feature_scaler.pkl`
- `feature_columns.json`

---

## Quick Start

### 1. Install Node.js dependencies
```powershell
cd D:\Leak\backend
npm install
```

### 2. (Optional) Change broker in `.env`
The default uses the free public HiveMQ broker — fine for testing.
For production, run your own Mosquitto broker locally:
```
MQTT_BROKER=mqtt://localhost:1883
```

### 3. Start the backend server
```powershell
node index.js
```

### 4. In a second terminal — run the simulator (no ESP32 needed)
```powershell
node simulator.js
```

### 5. Open the dashboard
```
http://localhost:3000
```

You should see live readings every 5 seconds. Every 10th reading is a simulated leak (red row + alert banner).

---

## How It Works

```
ESP32 (or simulator)
    │  JSON payload every 5s
    │  { "Pressure": 28, "Flow_Rate": 115, ... }
    ▼
MQTT Broker (HiveMQ / Mosquitto)
    │  topic: iot/sensor/water
    ▼
index.js (Node.js)
    │  spawns Python child process
    ▼
inference.py
    │  loads rf_leak_detector.pkl + feature_scaler.pkl
    │  engineers Pressure_Flow_Ratio, Flow_Pressure_Product, Pressure_per_RPM
    │  scales features → RandomForest.predict_proba()
    │  returns JSON: { result, probability, confidence, action }
    ▼
index.js
    ├── Publishes result to: iot/results
    ├── If LEAK: publishes alert to: iot/alerts/leak
    ├── Appends to: alerts.log
    └── Broadcasts to dashboard via Socket.io
```

---

## ESP32 Payload Format

The ESP32 firmware should publish this JSON to `iot/sensor/water`:

```json
{
  "Pressure": 62.3,
  "Flow_Rate": 78.1,
  "Temperature": 97.2,
  "Vibration": 2.8,
  "RPM": 2050,
  "Operational_Hours": 5000,
  "Latitude": -1.9441,
  "Longitude": 30.0619,
  "Zone_enc": 2,
  "Block_enc": 1,
  "Pipe_enc": 3
}
```

`Zone_enc`, `Block_enc`, `Pipe_enc` are integer zone IDs (0-indexed).
The backend automatically computes the 3 engineered features before inference.

---

## Wiring (ESP32 + YF-B5 + Pressure Sensor)

```
YF-B5 Flow Sensor:
  VCC  → ESP32 5V (VIN pin)
  GND  → ESP32 GND
  Signal → ESP32 GPIO 34 (interrupt-capable pin)

Pressure Transducer (0–1.2 MPa, 0.5–4.5V output):
  VCC  → 5V
  GND  → GND
  Signal → Voltage Divider → ESP32 GPIO 35 (ADC1)

  Voltage Divider (5V → 3.3V):
    Signal ──┬── 10kΩ ──── ESP32 GPIO 35
             └── 20kΩ ──── GND
  (Output = 5V × 20/(10+20) = 3.33V max — safe for ESP32 ADC)

Solenoid Valve (12V):
  Relay IN  → ESP32 GPIO 26
  Relay VCC → 5V
  Relay COM → 12V+
  Relay NC  → Valve+ (Normally Closed = valve open when no signal)
  Valve-    → 12V GND
```

---

## Adjusting the Leak Threshold

In `.env`:
```
LEAK_THRESHOLD=0.5   ← default (balanced)
LEAK_THRESHOLD=0.3   ← more sensitive (more alerts, fewer missed leaks)
LEAK_THRESHOLD=0.7   ← more conservative (fewer false alarms)
```

For a water utility, `0.3–0.4` is recommended — a missed leak
costs more in NRW revenue loss than a false alarm costs in inspection time.
