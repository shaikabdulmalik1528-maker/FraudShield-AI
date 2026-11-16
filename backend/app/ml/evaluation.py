"""
Model Evaluation and Metric Calculation Suite.
Evaluates imbalanced classification performance focusing on PR-AUC, F1, Recall and Precision.
"""

import numpy as np
from typing import Dict, Any, Tuple
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
    beta: float = 1.0
) -> Tuple[float, float]:
    """
    Finds the optimal decision threshold that maximizes the F-beta score
    on validation data. Beta > 1 weights recall higher than precision.
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_pred_proba)
    
    # Avoid division by zero
    numerator = (1 + beta**2) * (precisions * recalls)
    denominator = ((beta**2 * precisions) + recalls)
    f_scores = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator != 0)
    
    best_idx = np.argmax(f_scores[:-1]) if len(thresholds) > 0 else 0
    best_threshold = float(thresholds[best_idx]) if len(thresholds) > 0 else 0.5
    best_f_score = float(f_scores[best_idx]) if len(thresholds) > 0 else 0.0
    
    # Clip between 0.05 and 0.90 for practical operational safety
    best_threshold = max(0.05, min(0.90, best_threshold))
    return best_threshold, best_f_score
