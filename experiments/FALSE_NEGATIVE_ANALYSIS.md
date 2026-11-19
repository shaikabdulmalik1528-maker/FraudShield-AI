# FraudShield AI — False Negative Analysis Report

**Date:** November 16, 2026  
**Auditor Role:** Senior Machine Learning Engineer & Lead ML Auditor  
**Scope:** Held-Out Test False Negatives ($n=18$), Feature Divergence vs. True Positives ($n=53$), and Validation-Only Threshold Dynamics  
**Operating Threshold:** $\tau = 0.900$  

---

## 1. Executive Summary

During the held-out test evaluation of the champion XGBoost classifier ($\tau = 0.900$), the system successfully identified **53 out of 71 fraudulent transactions** ($\text{Recall} = 74.65\%$, $\text{Precision} = 92.98\%$, $\text{F1} = 0.8281$), while missing **18 fraudulent transactions** ($\text{False Negative Rate} = 25.35\%$).

### Key Findings:
1. **Bimodal Probability Distribution:** The 18 missed fraud cases do not cluster just beneath the $0.900$ decision threshold. Instead:
   - **50.0% (9 cases)** are **deep false negatives** with predicted probabilities $< 0.01$ (effectively zero detection signal).
   - **22.2% (4 cases)** fall in the moderate risk band $[0.50, 0.80)$.
   - **22.2% (4 cases)** fall in the low probability band $[0.01, 0.50)$.
   - **Only 5.6% (1 case)** is a near-threshold boundary miss ($p = 0.8848$).
2. **Subtle Feature Profiles:**
   - On $V_{14}$—the model's most critical feature ($43.15\%$ global importance)—the detected fraud cases exhibit a strong negative median shift of **$-7.08$**, whereas the missed fraud cases exhibit a median of **$-1.02$**, closely resembling legitimate traffic ($+0.06$).
   - On $V_4$, $V_{10}$, and $V_{12}$, missed cases consistently show much smaller deviations from legitimate norms than detected fraud.
   - **Micro-Transactions:** Over $40\%$ of missed fraud cases were transactions under $\$1.00$ (median amount $\$3.01$ vs $\$30.39$ for detected fraud and $\$21.29$ for legitimate transactions).
3. **Validation Threshold Impact (Validation Data Only):**
   - Lowering the decision threshold from $0.90$ to $0.80$ or $0.70$ on validation data catches **zero additional fraud cases**, while increasing false alarms from 6 to 10 ($+66\%$) and 12 ($+100\%$).
   - Lowering the threshold to $0.50$ catches only **1 additional fraud case** (out of 71) on validation data while nearly tripling false alarms (from 6 to 16, $+166\%$).
4. **Audit Recommendation:**
   - **Do NOT lower the global decision threshold.** Lowering the threshold causes an immediate explosion in false positives while failing to recover the vast majority of missed fraud cases (which lie deep below $0.50$).
   - **Recommended Strategy:** Rely on secondary defense layers: multi-factor risk scoring, unsupervised anomaly detection (Isolation Forest), and cardholder micro-transaction velocity rules.

---

## 2. Complete Inventory of the 18 Missed Fraud Cases

All 18 false negative records from the held-out test split are cataloged below and serialized in [false_negative_cases.csv](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/experiments/results/false_negative_cases.csv).

| Case ID | Test Index | Dataset Index | Actual Label | Predicted Prob | Operating Threshold | Distance to Threshold | Probability Bucket | Amount ($) | Time (s) |
|---|---|---|---|---|---|---|---|---|---|
| `FN-01` | 1975 | 68067 | 1 | 0.009549 | 0.900 | 0.890451 | Deep Zero-Signal ($<0.01$) | 519.90 | 52,814.0 |
| `FN-02` | 3642 | 10484 | 1 | 0.642744 | 0.900 | 0.257256 | Moderate Risk ($[0.50, 0.80)$) | 3.79 | 17,187.0 |
| `FN-03` | 7620 | 68633 | 1 | 0.000077 | 0.900 | 0.899923 | Deep Zero-Signal ($<0.01$) | 1.18 | 53,076.0 |
| `FN-04` | 7788 | 18472 | 1 | 0.561620 | 0.900 | 0.338380 | Moderate Risk ($[0.50, 0.80)$) | 0.68 | 29,531.0 |
| `FN-05` | 8629 | 131272 | 1 | 0.000432 | 0.900 | 0.899568 | Deep Zero-Signal ($<0.01$) | 0.20 | 79,540.0 |
| `FN-06` | 9579 | 100623 | 1 | 0.000140 | 0.900 | 0.899860 | Deep Zero-Signal ($<0.01$) | 549.06 | 67,571.0 |
| `FN-07` | 9880 | 229730 | 1 | 0.116408 | 0.900 | 0.783592 | Low Probability ($[0.01, 0.50)$) | 2.22 | 146,026.0 |
| `FN-08` | 13697 | 58761 | 1 | 0.002768 | 0.900 | 0.897232 | Deep Zero-Signal ($<0.01$) | 1.00 | 48,533.0 |
| `FN-09` | 13758 | 87354 | 1 | 0.586528 | 0.900 | 0.313472 | Moderate Risk ($[0.50, 0.80)$) | 19.04 | 61,646.0 |
| `FN-10` | 18489 | 249239 | 1 | 0.000720 | 0.900 | 0.899280 | Deep Zero-Signal ($<0.01$) | 1096.99 | 154,309.0 |
| `FN-11` | 18607 | 108258 | 1 | 0.017580 | 0.900 | 0.882420 | Low Probability ($[0.01, 0.50)$) | 0.76 | 70,828.0 |
| `FN-12` | 20428 | 33276 | 1 | 0.523554 | 0.900 | 0.376446 | Moderate Risk ($[0.50, 0.80)$) | 12.31 | 37,167.0 |
| `FN-13` | 20636 | 52521 | 1 | 0.004444 | 0.900 | 0.895556 | Deep Zero-Signal ($<0.01$) | 105.99 | 45,501.0 |
| `FN-14` | 24088 | 231978 | 1 | 0.028179 | 0.900 | 0.871821 | Low Probability ($[0.01, 0.50)$) | 8.00 | 146,998.0 |
| `FN-15` | 27429 | 56703 | 1 | 0.003921 | 0.900 | 0.896079 | Deep Zero-Signal ($<0.01$) | 0.76 | 47,545.0 |
| `FN-16` | 31784 | 154286 | 1 | 0.008586 | 0.900 | 0.891414 | Deep Zero-Signal ($<0.01$) | 0.92 | 101,051.0 |
| `FN-17` | 35172 | 6971 | 1 | 0.884860 | 0.900 | 0.015140 | Near-Threshold ($[0.80, 0.90)$) | 1809.68 | 9,064.0 |
| `FN-18` | 37578 | 240222 | 1 | 0.048009 | 0.900 | 0.851991 | Low Probability ($[0.01, 0.50)$) | 1.00 | 150,494.0 |

> [!NOTE]
> **Data Privacy Audit:** The exported CSV file contains only numerical model features (`Time`, `V1`–`V28`, `Amount`) and generated analytical indices. It contains zero Personally Identifiable Information (PII), PANs, CVVs, or cardholder credentials.

---

## 3. Probability Clustering & Proximity to Threshold

```
Predicted Probability Distribution of False Negatives (n=18)
┌──────────────────────────────────────────────┬───────┬────────────┐
│ Probability Band                             │ Count │ Percentage │
├──────────────────────────────────────────────┼───────┼────────────┤
│ Deep Zero-Signal (p < 0.01)                  │   9   │   50.0%    │
│ Low Probability (0.01 <= p < 0.50)           │   4   │   22.2%    │
│ Moderate Risk (0.50 <= p < 0.80)             │   4   │   22.2%    │
│ Near-Threshold (0.80 <= p < 0.90)            │   1   │    5.6%    │
└──────────────────────────────────────────────┴───────┴────────────┘
```

### Statistical Moments of Predicted Probabilities:
- **Mean:** $0.1911$
- **Median:** $0.0136$
- **Standard Deviation:** $0.2960$
- **Minimum:** $0.000077$ (`FN-03`)
- **Maximum:** $0.884860$ (`FN-17`)
- **Interquartile Range (IQR):** $0.003056$ to $0.421768$

### Key Analytical Takeaways:
1. **The "Boundary Fallacy":** It is tempting to assume missed fraud cases were near misses (e.g., $p \approx 0.88$). In reality, only **1 out of 18 cases** was near the $0.900$ boundary (`FN-17`, $p = 0.8849$).
2. **The "Stealth Clustering" Effect:** $50\%$ of all missed frauds had predicted probabilities below $0.01$. The supervised model was thoroughly deceived by their feature profiles, which exhibited virtually no typical fraud indicators.

---

## 4. Statistical Distribution Comparison (FN vs. TP vs. Legit)

To understand why the model failed to detect these cases, we compare the median and mean values of the model's top predictive features across three groups in the held-out test set:
- **Legitimate Transactions (TN):** $n = 42,484$
- **Detected Fraud (TP):** $n = 53$
- **Missed Fraud (FN):** $n = 18$

*Note: Features $V_1$–$V_{28}$ are anonymized PCA projections. Analysis is conducted strictly on statistical distributions without attributing speculative physical meanings.*

| Feature | Feature Importance | Legitimate Median | TP (Detected Fraud) Median | FN (Missed Fraud) Median | Legitimate Mean | TP Detected Mean | FN Missed Mean |
|---|---|---|---|---|---|---|---|
| **V14** | 43.15% | **+0.0612** | **-7.0769** | **-1.0191** | +0.0202 | -7.3803 | -1.6458 |
| **V4** | 6.35% | **-0.0257** | **+4.5225** | **+1.8904** | -0.0154 | +5.0319 | +2.2254 |
| **V10** | 3.99% | **-0.0941** | **-4.8912** | **-0.5891** | +0.0070 | -6.4892 | -0.5601 |
| **V12** | 3.02% | **+0.1421** | **-6.1471** | **-0.8074** | +0.0056 | -7.0630 | -1.1661 |
| **V17** | 2.07% | **-0.0672** | **-5.5221** | **+0.5061** | +0.0134 | -7.7164 | +0.4492 |
| **V11** | 1.85% | **-0.0384** | **+3.9698** | **+1.1225** | -0.0048 | +4.2513 | +0.9025 |
| **V8** | 4.01% | **+0.0197** | **+1.0912** | **-0.2419** | +0.0003 | +1.0546 | -0.8220 |
| **Amount ($)** | - | **$21.29** | **$30.39** | **$3.01** | $88.59 | $144.25 | $229.64 |
| **Time (s)** | - | **84,507s** | **70,270s** | **57,361s** | 94,551s | 73,189s | 73,271s |

### Statistical Observations:
1. **$V_{14}$ Insufficiency:** $V_{14}$ accounts for over $43\%$ of the tree splits. For detected fraud, $V_{14}$ collapses to a median of $-7.08$. However, for missed fraud, $V_{14}$ has a median of only $-1.02$. The model relies heavily on a severe negative deviation in $V_{14}$ to trigger high fraud probability; when that deviation is modest, the probability collapses.
2. **Positive Counter-Signal on $V_{17}$:** For detected fraud, $V_{17}$ has a median of $-5.52$. For missed fraud, $V_{17}$ actually shifted **positive** to $+0.51$, higher than legitimate transactions ($-0.07$), providing an active counter-signal that dampened the fraud probability.
3. **The Micro-Transaction Pattern:**
   - 8 of the 18 missed fraud cases ($44.4\%$) had transaction amounts under $\$1.20$ (`FN-03`=\$1.18, `FN-04`=\$0.68, `FN-05`=\$0.20, `FN-08`=\$1.00, `FN-11`=\$0.76, `FN-15`=\$0.76, `FN-16`=\$0.92, `FN-18`=\$1.00).
   - Median transaction amount for missed fraud was **\$3.01** (10 times smaller than detected fraud).
   - This suggests card testing / probing activity where fraudulent actors make tiny test authorizations that look identical to routine card verification charges.

---

## 5. Validation-Only Threshold Sensitivity Analysis

To rigorously assess whether lowering the operating threshold is viable without data leakage or test set contamination, we evaluated thresholds $0.90, 0.80, 0.70, 0.60,$ and $0.50$ **exclusively on the validation split** ($42,559$ transactions: $71$ fraud, $42,488$ legitimate).

The results are serialized in [validation_threshold_comparison.csv](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/experiments/results/validation_threshold_comparison.csv).

| Threshold ($\tau$) | Precision | Recall (TPR) | F1-Score | False Positives (FP) | True Positives (TP) | False Negatives (FN) | True Negatives (TN) | FPR (%) |
|---|---|---|---|---|---|---|---|---|
| **0.90 (Current)** | **0.9077** | **0.8310** | **0.8676** | **6** | **59** | **12** | **42,482** | **0.0141%** |
| **0.80** | 0.8551 | 0.8310 | 0.8429 | **10** (+66.7%) | 59 (+0) | 12 | 42,478 | 0.0235% |
| **0.70** | 0.8310 | 0.8310 | 0.8310 | **12** (+100%) | 59 (+0) | 12 | 42,476 | 0.0282% |
| **0.60** | 0.8219 | 0.8451 | 0.8333 | **13** (+116%) | **60** (+1) | 11 (-1) | 42,475 | 0.0306% |
| **0.50** | 0.7895 | 0.8451 | 0.8163 | **16** (+166%) | **60** (+1) | 11 (-1) | 42,472 | 0.0377% |

### Analysis of Threshold Lowering:
1. **Zero Gain Between 0.90 and 0.70:**
   - On the validation set, lowering $\tau$ from $0.90$ to $0.80$ caught **0 additional fraud cases** while increasing false alarms from 6 to 10.
   - Lowering $\tau$ further to $0.70$ still caught **0 additional fraud cases** while doubling false alarms to 12.
2. **Marginal Gain vs. Severe Cost at 0.60 and 0.50:**
   - Lowering $\tau$ to $0.60$ or $0.50$ recovered only **1 additional fraud transaction** (59 $\rightarrow$ 60).
   - In exchange, false alarms nearly tripled from 6 to 16 ($+166\%$), causing precision to fall from $90.77\%$ to $78.95\%$.
3. **Conclusion from Validation Data:** The peak validation F1-score is unambiguously at $\tau = 0.90$ ($F_1 = 0.8676$). Lowering the threshold causes immediate precision degradation without meaningful recall recovery.

---

## 6. Diagnostic Visualization

The generated visual artifact is located at:
[false_negative_probability_distribution.png](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/experiments/figures/false_negative_probability_distribution.png)

```
+---------------------------------------------------------------------------------------------------+
| Panel 1: Strip Plot of Missed Fraud Probabilities (n=18) relative to Threshold 0.900               |
| Panel 2: False Negatives Categorized by Probability Band (<0.01, 0.01-0.50, 0.50-0.80, 0.80-0.90) |
| Panel 3: Box Plot of V14 Distribution: Legitimate vs Detected Fraud vs Missed Fraud               |
+---------------------------------------------------------------------------------------------------+
```

---

## 7. Strategic Recommendations

Based on this empirical investigation, we advise the following:

### 1. Maintain the 0.900 Decision Threshold for Binary Supervised Action
Do not lower the primary decision threshold of the supervised model. The validation experiment demonstrates that lowering the threshold damages operational precision without catching the bulk of missed fraud cases (since half lie below $0.01$).

### 2. Leverage Hybrid Architecture Rather Than Global Threshold Reductions
The FraudShield AI architecture already includes a multi-factor risk engine:
- In the existing hybrid engine (`backend/app/services/fraud_engine.py`), transactions with moderate supervised probabilities ($0.50 \le p < 0.90$) combined with positive anomaly scores are assigned to the `MEDIUM` or `HIGH` risk categories, triggering analyst review workflows without raising blunt binary card declines.

### 3. Implement Micro-Transaction Velocity Heuristics
Because $44\%$ of the false negatives involve micro-charges ($<\$1.20$), rules-based velocity triggers (e.g., more than 3 transactions under $\$2.00$ within a 10-minute window) can capture card probing activity before larger fraudulent charges occur, entirely bypassing the supervised model's feature blind spots.

### 4. Continuous Feature Drift Monitoring
The substantial reliance on $V_{14}$ ($43\%$ importance) is a single-point-of-failure in the decision tree structure. If real-world fraud schemes produce neutral $V_{14}$ signatures, detection fails. Regular retraining with feature-shuffling and alternative tree depths should be explored in future modeling milestones.
