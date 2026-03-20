"""
collect_training_data.py — Real Sensor Data Collector for ML Retraining
────────────────────────────────────────────────────────────────────────
Subscribes to your ESP32 MQTT topic and saves labeled sensor readings
to a CSV file for retraining the leak detection model.

Usage:
  python collect_training_data.py

Instructions:
  1. Run this script
  2. It will ask you to choose a label: "normal" or "leak"
  3. Perform the action (normal shower use or simulate a leak)
  4. Press Enter to switch labels or Ctrl+C to stop
  5. The CSV file is saved automatically

Requirements:
  pip install paho-mqtt pandas
"""

import json
import csv
import os
import time
import threading
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Installing paho-mqtt...")
    os.system("pip install paho-mqtt")
    import paho.mqtt.client as mqtt

# ── MQTT Settings (must match your ESP32 code) ──────────────────────────────
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT   = 1883
MQTT_TOPIC  = "iot/sensor/water"

# ── Output file ──────────────────────────────────────────────────────────────
OUTPUT_FILE = "real_sensor_training_data.csv"
CSV_COLUMNS = [
    "timestamp",
    "Flow_Rate",
    "Temperature",
    "Vibration",
    "Pressure",
    "RPM",
    "Operational_Hours",
    "Latitude",
    "Longitude",
    "Zone_enc",
    "Block_enc",
    "Pipe_enc",
    "label"   # 0 = Normal, 1 = Leak
]

# ── Globals ──────────────────────────────────────────────────────────────────
current_label = 0   # 0 = Normal, 1 = Leak
reading_count = 0
file_exists = os.path.exists(OUTPUT_FILE)

# Open CSV file in append mode
csv_file = open(OUTPUT_FILE, 'a', newline='')
csv_writer = csv.writer(csv_file)

# Write header if new file
if not file_exists:
    csv_writer.writerow(CSV_COLUMNS)
    csv_file.flush()

# ── MQTT Callbacks ───────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✓ Connected to MQTT broker: {MQTT_BROKER}")
        client.subscribe(MQTT_TOPIC)
        print(f"✓ Subscribed to: {MQTT_TOPIC}\n")
    else:
        print(f"✗ Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global reading_count
    
    try:
        data = json.loads(msg.payload.decode())
        
        # Write row to CSV
        row = [
            datetime.now().isoformat(),
            data.get("Flow_Rate", 0),
            data.get("Temperature", 25),
            data.get("Vibration", 9.8),
            data.get("Pressure", 55),
            data.get("RPM", 2000),
            data.get("Operational_Hours", 0),
            data.get("Latitude", -1.9441),
            data.get("Longitude", 30.0619),
            data.get("Zone_enc", 0),
            data.get("Block_enc", 0),
            data.get("Pipe_enc", 0),
            current_label
        ]
        
        csv_writer.writerow(row)
        csv_file.flush()
        reading_count += 1
        
        label_text = "🔴 LEAK" if current_label == 1 else "🟢 NORMAL"
        flow = data.get("Flow_Rate", 0)
        temp = data.get("Temperature", 0)
        vib = data.get("Vibration", 0)
        
        print(f"  [{label_text}] #{reading_count:04d} | Flow: {flow:.2f} L/min | Temp: {temp:.2f}°C | Vib: {vib:.2f} m/s²")
        
    except json.JSONDecodeError:
        print("  ⚠️ Invalid JSON received")
    except Exception as e:
        print(f"  ⚠️ Error: {e}")

# ── Label switching (runs in background thread) ─────────────────────────────
def label_switcher():
    global current_label
    
    while True:
        print("\n" + "=" * 60)
        print(f"  Current label: {'🔴 LEAK (1)' if current_label == 1 else '🟢 NORMAL (0)'}")
        print(f"  Total readings collected: {reading_count}")
        print("=" * 60)
        print("\n  Commands:")
        print("    n  →  Switch to NORMAL label")
        print("    l  →  Switch to LEAK label")
        print("    s  →  Show stats")
        print("    q  →  Quit and save\n")
        
        try:
            cmd = input("  Enter command: ").strip().lower()
        except EOFError:
            break
        
        if cmd == 'n':
            current_label = 0
            print("\n  ✓ Label set to: 🟢 NORMAL")
            print("  → Turn on shower normally or leave tap off\n")
        elif cmd == 'l':
            current_label = 1
            print("\n  ✓ Label set to: 🔴 LEAK")
            print("  → Open tap to barely dripping to simulate a leak\n")
        elif cmd == 's':
            print(f"\n  📊 Total readings: {reading_count}")
            print(f"  📄 Saved to: {os.path.abspath(OUTPUT_FILE)}")
            # Count labels
            try:
                import pandas as pd
                df = pd.read_csv(OUTPUT_FILE)
                normal_count = len(df[df['label'] == 0])
                leak_count = len(df[df['label'] == 1])
                print(f"  🟢 Normal readings: {normal_count}")
                print(f"  🔴 Leak readings:   {leak_count}")
            except:
                pass
        elif cmd == 'q':
            print("\n  💾 Saving and exiting...")
            csv_file.close()
            print(f"  ✓ Data saved to: {os.path.abspath(OUTPUT_FILE)}")
            print(f"  ✓ Total readings: {reading_count}")
            os._exit(0)

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  WATER LEAK DETECTION — Training Data Collector")
    print("=" * 60)
    print(f"\n  MQTT Broker: {MQTT_BROKER}")
    print(f"  Topic:       {MQTT_TOPIC}")
    print(f"  Output:      {OUTPUT_FILE}")
    print(f"\n  Make sure your ESP32 is running and sending data!\n")
    
    # Start MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
    except Exception as e:
        print(f"✗ Cannot connect to MQTT: {e}")
        print("  Make sure you have internet access")
        sys.exit(1)
    
    # Start MQTT loop in background
    client.loop_start()
    
    # Wait for connection
    time.sleep(2)
    
    # Run label switcher in main thread
    try:
        label_switcher()
    except KeyboardInterrupt:
        print("\n\n  💾 Saving and exiting...")
        csv_file.close()
        print(f"  ✓ Data saved to: {os.path.abspath(OUTPUT_FILE)}")
        print(f"  ✓ Total readings: {reading_count}")
        client.loop_stop()
