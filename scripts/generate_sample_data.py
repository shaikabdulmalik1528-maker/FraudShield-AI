"""
FraudShield AI - Synthetic Sample Data Generator (FOR DEMO/TESTING ONLY)
Generates a small, structurally compatible sample dataset strictly for testing the
ML pipeline and integration tests when the 150MB raw creditcard.csv is not yet placed.
ALL RECORDS ARE MARKED CLEARLY AS SYNTHETIC.
"""

import numpy as np
import pandas as pd
from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"

def generate_synthetic_sample(n_samples: int = 5000, fraud_ratio: float = 0.005, random_state: int = 42):
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    target_path = SAMPLE_DIR / "synthetic_sample.csv"
    
    np.random.seed(random_state)
    n_fraud = int(n_samples * fraud_ratio)
    n_legit = n_samples - n_fraud
    
    # Generate Time (seconds over 48 hours)
    time = np.sort(np.random.uniform(0, 172800, size=n_samples))
    
    # Generate Amount
    amounts_legit = np.random.exponential(scale=88.0, size=n_legit)
    amounts_fraud = np.random.exponential(scale=122.0, size=n_fraud)
    amounts = np.concatenate([amounts_legit, amounts_fraud])
    
    # Generate V1 - V28 (PCA Gaussian-like distributions)
    # Legitimate transactions: standard normal
    features_legit = np.random.normal(loc=0.0, scale=1.0, size=(n_legit, 28))
    # Fraud transactions: slight distribution shifts on key known PCA features (V1, V2, V3, V4, V10, V14, V17)
    features_fraud = np.random.normal(loc=0.0, scale=1.2, size=(n_fraud, 28))
    features_fraud[:, 1] += 1.5   # V2 shift
    features_fraud[:, 3] += 1.8   # V4 shift
    features_fraud[:, 9] -= 2.0   # V10 shift
    features_fraud[:, 13] -= 2.5  # V14 shift
    features_fraud[:, 16] -= 2.0  # V17 shift
    
    features = np.concatenate([features_legit, features_fraud], axis=0)
    classes = np.concatenate([np.zeros(n_legit, dtype=int), np.ones(n_fraud, dtype=int)])
    
    # Shuffle while keeping alignment
    shuffle_idx = np.random.permutation(n_samples)
    time = time[shuffle_idx]
    amounts = np.round(amounts[shuffle_idx], 2)
    features = np.round(features[shuffle_idx], 6)
    classes = classes[shuffle_idx]
    
    columns = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount", "Class"]
    data = np.column_stack([time, features, amounts, classes])
    
    df = pd.DataFrame(data, columns=columns)
    df["Class"] = df["Class"].astype(int)
    
    df.to_csv(target_path, index=False)
    print(f"[SUCCESS] Synthetic sample dataset created at: {target_path}")
    print(f"Total Rows: {len(df)} | Legitimate: {(df['Class'] == 0).sum()} | Fraudulent: {(df['Class'] == 1).sum()} ({df['Class'].mean() * 100:.2f}%)")
    return str(target_path)

if __name__ == "__main__":
    generate_synthetic_sample()
