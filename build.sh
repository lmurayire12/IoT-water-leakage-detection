#!/usr/bin/env bash
# Install Node.js dependencies in the backend folder
cd backend && npm install && cd ..

# Install Python dependencies for inference.py
pip install numpy pandas scikit-learn joblib
