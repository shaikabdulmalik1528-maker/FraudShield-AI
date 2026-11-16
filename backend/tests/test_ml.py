"""
Machine Learning Pipeline & Engine Unit Tests.
"""

import numpy as np
import pandas as pd
import pytest
from backend.app.ml.preprocessing import FraudDataPreprocessor, FEATURE_COLUMNS
from backend.app.ml.evaluation import evaluate_predictions, find_optimal_threshold
from backend.app.ml.anomaly import AnomalyDetector
from backend.app.services.fraud_engine import fraud_engine

def test_preprocessor_fitting_and_transformation():
    """Verify preprocessor transforms Time and Amount while preserving PCA feature order."""
    # Create synthetic test frame
    np.random.seed(42)
    fake_data = np.random.randn(20, len(FEATURE_COLUMNS))
    fake_df = pd.DataFrame(fake_data, columns=FEATURE_COLUMNS)
    fake_df["Time"] = np.abs(fake_df["Time"]) * 1000
    fake_df["Amount"] = np.abs(fake_df["Amount"]) * 50

    preprocessor = FraudDataPreprocessor()
    preprocessor.fit(fake_df)
    transformed = preprocessor.transform(fake_df)

    assert transformed.shape == (20, 30)
    assert not np.isnan(transformed).any()

def test_anomaly_detector_scoring():
    """Verify Isolation Forest outputs normalized score [0.0, 1.0]."""
    np.random.seed(42)
    X = np.random.normal(0, 1, size=(100, 30))
    detector = AnomalyDetector(contamination=0.05, random_state=42)
    detector.fit(X)

    is_anomaly, norm_score = detector.predict_anomaly(X)
    assert len(is_anomaly) == 100
    assert (norm_score >= 0.0).all() and (norm_score <= 1.0).all()

def test_evaluation_metrics_calculation():
    """Verify precision, recall, F1, PR-AUC, and confusion matrix calculation."""
    y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    y_prob = np.array([0.1, 0.2, 0.3, 0.4, 0.7, 0.8, 0.9, 0.95])

    metrics = evaluate_predictions(y_true, y_prob, threshold=0.5)
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1_score"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["confusion_matrix"]["tp"] == 4
    assert metrics["confusion_matrix"]["tn"] == 4

def test_optimal_threshold_tuning():
    """Verify threshold optimization returns value between 0.05 and 0.90."""
    y_true = np.array([0, 0, 0, 0, 0, 1, 1, 1])
    y_prob = np.array([0.1, 0.15, 0.2, 0.3, 0.45, 0.55, 0.8, 0.9])

    best_thresh, best_f1 = find_optimal_threshold(y_true, y_prob)
    assert 0.05 <= best_thresh <= 0.90
    assert best_f1 > 0.0

def test_fraud_engine_risk_calculation():
    """Verify hybrid risk engine properly aggregates supervised and unsupervised signals."""
    fraud_engine.load_artifacts()
    # High probability fraud
    risk, cat, pred = fraud_engine.calculate_risk_score(
        fraud_prob=0.95,
        is_anomaly=True,
        anomaly_score=0.85
    )
    assert risk >= 75.0
    assert cat == "HIGH"
    assert pred == "SUSPICIOUS"

    # Low probability legitimate transaction
    risk_low, cat_low, pred_low = fraud_engine.calculate_risk_score(
        fraud_prob=0.01,
        is_anomaly=False,
        anomaly_score=0.10
    )
    assert risk_low < 30.0
    assert cat_low == "LOW"
    assert pred_low == "LEGITIMATE"
