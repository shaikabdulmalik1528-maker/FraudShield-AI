"""
FraudShield AI - Exploratory Data Analysis (EDA) Pipeline
Performs the 10 required EDA steps on the raw dataset:
1. Dataset shape
2. Missing values
3. Duplicate records
4. Fraud vs legitimate distribution
5. Fraud percentage
6. Transaction amount distribution
7. Correlation heatmap
8. Class imbalance visualization
9. Feature distributions
10. Summary statistics
Saves visualizations in reports/figures/
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "raw" / "creditcard.csv"
OUTPUT_DIR = BASE_DIR / "reports" / "figures"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Visual styling
plt.style.use('dark_background')
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['axes.edgecolor'] = '#1E293B'
plt.rcParams['axes.linewidth'] = 0.8

def run_eda():
    print("[INFO] Starting Exploratory Data Analysis on:", DATA_PATH)
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)
    
    # 1. Dataset Shape
    rows, cols = df.shape
    print(f"Step 1: Dataset Shape: {rows:,} rows, {cols} columns")

    # 2. Missing Values
    missing_count = int(df.isnull().sum().sum())
    print(f"Step 2: Total Missing Values: {missing_count}")

    # 3. Duplicate Records
    duplicate_count = int(df.duplicated().sum())
    duplicate_pct = (duplicate_count / rows) * 100.0
    print(f"Step 3: Duplicate Records: {duplicate_count:,} ({duplicate_pct:.2f}%)")

    # 4 & 5. Distribution & Percentage
    class_counts = df["Class"].value_counts()
    n_legit = int(class_counts.get(0, 0))
    n_fraud = int(class_counts.get(1, 0))
    fraud_pct = (n_fraud / rows) * 100.0
    print(f"Step 4 & 5: Legitimate: {n_legit:,} | Fraud: {n_fraud:,} | Fraud Rate: {fraud_pct:.4f}%")

    # 6. Transaction Amount Distribution
    amount_stats_legit = df[df["Class"] == 0]["Amount"].describe().to_dict()
    amount_stats_fraud = df[df["Class"] == 1]["Amount"].describe().to_dict()
    print("Step 6: Amount Stats:")
    print(f"   Legitimate Mean: ${amount_stats_legit['mean']:.2f}, Max: ${amount_stats_legit['max']:.2f}")
    print(f"   Fraudulent Mean: ${amount_stats_fraud['mean']:.2f}, Max: ${amount_stats_fraud['max']:.2f}")

    # --- PLOT 1: Class Imbalance Visualization ---
    fig, ax = plt.subplots(figsize=(8, 5), facecolor='#0A1128')
    ax.set_facecolor('#0F1A3A')
    bars = ax.bar(
        ['Legitimate (0)', 'Fraudulent (1)'],
        [n_legit, n_fraud],
        color=['#10B981', '#F43F5E'],
        width=0.45
    )
    ax.set_yscale('log')
    ax.set_title('Transaction Class Imbalance (Log Scale)', fontsize=14, color='#F8FAFC', pad=15, weight='bold')
    ax.set_ylabel('Transaction Count (Log Scale)', fontsize=11, color='#94A3B8')
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:,}\n({height/rows*100:.2f}%)',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, color='#F8FAFC', weight='bold')
    plt.tight_layout()
    plot1_path = OUTPUT_DIR / "class_imbalance.png"
    plt.savefig(plot1_path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"Saved: {plot1_path}")

    # --- PLOT 2: Amount Distribution (Fraud vs Legit) ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), facecolor='#0A1128')
    ax1.set_facecolor('#0F1A3A')
    ax2.set_facecolor('#0F1A3A')
    
    sns.histplot(df[df["Class"] == 0]["Amount"], bins=50, ax=ax1, color='#10B981', kde=True)
    ax1.set_title('Legitimate Amounts ($0 - $1,000)', fontsize=12, color='#F8FAFC', weight='bold')
    ax1.set_xlim(0, 1000)
    ax1.set_xlabel('Amount ($)', color='#94A3B8')
    ax1.set_ylabel('Frequency', color='#94A3B8')

    sns.histplot(df[df["Class"] == 1]["Amount"], bins=50, ax=ax2, color='#F43F5E', kde=True)
    ax2.set_title('Fraudulent Amounts ($0 - $1,000)', fontsize=12, color='#F8FAFC', weight='bold')
    ax2.set_xlim(0, 1000)
    ax2.set_xlabel('Amount ($)', color='#94A3B8')
    ax2.set_ylabel('Frequency', color='#94A3B8')

    plt.tight_layout()
    plot2_path = OUTPUT_DIR / "amount_distribution.png"
    plt.savefig(plot2_path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"Saved: {plot2_path}")

    # --- PLOT 3: Correlation Heatmap with Target 'Class' ---
    corrs = df.corr()['Class'].drop('Class').sort_values()
    fig, ax = plt.subplots(figsize=(12, 6), facecolor='#0A1128')
    ax.set_facecolor('#0F1A3A')
    
    colors = ['#F43F5E' if v > 0 else '#06B6D4' for v in corrs.values]
    bars = ax.barh(corrs.index, corrs.values, color=colors)
    ax.set_title('Feature Correlation with Fraud Label (Class)', fontsize=14, color='#F8FAFC', weight='bold', pad=15)
    ax.set_xlabel('Pearson Correlation Coefficient', fontsize=11, color='#94A3B8')
    ax.grid(axis='x', linestyle='--', alpha=0.3)
    
    plt.tight_layout()
    plot3_path = OUTPUT_DIR / "correlation_heatmap.png"
    plt.savefig(plot3_path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"Saved: {plot3_path}")

    # --- PLOT 4: Key Feature Distributions for Fraud vs Legitimate ---
    # Most negatively correlated (V17, V14, V12) and positively correlated (V11, V4, V2)
    top_features = ['V17', 'V14', 'V12', 'V11', 'V4', 'V2']
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), facecolor='#0A1128')
    axes = axes.flatten()
    
    for i, feature in enumerate(top_features):
        ax = axes[i]
        ax.set_facecolor('#0F1A3A')
        sns.kdeplot(df[df['Class'] == 0][feature], ax=ax, color='#10B981', label='Legit', fill=True, alpha=0.25)
        sns.kdeplot(df[df['Class'] == 1][feature], ax=ax, color='#F43F5E', label='Fraud', fill=True, alpha=0.4)
        ax.set_title(f'Distribution of {feature}', fontsize=12, color='#F8FAFC', weight='bold')
        ax.set_xlabel(feature, color='#94A3B8')
        ax.set_ylabel('Density', color='#94A3B8')
        ax.legend(loc='upper right', facecolor='#0A1128', edgecolor='#1E293B')

    plt.tight_layout()
    plot4_path = OUTPUT_DIR / "feature_distributions.png"
    plt.savefig(plot4_path, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"Saved: {plot4_path}")

    # 10. Summary Statistics Export
    summary_report = {
        "dataset_rows": rows,
        "dataset_columns": cols,
        "missing_values": missing_count,
        "duplicate_records": duplicate_count,
        "duplicate_pct": round(duplicate_pct, 3),
        "legitimate_count": n_legit,
        "fraudulent_count": n_fraud,
        "fraud_percentage": round(fraud_pct, 4),
        "amount_statistics": {
            "legitimate": {k: round(v, 2) for k, v in amount_stats_legit.items()},
            "fraudulent": {k: round(v, 2) for k, v in amount_stats_fraud.items()}
        },
        "top_correlated_features": {
            "positive": {k: round(float(v), 4) for k, v in corrs.tail(5).to_dict().items()},
            "negative": {k: round(float(v), 4) for k, v in corrs.head(5).to_dict().items()}
        }
    }

    report_json_path = OUTPUT_DIR / "eda_summary.json"
    with open(report_json_path, "w") as f:
        json.dump(summary_report, f, indent=2)
    print(f"[SUCCESS] EDA completed! Summary exported to: {report_json_path}")

if __name__ == "__main__":
    run_eda()
