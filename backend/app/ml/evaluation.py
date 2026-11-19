"""
Model Evaluation and Metric Calculation Suite.
Evaluates imbalanced classification performance focusing on PR-AUC, F1, Recall and Precision.
"""

import numpy as np
from typing import Dict, Any, Tuple, Union
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_curve
)

def evaluate_predictions(
    y_true: np.ndarray,
    y_pred_proba: np.ndarray,
    threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Computes rigorous classification metrics given ground truth and predicted probabilities.
    """
    y_pred = (y_pred_proba >= threshold).astype(int)
    
    # Calculate base metrics
    precision = float(precision_score(y_true, y_pred, zero_division=0))
    recall = float(recall_score(y_true, y_pred, zero_division=0))
    f1 = float(f1_score(y_true, y_pred, zero_division=0))
    
    # Compute Area Under Curves
    try:
        roc_auc = float(roc_auc_score(y_true, y_pred_proba))
    except Exception:
        roc_auc = 0.5
        
    try:
        pr_auc = float(average_precision_score(y_true, y_pred_proba))
    except Exception:
        pr_auc = 0.0
        
    cm = confusion_matrix(y_true, y_pred)
    # Ensure standard 2x2 shape
    if cm.shape == (2, 2):
        tn, fp, fn, tp = cm.ravel()
    else:
        tn, fp, fn, tp = 0, 0, 0, 0
        
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "roc_auc": round(roc_auc, 4),
        "pr_auc": round(pr_auc, 4),
        "threshold": round(threshold, 4),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp)
        }
    }

def find_optimal_threshold(
    y_true: np.ndarray,
    y_pred_proba: np.ndarray,
    beta: float = 1.0,
    min_threshold: float = 0.05,
    max_threshold: float = 0.90,
    return_details: bool = False
) -> Union[Tuple[float, float], Dict[str, Any]]:
    """
    Finds the optimal decision threshold that maximizes the F-beta score.
    Applies operational safety clipping between min_threshold and max_threshold (0.05 - 0.90).
    After clipping, precision, recall, and F-beta are strictly recalculated at the clipped
    operational threshold so that the returned threshold and score refer to the identical operating point.
    
    When return_details is True, returns a comprehensive dictionary retaining both
    unconstrained and operational threshold metrics along with clipping status.
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_pred_proba)
    
    # Avoid division by zero
    numerator = (1 + beta**2) * (precisions * recalls)
    denominator = ((beta**2 * precisions) + recalls)
    f_scores = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator != 0)
    
    best_idx = np.argmax(f_scores[:-1]) if len(thresholds) > 0 else 0
    raw_best_threshold = float(thresholds[best_idx]) if len(thresholds) > 0 else 0.5
    raw_best_f = float(f_scores[best_idx]) if len(thresholds) > 0 else 0.0
    raw_precision = float(precisions[best_idx]) if len(precisions) > 0 else 0.0
    raw_recall = float(recalls[best_idx]) if len(recalls) > 0 else 0.0
    
    # Operational safety clipping (default: 0.05 to 0.90)
    operational_threshold = max(min_threshold, min(max_threshold, raw_best_threshold))
    
    # Recalculate operational metrics directly at the clipped threshold
    y_pred_clipped = (y_pred_proba >= operational_threshold).astype(int)
    op_precision = float(precision_score(y_true, y_pred_clipped, zero_division=0))
    op_recall = float(recall_score(y_true, y_pred_clipped, zero_division=0))
    
    if (op_precision + op_recall) > 0:
        op_f_score = float((1 + beta**2) * (op_precision * op_recall) / ((beta**2 * op_precision) + op_recall + 1e-10))
    else:
        op_f_score = 0.0
        
    if return_details:
        return {
            "operational_threshold": round(operational_threshold, 4),
            "operational_f_score": round(op_f_score, 4),
            "operational_precision": round(op_precision, 4),
            "operational_recall": round(op_recall, 4),
            "unconstrained_threshold": round(raw_best_threshold, 6),
            "unconstrained_f_score": round(raw_best_f, 4),
            "unconstrained_precision": round(raw_precision, 4),
            "unconstrained_recall": round(raw_recall, 4),
            "is_clipped": bool(operational_threshold != raw_best_threshold),
            "min_threshold": min_threshold,
            "max_threshold": max_threshold
        }
        
    return operational_threshold, op_f_score
