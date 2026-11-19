# FraudShield AI — Milestone 1: Scientific Evaluation Workspace

This directory contains the independent scientific evaluation and audit suite for the FraudShield AI champion fraud detection model.

---

## Directory Structure

```
experiments/
├── README.md                      # Reproduction instructions and documentation
├── evaluate_baseline.py           # Pipeline integrity check & held-out test evaluation
├── scenario_tests.py              # Operational scenario and schema validation suite
├── results/
│   ├── heldout_metrics.json       # Serialized held-out test evaluation metrics
│   └── scenario_results.json      # Structured scenario testing results
└── figures/
    ├── confusion_matrix.png       # Held-out test confusion matrix heatmap
    ├── precision_recall_curve.png # Precision-Recall curve with operating point
    ├── roc_curve.png              # Receiver Operating Characteristic curve
    ├── probability_distribution.png# Log-scale fraud vs legit probability density
    └── val_threshold_analysis.png # Validation-only threshold sensitivity curves
```

---

## Prerequisites & Environment

The evaluation scripts utilize the project's existing Python virtual environment (`venv`).

### Activate Environment
**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

---

## Execution Instructions

### 1. Execute Baseline Model Evaluation & Generate Figures
Runs full pipeline integrity checks, evaluates the XGBoost champion model on the genuine held-out test split (42,559 transactions) at threshold `0.900`, and generates all 5 diagnostic figures:

```powershell
python experiments/evaluate_baseline.py
```

**Outputs generated:**
- `experiments/results/heldout_metrics.json`
- `experiments/figures/confusion_matrix.png`
- `experiments/figures/precision_recall_curve.png`
- `experiments/figures/roc_curve.png`
- `experiments/figures/probability_distribution.png`
- `experiments/figures/val_threshold_analysis.png`

### 2. Execute Transaction Scenario Test Suite
Evaluates the model and inference engine across clearly legitimate, high-risk, borderline, outlier, batch, and invalid input scenarios:

```powershell
python experiments/scenario_tests.py
```

**Outputs generated:**
- `experiments/results/scenario_results.json`

---

## Integrity & Non-Contamination Guarantees

1. **Zero Data Leakage:** The 3-way split (70% train, 15% validation, 15% test) is strictly stratified with zero sample index overlap (`random_state=42`).
2. **Untouched Preprocessor:** Transformations (`RobustScaler`) are fitted strictly on `X_train`.
3. **Independent Threshold:** The operational decision threshold ($0.900$) was derived strictly from the validation split. The held-out test set was never used for threshold tuning or model selection.
4. **Anonymized Feature Transparency:** Features $V1$–$V28$ are anonymized PCA projections. Synthetic scenarios are strictly grounded in empirical dataset percentiles rather than fabricated physical assumptions.
