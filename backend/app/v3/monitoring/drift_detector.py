"""
FraudShield 3.0 Drift Detection Service.
Computes Population Stability Index (PSI), Kolmogorov-Smirnov (KS) two-sample tests,
and concept drift tracking against empirical training reference baselines.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

logger = logging.getLogger(__name__)

DEFAULT_BASELINE_FILE = (
    Path(__file__).resolve().parent.parent.parent.parent / "artifacts" / "v3" / "baseline_feature_stats.json"
)


def compute_psi(
    expected_values: np.ndarray,
    actual_values: np.ndarray,
    num_bins: int = 10,
    epsilon: float = 1e-4
) -> Tuple[float, str]:
    """
    Computes Population Stability Index (PSI) between reference baseline and actual production data.
    Returns (psi_value, status_category).
    Categories: 'STABLE' (PSI < 0.10), 'MODERATE_DRIFT' (0.10 <= PSI < 0.25), 'SIGNIFICANT_DRIFT' (PSI >= 0.25).
    """
    exp = np.asarray(expected_values, dtype=float)
    act = np.asarray(actual_values, dtype=float)

    # Filter NaN / inf
    exp = exp[np.isfinite(exp)]
    act = act[np.isfinite(act)]

    if len(exp) < 10 or len(act) < 10:
        return 0.0, "INSUFFICIENT_DATA"

    # Define quantile bin boundaries based on expected/reference distribution
    quantiles = np.linspace(0, 100, num_bins + 1)
    bin_edges = np.percentile(exp, quantiles)
    bin_edges = np.unique(bin_edges)

    if len(bin_edges) < 2:
        return 0.0, "STABLE"

    # Ensure edge ranges cover all values
    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    exp_counts, _ = np.histogram(exp, bins=bin_edges)
    act_counts, _ = np.histogram(act, bins=bin_edges)

    exp_pct = (exp_counts / len(exp)) + epsilon
    act_pct = (act_counts / len(act)) + epsilon

    # Normalize back to 1.0 after epsilon smoothing
    exp_pct /= exp_pct.sum()
    act_pct /= act_pct.sum()

    psi_val = float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))
    psi_val = max(0.0, round(psi_val, 4))

    if psi_val < 0.10:
        status = "STABLE"
    elif psi_val < 0.25:
        status = "MODERATE_DRIFT"
    else:
        status = "SIGNIFICANT_DRIFT"

    return psi_val, status


class DriftDetector:
    """
    Monitors streaming feature vectors and prediction outputs against baseline reference statistics.
    """

    def __init__(self, baseline_path: Optional[Path] = None):
        self.baseline_path = baseline_path or DEFAULT_BASELINE_FILE
        self.baselines: Dict[str, Any] = {}
        self.recent_predictions: List[float] = []
        self.recent_features: Dict[str, List[float]] = {}
        self.window_capacity: int = 1000

        self.load_baselines()

    def load_baselines(self) -> bool:
        """Loads precomputed quantile distributions and stats from JSON."""
        if not self.baseline_path.exists():
            logger.warning("DriftDetector: Baseline file %s does not exist.", self.baseline_path)
            return False
        try:
            with open(self.baseline_path, "r", encoding="utf-8") as f:
                self.baselines = json.load(f)
            logger.info("DriftDetector: Loaded reference baselines for %d features.", len(self.baselines.get("features", {})))
            return True
        except Exception as exc:
            logger.error("DriftDetector: Failed to load baselines: %s", exc)
            return False

    def record_prediction(self, fraud_prob: float, features_dict: Optional[Dict[str, float]] = None):
        """Records streaming inference event for rolling drift tracking."""
        self.recent_predictions.append(float(fraud_prob))
        if len(self.recent_predictions) > self.window_capacity:
            self.recent_predictions.pop(0)

        if features_dict:
            for k, v in features_dict.items():
                if isinstance(v, (int, float)) and np.isfinite(v):
                    buf = self.recent_features.setdefault(k, [])
                    buf.append(float(v))
                    if len(buf) > self.window_capacity:
                        buf.pop(0)

    def evaluate_feature_drift(self, feature_name: str) -> Dict[str, Any]:
        """
        Evaluates PSI and KS-test for a specified feature against its baseline.
        """
        values = self.recent_features.get(feature_name, [])
        feat_base = self.baselines.get("features", {}).get(feature_name)

        if not feat_base or len(values) < 50:
            return {
                "feature": feature_name,
                "status": "INSUFFICIENT_DATA",
                "sample_count": len(values)
            }

        ref_sample = np.array(feat_base.get("sample_quantiles", []))
        if len(ref_sample) == 0:
            return {"feature": feature_name, "status": "NO_BASELINE_DATA"}

        psi_val, psi_status = compute_psi(ref_sample, np.array(values))
        ks_stat, p_val = ks_2samp(ref_sample, np.array(values))

        return {
            "feature": feature_name,
            "sample_count": len(values),
            "psi_value": psi_val,
            "psi_status": psi_status,
            "ks_statistic": round(float(ks_stat), 4),
            "ks_p_value": round(float(p_val), 5),
            "is_drift_detected": bool(psi_status == "SIGNIFICANT_DRIFT" or p_val < 0.001)
        }

    def evaluate_prediction_drift(self, optimal_threshold: float = 0.700) -> Dict[str, Any]:
        """
        Evaluates concept drift across recent prediction probabilities.
        """
        if len(self.recent_predictions) < 50:
            return {
                "status": "INSUFFICIENT_DATA",
                "sample_count": len(self.recent_predictions)
            }

        probs = np.array(self.recent_predictions)
        rolling_fraud_rate = float(np.mean(probs >= optimal_threshold))
        baseline_fraud_rate = float(self.baselines.get("target", {}).get("fraud_rate", 0.035))

        # Flag concept drift if fraud rate deviates significantly from training baseline (3.5% +/- 3.0%)
        rate_delta = abs(rolling_fraud_rate - baseline_fraud_rate)
        is_concept_drift = rate_delta > 0.035

        return {
            "sample_count": len(probs),
            "rolling_fraud_rate": round(rolling_fraud_rate, 4),
            "baseline_fraud_rate": round(baseline_fraud_rate, 4),
            "mean_probability": round(float(np.mean(probs)), 4),
            "std_probability": round(float(np.std(probs)), 4),
            "is_concept_drift": is_concept_drift,
            "status": "CONCEPT_DRIFT_ALERT" if is_concept_drift else "STABLE"
        }

    def get_full_report(self) -> Dict[str, Any]:
        """Produces overall drift telemetry for all tracked features and model output."""
        pred_drift = self.evaluate_prediction_drift()
        feature_reports = {}
        for feat in list(self.recent_features.keys()):
            feature_reports[feat] = self.evaluate_feature_drift(feat)

        any_drift = pred_drift.get("is_concept_drift", False) or any(
            f.get("is_drift_detected", False) for f in feature_reports.values()
        )

        return {
            "status": "DRIFT_ALERT" if any_drift else "HEALTHY",
            "prediction_drift": pred_drift,
            "feature_drifts": feature_reports,
            "baselines_loaded": bool(self.baselines)
        }


# Global drift detector instance
drift_detector = DriftDetector()
