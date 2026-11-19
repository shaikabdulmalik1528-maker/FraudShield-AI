"""
FraudShield AI - False Negative Analysis Script.

Analyzes the 18 missed fraud cases from the held-out test set:
1. Extracts case details, predicted probabilities, and feature profiles.
2. Compares statistical distributions between Missed Fraud (FN, n=18), Detected Fraud (TP, n=53), and Legitimate (TN, n=42,488).
3. Generates publication-grade diagnostic plots of false negative probabilities and distributions.
4. Performs threshold sensitivity analysis using VALIDATION DATA ONLY (thresholds: 0.90, 0.80, 0.70, 0.60, 0.50).
5. Exports CSV files and outputs audit tables.
"""

import sys
import json
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
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix
)

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from backend.app.ml.preprocessing import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    load_and_clean_data,
    prepare_stratified_split,
)

def run_false_negative_analysis(
    data_path: str = "data/raw/creditcard.csv",
    output_dir: Path = BASE_DIR / "experiments",
    primary_threshold: float = 0.900,
    random_state: int = 42
):
    print("=" * 75)
    print("FRAUDSHIELD AI: FALSE NEGATIVE (MISSED FRAUD) DEEP-DIVE AUDIT")
    print("=" * 75)

    results_dir = output_dir / "results"
    figures_dir = output_dir / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load and clean data, create stratified 70/15/15 split
    df = load_and_clean_data(str(BASE_DIR / data_path))
    X_train_df, X_val_df, X_test_df, y_train, y_val, y_test = prepare_stratified_split(
        df, test_size=0.15, val_size=0.15, random_state=random_state
    )

    # 2. Load preprocessor and model
    preprocessor = joblib.load(BASE_DIR / "backend" / "artifacts" / "preprocessor.joblib")
    model = joblib.load(BASE_DIR / "backend" / "artifacts" / "best_fraud_model.joblib")

    # -------------------------------------------------------------
    # 3. Test Set Evaluation & False Negative Extraction
    # -------------------------------------------------------------
    X_test_scaled = preprocessor.transform(X_test_df)
    y_test_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_test_arr = y_test.to_numpy()

    test_fraud_mask = (y_test_arr == 1)
    fn_mask = test_fraud_mask & (y_test_proba < primary_threshold)
    tp_mask = test_fraud_mask & (y_test_proba >= primary_threshold)
    tn_mask = (y_test_arr == 0) & (y_test_proba < primary_threshold)
    fp_mask = (y_test_arr == 0) & (y_test_proba >= primary_threshold)

    n_fn = int(fn_mask.sum())
    n_tp = int(tp_mask.sum())
    n_tn = int(tn_mask.sum())
    n_fp = int(fp_mask.sum())

    print(f"\n[Held-Out Test Set Verification]")
    print(f"  Total Test Cases:       {len(y_test_arr):,}")
    print(f"  Total Fraud in Test:    {test_fraud_mask.sum()} (TP: {n_tp}, FN: {n_fn})")
    print(f"  Total Legit in Test:    {(y_test_arr == 0).sum()} (TN: {n_tn}, FP: {n_fp})")

    assert n_fn == 18, f"Expected exactly 18 false negatives, found {n_fn}!"
    assert n_tp == 53, f"Expected exactly 53 true positives, found {n_tp}!"

    # Build false negative records table
    fn_test_indices = np.where(fn_mask)[0]
    fn_records = []

    for rank, idx in enumerate(fn_test_indices, 1):
        orig_row_idx = int(X_test_df.index[idx])
        prob = float(y_test_proba[idx])
        row_features = X_test_df.iloc[idx].to_dict()

        dist_to_thresh = round(primary_threshold - prob, 6)

        if prob >= 0.80:
            category = "Near-Threshold [>=0.80]"
        elif prob >= 0.50:
            category = "Moderate Risk [0.50 - 0.80)"
        elif prob >= 0.01:
            category = "Low Probability [0.01 - 0.50)"
        else:
            category = "Deep Zero-Signal [<0.01)"

        rec = {
            "fn_case_id": f"FN-{rank:02d}",
            "test_split_index": int(idx),
            "original_row_index": orig_row_idx,
            "actual_label": 1,
            "predicted_probability": round(prob, 6),
            "operating_threshold": primary_threshold,
            "distance_to_threshold": dist_to_thresh,
            "probability_bucket": category,
            "amount": round(row_features["Amount"], 2),
            "time_seconds": round(row_features["Time"], 1)
        }
        # Add all 28 PCA features
        for i in range(1, 29):
            rec[f"V{i}"] = round(row_features[f"V{i}"], 6)

        fn_records.append(rec)

    fn_df = pd.DataFrame(fn_records)
    fn_csv_path = results_dir / "false_negative_cases.csv"
    fn_df.to_csv(fn_csv_path, index=False)
    print(f"\n[SUCCESS] Serialized 18 False Negative Cases to: {fn_csv_path.name}")

    # -------------------------------------------------------------
    # 4. Statistical Distribution Comparison (FN vs TP vs Legit)
    # -------------------------------------------------------------
    tp_features_df = X_test_df.iloc[np.where(tp_mask)[0]]
    fn_features_df = X_test_df.iloc[np.where(fn_mask)[0]]
    tn_features_df = X_test_df.iloc[np.where(tn_mask)[0]]

    # Compare key model features
    key_features = ["Amount", "V14", "V4", "V10", "V12", "V17", "V11", "V8", "V16", "V2", "Time"]
    stats_rows = []

    for feat in key_features:
        stats_rows.append({
            "feature": feat,
            "legit_median": round(float(tn_features_df[feat].median()), 4),
            "legit_mean": round(float(tn_features_df[feat].mean()), 4),
            "tp_detected_median": round(float(tp_features_df[feat].median()), 4),
            "tp_detected_mean": round(float(tp_features_df[feat].mean()), 4),
            "fn_missed_median": round(float(fn_features_df[feat].median()), 4),
            "fn_missed_mean": round(float(fn_features_df[feat].mean()), 4),
        })

    stats_df = pd.DataFrame(stats_rows)
    print("\n[Statistical Feature Comparison Summary]")
    print(stats_df.to_string(index=False))

    # -------------------------------------------------------------
    # 5. Diagnostic Figures: False Negative Distribution
    # -------------------------------------------------------------
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

    # Subplot 1: Strip plot of individual probabilities relative to threshold
    sns.stripplot(
        x=fn_df["predicted_probability"],
        ax=axes[0],
        color="#DC2626",
        size=10,
        jitter=0.25,
        alpha=0.85
    )
    axes[0].axvline(x=primary_threshold, color="black", linestyle="--", lw=2, label=f"Threshold ({primary_threshold:.2f})")
    axes[0].set_xlim([-0.05, 1.05])
    axes[0].set_title("Missed Fraud Predicted Probabilities\n(Held-Out Test Set, n=18)", fontsize=12, pad=10)
    axes[0].set_xlabel("Predicted Fraud Probability", fontsize=11)
    axes[0].grid(True, linestyle=":", alpha=0.6)
    axes[0].legend(loc="upper left")

    # Annotate key points
    highest_fn = fn_df.loc[fn_df["predicted_probability"].idxmax()]
    axes[0].annotate(
        f"{highest_fn['fn_case_id']}: {highest_fn['predicted_probability']:.4f}",
        xy=(highest_fn["predicted_probability"], 0),
        xytext=(highest_fn["predicted_probability"] - 0.25, 0.25),
        arrowprops=dict(arrowstyle="->", color="#DC2626", lw=1.5),
        fontsize=9,
        fontweight="bold"
    )

    # Subplot 2: Probability Buckets Histogram
    bucket_counts = fn_df["probability_bucket"].value_counts()[
        ["Deep Zero-Signal [<0.01)", "Low Probability [0.01 - 0.50)", "Moderate Risk [0.50 - 0.80)", "Near-Threshold [>=0.80]"]
    ].fillna(0)

    bucket_labels = ["< 0.01\n(Deep Miss)", "0.01 - 0.50\n(Low Prob)", "0.50 - 0.80\n(Moderate)", "0.80 - 0.90\n(Near Thresh)"]
    palette = ["#991B1B", "#DC2626", "#F59E0B", "#10B981"]
    bars = axes[1].bar(bucket_labels, bucket_counts.values, color=palette, width=0.55, edgecolor="black", alpha=0.85)
    for bar in bars:
        h = bar.get_height()
        axes[1].text(bar.get_x() + bar.get_width() / 2, h + 0.2, f"{int(h)} ({int(h)/18*100:.1f}%)", ha="center", fontsize=10, fontweight="bold")
    axes[1].set_ylim([0, 11])
    axes[1].set_title("False Negatives by Probability Band", fontsize=12, pad=10)
    axes[1].set_ylabel("Count of Missed Cases", fontsize=11)
    axes[1].grid(True, linestyle=":", alpha=0.6, axis="y")

    # Subplot 3: Boxplot comparison of V14 (Model's top feature)
    comp_v14_data = pd.DataFrame({
        "Group": ["Legitimate (TN)"] * len(tn_features_df) + ["Detected Fraud (TP)"] * len(tp_features_df) + ["Missed Fraud (FN)"] * len(fn_features_df),
        "V14": list(tn_features_df["V14"]) + list(tp_features_df["V14"]) + list(fn_features_df["V14"])
    })
    sns.boxplot(
        x="Group", y="V14", data=comp_v14_data, ax=axes[2],
        palette=["#3B82F6", "#10B981", "#EF4444"],
        showfliers=False, width=0.45
    )
    axes[2].set_title("Distribution of V14 (Top Predictive Feature)\nLegit vs Detected vs Missed", fontsize=12, pad=10)
    axes[2].set_ylabel("V14 Value (PCA Component)", fontsize=11)
    axes[2].grid(True, linestyle=":", alpha=0.6)

    plt.tight_layout()
    dist_plot_path = figures_dir / "false_negative_probability_distribution.png"
    plt.savefig(dist_plot_path, dpi=300)
    plt.close()
    print(f"[SUCCESS] Saved diagnostic figure to: {dist_plot_path.name}")

    # -------------------------------------------------------------
    # 6. Validation-Only Threshold Sensitivity Analysis
    # -------------------------------------------------------------
    print("\n[Executing Validation-Only Threshold Evaluation]")
    X_val_scaled = preprocessor.transform(X_val_df)
    y_val_proba = model.predict_proba(X_val_scaled)[:, 1]
    y_val_arr = y_val.to_numpy()

    val_thresholds = [0.90, 0.80, 0.70, 0.60, 0.50]
    val_comparison_records = []

    for t in val_thresholds:
        preds = (y_val_proba >= t).astype(int)
        cm = confusion_matrix(y_val_arr, preds)
        tn_v, fp_v, fn_v, tp_v = cm.ravel()

        p = float(precision_score(y_val_arr, preds, zero_division=0))
        r = float(recall_score(y_val_arr, preds, zero_division=0))
        f1 = float(f1_score(y_val_arr, preds, zero_division=0))
        fpr = float(fp_v / (fp_v + tn_v)) if (fp_v + tn_v) > 0 else 0.0
        tpr = float(tp_v / (tp_v + fn_v)) if (tp_v + fn_v) > 0 else 0.0

        val_comparison_records.append({
            "threshold": t,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1_score": round(f1, 4),
            "false_positive_rate": round(fpr, 6),
            "true_positive_rate": round(tpr, 4),
            "true_positives": int(tp_v),
            "false_positives": int(fp_v),
            "false_negatives": int(fn_v),
            "true_negatives": int(tn_v),
            "total_fraud_val": int(tp_v + fn_v),
            "total_legit_val": int(tn_v + fp_v),
            "total_samples_val": len(y_val_arr)
        })

    val_comp_df = pd.DataFrame(val_comparison_records)
    val_csv_path = results_dir / "validation_threshold_comparison.csv"
    val_comp_df.to_csv(val_csv_path, index=False)
    print(f"[SUCCESS] Serialized Validation Threshold Comparison to: {val_csv_path.name}")
    print("\n[Validation Threshold Comparison Table]")
    print(val_comp_df[["threshold", "precision", "recall", "f1_score", "true_positives", "false_positives", "false_negatives"]].to_string(index=False))

    return {
        "fn_records": fn_records,
        "stats_summary": stats_rows,
        "val_threshold_comparison": val_comparison_records,
        "csv_paths": {
            "false_negative_cases": str(fn_csv_path.resolve()),
            "validation_threshold_comparison": str(val_csv_path.resolve())
        },
        "plot_path": str(dist_plot_path.resolve())
    }

if __name__ == "__main__":
    run_false_negative_analysis()
