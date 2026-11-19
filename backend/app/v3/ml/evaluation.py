"""
FraudShield 3.0 Model Evaluation & Benchmarking Suite.
Computes ROC-AUC, PR-AUC, optimal threshold sweeps, confusion matrices,
and microsecond-precision inference latency measurements.
"""

import time
import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)

logger = logging.getLogger(__name__)

# Frozen FraudShield 1.0 XGBoost Baseline Benchmarks (for comparative reporting)
FROZEN_BASELINE_1_0 = {
    "model_name": "FraudShield 1.0 (XGBoost PCA)",
    "feature_space": "30 Features (Time, Amount, V1-V28 PCA)",
    "optimal_threshold": 0.895,
    "roc_auc": 0.9782,
    "pr_auc": 0.8651,
    "precision": 0.9298,
    "recall": 0.7465,
    "f1_score": 0.8281,
    "latency_p99_ms": 7.85
}


def compute_classification_metrics(
    y_true: np.ndarray,
    y_pred_proba: np.ndarray,
    threshold: float = 0.50
) -> Dict[str, Any]:
    """
    Computes standard fraud detection metrics across continuous probabilities
    and thresholded binary decisions.
    """
    y_arr = np.asarray(y_true, dtype=int)
    p_arr = np.asarray(y_pred_proba, dtype=float)

    # 1. Ranking & Discrimination Metrics
    roc_auc = float(roc_auc_score(y_arr, p_arr))
    pr_auc = float(average_precision_score(y_arr, p_arr))

    # 2. Threshold Decisions
    y_pred = (p_arr >= threshold).astype(int)

    precision = float(precision_score(y_arr, y_pred, zero_division=0))
    recall = float(recall_score(y_arr, y_pred, zero_division=0))
    f1 = float(f1_score(y_arr, y_pred, zero_division=0))

    # 3. Confusion Matrix Breakdown
    cm = confusion_matrix(y_arr, y_pred)
    if cm.shape == (2, 2):
        tn, fp, fn, tp = [int(v) for v in cm.ravel()]
    else:
        tn, fp, fn, tp = int(cm[0, 0]), 0, 0, 0

    fpr = round(fp / max(fp + tn, 1), 5)
    fnr = round(fn / max(fn + tp, 1), 5)
    specificity = round(tn / max(tn + fp, 1), 5)

    return {
        "threshold": round(threshold, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "fpr": fpr,
        "fnr": fnr,
        "specificity": specificity,
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "total_samples": len(y_arr),
        "fraud_prevalence": round(float(y_arr.mean()), 4)
    }


def find_optimal_threshold_v3(
    y_true: np.ndarray,
    y_pred_proba: np.ndarray,
    metric: str = "f1",
    min_threshold: float = 0.05,
    max_threshold: float = 0.95,
    step: float = 0.01
) -> Dict[str, Any]:
    """
    Sweeps decision threshold across candidate values on validation split
    to locate optimal operating point maximizing specified metric (F1).
    """
    logger.info("Sweeping decision thresholds from %.2f to %.2f (metric=%s)...", min_threshold, max_threshold, metric)
    thresholds = np.arange(min_threshold, max_threshold + 1e-5, step)

    best_threshold = 0.50
    best_score = -1.0
    best_metrics: Dict[str, Any] = {}
    history = []

    for tau in thresholds:
        m = compute_classification_metrics(y_true, y_pred_proba, threshold=float(tau))
        score = m[metric] if metric in m else m["f1_score"]
        history.append({"threshold": round(float(tau), 3), metric: score, "precision": m["precision"], "recall": m["recall"]})

        if score > best_score:
            best_score = score
            best_threshold = float(tau)
            best_metrics = m

    logger.info("Optimal threshold located: tau=%.3f, best_%s=%.4f (Prec=%.4f, Rec=%.4f)",
                best_threshold, metric, best_score, best_metrics["precision"], best_metrics["recall"])

    return {
        "optimal_threshold": round(best_threshold, 3),
        "optimized_metric": metric,
        "optimal_score": round(best_score, 4),
        "metrics_at_threshold": best_metrics,
        "sweep_history": history
    }


def benchmark_inference_latency(
    model: Any,
    sample_row: pd.Series,
    n_iterations: int = 1000
) -> Dict[str, float]:
    """
    Benchmarks single-row inference latency with microsecond precision.
    Simulates high-throughput production authorization SLA.
    """
    logger.info("Benchmarking single-row inference latency over N=%d iterations...", n_iterations)

    # Warmup runs
    for _ in range(50):
        if hasattr(model, "predict_single"):
            _ = model.predict_single(sample_row)
        else:
            _ = model.predict_proba(sample_row)[:, 1]

    latencies_ms: List[float] = []
    for _ in range(n_iterations):
        t0 = time.perf_counter_ns()
        if hasattr(model, "predict_single"):
            _ = model.predict_single(sample_row)
        else:
            _ = model.predict_proba(sample_row)[:, 1]
        t1 = time.perf_counter_ns()
        latencies_ms.append((t1 - t0) / 1_000_000.0)

    p50 = float(np.percentile(latencies_ms, 50))
    p90 = float(np.percentile(latencies_ms, 90))
    p95 = float(np.percentile(latencies_ms, 95))
    p99 = float(np.percentile(latencies_ms, 99))
    mean_lat = float(np.mean(latencies_ms))

    logger.info("Inference Latency Benchmark: P50=%.3fms | P90=%.3fms | P99=%.3fms", p50, p90, p99)

    return {
        "latency_p50_ms": round(p50, 3),
        "latency_p90_ms": round(p90, 3),
        "latency_p95_ms": round(p95, 3),
        "latency_p99_ms": round(p99, 3),
        "latency_mean_ms": round(mean_lat, 3),
        "iterations_measured": n_iterations
    }


def compare_models(
    v3_metrics: Dict[str, Any],
    v3_latency: Dict[str, float],
    baseline: Optional[Dict[str, Any]] = None
) -> pd.DataFrame:
    """
    Constructs a side-by-side comparative table between FraudShield 3.0 (LightGBM)
    and the frozen FraudShield 1.0 (XGBoost) baseline.
    """
    base = baseline or FROZEN_BASELINE_1_0
    comparison_data = [
        {
            "System": base["model_name"],
            "Feature Architecture": base["feature_space"],
            "Decision Threshold": base["optimal_threshold"],
            "ROC-AUC": base["roc_auc"],
            "PR-AUC": base["pr_auc"],
            "Precision": base["precision"],
            "Recall": base["recall"],
            "F1-Score": base["f1_score"],
            "P99 Latency (ms)": base["latency_p99_ms"]
        },
        {
            "System": "FraudShield 3.0 (LightGBM)",
            "Feature Architecture": "Raw Schema + Streaming Behavioral Velocity",
            "Decision Threshold": v3_metrics["threshold"],
            "ROC-AUC": v3_metrics["roc_auc"],
            "PR-AUC": v3_metrics["pr_auc"],
            "Precision": v3_metrics["precision"],
            "Recall": v3_metrics["recall"],
            "F1-Score": v3_metrics["f1_score"],
            "P99 Latency (ms)": v3_latency.get("latency_p99_ms", 0.0)
        }
    ]
    return pd.DataFrame(comparison_data)
