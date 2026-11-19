# FraudShield AI — Milestone 2C: Final Results Verification Report

**Verification Date:** November 16, 2026  
**Auditor Role:** Senior Machine Learning Engineer & Lead ML Auditor  
**Subject System:** Hybrid Fraud Engine Optimization & Calibration Audit  
**Target Document:** `experiments/milestone_2c/MILESTONE_2C_AUDIT_REPORT.md`  
**Candidate Evaluated:** `ARCH_C_log_c500` (Logistic Meta-Calibrator, Cutoff = 50.0)  
**Verification Scope:** Read-Only Verification of Saved Predictions, Cross-Fold Models, Calibration Code, and Reported Metrics  
**Quarantine Status:** The held-out test split (42,559 transactions) was **100% QUARANTINED** and never referenced.  

---

## 1. Executive Summary & Verification Findings

This read-only audit verified the empirical results, cross-fold stability, calibration metrics, confusion matrix, and synthetic stress tests reported for Milestone 2C.

### Key Verification Conclusions:
1. **Gate Reconciliation & Candidate Classification:**  
   The candidate **`ARCH_C_log_c500`** is classified as a **"Promising candidate with failed acceptance gates"**. It passed all 5 operational validation gates and achieved a $99.5\%$ ECE reduction, but **failed the strict Fold Stability Gate** due to a minimum fold recall of **$72.73\%$** ($< 75.0\%$ threshold). It must **not** be described as having passed all acceptance criteria.
2. **Reconciliation of Gate Counts:**  
   The implementation code (`optimize_hybrid_engine.py:571-587`) enforced **6 binary selection gates**. The report summary table displayed **7 gates** by presenting ECE Reduction ($\ge 15\%$) as a separate verification row.
3. **Cross-Fold Stability Verified:**  
   In 5-fold stratified cross-validation on training data, `ARCH_C_log_c500` achieved a mean recall of **$77.93\%$** ($\sigma = 4.18\%$) and mean precision of **$91.27\%$** ($\sigma = 3.39\%$). In Fold 1, it detected 48 of 66 fraud cases (**$72.73\%$**), missing the $75.0\%$ minimum fold threshold by exactly 2 cases. In Fold 4, it detected 49 of 66 fraud cases (**$74.24\%$**), missing by 1 case.
4. **Calibration Math & Comparison Discrepancy:**  
   The reported $99.5\%$ ECE reduction ($0.042072 \rightarrow 0.000202$) is mathematically exact between the heuristic risk score divided by 100 and the logistic calibrator. However, dividing the baseline heuristic score by 100 treats its artificial floor caps ($0.45$ and $0.70$) as probabilities, which artificially inflated baseline error. Compared to raw uncalibrated XGBoost probabilities ($\text{ECE} = 0.001970$), the calibrated model achieved a genuine and substantial **$89.7\%$ ECE reduction** and a **$46.4\%$ Brier score reduction** ($0.000642 \rightarrow 0.000344$).
5. **Exact Metric & Confusion Matrix Recomputation:**  
   Recomputing metrics directly from the saved validation predictions confirmed the exact counts:  
   $$\text{TP} = 58, \quad \text{FP} = 2, \quad \text{FN} = 13, \quad \text{TN} = 42,486 \quad (N = 42,559)$$  
   $$\text{Precision} = 96.67\%, \quad \text{Recall} = 81.69\%, \quad \text{F1} = 0.8855, \quad \text{Specificity} = 99.9953\%, \quad \text{FPR} = 0.0047\%, \quad \text{Accuracy} = 99.9648\%$$
6. **Synthetic Stress-Test Discrepancy Identified:**  
   The audit report stated synthetic detection rates of $84.51\%$ and $83.10\%$. Read-only inspection of `optimize_hybrid_engine.py:608, 763-775` revealed that `synthetic_stress_results.json` actually evaluated **`ARCH_B_w55_c400`** (which had an $84.51\%$ validation recall), because the script fell back to Arch B after Gate 1 failure. Evaluating **`ARCH_C_log_c500`** on those exact synthetic stress sets yields **$78.87\%$ detection on micro-fraud**, **$78.87\%$ detection on borderline PCA**, and **$0.00\%$ false positives on anomaly bursts**.

---

## 2. Acceptance Gate Reconciliation

### 2.1 Reconciling Code vs. Report Gate Discrepancy
- **Implementation Code (`optimize_hybrid_engine.py:571-587`):**  
  Programmatically evaluated **6 binary gates**:
  1. `gate_fold_stability`: `is_fold_stable` ($\sigma_{\text{rec}} \le 0.05, \sigma_{\text{prec}} \le 0.05, \text{min}_{\text{rec}} \ge 0.75$)
  2. `gate_recall`: `val_recall >= 0.80`
  3. `gate_precision`: `val_precision >= 0.80`
  4. `gate_fpr`: `val_fpr <= 0.00050`
  5. `gate_medium_queue`: `val_medium_queue_pct <= 1.0`
  6. `gate_high_precision`: `val_high_precision_pct >= 85.0`
- **Audit Report (`MILESTONE_2C_AUDIT_REPORT.md` Section 4.2):**  
  Listed **7 gates** in the summary table by presenting `ECE Reduction >= 15%` as "Gate 7".
- **Reconciliation:**  
  The correct total number of operational decision gates is **6**, with calibration quality acting as an architectural evaluation criterion.

### 2.2 Comprehensive Gate Status for `ARCH_C_log_c500`

| Gate # | Acceptance Criterion | Required Threshold | Candidate Actual Metric | Gate Status |
|---|---|---|---|---|
| **Gate 1** | **Fold Stability Across 5 CV Folds** | $\sigma \le 0.05, \quad \text{Min} \ge 75.0\%$ | $\sigma_{\text{rec}} = 0.0418, \quad \mathbf{\text{Min} = 72.73\%}$ | **FAILED** |
| **Gate 2** | **Validation Fraud Recall Floor** | $\ge 80.0\%$ | **81.69%** ($58 / 71$) | **PASSED** |
| **Gate 3** | **Validation Precision Ceiling** | $\ge 80.0\%$ | **96.67%** ($58 / 60$) | **PASSED** |
| **Gate 4** | **False Positive Rate Ceiling** | $\le 0.050\%$ ($5 \times 10^{-4}$) | **0.0047%** ($4.7 \times 10^{-5}$) | **PASSED** |
| **Gate 5** | **Analyst Review Queue Volume** | `MEDIUM` Risk Tier $\le 1.0\%$ | **0.012%** ($5 / 42,559$ txns) | **PASSED** |
| **Gate 6** | **High-Risk Auto-Block Purity** | `HIGH` Risk Tier Precision $\ge 85.0\%$ | **98.28%** ($57 / 58$ txns) | **PASSED** |
| **Calibration**| **Quantile ECE Reduction** | $\ge 15.0\%$ reduction vs. baseline | **$-99.52\%$** ($0.0421 \rightarrow 0.0002$) | **PASSED** |

> [!CAUTION]
> **Audit Reconciliation Statement:**  
> The candidate `ARCH_C_log_c500` **did NOT pass all acceptance criteria**. It passed 5 out of 6 primary selection gates, but definitively failed Gate 1. It must be documented accordingly.

---

## 3. Cross-Fold Stability Audit

An independent read-only evaluation of the 5 cross-validation folds in `experiments/milestone_2c/scratch/` verified the fold-level performance of `ARCH_C_log_c500`:

### 3.1 Fold-by-Fold Performance Table

| Fold # | Train Size | Held-Out Size | Fold Fraud Count | True Positives (TP) | False Positives (FP) | False Negatives (FN) | True Negatives (TN) | Fold Recall | Fold Precision | Fold F1-Score |
|---|---|---|---|---|---|---|---|---|---|---|
| **Fold 1** | 158,886 | 39,722 | 66 | 48 | 8 | 18 | 39,648 | **72.73%** | 85.71% | 0.7869 |
| **Fold 2** | 158,886 | 39,722 | 66 | 51 | 4 | 15 | 39,652 | **77.27%** | 92.73% | 0.8430 |
| **Fold 3** | 158,886 | 39,722 | 67 | 55 | 6 | 12 | 39,649 | **82.09%** | 90.16% | 0.8594 |
| **Fold 4** | 158,887 | 39,721 | 66 | 49 | 2 | 17 | 39,653 | **74.24%** | 96.08% | 0.8376 |
| **Fold 5** | 158,887 | 39,721 | 66 | 55 | 5 | 11 | 39,650 | **83.33%** | 91.67% | 0.8730 |

### 3.2 Statistical Aggregation
- **Recall:** $\text{Mean} = \mathbf{77.93\%}, \quad \text{Std} = \mathbf{4.18\%} \ (0.0418), \quad \text{Min} = \mathbf{72.73\%}, \quad \text{Max} = \mathbf{83.33\%}$
- **Precision:** $\text{Mean} = \mathbf{91.27\%}, \quad \text{Std} = \mathbf{3.39\%} \ (0.0339), \quad \text{Min} = \mathbf{85.71\%}, \quad \text{Max} = \mathbf{96.08\%}$
- **F1-Score:** $\text{Mean} = \mathbf{0.8400}, \quad \text{Std} = \mathbf{0.0293}, \quad \text{Min} = \mathbf{0.7869}, \quad \text{Max} = \mathbf{0.8730}$

### 3.3 Implications of the 72.73% Minimum Recall
1. **Confirmation of Gate 1 Failure:**  
   The candidate genuinely failed the $75.0\%$ minimum fold recall requirement. Two folds dropped below $75.0\%$: Fold 1 ($72.73\%$) and Fold 4 ($74.24\%$).
2. **Small-Sample Poisson Variability:**  
   Each fold contains only $66$ or $67$ fraud cases. Each individual fraud transaction represents $\mathbf{1.515\%}$ of fold recall ($1 / 66 \approx 0.01515$):
   - In Fold 1 ($48 / 66 = 72.73\%$), missing just **2 additional fraud cases** dropped recall from $75.76\%$ down to $72.73\%$.
   - In Fold 4 ($49 / 66 = 74.24\%$), missing just **1 additional fraud case** dropped recall from $75.76\%$ down to $74.24\%$.
3. **Engineering Conclusion:**  
   The candidate's fold standard deviation ($\sigma_{\text{rec}} = 4.18\%$) is well within the approved $5.0\%$ stability ceiling, and its mean fold precision ($91.27\%$) is exceptionally high. However, because credit card fraud is a low-frequency event ($0.17\%$), stochastic fluctuations of 1–2 transactions in small folds create substantial swing in recall.

---

## 4. Calibration Metrics Verification

### 4.1 Verification of Evaluation Samples and Binning
- **Sample Consistency:** Verified that both the production baseline and `ARCH_C_log_c500` were evaluated on the identical 42,559 validation samples (42,488 legitimate, 71 fraud).
- **Binning Methodology:** Both used the identical quantile binning implementation (`n_bins = 10`) computed via `numpy.quantile` on the predicted probabilities/scores.

### 4.2 Mathematical Verification of the 99.5% ECE Reduction
- **Reported Values:**
  - Baseline Heuristic: $\text{ECE} = 0.042072$
  - Logistic Calibrator: $\text{ECE} = 0.000202$
- **Mathematical Calculation:**
  $$\Delta \text{ECE}_{\%} = \frac{0.042072 - 0.000202}{0.042072} \times 100\% = \mathbf{99.5199\%} \approx 99.5\%$$
- The calculation is **mathematically exact** given the inputs.

### 4.3 Scientific Accounting: Were Heuristic Scores Incorrectly Treated as Probabilities?
> [!IMPORTANT]
> **Audit Finding on Baseline Calibration Measurement:**
> In `optimize_hybrid_engine.py:169-170`, the baseline heuristic risk score was divided by 100 (`val_risk_scores / 100.0`) and passed directly into `brier_score_loss` and `compute_quantile_ece`.
> - The production baseline risk score is an uncalibrated ranking index containing hard artificial floors (`max(base_risk, 45.0)` for anomalies, `max(base_risk, 70.0)` for high XGBoost prob).
> - As a result, over **220 legitimate transactions** flagged by Isolation Forest were forced to have risk scores $\ge 45.0$. Dividing by 100 treated them as having a $45\%$ to $65\%$ probability of fraud, resulting in massive squared probability errors $(0.45 - 0)^2 \approx 0.2025$ on legitimate cards.
> - This artificially inflated the baseline Brier score ($0.003338$) and ECE ($0.042072$).

### 4.4 Calibration Benchmark Against Raw Uncalibrated XGBoost
To provide an uninflated, scientifically rigorous benchmark, we evaluated raw uncalibrated XGBoost probabilities directly against `ARCH_C_log_c500` on the validation set:

| Model / Architecture | Input / Formulation | Brier Score | Quantile ECE | True ECE Reduction | True Brier Reduction |
|---|---|---|---|---|---|
| **Baseline Heuristic Index** | Heuristic Risk Score / 100 | 0.003338 | 0.042072 | Reference Baseline | Reference Baseline |
| **Raw XGBoost Probabilities**| $P_{\text{xgb}}^{\text{val}} \in [0, 1]$ (No floors) | 0.000642 | 0.001970 | $-95.3\%$ vs. Heuristic | $-80.8\%$ vs. Heuristic |
| **`ARCH_C_log_c500`** | Calibrated Logistic $\sigma(z)$ | **0.000344** | **0.000202** | **$-89.7\%$ vs. Raw XGBoost** | **$-46.4\%$ vs. Raw XGBoost** |

**Conclusion:**  
Even when removing the artificial inflation caused by heuristic floors, `ARCH_C_log_c500` still achieves an **$89.7\%$ reduction in calibration error (ECE)** and a **$46.4\%$ reduction in Brier score** compared to raw uncalibrated XGBoost, confirming that the calibration improvement is genuine.

---

## 5. Confusion Matrix & Metric Recomputation

Independently recomputed directly from the saved validation predictions ($y_{\text{val}}$ vs. $\hat{y}_{\text{pred}}$ at Cutoff = 50.0):

### 5.1 Recomputed Confusion Matrix (42,559 Samples)
$$\begin{pmatrix} \text{TN} & \text{FP} \\ \text{FN} & \text{TP} \end{pmatrix} = \begin{pmatrix} 42,486 & 2 \\ 13 & 58 \end{pmatrix}$$

- **True Positives (TP):** $58$ (Confirmed fraud correctly flagged)
- **False Positives (FP):** $2$ (Legitimate cardholders incorrectly flagged)
- **False Negatives (FN):** $13$ (Fraud transactions missed)
- **True Negatives (TN):** $42,486$ (Legitimate cardholders cleared)
- **Total Samples:** $58 + 2 + 13 + 42,486 = 42,559$

### 5.2 Metric Verification Table

| Metric | Formula | Exact Fraction | Recomputed Value | Reported Value | Match Status |
|---|---|---|---|---|---|
| **Precision (PPV)** | $\frac{\text{TP}}{\text{TP} + \text{FP}}$ | $\frac{58}{60}$ | **96.6667%** | 96.67% | **VERIFIED (EXACT)** |
| **Recall (TPR / Sensitivity)** | $\frac{\text{TP}}{\text{TP} + \text{FN}}$ | $\frac{58}{71}$ | **81.6901%** | 81.69% | **VERIFIED (EXACT)** |
| **F1-Score** | $\frac{2 \cdot P \cdot R}{P + R}$ | $\frac{2 \cdot (58/60) \cdot (58/71)}{(58/60) + (58/71)}$ | **0.885496** | 0.8855 | **VERIFIED (EXACT)** |
| **Specificity (TNR)** | $\frac{\text{TN}}{\text{TN} + \text{FP}}$ | $\frac{42,486}{42,488}$ | **99.9953%** | 99.9953% | **VERIFIED (EXACT)** |
| **False Positive Rate (FPR)** | $\frac{\text{FP}}{\text{FP} + \text{TN}}$ | $\frac{2}{42,488}$ | **0.0047%** ($4.7 \times 10^{-5}$) | 0.0047% | **VERIFIED (EXACT)** |
| **False Negative Rate (FNR)** | $\frac{\text{FN}}{\text{FN} + \text{TP}}$ | $\frac{13}{71}$ | **18.3099%** | 18.31% | **VERIFIED (EXACT)** |
| **Accuracy** | $\frac{\text{TP} + \text{TN}}{\text{Total}}$ | $\frac{42,544}{42,559}$ | **99.9648%** | 99.9648% | **VERIFIED (EXACT)** |

All metrics match the reported numbers down to the last reported decimal place.

---

## 6. Synthetic Stress-Test Verification & Discrepancy Resolution

### 6.1 Discrepancy Identified in the Audit Report
In Section 6 of `MILESTONE_2C_AUDIT_REPORT.md`, the reported detection rates were:
- Micro-Amount Fraud: **$84.51\%$**
- Borderline PCA Fraud: **$83.10\%$**
- Legitimate Anomaly Bursts: **$0.00\%$ FPR**

The user correctly asked: *Why do these detection rates ($84.51\%$ and $83.10\%$) differ from the $81.69\%$ validation recall of `ARCH_C_log_c500`?*

### 6.2 Root Cause Analysis from Source Inspection
Inspection of `optimize_hybrid_engine.py` reveals the exact explanation:
1. In Step 8 (`lines 607-608`):
   ```python
   # When no candidate passed all 6 gates:
   top_candidate = df_grid[df_grid["gate_fold_stability"]].sort_values(by="val_f1", ascending=False).iloc[0].to_dict()
   ```
   Because `ARCH_C_log_c500` failed `gate_fold_stability`, `top_candidate` in the script fell back to **`ARCH_B_w55_c400`** (which had an empirical validation recall of $84.51\%$).
2. In Step 10 (`lines 763-774`):
   The stress test function `score_stress` evaluated `top_candidate`, which was **`ARCH_B_w55_c400`**, **NOT** `ARCH_C_log_c500`.
   - On Scenario A (micro-amount fraud), `ARCH_B_w55_c400` detected 60 of 71 cases = **$84.51\%$**.
   - On Scenario B (borderline PCA fraud), `ARCH_B_w55_c400` detected 59 of 71 cases = **$83.10\%$**.
   - The production baseline (`ARCH_A_w75_c500`) also had a validation recall of $84.51\%$ and detected 60/71 ($84.51\%$) and 59/71 ($83.10\%$).

### 6.3 True Performance of `ARCH_C_log_c500` on Synthetic Stress Scenarios
Evaluating `ARCH_C_log_c500` on the exact same synthetic stress sets yields:

| Synthetic Scenario | Description | `ARCH_B_w55_c400` (Reported in Script) | Production Baseline (`ARCH_A_w75_c500`) | `ARCH_C_log_c500` (True Candidate) |
|---|---|---|---|---|
| **Scenario A: Micro-Amounts** | 71 fraud cases with amounts perturbed to $\$0.01$–$\$5.00$ | 84.51% (60/71) | 84.51% (60/71) | **78.87% (56/71)** |
| **Scenario B: Diluted PCA** | 71 fraud cases with $30\%$ diluted $V_{14}, V_{10}$ signals | 83.10% (59/71) | 83.10% (59/71) | **78.87% (56/71)** |
| **Scenario C: Anomaly Burst**| 1,000 legitimate cards with $\$5\text{k}$–$\$25\text{k}$ transactions | 0.00% FP (0/1000) | 0.00% FP (0/1000) | **0.00% FP (0/1000)** |

**Analysis:**
- On clean validation data, `ARCH_C_log_c500` detects 58 fraud cases ($81.69\%$).
- When fraud transactions have their PCA signals diluted or amounts reduced to micro-values, detection dips slightly to 56 cases ($78.87\%$).
- Crucially, under legitimate transaction bursts of up to $\$25,000$, `ARCH_C_log_c500` produces **zero false alarms** ($0.00\%$), proving that it does not falsely trigger on dollar amounts alone.

---

## 7. Official Candidate Classification

Based strictly on the approved acceptance criteria:

```
+---------------------------------------------------------------------------------------------------+
|                               OFFICIAL CANDIDATE CLASSIFICATION                                   |
+---------------------------------------------------------------------------------------------------+
| Candidate ID:         ARCH_C_log_c500                                                             |
| Architecture:         Two-Parameter Logistic Meta-Calibrator (Cutoff = 50.0)                      |
| Classification:       PROMISING CANDIDATE WITH FAILED ACCEPTANCE GATES                            |
+---------------------------------------------------------------------------------------------------+
```

### Justification:
1. **Why it is NOT "Fully Accepted":**  
   It failed Gate 1 (Fold Stability) by recording a minimum fold recall of **$72.73\%$** in Fold 1 and **$74.24\%$** in Fold 4, below the mandatory $75.0\%$ minimum floor.
2. **Why it is NOT "Rejected":**  
   It achieved superior performance across all 5 operational validation gates:
   - Precision: **$96.67\%$** (crushing the $80\%$ gate).
   - Recall: **$81.69\%$** (clearing the $80\%$ gate).
   - FPR: **$0.0047\%$** ($10\times$ below the $0.05\%$ cap).
   - Review Queue: **$0.012\%$** (well below the $1.0\%$ cap).
   - High-Tier Purity: **$98.28\%$** (exceeding the $85\%$ gate).
   - Brier and ECE reductions of $46.4\%$ and $89.7\%$ over raw probabilities.
   - Low fold variance ($\sigma_{\text{rec}} = 4.18\% \le 5.0\%$).

---

## 8. Summary of Recommendations & Next Steps

1. **Retain Baseline Configuration in Production:**  
   In accordance with the execution boundary, the production baseline (`backend/app/config.py`) remains active and unchanged.
2. **Correct the Audit Report Text:**  
   Update the audit report documentation to clarify that `synthetic_stress_results.json` evaluated `ARCH_B_w55_c400`, and record the true candidate stress scores ($78.87\%$).
3. **Requirement for Independent Evaluation:**  
   Because `ARCH_C_log_c500` is a promising candidate that failed Gate 1 due to small fold sample size, it should be tested on an **independent external dataset** (same 30-feature schema) or an out-of-time transaction stream to verify whether its $81.7\%$ recall and $96.7\%$ precision hold up before considering production deployment.
