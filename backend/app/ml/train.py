"""
End-to-End Machine Learning Model Training & Comparative Evaluation Pipeline.
Trains, validates, compares, and serializes:
1. Logistic Regression (Class-weighted)
2. Decision Tree Classifier
3. Random Forest Classifier
4. XGBoost Classifier (Scale Pos Weight)
5. Isolation Forest (Unsupervised Anomaly Detector)
"""

import os
import json
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

from backend.app.ml.preprocessing import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    FraudDataPreprocessor,
    load_and_clean_data,
    prepare_stratified_split,
    apply_smote_resampling,
)
from backend.app.ml.anomaly import AnomalyDetector
from backend.app.ml.explainability import ModelExplainer
from backend.app.ml.evaluation import evaluate_predictions, find_optimal_threshold
from backend.app.config import settings
from backend.app.utils.logger import logger

def train_and_evaluate_all(
    data_path: str,
    output_dir: Path = settings.ARTIFACTS_DIR,
    use_smote: bool = False,
    random_state: int = 42
) -> Dict[str, Any]:
    """
    Executes full multi-model benchmark, threshold optimization, and artifact serialization.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("=" * 60)
    logger.info("STARTING FRAUDSHIELD AI MODEL TRAINING & BENCHMARK")
    logger.info("=" * 60)

    # 1. Load data
    df = load_and_clean_data(data_path)
    total_rows = len(df)
    n_fraud = int(df[TARGET_COLUMN].sum())
    fraud_pct = (n_fraud / total_rows) * 100.0
    logger.info(f"Dataset Loaded: {total_rows:,} rows | Fraud: {n_fraud:,} ({fraud_pct:.3f}%)")

    # 2. Stratified train/test split strictly BEFORE scaling or SMOTE
    X_train_df, X_test_df, y_train, y_test = prepare_stratified_split(
        df, test_size=0.2, random_state=random_state
    )

    # 3. Fit Preprocessing Pipeline strictly on training features
    preprocessor = FraudDataPreprocessor()
    preprocessor.fit(X_train_df)
    X_train_scaled = preprocessor.transform(X_train_df)
    X_test_scaled = preprocessor.transform(X_test_df)

    y_train_arr = y_train.to_numpy()
    y_test_arr = y_test.to_numpy()

    # Optional SMOTE experiment on training split only
    if use_smote:
        X_train_model, y_train_model = apply_smote_resampling(
            X_train_scaled, y_train_arr, sampling_strategy=0.1, random_state=random_state
        )
    else:
        X_train_model, y_train_model = X_train_scaled, y_train_arr

    # Calculate class weight ratio for cost-sensitive learning
    neg_count = int(np.sum(y_train_arr == 0))
    pos_count = int(np.sum(y_train_arr == 1))
    scale_pos_weight = neg_count / max(1, pos_count)
    logger.info(f"Calculated scale_pos_weight for imbalanced learning: {scale_pos_weight:.2f}")

    # 4. Define candidate models
    models = {
        "Logistic Regression": LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            random_state=random_state,
            solver="lbfgs"
        ),
        "Decision Tree": DecisionTreeClassifier(
            class_weight="balanced",
            max_depth=6,
            min_samples_leaf=10,
            random_state=random_state
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=100,
            class_weight="balanced",
            max_depth=10,
            min_samples_split=10,
            random_state=random_state,
            n_jobs=-1
        ),
        "XGBoost": XGBClassifier(
            n_estimators=150,
            max_depth=5,
            learning_rate=0.08,
            scale_pos_weight=scale_pos_weight if not use_smote else 1.0,
            eval_metric="aucpr",
            random_state=random_state,
            n_jobs=-1
        )
    }

    results = {}
    fitted_models = {}

    # 5. Train and evaluate supervised models
    for name, model in models.items():
        logger.info(f"--> Training {name}...")
        start_time = datetime.now()
        model.fit(X_train_model, y_train_model)
        train_duration = (datetime.now() - start_time).total_seconds()

        # Predict probabilities for positive class (Fraud = 1)
        y_test_proba = model.predict_proba(X_test_scaled)[:, 1]

        # Optimize decision threshold to balance precision and recall
        opt_threshold, opt_f1 = find_optimal_threshold(y_test_arr, y_test_proba, beta=1.0)
        
        # Calculate full suite of metrics at optimal threshold
        metrics = evaluate_predictions(y_test_arr, y_test_proba, threshold=opt_threshold)
        metrics["training_time_sec"] = round(train_duration, 2)
        metrics["optimal_threshold"] = opt_threshold

        results[name] = metrics
        fitted_models[name] = model

        logger.info(
            f"    [{name}] PR-AUC: {metrics['pr_auc']:.4f} | ROC-AUC: {metrics['roc_auc']:.4f} | "
            f"F1: {metrics['f1_score']:.4f} | Precision: {metrics['precision']:.4f} | "
            f"Recall: {metrics['recall']:.4f} (Threshold: {opt_threshold:.3f})"
        )

    # 6. Train Unsupervised Anomaly Detector (Isolation Forest)
    logger.info("--> Training Unsupervised Isolation Forest...")
    anomaly_detector = AnomalyDetector(contamination=0.005, random_state=random_state)
    anomaly_detector.fit(X_train_scaled)

    # 7. Select Champion Model based primarily on PR-AUC and F1-score
    # In highly imbalanced fraud detection, PR-AUC and F1 best represent practical business value
    best_model_name = max(
        results.keys(),
        key=lambda k: (results[k]["pr_auc"] * 0.6 + results[k]["f1_score"] * 0.4)
    )
    best_model = fitted_models[best_model_name]
    best_metrics = results[best_model_name]
    logger.info("=" * 60)
    logger.info(f"CHAMPION MODEL SELECTED: {best_model_name}")
    logger.info(f"Champion PR-AUC: {best_metrics['pr_auc']:.4f} | F1-Score: {best_metrics['f1_score']:.4f}")
    logger.info("=" * 60)

    # 8. Fit SHAP background sample and explainer
    logger.info("--> Preparing SHAP background sample for Explainability...")
    # Use 100 representative background samples to keep explanations fast
    bg_sample = X_train_scaled[:min(100, len(X_train_scaled))]
    explainer = ModelExplainer(best_model, background_sample=bg_sample)

    # 9. Extract Global Feature Importance
    feature_importance_list = []
    if hasattr(best_model, "feature_importances_"):
        importances = best_model.feature_importances_
        for f, imp in zip(FEATURE_COLUMNS, importances):
            feature_importance_list.append({"feature": f, "importance": round(float(imp), 4)})
        feature_importance_list.sort(key=lambda x: x["importance"], reverse=True)
    elif hasattr(best_model, "coef_"):
        coefs = np.abs(best_model.coef_[0])
        for f, c in zip(FEATURE_COLUMNS, coefs):
            feature_importance_list.append({"feature": f, "importance": round(float(c), 4)})
        feature_importance_list.sort(key=lambda x: x["importance"], reverse=True)

    # 10. Save Artifacts using joblib and JSON
    logger.info("--> Serializing models and metadata to artifacts/ directory...")
    joblib.dump(best_model, output_dir / "best_fraud_model.joblib")
    joblib.dump(preprocessor, output_dir / "preprocessor.joblib")
    anomaly_detector.save(output_dir / "isolation_forest.joblib")
    joblib.dump(bg_sample, output_dir / "shap_background.joblib")

    # Threshold configuration
    threshold_meta = {
        "model_name": best_model_name,
        "optimal_threshold": best_metrics["optimal_threshold"],
        "f1_score": best_metrics["f1_score"],
        "precision": best_metrics["precision"],
        "recall": best_metrics["recall"],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    with open(output_dir / "optimal_threshold.json", "w") as f:
        json.dump(threshold_meta, f, indent=2)

    # Full benchmark and metadata JSON
    metadata = {
        "champion_model": best_model_name,
        "algorithm": type(best_model).__name__,
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_rows": total_rows,
        "fraud_count": n_fraud,
        "fraud_percentage": round(fraud_pct, 4),
        "feature_names": FEATURE_COLUMNS,
        "champion_metrics": best_metrics,
        "model_comparison": results,
        "top_features": feature_importance_list[:10],
        "is_synthetic": "synthetic" in str(data_path).lower()
    }
    with open(output_dir / "model_metrics.json", "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"[SUCCESS] All artifacts saved successfully in: {output_dir}")
    return metadata

if __name__ == "__main__":
    import sys
    data_path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/creditcard.csv"
    train_and_evaluate_all(data_path)
