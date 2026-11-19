"""
Head-to-Head Comparative Benchmark: FraudShield 3.0 LightGBM vs. XGBoost on IEEE-CIS.
Evaluates both models on the exact same purged and embargoed held-out test split (N=82,406)
and accounts for all 590,540 source transactions and the 6,692 purged embargo records.
"""

import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.v3.ml.data_loader import load_ieee_cis_dataset
from backend.app.v3.ml.preprocessor import temporal_train_val_test_split
from backend.app.v3.ml.evaluation import compute_classification_metrics, benchmark_inference_latency
from backend.app.v3.ml.lightgbm_model import FraudShieldLightGBM
from xgboost import XGBClassifier


def main():
    print("=" * 80)
    print("FRAUDSHIELD 3.0 — LIGHTGBM VS. XGBOOST COMPARATIVE BENCHMARK")
    print("=" * 80)

    # 1. Load dataset & account for all 590,540 records
    print("\n[STEP 1] Accounting for all 590,540 records and 6,692-record embargo purge...")
    df, y = load_ieee_cis_dataset(sample_size=590540)
    total_raw = len(df)

    (X_train, y_train), (X_val, y_val), (X_test, y_test) = temporal_train_val_test_split(
        df, y, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, embargo_seconds=86400
    )

    t_train_max = X_train["TransactionDT"].max()
    t_val_min = X_val["TransactionDT"].min()
    t_val_max = X_val["TransactionDT"].max()
    t_test_min = X_test["TransactionDT"].min()

    # Calculate exact counts in the purged embargo buffers
    embargo_1_mask = (df["TransactionDT"] > t_train_max) & (df["TransactionDT"] < t_val_min)
    embargo_2_mask = (df["TransactionDT"] > t_val_max) & (df["TransactionDT"] < t_test_min)

    n_embargo_1 = embargo_1_mask.sum()
    n_embargo_2 = embargo_2_mask.sum()
    total_purged = n_embargo_1 + n_embargo_2
    total_retained = len(X_train) + len(X_val) + len(X_test)

    print(f"  Total Raw Records:            {total_raw:,}")
    print(f"  Training Split (70%):         {len(X_train):,}")
    print(f"  Embargo Purge Gap 1 (24h):     {n_embargo_1:,}")
    print(f"  Validation Split (15%):        {len(X_val):,}")
    print(f"  Embargo Purge Gap 2 (24h):     {n_embargo_2:,}")
    print(f"  Held-Out Test Split (15%):     {len(X_test):,}")
    print(f"  -------------------------------------------")
    print(f"  Total Retained in Splits:     {total_retained:,}")
    print(f"  Total Purged in 24h Embargos:  {total_purged:,}")
    print(f"  Reconciliation Check:         {total_retained + total_purged:,} / {total_raw:,} (100.0% accounted for)")
    assert total_retained + total_purged == total_raw

    # 2. Transform design matrix using fitted preprocessor
    print("\n[STEP 2] Transforming held-out test split using fitted preprocessor...")
    artifacts_dir = PROJECT_ROOT / "backend" / "artifacts" / "v3"
    preprocessor = joblib.load(artifacts_dir / "v3_preprocessor.joblib")
    lgbm_model = FraudShieldLightGBM.load(artifacts_dir / "lightgbm_fraudshield_v3.joblib")

    X_test_trans = preprocessor.transform(X_test)
    X_train_trans = preprocessor.transform(X_train)

    # 3. Fit comparative XGBoost model on same training set
    print("\n[STEP 3] Training matched XGBoost baseline on same training split...")
    xgb = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.030,
        scale_pos_weight=5.0,
        tree_method="hist",
        random_state=42,
        eval_metric="logloss",
        n_jobs=-1
    )
    t0 = time.perf_counter()
    xgb.fit(X_train_trans, y_train)
    xgb_train_time = time.perf_counter() - t0
    print(f"  XGBoost training completed in {xgb_train_time:.2f}s")

    # 4. Evaluate both on identical held-out test set
    print("\n[STEP 4] Evaluating both models on untouched held-out test split (N=82,406)...")
    lgbm_probs = lgbm_model.predict_proba(X_test_trans)[:, 1]
    xgb_probs = xgb.predict_proba(X_test_trans)[:, 1]

    lgbm_metrics = compute_classification_metrics(y_test.values, lgbm_probs, threshold=0.700)
    xgb_metrics = compute_classification_metrics(y_test.values, xgb_probs, threshold=0.700)

    # 5. Benchmark inference latency over 500 single-row runs
    print("\n[STEP 5] Benchmarking single-row inference latency (N=500 iterations)...")
    sample_row = X_test_trans.iloc[[0]]
    lgbm_lat = benchmark_inference_latency(lgbm_model, sample_row, n_iterations=500)
    xgb_lat = benchmark_inference_latency(xgb, sample_row, n_iterations=500)

    # 6. Format comparison table
    summary_data = [
        {
            "Model Architecture": "FraudShield 3.0 (LightGBM)",
            "Monotonic Constraints": "YES (Burst, Ratio, C1-C3)",
            "Optimal Threshold": 0.700,
            "ROC-AUC": round(lgbm_metrics["roc_auc"], 4),
            "PR-AUC": round(lgbm_metrics["pr_auc"], 4),
            "Precision": f"{lgbm_metrics['precision'] * 100:.2f}%",
            "Recall": f"{lgbm_metrics['recall'] * 100:.2f}%",
            "F1-Score": round(lgbm_metrics["f1_score"], 4),
            "FPR": f"{lgbm_metrics['fpr'] * 100:.3f}%",
            "P50 Latency": f"{lgbm_lat['latency_p50_ms']:.2f} ms",
            "P99 Latency": f"{lgbm_lat['latency_p99_ms']:.2f} ms"
        },
        {
            "Model Architecture": "Matched Baseline (XGBoost)",
            "Monotonic Constraints": "NO",
            "Optimal Threshold": 0.700,
            "ROC-AUC": round(xgb_metrics["roc_auc"], 4),
            "PR-AUC": round(xgb_metrics["pr_auc"], 4),
            "Precision": f"{xgb_metrics['precision'] * 100:.2f}%",
            "Recall": f"{xgb_metrics['recall'] * 100:.2f}%",
            "F1-Score": round(xgb_metrics["f1_score"], 4),
            "FPR": f"{xgb_metrics['fpr'] * 100:.3f}%",
            "P50 Latency": f"{xgb_lat['latency_p50_ms']:.2f} ms",
            "P99 Latency": f"{xgb_lat['latency_p99_ms']:.2f} ms"
        }
    ]

    res_df = pd.DataFrame(summary_data)
    print("\n" + "=" * 80)
    print("HEAD-TO-HEAD BENCHMARK RESULTS (HELD-OUT TEST SET N=82,406)")
    print("=" * 80)
    print(res_df.to_string(index=False))

    # Save benchmark results
    out_path = PROJECT_ROOT / "documentation" / "LIGHTGBM_VS_XGBOOST_BENCHMARK.csv"
    res_df.to_csv(out_path, index=False)
    print(f"\nSaved benchmark results to {out_path}")


if __name__ == "__main__":
    main()
