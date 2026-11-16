"""
Hybrid Fraud Detection Engine.
Combines:
1. Supervised Fraud Classifier (e.g. XGBoost / Random Forest)
2. Unsupervised Anomaly Detector (Isolation Forest)
3. Configurable Multi-Factor Risk Scoring Engine
4. SHAP Local Explainability
"""

import json
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from pathlib import Path

from backend.app.config import settings
from backend.app.ml.preprocessing import FEATURE_COLUMNS, FraudDataPreprocessor
from backend.app.ml.anomaly import AnomalyDetector
from backend.app.ml.explainability import ModelExplainer
from backend.app.utils.logger import logger

class HybridFraudEngine:
    """
    Singleton service managing model artifact loading, preprocessing,
    hybrid inference, risk scoring, and SHAP explainability.
    """
    def __init__(self):
        self.supervised_model = None
        self.preprocessor: Optional[FraudDataPreprocessor] = None
        self.anomaly_detector: Optional[AnomalyDetector] = None
        self.explainer: Optional[ModelExplainer] = None
        self.threshold: float = 0.50
        self.metadata: Dict[str, Any] = {}
        self.is_loaded: bool = False
        
        # Risk engine weights (Configurable)
        self.fraud_weight: float = settings.FRAUD_WEIGHT
        self.anomaly_weight: float = settings.ANOMALY_WEIGHT
        self.low_threshold: float = settings.LOW_RISK_THRESHOLD
        self.high_threshold: float = settings.HIGH_RISK_THRESHOLD

    def load_artifacts(self) -> bool:
        """
        Loads preprocessor, supervised model, isolation forest, and threshold metadata.
        Returns True if successful, False otherwise.
        """
        try:
            if not settings.SUPERVISED_MODEL_PATH.exists():
                logger.warning(f"Supervised model artifact not found at {settings.SUPERVISED_MODEL_PATH}. Engine in uninitialized state.")
                return False

            logger.info("Loading ML artifacts into HybridFraudEngine...")
            self.supervised_model = joblib.load(settings.SUPERVISED_MODEL_PATH)
            self.preprocessor = joblib.load(settings.PREPROCESSOR_PATH)
            self.anomaly_detector = AnomalyDetector.load(settings.ANOMALY_MODEL_PATH)
            
            # Load threshold if available
            if settings.THRESHOLD_PATH.exists():
                with open(settings.THRESHOLD_PATH, "r") as f:
                    meta = json.load(f)
                    self.threshold = float(meta.get("optimal_threshold", 0.50))
            
            # Load metadata
            if settings.METRICS_PATH.exists():
                with open(settings.METRICS_PATH, "r") as f:
                    self.metadata = json.load(f)

            # Load background sample for SHAP explainability
            bg_sample = None
            if settings.SHAP_BACKGROUND_PATH.exists():
                bg_sample = joblib.load(settings.SHAP_BACKGROUND_PATH)
            self.explainer = ModelExplainer(self.supervised_model, background_sample=bg_sample)

            self.is_loaded = True
            logger.info(f"HybridFraudEngine initialized successfully. Decision threshold: {self.threshold:.3f}")
            return True
        except Exception as e:
            logger.error(f"Failed to load engine artifacts: {e}", exc_info=True)
            self.is_loaded = False
            return False

    def calculate_risk_score(
        self,
        fraud_prob: float,
        is_anomaly: bool,
        anomaly_score: float
    ) -> Tuple[float, str, str]:
        """
        Calculates calibrated multi-signal transaction risk score (0 - 100),
        risk category (LOW, MEDIUM, HIGH), and final prediction (LEGITIMATE, SUSPICIOUS).
        
        The supervised fraud probability carries the primary weight (75%), while
        unsupervised anomaly detection provides an orthogonal signal (25%) to detect novel patterns.
        """
        # Weighted combination of signals
        base_risk = (fraud_prob * self.fraud_weight + anomaly_score * self.anomaly_weight) * 100.0

        # Anomaly modifier: If Isolation Forest detects a severe outlier, ensure minimum risk floor
        if is_anomaly:
            base_risk = max(base_risk, 45.0)

        # Scale pos boost if fraud probability alone exceeds the decision threshold
        if fraud_prob >= self.threshold:
            base_risk = max(base_risk, 70.0)

        risk_score = round(float(np.clip(base_risk, 0.0, 100.0)), 1)

        # Determine Risk Category
        if risk_score >= self.high_threshold:
            category = "HIGH"
        elif risk_score >= self.low_threshold:
            category = "MEDIUM"
        else:
            category = "LOW"

        # Determine Decision
        prediction = "SUSPICIOUS" if (risk_score >= 50.0 or fraud_prob >= self.threshold) else "LEGITIMATE"

        return risk_score, category, prediction

    def predict_transaction(
        self,
        transaction_dict: Dict[str, float],
        generate_explanation: bool = True
    ) -> Dict[str, Any]:
        """
        Executes complete end-to-end inference pipeline for a single transaction.
        """
        if not self.is_loaded:
            # Attempt lazy load
            if not self.load_artifacts():
                raise RuntimeError("FraudShield AI ML artifacts are not trained/loaded yet.")

        # 1. Transform features strictly through fitted preprocessor
        features_scaled = self.preprocessor.transform_single(transaction_dict)

        # 2. Supervised Fraud Prediction
        fraud_probs = self.supervised_model.predict_proba(features_scaled)
        fraud_prob = float(fraud_probs[0, 1])

        # 3. Unsupervised Anomaly Prediction
        is_anomaly_arr, anomaly_score_arr = self.anomaly_detector.predict_anomaly(features_scaled)
        is_anomaly = bool(is_anomaly_arr[0])
        anomaly_score = float(anomaly_score_arr[0])

        # 4. Calibrated Multi-Signal Risk Scoring
        risk_score, risk_cat, prediction = self.calculate_risk_score(
            fraud_prob=fraud_prob,
            is_anomaly=is_anomaly,
            anomaly_score=anomaly_score
        )

        # 5. SHAP Explainability
        explanation = None
        if generate_explanation and self.explainer:
            explanation = self.explainer.explain_instance(
                features_array=features_scaled,
                raw_feature_dict=transaction_dict,
                top_k=5
            )

        return {
            "fraud_probability": round(fraud_prob, 4),
            "fraud_probability_pct": round(fraud_prob * 100.0, 2),
            "is_anomaly": is_anomaly,
            "anomaly_score": round(anomaly_score, 4),
            "risk_score": risk_score,
            "risk_category": risk_cat,
            "prediction": prediction,
            "model_version": self.metadata.get("version", "1.0.0"),
            "explanation": explanation
        }

# Global singleton
fraud_engine = HybridFraudEngine()
