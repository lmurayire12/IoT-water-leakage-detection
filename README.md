# Smart IoT & AI-Driven Water Leak Detection System

**BSc. Software Engineering - Mission Capstone Project**
**Author:** Lievin Murayire | **Supervisor:** Kevin Sebineza
**African Leadership University (ALU), Kigali, Rwanda**

---

## Overview

This project detects water pipe leaks in real time by combining IoT sensor hardware (ESP32 + 4 sensors) with a hybrid AI detection system (rule-based + Random Forest ML). Sensor readings are published over MQTT, processed by a Node.js backend, and classified by a Python inference engine. Alerts are broadcast instantly to a live web dashboard with SMS/WhatsApp notifications.

The system addresses Rwanda's **Non-Revenue Water (NRW)** crisis - the country loses **41–44% of its treated water** to leaks, costing approximately **28.8 billion RWF annually**. This solution targets the "last-mile" gap where WASAC monitors the grid but individual households remain blind to their own leaks.

## Live Demo & Web Deployment

| Resource | Link |
|----------|------|
| Deployed Web App | https://iot-water-leakage-detection.onrender.com/ |
| Video Demo | https://drive.google.com/file/d/1qRbhAsdbvJtqkHWG75cNOC3DQ-3HyOg5/view?usp=sharing |


---

## Hardware Setup

### ESP32 NodeMCU ESP-32S + 4 Sensors

| Sensor | Model | Purpose | GPIO Pin | Protocol |
|--------|-------|---------|----------|----------|
| Water Flow | YF-S201 (G1/2) | Measures flow rate (L/min) | GPIO 19 | Pulse/Interrupt |
| Temperature | DS18B20  | Monitors water/pipe temperature | GPIO 4 | OneWire (via adapter module) |
| Vibration | ADXL345 | Detects pipe vibration anomalies | GPIO 21 (SDA), GPIO 22 (SCL) | I2C |
| Pressure | HX710B | Measures barometric/water pressure | GPIO 32 (OUT), GPIO 33 (SCK) | Custom 24-bit |

### Wiring Summary

```
ESP32 NodeMCU ESP-32S (on breadboard)
├── GPIO 19  ← YF-S201 Signal (Yellow wire)
├── VIN (5V) ← YF-S201 VCC (Red wire)
├── GND      ← YF-S201 GND (Black wire)
│
├── GPIO 4   ← DS18B20 Adapter DAT
├── 3.3V     ← DS18B20 Adapter VCC
├── GND      ← DS18B20 Adapter GND
│
├── GPIO 21 (SDA) ← ADXL345 SDA
├── GPIO 22 (SCL) ← ADXL345 SCL
├── 3.3V          ← ADXL345 VCC
├── GND           ← ADXL345 GND
│
├── GPIO 32  ← HX710B OUT
├── GPIO 33  ← HX710B SCK
├── 3.3V     ← HX710B VCC
└── GND      ← HX710B GND
```

### Physical Test Setup

```
[Wall Tap] → [Shower Hose] → [YF-S201 Flow Sensor inline] → [Shower Head / Bucket]
                  │
                  ├── DS18B20 probe taped/clamped to hose exterior
                  │
┌─────────────────────────────────────────────────┐
│  BREADBOARD (dry surface near pipe)             │
│  ESP32 + ADXL345 + HX710B + DS18B20 Adapter    │
│  Connected to laptop via USB                     │
└─────────────────────────────────────────────────┘
```

### Sensor Data Published via MQTT

The ESP32 publishes JSON to `iot/sensor/water` every 2 seconds:

```json
{
  "Flow_Rate": 2.20,
  "Temperature": 22.75,
  "Vibration": 9.81,
  "Pressure": 0.15,
  "RPM": 2000.0,
  "Operational_Hours": 42,
  "Latitude": -1.9441,
  "Longitude": 30.0619,
  "Zone_enc": 0,
  "Block_enc": 0,
  "Pipe_enc": 0
}
```

### ESP32 Arduino Libraries Required

- WiFi (built into ESP32 core)
- PubSubClient (by Nick O'Leary)
- ArduinoJson (by Benoit Blanchon)
- OneWire (by Jim Studt)
- DallasTemperature (by Miles Burton)
- Adafruit ADXL345 (by Adafruit)
- Adafruit Unified Sensor (by Adafruit)

---

## Repository Structure

```
Leak/
├── leakdetection.ipynb                     ← ML notebook (original training pipeline)
├── location_aware_gis_leakage_dataset.csv  ← Source Kaggle training dataset
├── real_sensor_training_data.csv           ← Real sensor data (collected from ESP32)
├── rf_leak_detector.pkl                    ← Trained Random Forest (retrained on real data)
├── rf_leak_detector_backup.pkl             ← Backup of Kaggle-trained model
├── feature_scaler.pkl                      ← StandardScaler for feature normalization
├── nn_leak_detector.keras                  ← Trained Neural Network (from notebook)
├── feature_columns.json                    ← Feature list for inference
├── sensor_history.json                     ← Recent readings for pattern detection
├── training_report.txt                     ← Model accuracy report
├── collect_training_data.py                ← Real sensor data collection script
├── retrain_model.py                        ← Model retraining script
├── build.sh                                ← Render deployment build script
├── render.yaml                             ← Render deployment configuration
├── schema.sql                              ← MySQL database schema
│
├── backend/
│   ├── index.js                            ← MQTT server + Express + Socket.io
│   ├── inference.py                        ← Hybrid AI inference (Rules + RF model)
│   ├── simulator.js                        ← Fake ESP32 for testing without hardware
│   ├── db.js                               ← MySQL connection pool
│   ├── package.json                        ← Node.js dependencies
│   ├── .env                                ← Configuration (broker, topics, threshold, DB)
│   ├── alerts.log                          ← Auto-created JSON log of all leak events
│   └── public/
│       └── index.html                      ← Real-time web dashboard
│
└── sketch_mar9a/
    └── sketch_mar9a.ino                    ← ESP32 firmware (4 sensors + MQTT)
```

---

## AI/ML Leak Detection

### Hybrid Detection System (v2)

The system uses **two detection layers** for maximum accuracy:

#### Layer 1 - Rule-Based Detection (tuned for real sensor data)

| Rule | Condition | Score |
|------|-----------|-------|
| Low continuous flow | 0.05–1.0 L/min detected | +0.5 |
| Persistent low flow (6s) | Low flow for 3+ consecutive readings | +0.4 |
| Persistent low flow (20s) | Low flow for 10+ consecutive readings | = 1.0 (definite leak) |
| Unexpected flow after idle | Flow appears after zero-flow period | +0.3 |
| Sudden flow change | >50% change in flow rate | +0.2 |
| Temperature anomaly | >2°C drop with flow present | +0.15 |
| Vibration anomaly | Abnormal vibration with low flow | +0.15 |
| Normal usage | Steady high flow (>1.5 L/min) | −0.3 (reduces score) |
| Zero flow | No flow detected | = 0.0 (no leak) |

#### Layer 2 - Random Forest ML Model

- **Algorithm:** Random Forest (200 trees, balanced class weights)
- **Training Data:** 388 real sensor readings from ESP32 (165 normal + 273 leak)
- **Accuracy:** 98.7% on test set
- **Top Features:** Temperature (35%), Flow_Rate (13%), Flow_Temp_Ratio (11%)

#### Combined Score

```
combined_score = max(rule_score, ml_score)
```

If **either** layer detects a leak, the alert is triggered. Threshold: **0.5** (configurable in `.env`).

### Original ML Notebook

The notebook (`leakdetection.ipynb`) contains the full supervised + unsupervised pipeline:

| Step | Description |
|------|-------------|
| Data loading | 5,000-row GIS-annotated Kaggle dataset |
| EDA | Class distribution, Pressure vs Flow scatter, correlation heatmap |
| Feature engineering | Pressure_Flow_Ratio, Pressure_x_Vib, Flow_Temp_Ratio |
| Preprocessing | Label encoding, MinMaxScaler, stratified split |
| SMOTE | Balances the 6.5% minority leak class |
| Model 1 - Random Forest | 300 trees, balanced class weight |
| Model 2 - Neural Network | 4-layer MLP, BatchNorm, Dropout, EarlyStopping |
| Model 3 - Isolation Forest | Unsupervised anomaly detection |
| Evaluation | ROC curves, Precision-Recall curves, confusion matrices |

### Retraining with Real Sensor Data

```bash
# Step 1: Collect labeled data from live ESP32
python collect_training_data.py
# Use 'n' for normal, 'l' for leak, 'q' to quit

# Step 2: Retrain the model
python retrain_model.py
# Outputs: rf_leak_detector.pkl, feature_scaler.pkl, training_report.txt
```

---

## Backend Architecture

```
ESP32 (4 sensors)
    │  JSON payload every 2s
    │  topic: iot/sensor/water
    ▼
MQTT Broker (broker.hivemq.com:1883)
    ▼
index.js  (Node.js · Express · Socket.io · MySQL)
    │  spawns Python child process per reading
    ▼
inference.py  (Hybrid Detection)
    │  Layer 1: Rule-based pattern analysis
    │  Layer 2: Random Forest ML model
    │  Returns: leak probability + reasons
    ▼
index.js
    ├── Stores reading in MySQL (sensor_reading table)
    ├── Publishes result → iot/results
    ├── If LEAK: publishes alert → iot/alerts/leak
    ├── If LEAK: sends SMS via Africa's Talking
    ├── If LEAK: sends shutoff command → iot/commands/shutoff
    ├── Appends entry to alerts.log
    └── Broadcasts to dashboard via Socket.io
```

---

## Database (MySQL / TiDB Cloud)

### Tables

| Table | Purpose |
|-------|---------|
| `user` | Homeowner accounts |
| `household_node` | Physical ESP32 devices |
| `sensor_reading` | Every sensor packet (grows large) |
| `alert_event` | Leak alerts with resolution tracking |

### Setup

```bash
# Local MySQL
mysql -u root -p < schema.sql

# Cloud (TiDB Cloud - free tier)
# Run schema.sql in TiDB Cloud SQL Editor
```

---

## Quick Start

### 1. Train the models (if not already done)

```bash
# Option A: Run the Jupyter notebook
jupyter notebook leakdetection.ipynb

# Option B: Retrain with real sensor data
python collect_training_data.py
python retrain_model.py
```

### 2. Install Node.js dependencies

```bash
cd backend
npm install
```

### 3. Configure environment

Edit `.env` with your MQTT broker, database credentials, and alert settings.

### 4. Start the backend

```bash
node index.js
```

### 5. Upload ESP32 firmware

Open `sketch_mar9a/sketch_mar9a.ino` in Arduino IDE, install required libraries, and upload to ESP32 (remove from breadboard during upload, reconnect after).

### 6. Open the dashboard

```
http://localhost:3000
```

### 7. Run without hardware (simulator)

```bash
node simulator.js
```

---

## Deployment

### Render (Cloud Deployment)

The project includes `render.yaml` and `build.sh` for one-click deployment to Render.

1. Push code to GitHub
2. Connect repository on [render.com](https://render.com)
3. Set environment variables (DB credentials, API keys)
4. Deploy

### Database: TiDB Cloud (Free Tier)

- Serverless MySQL-compatible database
- Region: eu-central-1 (Frankfurt)
- Run `schema.sql` in TiDB Cloud SQL Editor

---

## WASAC Water Tariffs (Rwanda)

Used for cost-of-leak calculations in alerts:

| Customer Category | Block | Tariff (RWF/m³, excl. VAT) |
|-------------------|-------|----------------------------|
| Residential | 0–5 m³ | 340 |
| Residential | 5–20 m³ | 720 |
| Residential | 20–50 m³ | 845 |
| Residential | >50 m³ | 877 |
| Non-Residential | 0–50 m³ | 877 |
| Non-Residential | >50 m³ | 895 |
| Industries | N/A | 736 |
| Public tap | N/A | 323 |

**Default for leak cost calculation:** 720 RWF/m³ (residential 5–20 m³ block = 0.72 RWF/liter)

---

## Leak Threshold Tuning

Set `LEAK_THRESHOLD` in `.env`:

| Value | Behaviour |
|-------|-----------|
| 0.3 | High sensitivity - fewer missed leaks, more false alarms |
| 0.5 | Balanced (default) |
| 0.7 | Conservative - fewer false alarms, may miss slow leaks |

For water utilities, **0.3–0.4 is recommended** - a missed leak costs more in NRW revenue loss than a false alarm costs in inspection time.

---

## Key Findings

- **Flow_Rate and Temperature** are the strongest leak predictors when using real sensor data, validating the multi-sensor hardware approach.
- **Hybrid detection (Rules + ML)** outperforms either approach alone - rule-based catches persistent low-flow patterns while ML detects statistical anomalies.
- **Real sensor retraining** improved detection of slow leaks that the Kaggle-trained model missed.
- The **YF-S201 has a minimum detection threshold of ~1 L/min** - for production deployment, the YF-S401 (0.3 L/min minimum) is recommended for catching smaller leaks.
- **SMOTE is essential** at 6.5% leak prevalence in the original dataset.
- The system detects a simulated leak within **6–20 seconds** of onset.
- At **0.5 L/min leak rate**, the projected water loss is **30 liters/hour** costing approximately **21.6 RWF/hour** (720 RWF/m³ tariff).

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Microcontroller | ESP32 NodeMCU ESP-32S |
| Firmware | Arduino C++ (Arduino IDE) |
| Communication | MQTT (HiveMQ public broker) |
| Backend | Node.js + Express + Socket.io |
| ML Inference | Python (scikit-learn Random Forest) |
| Database | MySQL (TiDB Cloud - free tier) |
| Dashboard | HTML/CSS/JS (served by Express) |
| SMS Alerts | Africa's Talking API |
| Deployment | Render (cloud) |

---

## Requirements

### Python

- Python 3.10+
- numpy, pandas, scikit-learn, joblib
- paho-mqtt (for data collection)

### Node.js

- Node.js 18+
- See `backend/package.json` for dependencies

### Arduino IDE

- ESP32 board support package
- Libraries listed in Hardware Setup section

---

## References

- Mwitirehe et al. (2024). Machine Learning for NRW reduction in Rwandan water utilities.
- Oren, M. & Stroh, N. (2013). Hydraulic anomaly detection via pressure-flow ratio analysis.
- Rwanda Water Utility (2022). Annual Non-Revenue Water Report.
- RURA (2024). Approved Water End User Tariffs for WASAC.

---

## Author

**Lievin Murayire**
BSc. Software Engineering, African Leadership University (Kigali)
Email: l.murayire@alustudent.com
