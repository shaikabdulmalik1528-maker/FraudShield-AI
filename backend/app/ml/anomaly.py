"""
Unsupervised Anomaly Detection using Isolation Forest.
Identifies outlier patterns in credit card transactions without requiring ground truth labels.
"""

import numpy as np
import joblib
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from sklearn.ensemble import IsolationForest
from backend.app.utils.logger import logger

class AnomalyDetector:
    """
    Wrapper around Isolation Forest for transaction anomaly detection.
    Normalizes decision function scores to a clean [0.0, 1.0] anomaly risk scale.
    """
    def __init__(self, contamination: float = 0.005, random_state: int = 42):
        self.contamination = contamination
        self.random_state = random_state
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=150,
            max_samples="auto",
            n_jobs=-1
        )
        self.is_fitted = False
        self.min_score_ = None
        self.max_score_ = None

    def fit(self, X: np.ndarray):
        """Fit Isolation Forest on preprocessed training data."""
        logger.info(f"Fitting Isolation Forest on {X.shape[0]} samples (contamination={self.contamination})...")
        self.model.fit(X)
        self.is_fitted = True
        
        # Calculate score distribution for normalization
        raw_scores = self.model.decision_function(X)
        self.min_score_ = float(np.min(raw_scores))
        self.max_score_ = float(np.max(raw_scores))
        logger.info(f"Isolation Forest fitted. Raw score range: [{self.min_score_:.4f}, {self.max_score_:.4f}]")
        return self

    def predict_anomaly(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Predicts anomaly status and normalized anomaly probability.
        Returns:
            is_anomaly: boolean array (True if anomalous)
            normalized_score: float array [0.0, 1.0], where 1.0 is highest anomaly risk
        """
        if not self.is_fitted:
            raise RuntimeError("AnomalyDetector must be fitted before making predictions.")
            
        preds = self.model.predict(X) # 1 for inlier, -1 for outlier/anomaly
        is_anomaly = (preds == -1)
        
        raw_scores = self.model.decision_function(X)
        # Invert and normalize: raw score is lower for anomalies, higher for inliers
        denom = (self.max_score_ - self.min_score_) if (self.max_score_ != self.min_score_) else 1.0
        normalized = (self.max_score_ - raw_scores) / denom
        normalized = np.clip(normalized, 0.0, 1.0)
        
        return is_anomaly, normalized

    def save(self, filepath: Path):
        """Save model state to disk using joblib."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, filepath)
        logger.info(f"Saved AnomalyDetector to {filepath}")

    @classmethod
    def load(cls, filepath: Path) -> "AnomalyDetector":
        """Load model state from disk."""
        if not filepath.exists():
            raise FileNotFoundError(f"Anomaly model not found at {filepath}")
        detector = joblib.load(filepath)
        logger.info(f"Loaded AnomalyDetector from {filepath}")
        return detector
