"""
retrain_model.py — Retrain Leak Detection Model with Real Sensor Data
──────────────────────────────────────────────────────────────────────
Takes the CSV file from collect_training_data.py and trains a new
Random Forest model tuned for your real ESP32 sensor ranges.

Usage:
  python retrain_model.py

Output:
  - rf_leak_detector.pkl     (new trained model)
  - feature_scaler.pkl       (new scaler)
  - feature_columns.json     (feature column list)
  - training_report.txt      (accuracy metrics)

Requirements:
  pip install pandas scikit-learn joblib
"""

import os
import json
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_FILE   = "real_sensor_training_data.csv"
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH  = os.path.join(BASE_DIR, 'rf_leak_detector.pkl')
SCALER_PATH = os.path.join(BASE_DIR, 'feature_scaler.pkl')
COLS_PATH   = os.path.join(BASE_DIR, 'feature_columns.json')
REPORT_PATH = os.path.join(BASE_DIR, 'training_report.txt')

# ── Load data ────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  RETRAINING LEAK DETECTION MODEL")
print("=" * 60)

if not os.path.exists(DATA_FILE):
    print(f"\n  ✗ Data file not found: {DATA_FILE}")
    print("  Run collect_training_data.py first!")
    exit(1)

df = pd.read_csv(DATA_FILE)
print(f"\n  ✓ Loaded {len(df)} readings from {DATA_FILE}")
print(f"  🟢 Normal readings: {len(df[df['label'] == 0])}")
print(f"  🔴 Leak readings:   {len(df[df['label'] == 1])}")

# Check if we have enough data
if len(df) < 50:
    print(f"\n  ⚠️ Only {len(df)} readings — recommend at least 50 for each class")
    print("  Continue anyway? (y/n)")
    if input().strip().lower() != 'y':
        exit(0)

if len(df[df['label'] == 0]) == 0 or len(df[df['label'] == 1]) == 0:
    print("\n  ✗ Need both Normal AND Leak readings to train!")
    print("  Run collect_training_data.py and collect both types")
    exit(1)

# ── Feature Engineering ──────────────────────────────────────────────────────
print("\n  Engineering features...")

# Rename columns to match the expected format
df['Zone']  = df['Zone_enc']
df['Block'] = df['Block_enc']
df['Pipe']  = df['Pipe_enc']
df['Location_Code'] = 0

# Create engineered features
df['Pressure_Flow_Ratio'] = df['Pressure'] / (df['Flow_Rate'] + 1e-6)
df['Pressure_x_Vib']      = df['Pressure'] * df['Vibration']
df['Flow_Temp_Ratio']     = df['Flow_Rate'] / (df['Temperature'] + 1e-6)

# ── Define features ──────────────────────────────────────────────────────────
FEATURE_COLS = [
    'Pressure', 'Flow_Rate', 'Temperature', 'Vibration', 'RPM',
    'Operational_Hours', 'Latitude', 'Longitude',
    'Zone', 'Block', 'Pipe', 'Location_Code',
    'Pressure_Flow_Ratio', 'Pressure_x_Vib', 'Flow_Temp_Ratio'
]

X = df[FEATURE_COLS]
y = df['label']

print(f"  ✓ {len(FEATURE_COLS)} features prepared")

# ── Split data ───────────────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print(f"  ✓ Training set: {len(X_train)} | Test set: {len(X_test)}")

# ── Scale features ───────────────────────────────────────────────────────────
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled  = scaler.transform(X_test)

# ── Train model ──────────────────────────────────────────────────────────────
print("\n  Training Random Forest model...")

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    min_samples_split=5,
    min_samples_leaf=2,
    random_state=42,
    class_weight='balanced'   # Important: handles imbalanced data
)

model.fit(X_train_scaled, y_train)

# ── Evaluate ─────────────────────────────────────────────────────────────────
y_pred = model.predict(X_test_scaled)
accuracy = accuracy_score(y_test, y_pred)
report = classification_report(y_test, y_pred, target_names=['Normal', 'Leak'])
conf_matrix = confusion_matrix(y_test, y_pred)

print(f"\n  ✓ Model trained!")
print(f"  📊 Accuracy: {accuracy * 100:.1f}%")
print(f"\n{report}")
print(f"  Confusion Matrix:")
print(f"    {conf_matrix}")

# ── Feature importance ───────────────────────────────────────────────────────
importances = model.feature_importances_
feature_importance = sorted(zip(FEATURE_COLS, importances), key=lambda x: x[1], reverse=True)

print(f"\n  Top 5 most important features:")
for feat, imp in feature_importance[:5]:
    print(f"    {feat}: {imp:.4f}")

# ── Save model artefacts ────────────────────────────────────────────────────
print(f"\n  Saving model files...")

# Backup old model if exists
if os.path.exists(MODEL_PATH):
    backup_path = MODEL_PATH.replace('.pkl', '_backup.pkl')
    os.rename(MODEL_PATH, backup_path)
    print(f"  ✓ Old model backed up to: {backup_path}")

joblib.dump(model, MODEL_PATH)
print(f"  ✓ Model saved:   {MODEL_PATH}")

joblib.dump(scaler, SCALER_PATH)
print(f"  ✓ Scaler saved:  {SCALER_PATH}")

with open(COLS_PATH, 'w') as f:
    json.dump(FEATURE_COLS, f)
print(f"  ✓ Columns saved: {COLS_PATH}")

# ── Save training report ────────────────────────────────────────────────────
with open(REPORT_PATH, 'w') as f:
    f.write("WATER LEAK DETECTION — MODEL TRAINING REPORT\n")
    f.write("=" * 50 + "\n\n")
    f.write(f"Date: {pd.Timestamp.now()}\n")
    f.write(f"Training data: {DATA_FILE}\n")
    f.write(f"Total readings: {len(df)}\n")
    f.write(f"Normal readings: {len(df[df['label'] == 0])}\n")
    f.write(f"Leak readings: {len(df[df['label'] == 1])}\n\n")
    f.write(f"Accuracy: {accuracy * 100:.1f}%\n\n")
    f.write(f"Classification Report:\n{report}\n\n")
    f.write(f"Confusion Matrix:\n{conf_matrix}\n\n")
    f.write(f"Feature Importance:\n")
    for feat, imp in feature_importance:
        f.write(f"  {feat}: {imp:.4f}\n")

print(f"  ✓ Report saved:  {REPORT_PATH}")

print(f"\n" + "=" * 60)
print(f"  ✓ MODEL RETRAINED SUCCESSFULLY!")
print(f"  ✓ Accuracy: {accuracy * 100:.1f}%")
print(f"  ✓ Restart your Node.js backend to use the new model")
print(f"=" * 60 + "\n")
