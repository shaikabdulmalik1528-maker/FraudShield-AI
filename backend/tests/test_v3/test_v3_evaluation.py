"""
Unit tests for FraudShield 3.0 Model Evaluation & Benchmarking Suite.
Verifies ROC-AUC, PR-AUC, optimal threshold search, confusion matrix, and baseline comparison.
"""

import pytest
import numpy as np
import pandas as pd
from backend.app.v3.ml.evaluation import (
    compute_classification_metrics,
    find_optimal_threshold_v3,
    compare_models,
    FROZEN_BASELINE_1_0
)


def test_classification_metrics_computation():
    """Asserts mathematical consistency of discrimination and threshold metrics."""
    # Synthetic ground truth & probabilities
    y_true = np.array([0, 0, 0, 0, 0, 1, 1, 1, 0, 1])
    y_pred_proba = np.array([0.1, 0.2, 0.15, 0.8, 0.05, 0.9, 0.85, 0.6, 0.3, 0.4])

    metrics = compute_classification_metrics(y_true, y_pred_proba, threshold=0.50)

    assert "roc_auc" in metrics
    assert "pr_auc" in metrics
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1_score" in metrics
    assert "true_positives" in metrics
    assert "false_positives" in metrics

    # At threshold 0.5:
    # Pred positives: indices [3 (prob 0.8, true 0), 5 (0.9, true 1), 6 (0.85, true 1), 7 (0.6, true 1)]
    # TP = 3 (indices 5, 6, 7), FP = 1 (index 3)
    assert metrics["true_positives"] == 3
    assert metrics["false_positives"] == 1
    assert metrics["precision"] == 0.75  # 3 / (3 + 1)
    assert metrics["recall"] == 0.75     # 3 / 4 true frauds


def test_optimal_threshold_search():
    """Asserts that threshold optimization maximizes F1 score."""
    y_true = np.array([0, 0, 0, 0, 1, 1, 1, 0, 1, 0])
    y_pred_proba = np.array([0.05, 0.10, 0.20, 0.45, 0.55, 0.70, 0.80, 0.30, 0.65, 0.15])

    res = find_optimal_threshold_v3(y_true, y_pred_proba, metric="f1", min_threshold=0.1, max_threshold=0.9, step=0.05)

    assert "optimal_threshold" in res
    assert "optimal_score" in res
    assert 0.40 <= res["optimal_threshold"] <= 0.60
    assert res["optimal_score"] > 0.80


def test_compare_models_structure():
    """Asserts that model comparison dataframe contains both systems."""
    v3_m = {
        "threshold": 0.45,
        "roc_auc": 0.985,
        "pr_auc": 0.892,
        "precision": 0.915,
        "recall": 0.820,
        "f1_score": 0.865
    }
    v3_lat = {"latency_p99_ms": 2.15}

    df = compare_models(v3_metrics=v3_m, v3_latency=v3_lat)

    assert len(df) == 2
    assert "FraudShield 1.0 (XGBoost PCA)" in df["System"].values
    assert "FraudShield 3.0 (LightGBM)" in df["System"].values
    assert "PR-AUC" in df.columns
    assert "P99 Latency (ms)" in df.columns
