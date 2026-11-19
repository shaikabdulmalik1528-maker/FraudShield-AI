"""
Computes reference baseline feature distributions and quantile statistics
from the IEEE-CIS training split for drift detection.
Saves to backend/artifacts/v3/baseline_feature_stats.json.
"""

import sys
import json
from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.v3.ml.data_loader import load_ieee_cis_dataset
from backend.app.v3.ml.preprocessor import temporal_train_val_test_split


def main():
    print("Computing feature distribution baselines from IEEE-CIS training split...")
    df, y = load_ieee_cis_dataset(sample_size=590540)

    (X_train, y_train), _, _ = temporal_train_val_test_split(
        df, y, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, embargo_seconds=86400
    )

    baseline_features = ["TransactionAmt", "C1", "C2", "C3", "C13", "C14", "dist1"]
    feature_stats = {}

    for col in baseline_features:
        if col in X_train.columns:
            vals = X_train[col].dropna().values
            quantiles = np.percentile(vals, np.linspace(0, 100, 101)).tolist()
            feature_stats[col] = {
                "mean": round(float(np.mean(vals)), 4),
                "std": round(float(np.std(vals)), 4),
                "min": round(float(np.min(vals)), 4),
                "max": round(float(np.max(vals)), 4),
                "sample_quantiles": quantiles
            }
            print(f"  Processed {col}: Mean={feature_stats[col]['mean']}, Std={feature_stats[col]['std']}")

    output_data = {
        "dataset_name": "IEEE-CIS Fraud Detection (Training Split N=412,859)",
        "embargo_purged": True,
        "target": {
            "fraud_rate": round(float(np.mean(y_train)), 4),
            "total_samples": len(y_train)
        },
        "features": feature_stats
    }

    out_file = PROJECT_ROOT / "backend" / "artifacts" / "v3" / "baseline_feature_stats.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nBaseline feature stats successfully saved to {out_file}")


if __name__ == "__main__":
    main()
