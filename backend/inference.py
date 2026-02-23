"""
inference.py - Water Leak Detection Inference Script
-----------------------------------------------------
Called by the Node.js MQTT server with a JSON sensor reading via stdin.
Loads the trained Random Forest model + scaler from D:/Leak/ and returns
a JSON prediction result to stdout.

Usage (from Node.js child_process):
    echo '{"Pressure":28,"Flow_Rate":115,...}' | python inference.py
"""

import sys
import json
import os
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import joblib

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # D:\Leak
MODEL_PATH  = os.path.join(BASE_DIR, 'rf_leak_detector.pkl')
SCALER_PATH = os.path.join(BASE_DIR, 'feature_scaler.pkl')
COLS_PATH   = os.path.join(BASE_DIR, 'feature_columns.json')

# ── Load artefacts (cached after first call in long-running process) ──────────
try:
    model  = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(COLS_PATH) as f:
        FEATURE_COLS = json.load(f)
except FileNotFoundError as e:
    print(json.dumps({'error': str(e), 'hint': 'Ensure model files are in D:\\Leak\\'}))
    sys.exit(1)

# ── Inference ─────────────────────────────────────────────────────────────────
def predict(reading: dict) -> dict:
    """
    reading: dict with keys matching raw ESP32 sensor output:
        Pressure, Flow_Rate, Temperature, Vibration, RPM,
        Operational_Hours, Latitude, Longitude,
        Zone_enc, Block_enc, Pipe_enc
    Returns: dict with Result, Confidence, Action, Probability
    """
    r = reading.copy()

    # ── Map ESP32 encoded columns to training column names ────────────────────
    r['Zone']          = r.pop('Zone_enc',  r.get('Zone', 0))
    r['Block']         = r.pop('Block_enc', r.get('Block', 0))
    r['Pipe']          = r.pop('Pipe_enc',  r.get('Pipe', 0))
    r['Location_Code'] = r.get('Location_Code', 0)

    # ── Engineered features (must match training pipeline exactly) ────────────
    r['Pressure_Flow_Ratio'] = r['Pressure']   / (r['Flow_Rate']    + 1e-6)
    r['Pressure_x_Vib']      = r['Pressure']   * r['Vibration']
    r['Flow_Temp_Ratio']     = r['Flow_Rate']  / (r['Temperature']  + 1e-6)

    # ── Scale ──────────────────────────────────────────────────────────────────
    X = pd.DataFrame([r])[FEATURE_COLS]
    X_scaled = scaler.transform(X)

    # ── Predict ────────────────────────────────────────────────────────────────
    prob  = float(model.predict_proba(X_scaled)[0][1])
    label = 'LEAK DETECTED' if prob >= 0.5 else 'Normal'

    return {
        'result':      label,
        'probability': round(prob, 4),
        'confidence':  f'{prob * 100:.1f}%',
        'action':      'ALERT — close solenoid valve' if label == 'LEAK DETECTED' else 'No action',
        'threshold':   0.5,
        'model':       'RandomForest-200'
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
        print(json.dumps({'error': f'Missing field: {e}', 'required': FEATURE_COLS[:11]}))
        sys.exit(1)
