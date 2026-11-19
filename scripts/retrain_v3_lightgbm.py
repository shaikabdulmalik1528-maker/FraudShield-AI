"""
Reproducible Retraining Pipeline for FraudShield 3.0 LightGBM.
Enforces 24-hour temporal embargoes, monotonic constraints, and strict
performance gating criteria before staging or promoting model candidates.
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.v3.ml.data_loader import load_ieee_cis_dataset
from backend.app.v3.ml.preprocessor import temporal_train_val_test_split, IeeeCisPreprocessor
from backend.app.v3.ml.lightgbm_model import FraudShieldLightGBM
from backend.app.v3.ml.evaluation import compute_classification_metrics, find_optimal_threshold_v3
from backend.app.v3.ml.registry import model_registry, ModelVersionMetadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RetrainPipeline")


def run_retraining(
    sample_size: int = 590540,
    embargo_seconds: int = 86400,
    promote: bool = False,
    version_tag: str = "3.1.0-candidate"
) -> bool:
    logger.info("Starting reproducible retraining pipeline (version=%s, sample_size=%d)...", version_tag, sample_size)

    # 1. Load data
    df, y = load_ieee_cis_dataset(sample_size=sample_size)

    # 2. Chronological split with 24h embargos
    (X_train, y_train), (X_val, y_val), (X_test, y_test) = temporal_train_val_test_split(
        df, y, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, embargo_seconds=embargo_seconds
    )

    # 3. Fit preprocessor strictly on training data
    preprocessor = IeeeCisPreprocessor(max_cat_levels=25)
    X_train_trans = preprocessor.fit_transform(X_train, y_train)
    X_val_trans = preprocessor.transform(X_val)
    X_test_trans = preprocessor.transform(X_test)

    # 4. Train LightGBM with monotonic constraints
    model = FraudShieldLightGBM(
        n_estimators=300,
        learning_rate=0.030,
        num_leaves=63,
        scale_pos_weight=5.0,
        monotonic_constraints=True
    )
    model.fit(X_train_trans, y_train, eval_set=(X_val_trans, y_val), early_stopping_rounds=30)

    # 5. Evaluate on validation to locate optimal threshold
    val_probs = model.predict_proba(X_val_trans)[:, 1]
    opt_sweep = find_optimal_threshold_v3(y_val.values, val_probs, metric="f1", step=0.01)
    best_tau = opt_sweep["optimal_threshold"]

    # 6. Evaluate on held-out test split
    test_probs = model.predict_proba(X_test_trans)[:, 1]
    test_metrics = compute_classification_metrics(y_test.values, test_probs, threshold=best_tau)

    logger.info("Evaluation on Held-Out Test Set (tau=%.3f):", best_tau)
    logger.info("  ROC-AUC:   %.4f", test_metrics["roc_auc"])
    logger.info("  PR-AUC:    %.4f", test_metrics["pr_auc"])
    logger.info("  F1-Score:  %.4f", test_metrics["f1_score"])
    logger.info("  Recall:    %.2f%%", test_metrics["recall"] * 100)
    logger.info("  Precision: %.2f%%", test_metrics["precision"] * 100)

    # 7. Quality Gating Criteria
    gates_passed = (
        test_metrics["roc_auc"] >= 0.950 and
        test_metrics["pr_auc"] >= 0.780 and
        test_metrics["f1_score"] >= 0.720 and
        test_metrics["recall"] >= 0.650
    )

    if not gates_passed:
        logger.error("GATING CRITERIA FAILED! Candidate rejected. Active production model preserved.")
        return False

    logger.info("ALL PERFORMANCE GATES PASSED! Staging candidate artifact...")

    # 8. Save candidate artifacts
    out_dir = PROJECT_ROOT / "backend" / "artifacts" / "v3" / "candidates" / version_tag
    out_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = out_dir / "lightgbm_fraudshield_v3.joblib"
    prep_path = out_dir / "v3_preprocessor.joblib"
    thresh_path = out_dir / "v3_optimal_threshold.json"

    model.save(model_path)
    joblib.dump(preprocessor, prep_path)
    with open(thresh_path, "w", encoding="utf-8") as f:
        json.dump(opt_sweep, f, indent=2)

    with open(model_path, "rb") as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()

    meta = ModelVersionMetadata(
        version=version_tag,
        created_at=datetime.now(timezone.utc).isoformat(),
        is_active=promote,
        model_file=str(model_path.name),
        preprocessor_file=str(prep_path.name),
        threshold=best_tau,
        roc_auc=round(test_metrics["roc_auc"], 4),
        pr_auc=round(test_metrics["pr_auc"], 4),
        f1_score=round(test_metrics["f1_score"], 4),
        monotonic_constraints_enforced=True,
        sha256=sha256,
        description=f"Retrained LightGBM candidate {version_tag} with validated gating."
    )

    model_registry.register_version(meta, make_active=promote)
    logger.info("Retraining workflow successfully completed. Registered %s in ModelRegistry (active=%s)", version_tag, promote)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FraudShield 3.0 Retraining Workflow")
    parser.add_argument("--sample-size", type=int, default=50000, help="Sample size for training run")
    parser.add_argument("--promote", action="store_true", help="Promote candidate to active immediately")
    parser.add_argument("--version", type=str, default="3.1.0-candidate", help="Version tag")
    args = parser.parse_args()

    success = run_retraining(sample_size=args.sample_size, promote=args.promote, version_tag=args.version)
    sys.exit(0 if success else 1)
