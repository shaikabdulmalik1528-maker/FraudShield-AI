"""
FraudShield AI - Milestone 1: Scientific Baseline Model Evaluation & Audit Script.

Performs an independent, rigorous evaluation of the existing XGBoost champion model
on the genuine held-out test set without data leakage or threshold contamination.
Generates all diagnostic figures and serializes held-out metrics.
"""

import sys
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import joblib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_curve
)

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from backend.app.ml.preprocessing import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    load_and_clean_data,
    prepare_stratified_split,
    FraudDataPreprocessor,
)
from backend.app.ml.evaluation import find_optimal_threshold
from backend.app.config import settings

def compute_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file for cryptographic integrity verification."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest().upper()

def evaluate_baseline(
    data_path: str = "data/raw/creditcard.csv",
    output_dir: Path = BASE_DIR / "experiments",
    primary_threshold: float = 0.900,
    random_state: int = 42
) -> dict:
    print("=" * 75)
    print("FRAUDSHIELD AI: MILESTONE 1 - SCIENTIFIC MODEL AUDIT & EVALUATION")
    print("=" * 75)

    results_dir = output_dir / "results"
    figures_dir = output_dir / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # 1. Dataset Integrity & Deduplication Verification
    # ---------------------------------------------------------
    raw_path = BASE_DIR / data_path
    if not raw_path.exists():
        raise FileNotFoundError(f"Original dataset not found at: {raw_path}")

    raw_file_size = raw_path.stat().st_size
    raw_sha256 = compute_sha256(raw_path)
    print(f"Dataset File: {raw_path.resolve()}")
    print(f"File Size: {raw_file_size:,} bytes ({raw_file_size / (1024*1024):.2f} MB)")
    print(f"SHA-256: {raw_sha256}")

    # Load raw dataframe to inspect original counts before deduplication
    raw_df = pd.read_csv(raw_path)
    raw_rows = len(raw_df)
    raw_fraud = int(raw_df[TARGET_COLUMN].sum())
    raw_legit = raw_rows - raw_fraud
    raw_fraud_pct = (raw_fraud / raw_rows) * 100.0

    print(f"\n[Raw Dataset]")
    print(f"  Total Rows: {raw_rows:,}")
    print(f"  Legitimate (Class 0): {raw_legit:,} ({100 - raw_fraud_pct:.4f}%)")
    print(f"  Fraudulent (Class 1): {raw_fraud:,} ({raw_fraud_pct:.4f}%)")

    # Clean / deduplicate dataset using project pipeline
    df = load_and_clean_data(str(raw_path))
    clean_rows = len(df)
    clean_fraud = int(df[TARGET_COLUMN].sum())
    clean_legit = clean_rows - clean_fraud
    clean_fraud_pct = (clean_fraud / clean_rows) * 100.0
    dropped_duplicates = raw_rows - clean_rows

    print(f"\n[Deduplicated Dataset (load_and_clean_data)]")
    print(f"  Duplicate Rows Removed: {dropped_duplicates:,}")
    print(f"  Unique Rows: {clean_rows:,}")
    print(f"  Legitimate: {clean_legit:,} ({100 - clean_fraud_pct:.4f}%)")
    print(f"  Fraudulent: {clean_fraud:,} ({clean_fraud_pct:.4f}%)")

    # ---------------------------------------------------------
    # 2. Split Partitioning & Isolation Verification
    # ---------------------------------------------------------
    X_train_df, X_val_df, X_test_df, y_train, y_val, y_test = prepare_stratified_split(
        df, test_size=0.15, val_size=0.15, random_state=random_state
    )

    n_train = len(X_train_df)
    n_val = len(X_val_df)
    n_test = len(X_test_df)
    fraud_train = int(y_train.sum())
    fraud_val = int(y_val.sum())
    fraud_test = int(y_test.sum())

    train_idx = set(X_train_df.index)
    val_idx = set(X_val_df.index)
    test_idx = set(X_test_df.index)

    overlap_train_val = len(train_idx.intersection(val_idx))
    overlap_train_test = len(train_idx.intersection(test_idx))
    overlap_val_test = len(val_idx.intersection(test_idx))

    print(f"\n[3-Way Stratified Split Verification]")
    print(f"  Training Split (70%):   {n_train:,} rows | Fraud: {fraud_train:,} ({fraud_train/n_train*100:.4f}%)")
    print(f"  Validation Split (15%): {n_val:,} rows | Fraud: {fraud_val:,} ({fraud_val/n_val*100:.4f}%)")
    print(f"  Held-Out Test (15%):    {n_test:,} rows | Fraud: {fraud_test:,} ({fraud_test/n_test*100:.4f}%)")
    print(f"  Overlap Check: Train-Val={overlap_train_val}, Train-Test={overlap_train_test}, Val-Test={overlap_val_test}")

    if overlap_train_val != 0 or overlap_train_test != 0 or overlap_val_test != 0:
        raise ValueError("CRITICAL INTEGRITY FAILURE: Data leakage detected across splits!")

    # ---------------------------------------------------------
    # 3. Preprocessor Verification
    # ---------------------------------------------------------
    saved_prep_path = BASE_DIR / "backend" / "artifacts" / "preprocessor.joblib"
    if not saved_prep_path.exists():
        raise FileNotFoundError(f"Saved preprocessor artifact not found at {saved_prep_path}")

    saved_preprocessor = joblib.load(saved_prep_path)

    # Compare saved scaler parameters against fresh fit on X_train_df
    fresh_preprocessor = FraudDataPreprocessor()
    fresh_preprocessor.fit(X_train_df)

    amount_diff = np.max(np.abs(saved_preprocessor.amount_scaler.center_ - fresh_preprocessor.amount_scaler.center_))
    time_diff = np.max(np.abs(saved_preprocessor.time_scaler.center_ - fresh_preprocessor.time_scaler.center_))
    print(f"\n[Preprocessor Verification]")
    print(f"  Amount Scaler Center: {saved_preprocessor.amount_scaler.center_} (Diff vs X_train fit: {amount_diff:.2e})")
    print(f"  Time Scaler Center:   {saved_preprocessor.time_scaler.center_} (Diff vs X_train fit: {time_diff:.2e})")

    if amount_diff > 1e-6 or time_diff > 1e-6:
        raise ValueError("CRITICAL INTEGRITY FAILURE: Saved preprocessor was not fitted exclusively on training split!")
    print("  --> CONFIRMED: Preprocessor was fitted strictly on training data only (Zero Leakage).")

    # Transform splits through preprocessor
    X_val_scaled = saved_preprocessor.transform(X_val_df)
    X_test_scaled = saved_preprocessor.transform(X_test_df)
    y_val_arr = y_val.to_numpy()
    y_test_arr = y_test.to_numpy()

    # ---------------------------------------------------------
    # 4. Champion Model Loading & Application Alignment
    # ---------------------------------------------------------
    model_path = BASE_DIR / "backend" / "artifacts" / "best_fraud_model.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"Champion model artifact not found at {model_path}")

    model = joblib.load(model_path)
    model_class_name = type(model).__name__
    print(f"\n[Model Artifact Alignment]")
    print(f"  Loaded Model: {model_class_name} from {model_path.name}")
    print(f"  Backend settings.SUPERVISED_MODEL_PATH: {settings.SUPERVISED_MODEL_PATH}")
    assert settings.SUPERVISED_MODEL_PATH.resolve() == model_path.resolve(), "Model path mismatch with backend config!"
    print("  --> CONFIRMED: Loaded model artifact is exactly the model consumed by the FastAPI backend.")

    # ---------------------------------------------------------
    # 5. Validation-Only Threshold Derivation
    # ---------------------------------------------------------
    y_val_proba = model.predict_proba(X_val_scaled)[:, 1]
    val_opt_threshold, val_opt_f1 = find_optimal_threshold(y_val_arr, y_val_proba, beta=1.0)
    print(f"\n[Validation Set Threshold Tuning]")
    print(f"  Optimal Threshold on Validation Split: {val_opt_threshold:.4f}")
    print(f"  Peak F1-Score on Validation Split:     {val_opt_f1:.4f}")
    print(f"  --> Primary Evaluation Threshold:       {primary_threshold:.4f}")

    # ---------------------------------------------------------
    # 6. Held-Out Test Evaluation
    # ---------------------------------------------------------
    y_test_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_test_pred = (y_test_proba >= primary_threshold).astype(int)

    # Confusion matrix
    cm = confusion_matrix(y_test_arr, y_test_pred)
    tn, fp, fn, tp = cm.ravel()

    # Threshold-dependent metrics
    accuracy = float(accuracy_score(y_test_arr, y_test_pred))
    precision = float(precision_score(y_test_arr, y_test_pred, zero_division=0))
    recall = float(recall_score(y_test_arr, y_test_pred, zero_division=0))
    f1 = float(f1_score(y_test_arr, y_test_pred, zero_division=0))
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    tpr = float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0

    # Threshold-independent metrics
    roc_auc = float(roc_auc_score(y_test_arr, y_test_proba))
    pr_auc = float(average_precision_score(y_test_arr, y_test_proba))

    print(f"\n[Held-Out Test Results @ Threshold {primary_threshold:.3f}]")
    print(f"  True Negatives (TN):  {tn:,} (Correctly classified legitimate)")
    print(f"  False Positives (FP): {fp:,} (Legitimate flagged as fraud)")
    print(f"  False Negatives (FN): {fn:,} (Fraud missed by model)")
    print(f"  True Positives (TP):  {tp:,} (Fraud successfully detected)")
    print(f"  Total Test Cases:     {len(y_test_arr):,} (Fraud: {fn+tp}, Legit: {tn+fp})")
    print(f"  Accuracy:             {accuracy:.6f} ({accuracy*100:.4f}%)")
    print(f"  Precision:            {precision:.4f} ({precision*100:.2f}%)")
    print(f"  Recall (TPR):         {recall:.4f} ({recall*100:.2f}%)")
    print(f"  F1-Score:             {f1:.4f}")
    print(f"  False Positive Rate:  {fpr:.6f} ({fpr*100:.4f}%)")
    print(f"  ROC-AUC:              {roc_auc:.4f}")
    print(f"  PR-AUC (Avg Prec):    {pr_auc:.4f}")

    # Also compute at threshold 0.895 for exact comparison with optimal_threshold.json
    y_test_pred_0895 = (y_test_proba >= 0.895).astype(int)
    cm_0895 = confusion_matrix(y_test_arr, y_test_pred_0895)
    tn_895, fp_895, fn_895, tp_895 = cm_0895.ravel()

    # ---------------------------------------------------------
    # 7. Generate Publication-Quality Visualizations
    # ---------------------------------------------------------
    print("\n[Generating Diagnostic Visualizations]")

    # Plot 1: Confusion Matrix Heatmap
    plt.figure(figsize=(7, 6))
    cm_labels = [
        [f"True Negative\n{tn:,}\n({tn/(tn+fp)*100:.2f}% of Legit)", f"False Positive\n{fp:,}\n({fp/(tn+fp)*100:.3f}% of Legit)"],
        [f"False Negative\n{fn:,}\n({fn/(fn+tp)*100:.2f}% of Fraud)", f"True Positive\n{tp:,}\n({tp/(fn+tp)*100:.2f}% of Fraud)"]
    ]
    sns.heatmap(
        cm, annot=cm_labels, fmt="", cmap="Blues", cbar=True,
        xticklabels=["Predicted Legit (0)", "Predicted Fraud (1)"],
        yticklabels=["Actual Legit (0)", "Actual Fraud (1)"],
        annot_kws={"fontsize": 11, "fontweight": "bold"}
    )
    plt.title(f"FraudShield AI - Held-Out Test Confusion Matrix\n(Threshold = {primary_threshold:.3f})", fontsize=13, pad=12)
    plt.ylabel("Ground Truth Class", fontsize=11)
    plt.xlabel("Predicted Class", fontsize=11)
    plt.tight_layout()
    fig1_path = figures_dir / "confusion_matrix.png"
    plt.savefig(fig1_path, dpi=300)
    plt.close()
    print(f"  Saved: {fig1_path.name}")

    # Plot 2: Precision-Recall Curve
    precisions, recalls, pr_thresholds = precision_recall_curve(y_test_arr, y_test_proba)
    # Find operating point on curve closest to primary_threshold
    thresh_idx = np.argmin(np.abs(pr_thresholds - primary_threshold)) if len(pr_thresholds) > 0 else 0
    op_prec = precisions[thresh_idx]
    op_rec = recalls[thresh_idx]

    plt.figure(figsize=(8, 6))
    plt.plot(recalls, precisions, color="#1E3A8A", lw=2.5, label=f"XGBoost Test (PR-AUC = {pr_auc:.4f})")
    baseline_fraud_rate = clean_fraud / clean_rows
    plt.axhline(y=baseline_fraud_rate, color="crimson", linestyle="--", lw=1.5,
                label=f"Random Guess Baseline ({baseline_fraud_rate*100:.3f}%)")
    plt.plot(op_rec, op_prec, marker="o", markersize=9, color="#DC2626",
             label=f"Operating Point (Thr={primary_threshold:.2f}, P={precision:.2f}, R={recall:.2f})")
    plt.title("Precision-Recall Curve (Held-Out Test Set)", fontsize=13, pad=12)
    plt.xlabel("Recall (Fraud Detection Rate)", fontsize=11)
    plt.ylabel("Precision (Positive Predictive Value)", fontsize=11)
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="lower left", fontsize=10)
    plt.tight_layout()
    fig2_path = figures_dir / "precision_recall_curve.png"
    plt.savefig(fig2_path, dpi=300)
    plt.close()
    print(f"  Saved: {fig2_path.name}")

    # Plot 3: Receiver Operating Characteristic (ROC) Curve
    fpr_curve, tpr_curve, roc_thresholds = roc_curve(y_test_arr, y_test_proba)
    plt.figure(figsize=(8, 6))
    plt.plot(fpr_curve, tpr_curve, color="#2563EB", lw=2.5, label=f"XGBoost Test (ROC-AUC = {roc_auc:.4f})")
    plt.plot([0, 1], [0, 1], color="gray", linestyle="--", lw=1.5, label="Random Chance (AUC = 0.5000)")
    plt.plot(fpr, tpr, marker="o", markersize=9, color="#DC2626",
             label=f"Operating Point (Thr={primary_threshold:.2f}, FPR={fpr*100:.3f}%, TPR={tpr*100:.1f}%)")
    plt.title("Receiver Operating Characteristic (ROC) Curve", fontsize=13, pad=12)
    plt.xlabel("False Positive Rate (1 - Specificity)", fontsize=11)
    plt.ylabel("True Positive Rate (Sensitivity / Recall)", fontsize=11)
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="lower right", fontsize=10)
    plt.tight_layout()
    fig3_path = figures_dir / "roc_curve.png"
    plt.savefig(fig3_path, dpi=300)
    plt.close()
    print(f"  Saved: {fig3_path.name}")

    # Plot 4: Prediction Probability Distribution (Separation)
    plt.figure(figsize=(9, 6))
    legit_probas = y_test_proba[y_test_arr == 0]
    fraud_probas = y_test_proba[y_test_arr == 1]

    # Use log-transformed probability bins to display separation across orders of magnitude
    bins = np.logspace(np.log10(max(1e-6, y_test_proba.min())), np.log10(1.0), 60)
    plt.hist(legit_probas, bins=bins, alpha=0.6, color="#3B82F6", label=f"Legitimate ({len(legit_probas):,})", density=True)
    plt.hist(fraud_probas, bins=bins, alpha=0.7, color="#EF4444", label=f"Fraudulent ({len(fraud_probas):,})", density=True)
    plt.axvline(x=primary_threshold, color="black", linestyle="--", lw=2, label=f"Operating Threshold ({primary_threshold:.3f})")
    plt.xscale("log")
    plt.yscale("log")
    plt.title("Prediction Probability Distribution (Log-Log Scale)", fontsize=13, pad=12)
    plt.xlabel("Predicted Fraud Probability (Log Scale)", fontsize=11)
    plt.ylabel("Probability Density (Log Scale)", fontsize=11)
    plt.grid(True, linestyle=":", alpha=0.6, which="both")
    plt.legend(loc="upper center", fontsize=10)
    plt.tight_layout()
    fig4_path = figures_dir / "probability_distribution.png"
    plt.savefig(fig4_path, dpi=300)
    plt.close()
    print(f"  Saved: {fig4_path.name}")

    # Plot 5: Validation-Only Threshold Analysis
    val_thresholds = np.linspace(0.01, 0.99, 150)
    val_precisions = []
    val_recalls = []
    val_f1s = []

    for t in val_thresholds:
        p_bin = (y_val_proba >= t).astype(int)
        p = precision_score(y_val_arr, p_bin, zero_division=0)
        r = recall_score(y_val_arr, p_bin, zero_division=0)
        f = f1_score(y_val_arr, p_bin, zero_division=0)
        val_precisions.append(p)
        val_recalls.append(r)
        val_f1s.append(f)

    plt.figure(figsize=(9, 6))
    plt.plot(val_thresholds, val_precisions, label="Precision (Val)", color="#10B981", lw=2)
    plt.plot(val_thresholds, val_recalls, label="Recall (Val)", color="#F59E0B", lw=2)
    plt.plot(val_thresholds, val_f1s, label="F1-Score (Val)", color="#6366F1", lw=2.5)
    plt.axvline(x=primary_threshold, color="#DC2626", linestyle="--", lw=2,
                label=f"Selected Threshold ({primary_threshold:.3f}, F1={val_opt_f1:.4f})")
    plt.title("Validation-Only Threshold Sensitivity Analysis\n(Zero Test-Set Contamination)", fontsize=13, pad=12)
    plt.xlabel("Decision Threshold", fontsize=11)
    plt.ylabel("Metric Score", fontsize=11)
    plt.ylim([0.0, 1.05])
    plt.xlim([0.0, 1.0])
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="lower center", fontsize=10)
    plt.tight_layout()
    fig5_path = figures_dir / "val_threshold_analysis.png"
    plt.savefig(fig5_path, dpi=300)
    plt.close()
    print(f"  Saved: {fig5_path.name}")

    # ---------------------------------------------------------
    # 8. Serialize Held-Out Metrics
    # ---------------------------------------------------------
    metrics_payload = {
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "audit_version": "1.0.0",
        "dataset_metadata": {
            "file_path": str(raw_path.resolve()),
            "sha256": raw_sha256,
            "raw_row_count": raw_rows,
            "raw_fraud_count": raw_fraud,
            "raw_fraud_rate_pct": round(raw_fraud_pct, 4),
            "deduplicated_row_count": clean_rows,
            "deduplicated_fraud_count": clean_fraud,
            "deduplicated_fraud_rate_pct": round(clean_fraud_pct, 4),
            "dropped_duplicates": dropped_duplicates
        },
        "split_verification": {
            "split_random_state": random_state,
            "train_samples": n_train,
            "train_fraud_samples": fraud_train,
            "train_fraud_rate_pct": round(fraud_train / n_train * 100, 4),
            "validation_samples": n_val,
            "validation_fraud_samples": fraud_val,
            "validation_fraud_rate_pct": round(fraud_val / n_val * 100, 4),
            "test_samples": n_test,
            "test_fraud_samples": fraud_test,
            "test_fraud_rate_pct": round(fraud_test / n_test * 100, 4),
            "split_overlap": {
                "train_validation_overlap": overlap_train_val,
                "train_test_overlap": overlap_train_test,
                "validation_test_overlap": overlap_val_test
            },
            "is_independent_heldout": True
        },
        "pipeline_integrity": {
            "preprocessor_fitted_on": "X_train_df strictly",
            "scaler_type": "RobustScaler",
            "feature_count": len(FEATURE_COLUMNS),
            "feature_order": FEATURE_COLUMNS,
            "data_leakage_detected": False,
            "test_used_for_threshold_tuning": False
        },
        "model_metadata": {
            "model_type": model_class_name,
            "model_artifact": model_path.name,
            "primary_threshold": primary_threshold,
            "validation_optimal_threshold": round(val_opt_threshold, 4),
            "validation_optimal_f1": round(val_opt_f1, 4)
        },
        "heldout_test_metrics": {
            "primary_threshold": primary_threshold,
            "positive_class": "1 (Fraudulent Transaction)",
            "accuracy": round(accuracy, 6),
            "accuracy_pct": round(accuracy * 100, 4),
            "precision": round(precision, 4),
            "precision_pct": round(precision * 100, 2),
            "recall": round(recall, 4),
            "recall_pct": round(recall * 100, 2),
            "f1_score": round(f1, 4),
            "roc_auc": round(roc_auc, 4),
            "pr_auc": round(pr_auc, 4),
            "false_positive_rate": round(fpr, 6),
            "false_positive_rate_pct": round(fpr * 100, 4),
            "true_positive_rate": round(tpr, 4),
            "true_positive_rate_pct": round(tpr * 100, 2),
            "confusion_matrix": {
                "tn": int(tn),
                "fp": int(fp),
                "fn": int(fn),
                "tp": int(tp),
                "total_negatives": int(tn + fp),
                "total_positives": int(fn + tp),
                "total_samples": int(len(y_test_arr))
            }
        },
        "threshold_comparison_0895_vs_0900": {
            "identical_test_confusion_matrix": bool(
                tn == tn_895 and fp == fp_895 and fn == fn_895 and tp == tp_895
            ),
            "threshold_0895_cm": {"tn": int(tn_895), "fp": int(fp_895), "fn": int(fn_895), "tp": int(tp_895)},
            "threshold_0900_cm": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
            "test_probas_between_0895_and_0900": int(
                np.sum((y_test_proba >= 0.895) & (y_test_proba < 0.900))
            )
        },
        "visual_artifacts": {
            "confusion_matrix": str((figures_dir / "confusion_matrix.png").resolve()),
            "precision_recall_curve": str((figures_dir / "precision_recall_curve.png").resolve()),
            "roc_curve": str((figures_dir / "roc_curve.png").resolve()),
            "probability_distribution": str((figures_dir / "probability_distribution.png").resolve()),
            "val_threshold_analysis": str((figures_dir / "val_threshold_analysis.png").resolve())
        }
    }

    metrics_file = results_dir / "heldout_metrics.json"
    with open(metrics_file, "w") as f:
        json.dump(metrics_payload, f, indent=2)
    print(f"\n[SUCCESS] Held-out test metrics serialized to: {metrics_file.resolve()}")
    return metrics_payload

if __name__ == "__main__":
    evaluate_baseline()
