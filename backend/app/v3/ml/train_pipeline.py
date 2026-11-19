"""
FraudShield 3.0 End-to-End Reproducible LightGBM Training Pipeline.
Executes data loading, purged/embargoed temporal splitting, feature preprocessing,
LightGBM training with early stopping, threshold optimization, latency benchmarking,
and artifact serialization with cryptographic SHA-256 manifests.
"""

import sys
import os
import argparse
import hashlib
import json
import logging
from typing import Dict, Any
from pathlib import Path
from datetime import datetime, timezone
import joblib
import pandas as pd

from backend.app.v3.ml.data_loader import load_ieee_cis_dataset
from backend.app.v3.ml.preprocessor import temporal_train_val_test_split, IeeeCisPreprocessor
from backend.app.v3.ml.lightgbm_model import FraudShieldLightGBM
from backend.app.v3.ml.evaluation import (
    compute_classification_metrics,
    find_optimal_threshold_v3,
    benchmark_inference_latency,
    compare_models
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("train_pipeline_v3")

ARTIFACTS_DIR = Path("backend/artifacts/v3")


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 cryptographic digest of an artifact file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_training_pipeline(
    sample_size: int = 100000,
    enforce_monotonic: bool = True,
    artifacts_dir: Path = ARTIFACTS_DIR
) -> Dict[str, Any]:
    """
    Executes full reproducible training workflow.
    """
    logger.info("=================================================================")
    logger.info("Starting FraudShield 3.0 Milestone 3C LightGBM Training Pipeline")
    logger.info("Sample size: %d | Monotonic constraints: %s", sample_size, enforce_monotonic)
    logger.info("=================================================================")

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ingest Dataset
    df, y = load_ieee_cis_dataset(sample_size=sample_size)
    logger.info("Dataset loaded: shape=%s, target_mean=%.4f", df.shape, y.mean())

    # 2. Chronological Purged & Embargoed Temporal Split
    (X_train, y_train), (X_val, y_val), (X_test, y_test) = temporal_train_val_test_split(
        df=df,
        y=y,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        embargo_seconds=86400  # 24h embargo gap
    )

    # 3. Fit Preprocessor Strictly on Training Split
    logger.info("Fitting feature preprocessor strictly on Train split...")
    preprocessor = IeeeCisPreprocessor()
    preprocessor.fit(X_train, y_train)

    X_train_proc = preprocessor.transform(X_train)
    X_val_proc = preprocessor.transform(X_val)
    X_test_proc = preprocessor.transform(X_test)
    logger.info("Transformed features: shape=%s, categoricals=%d", X_train_proc.shape, len(preprocessor.categorical_features_))

    # 4. Train LightGBM Model with Early Stopping
    model = FraudShieldLightGBM(enforce_monotonic=enforce_monotonic)
    model.fit(
        X_train=X_train_proc,
        y_train=y_train,
        eval_set=[(X_val_proc, y_val)],
        categorical_feature=preprocessor.categorical_features_,
        early_stopping_rounds=50
    )

    # 5. Threshold Optimization on Validation Set
    logger.info("Executing decision threshold sweep on Validation set...")
    p_val = model.predict_fraud_probability(X_val_proc)
    threshold_results = find_optimal_threshold_v3(
        y_true=y_val.values,
        y_pred_proba=p_val,
        metric="f1"
    )
    optimal_tau = threshold_results["optimal_threshold"]
    logger.info("Optimal threshold chosen: tau=%.3f, Val F1=%.4f", optimal_tau, threshold_results["optimal_score"])

    # 6. Final Evaluation on Held-Out Test Set
    logger.info("Evaluating finalized model on untouched Held-Out Test split (tau=%.3f)...", optimal_tau)
    p_test = model.predict_fraud_probability(X_test_proc)
    test_metrics = compute_classification_metrics(
        y_true=y_test.values,
        y_pred_proba=p_test,
        threshold=optimal_tau
    )
    logger.info(
        "Held-Out Test Results: ROC-AUC=%.4f | PR-AUC=%.4f | Prec=%.4f | Rec=%.4f | F1=%.4f",
        test_metrics["roc_auc"], test_metrics["pr_auc"],
        test_metrics["precision"], test_metrics["recall"], test_metrics["f1_score"]
    )

    # 7. Single-Row Inference Latency Benchmark
    sample_row = X_test_proc.iloc[0]
    latency_metrics = benchmark_inference_latency(model, sample_row, n_iterations=1000)

    # 8. Model Comparison Table
    comparison_df = compare_models(v3_metrics=test_metrics, v3_latency=latency_metrics)
    logger.info("\n=== Head-to-Head Architecture Benchmark ===\n%s", comparison_df.to_string(index=False))

    # 9. Save Artifacts Strictly to backend/artifacts/v3/
    model_base_path = artifacts_dir / "lightgbm_fraudshield_v3"
    model.save(model_base_path)

    preprocessor_path = artifacts_dir / "v3_preprocessor.joblib"
    joblib.dump(preprocessor, preprocessor_path)

    threshold_config_path = artifacts_dir / "v3_optimal_threshold.json"
    threshold_data = {
        "model_name": "FraudShield 3.0 (LightGBM)",
        "optimal_threshold": optimal_tau,
        "f1_score": test_metrics["f1_score"],
        "precision": test_metrics["precision"],
        "recall": test_metrics["recall"],
        "roc_auc": test_metrics["roc_auc"],
        "pr_auc": test_metrics["pr_auc"],
        "validation_f1": threshold_results["optimal_score"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": sample_size,
        "enforce_monotonic": enforce_monotonic
    }
    with open(threshold_config_path, "w", encoding="utf-8") as f:
        json.dump(threshold_data, f, indent=2)

    # 10. Generate SHA-256 Manifest
    manifest_path = artifacts_dir / "model_manifest.json"
    manifest_data = {
        "model_version": "3.0.0-rc1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "training_sample_size": sample_size,
        "enforce_monotonic": enforce_monotonic,
        "feature_count": len(preprocessor.feature_names_),
        "categorical_feature_count": len(preprocessor.categorical_features_),
        "artifacts": {
            "lightgbm_joblib": {
                "file": "lightgbm_fraudshield_v3.joblib",
                "sha256": compute_file_sha256(artifacts_dir / "lightgbm_fraudshield_v3.joblib")
            },
            "lightgbm_txt": {
                "file": "lightgbm_fraudshield_v3.txt",
                "sha256": compute_file_sha256(artifacts_dir / "lightgbm_fraudshield_v3.txt")
            },
            "preprocessor_joblib": {
                "file": "v3_preprocessor.joblib",
                "sha256": compute_file_sha256(preprocessor_path)
            },
            "optimal_threshold_json": {
                "file": "v3_optimal_threshold.json",
                "sha256": compute_file_sha256(threshold_config_path)
            }
        },
        "test_metrics": test_metrics,
        "latency_metrics": latency_metrics
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    logger.info("All artifacts and cryptographic manifests persisted to %s", artifacts_dir)

    return {
        "test_metrics": test_metrics,
        "threshold_results": threshold_results,
        "latency_metrics": latency_metrics,
        "comparison_df": comparison_df,
        "manifest": manifest_data
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FraudShield 3.0 LightGBM Training Pipeline")
    parser.add_argument("--sample-size", type=int, default=100000, help="Training dataset sample size")
    parser.add_argument("--no-monotonic", dest="enforce_monotonic", action="store_false", help="Disable monotonic constraints")
    args = parser.parse_args()

    results = run_training_pipeline(sample_size=args.sample_size, enforce_monotonic=args.enforce_monotonic)
    print("\nTraining completed successfully.")
