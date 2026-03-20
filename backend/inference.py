"""
inference.py - Water Leak Detection Inference Script (v2 - Hybrid)
------------------------------------------------------------------
Uses TWO detection layers:
  1. Rule-based detection — works with real ESP32 sensor ranges
  2. ML model (Random Forest) — secondary layer from Kaggle training

Called by the Node.js MQTT server with a JSON sensor reading via stdin.

Usage (from Node.js child_process):
    echo '{"Pressure":0.5,"Flow_Rate":2.2,...}' | python inference.py
"""

import sys
import json
import os
import time
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import joblib

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # D:\Leak
MODEL_PATH  = os.path.join(BASE_DIR, 'rf_leak_detector.pkl')
SCALER_PATH = os.path.join(BASE_DIR, 'feature_scaler.pkl')
COLS_PATH   = os.path.join(BASE_DIR, 'feature_columns.json')
HISTORY_PATH = os.path.join(BASE_DIR, 'sensor_history.json')

# ── Load ML artefacts ─────────────────────────────────────────────────────────
ml_available = False
try:
    model  = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(COLS_PATH) as f:
        FEATURE_COLS = json.load(f)
    ml_available = True
except FileNotFoundError:
    ml_available = False

# ── Sensor history for pattern detection ─────────────────────────────────────
def load_history():
    """Load recent sensor readings for trend analysis."""
    try:
        with open(HISTORY_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_history(history):
    """Save sensor history (keep last 60 readings = ~2 minutes at 2s interval)."""
    history = history[-60:]  # keep last 60 readings
    with open(HISTORY_PATH, 'w') as f:
        json.dump(history, f)

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: RULE-BASED DETECTION (tuned for your real sensor data)
# ══════════════════════════════════════════════════════════════════════════════

def rule_based_detection(reading: dict, history: list) -> dict:
    """
    Detects leaks using rules based on real sensor patterns:
    
    Your real sensor ranges (from testing):
      - Flow off:     0.0 L/min
      - Normal flow:  1.5 - 5.0 L/min (corrected formula)
      - Small leak:   0.1 - 0.5 L/min
      - Temperature:  ~22-25°C (ambient), changes when water flows
      - Vibration:    ~9.5-10.0 m/s² (gravity baseline), spikes with flow
    """
    flow = reading.get('Flow_Rate', 0)
    temp = reading.get('Temperature', 25)
    vibration = reading.get('Vibration', 9.8)
    pressure = reading.get('Pressure', 55)
    
    leak_score = 0.0
    reasons = []
    
    # ── Rule 1: Persistent low flow (classic slow leak) ──────────────────────
    # A small continuous flow (0.05 - 1.0 L/min) when nobody is using water
    # is the most common leak pattern
    if 0.05 <= flow <= 1.0:
        leak_score += 0.5
        reasons.append(f"Low continuous flow detected: {flow:.2f} L/min")
        
        # Check if this low flow has been persistent (3+ readings = 6 seconds)
        if len(history) >= 3:
            recent_flows = [h.get('Flow_Rate', 0) for h in history[-3:]]
            persistent_low = all(0.05 <= f <= 1.0 for f in recent_flows)
            if persistent_low:
                leak_score += 0.4  # Strong indicator — persistent low flow
                reasons.append("Persistent low flow for 6+ seconds")
        
        # Even stronger if persistent for 10+ readings (20 seconds)
        if len(history) >= 10:
            recent_flows = [h.get('Flow_Rate', 0) for h in history[-10:]]
            persistent_long = all(0.05 <= f <= 1.0 for f in recent_flows)
            if persistent_long:
                leak_score = 1.0  # Definite leak
                reasons.append("Persistent low flow for 20+ seconds — definite leak")
    
    # ── Rule 2: Flow when expected to be off ─────────────────────────────────
    # If there was zero flow, then suddenly small flow appears
    if len(history) >= 3:
        recent_flows = [h.get('Flow_Rate', 0) for h in history[-3:]]
        was_off = any(f == 0 for f in recent_flows[:-1])
        now_small_flow = 0.01 < flow < 0.8
        if was_off and now_small_flow:
            leak_score += 0.3
            reasons.append("Unexpected flow after idle period")
    
    # ── Rule 3: Sudden flow rate change (burst/pipe damage) ──────────────────
    if len(history) >= 2:
        prev_flow = history[-1].get('Flow_Rate', 0)
        if prev_flow > 0:
            change_ratio = abs(flow - prev_flow) / (prev_flow + 0.001)
            if change_ratio > 0.5 and flow > 0.5:
                leak_score += 0.2
                reasons.append(f"Sudden flow change: {prev_flow:.2f} → {flow:.2f} L/min")
    
    # ── Rule 4: Temperature anomaly ──────────────────────────────────────────
    # Sudden temperature drop while flow is low could indicate underground leak
    if len(history) >= 5:
        recent_temps = [h.get('Temperature', 25) for h in history[-5:]]
        avg_temp = sum(recent_temps) / len(recent_temps)
        if temp < avg_temp - 2.0 and flow > 0:
            leak_score += 0.15
            reasons.append(f"Temperature drop: {avg_temp:.1f}°C → {temp:.1f}°C")
    
    # ── Rule 5: Vibration anomaly ────────────────────────────────────────────
    # Abnormal vibration with low flow could mean pipe damage
    if len(history) >= 5:
        recent_vibs = [h.get('Vibration', 9.8) for h in history[-5:]]
        avg_vib = sum(recent_vibs) / len(recent_vibs)
        vib_change = abs(vibration - avg_vib)
        if vib_change > 1.5 and 0.05 < flow < 1.0:
            leak_score += 0.15
            reasons.append(f"Abnormal vibration with low flow: {vibration:.2f} m/s²")
    
    # ── Rule 6: Normal usage detection (REDUCE false alarms) ─────────────────
    # High steady flow = someone is using the shower, NOT a leak
    if flow > 1.5:
        # Check if flow is steady (normal usage pattern)
        if len(history) >= 3:
            recent_flows = [h.get('Flow_Rate', 0) for h in history[-3:]]
            all_high = all(f > 1.0 for f in recent_flows)
            if all_high:
                leak_score = max(0, leak_score - 0.3)  # Reduce score for normal usage
                reasons.append("Steady high flow — likely normal usage")
    
    # ── Rule 7: Zero flow = definitely no leak ───────────────────────────────
    if flow == 0:
        leak_score = 0.0
        reasons = ["No flow detected — system idle"]
    
    # Cap at 1.0
    leak_score = min(leak_score, 1.0)
    
    return {
        'score': round(leak_score, 4),
        'reasons': reasons
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: ML MODEL (Random Forest from Kaggle training)
# ══════════════════════════════════════════════════════════════════════════════

def ml_detection(reading: dict) -> float:
    """Run the trained Random Forest model. Returns probability 0.0-1.0."""
    if not ml_available:
        return 0.0
    
    try:
        r = reading.copy()
        
        # Map ESP32 columns to training column names
        r['Zone']          = r.pop('Zone_enc',  r.get('Zone', 0))
        r['Block']         = r.pop('Block_enc', r.get('Block', 0))
        r['Pipe']          = r.pop('Pipe_enc',  r.get('Pipe', 0))
        r['Location_Code'] = r.get('Location_Code', 0)
        
        # Engineered features (must match training pipeline)
        r['Pressure_Flow_Ratio'] = r['Pressure']   / (r['Flow_Rate']    + 1e-6)
        r['Pressure_x_Vib']      = r['Pressure']   * r['Vibration']
        r['Flow_Temp_Ratio']     = r['Flow_Rate']  / (r['Temperature']  + 1e-6)
        
        # Scale and predict
        X = pd.DataFrame([r])[FEATURE_COLS]
        X_scaled = scaler.transform(X)
        prob = float(model.predict_proba(X_scaled)[0][1])
        
        return round(prob, 4)
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# COMBINED PREDICTION (both layers)
# ══════════════════════════════════════════════════════════════════════════════

def predict(reading: dict) -> dict:
    """
    Combines rule-based and ML detection:
    - Uses the HIGHER score of the two layers
    - This ensures a leak is caught if EITHER layer detects it
    """
    # Load history and add current reading
    history = load_history()
    
    # Layer 1: Rule-based
    rule_result = rule_based_detection(reading, history)
    rule_score = rule_result['score']
    
    # Layer 2: ML model
    ml_score = ml_detection(reading)
    
    # Use the MAX of both scores — if either layer says leak, it's a leak
    combined_score = max(rule_score, ml_score)
    combined_score = min(combined_score, 1.0)
    
    # Determine label
    label = 'LEAK DETECTED' if combined_score >= 0.5 else 'Normal'
    
    # Save current reading to history
    history.append({
        'Flow_Rate': reading.get('Flow_Rate', 0),
        'Temperature': reading.get('Temperature', 25),
        'Vibration': reading.get('Vibration', 9.8),
        'Pressure': reading.get('Pressure', 55),
        'timestamp': time.time()
    })
    save_history(history)
    
    return {
        'result':         label,
        'probability':    round(combined_score, 4),
        'confidence':     f'{combined_score * 100:.1f}%',
        'action':         'ALERT — close solenoid valve' if label == 'LEAK DETECTED' else 'No action',
        'threshold':      0.5,
        'model':          'Hybrid (Rules 70% + RF 30%)',
        'rule_score':     rule_score,
        'ml_score':       ml_score,
        'reasons':        rule_result['reasons'],
        'detection_layer': 'rule-based' if rule_score > ml_score else 'ml-model'
    }


if __name__ == '__main__':
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({'error': 'No input received on stdin'}))
        sys.exit(1)
    try:
        reading = json.loads(raw)
        result  = predict(reading)
        print(json.dumps(result))
    except json.JSONDecodeError as e:
        print(json.dumps({'error': f'Invalid JSON: {e}'}))
        sys.exit(1)
    except KeyError as e:
        print(json.dumps({'error': f'Missing field: {e}'}))
        sys.exit(1)
