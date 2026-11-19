# FraudShield AI — Milestone 2D: Independent Generalization Evaluation Plan (Version 3.4.0)

**Document Version:** 3.4.0 (Provisional Research Margin Governance & Domain Alignment)  
**Status:** DRAFT / PROPOSED (STRICT PLANNING ONLY)  
**Author:** Senior Machine Learning Engineer & Lead ML Auditor  
**Date:** November 17, 2026  
**Subject System:** Hybrid Fraud Engine Generalization & Out-of-Distribution Validation  
**Target Candidates:** Frozen Production Baseline (`ARCH_A_w75_c500`) vs. Frozen Candidate (`ARCH_C_log_c500`)  
**Target Working Directory:** `experiments/milestone_2d/`  

---

## 1. Executive Summary & Audit Context

In **Milestone 2C**, the Logistic Meta-Calibrator candidate (**`ARCH_C_log_c500`**) demonstrated substantial advantages over the production baseline on validation data (cutting false alarms by $85.7\%$ while maintaining $81.69\%$ recall and reducing ECE by $89.7\%$ over raw probabilities). However, the final verification audit established that `ARCH_C_log_c500` is officially classified as a **"Promising candidate with failed acceptance gates"** because its minimum cross-fold recall was **$72.73\%$** in Fold 1 (below the $75.0\%$ floor).

### The Generalization Problem:
1. The original held-out test split (42,559 transactions) was inspected during Milestones 1 and 2B.
2. The validation split (42,559 transactions) was utilized for hyperparameter grid sweeps and calibrator evaluation during Milestone 2C.
3. Evaluating either system on these previously inspected splits introduces **post-hoc data snooping bias**.
4. **Milestone 2D Objective:** Design an independent generalization evaluation protocol to scientifically compare the frozen baseline against the frozen candidate on genuinely unseen transaction data, with pre-registered hypotheses, system-specific decision logic, and zero in-sample tuning.

---

## 2. Production Threshold Verification & Decision Logic Audit

A line-by-line inspection of the active codebase resolves the discrepancy between the $0.895$ and $0.900$ thresholds:

### 2.1 Code and Configuration Inspection
- **Artifact on Disk (`backend/artifacts/optimal_threshold.json`):**
  ```json
  {
    "model_name": "XGBoost",
    "optimal_threshold": 0.895,
    "f1_score": 0.8281,
    "precision": 0.9298,
    "recall": 0.7465,
    "updated_at": "2026-11-16T09:02:56.541594+00:00"
  }
  ```
- **Engine Initialization (`backend/app/services/fraud_engine.py:59-63`):**
  ```python
  if settings.THRESHOLD_PATH.exists():
      with open(settings.THRESHOLD_PATH, "r") as f:
          meta = json.load(f)
          self.threshold = float(meta.get("optimal_threshold", 0.50))
  ```
  At engine initialization, `self.threshold` is dynamically assigned **`0.895`**.
- **Inference Decision Rule (`backend/app/services/fraud_engine.py:119`):**
  ```python
  prediction = "SUSPICIOUS" if (risk_score >= 50.0 or fraud_prob >= self.threshold) else "LEGITIMATE"
  ```
  The active decision logic explicitly compares `fraud_prob >= self.threshold` (where `self.threshold = 0.895`).
- **Safety Clipping Constraint (`backend/app/ml/evaluation.py:72`):**
  ```python
  def find_optimal_threshold(..., min_threshold=0.05, max_threshold=0.90, ...):
      operational_threshold = max(min_threshold, min(max_threshold, raw_best_threshold))
  ```
  The optimization safety constraint is capped at **`0.900`**.

### 2.2 Reconciling the 0.895 vs. 0.900 Discrepancy
- In Milestone 1, the initial prompt specified: *"Current decision threshold: 0.900"*, and `evaluate_baseline.py` was executed with `threshold = 0.900`.
- Inspection of the discrete probability outputs in `creditcard.csv` shows that **zero transactions fall into the half-open interval $[0.895, 0.900)$**. Consequently, thresholds $0.895$ and $0.900$ yielded mathematically identical confusion matrices on both validation and held-out test splits.
- **Audit Conclusion:** The **actual active threshold supported by production code** is **`0.895`**. In Milestone 2D, the baseline will be evaluated strictly using `self.threshold = 0.895` as loaded from `optimal_threshold.json`. If any transaction falls in $[0.895, 0.900)$, metrics will be reported at both points for full audit transparency.

---

## 3. System-Specific Decision Rules & Review Queue Policies

To guarantee evaluation fairness and eliminate architectural conflation, separate binary decision rules, review queue policies, and step-up authentication bands are explicitly documented for each system:

```
+---------------------------------------------------------------------------------------------------+
|                            SYSTEM-SPECIFIC OPERATIONAL DECISION LOGIC                             |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [PIPELINE 1: PRODUCTION BASELINE (ARCH_A_w75_c500)]                                              |
|  1. Heuristic Risk Score: BaseRisk = (P_xgb * 0.75 + S_iforest * 0.25) * 100.0                    |
|     - Severe Anomaly Floor: if is_anomaly -> max(BaseRisk, 45.0)                                  |
|     - High Probability Floor: if P_xgb >= 0.895 -> max(BaseRisk, 70.0)                            |
|     - RiskScore_base = round(clip(BaseRisk, 0.0, 100.0), 1)                                       |
|  2. Binary Decision Rule:                                                                         |
|     y_hat_base = SUSPICIOUS if (RiskScore_base >= 50.0 OR P_xgb >= 0.895) else LEGITIMATE         |
|  3. Operational Review Queue (ORQ_base):                                                          |
|     ORQ_base = { i : RiskCategory_base = "MEDIUM" AND y_hat_base = SUSPICIOUS }                  |
|              = { i : RiskScore_base in [30.0, 75.0) AND (RiskScore_base >= 50.0 OR P_xgb >= 0.895) }|
|  4. Stepped-Up Authentication Band (Friction_base):                                               |
|     Friction_base = { i : RiskScore_base in [30.0, 50.0) AND P_xgb < 0.895 }                     |
|                                                                                                   |
|  -----------------------------------------------------------------------------------------------  |
|                                                                                                   |
|  [PIPELINE 2: CANDIDATE LOGISTIC META-CALIBRATOR (ARCH_C_log_c500)]                                |
|  1. Calibrated Probability: x_cal = [logit(clip(P_xgb, 1e-6, 1 - 1e-6)), S_iforest]               |
|     - P_cal = sigma(beta_0 + beta_1 * logit(P_xgb) + beta_2 * S_iforest)                           |
|     - RiskScore_cand = round(clip(P_cal * 100.0, 0.0, 100.0), 1)                                 |
|  2. Binary Decision Rule:                                                                         |
|     y_hat_cand = SUSPICIOUS if (RiskScore_cand >= 50.0) else LEGITIMATE                           |
|     (CRITICAL SAFEGUARD: Baseline's P_xgb >= 0.895 condition is NEVER applied to candidate)       |
|  3. Operational Review Queue (ORQ_cand):                                                          |
|     ORQ_cand = { i : RiskCategory_cand = "MEDIUM" AND y_hat_cand = SUSPICIOUS }                  |
|              = { i : RiskScore_cand in [50.0, 75.0) }  (since all scores >= 50.0 are SUSPICIOUS)   |
|  4. Stepped-Up Authentication Band (Friction_cand):                                               |
|     Friction_cand = { i : RiskScore_cand in [30.0, 50.0) }                                        |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### 3.2 High-Risk Alerts Classification (Both Systems)
Transactions with $\text{RiskScore} \ge 75.0$ are categorized as `HIGH` risk:
- **Operational Classification:** In both systems, `HIGH` risk cases are defined as **high-priority alerts requiring immediate analyst review or step-up authentication**, NOT irreversible automated blocks.

---

## 4. Dataset Requirements & External Availability Limitations

### 4.1 Schema Compatibility Constraints
The FraudShield pipeline requires strictly 30 continuous input features:
$$\mathbf{X} = \left[ \text{Time}, V_1, V_2, \dots, V_{28}, \text{Amount} \right]$$
Features $V_1..V_{28}$ are anonymized principal components from an undisclosed European bank (September 2013). Because the projection matrix $\mathbf{W}_{\text{PCA}}$ was never released, **no raw external dataset can be projected into this latent space**.

### 4.2 Five Mandatory Metadata Requirements for Candidate Data
To qualify for independent evaluation, an external dataset must document:
1. **Source Origin:** Issuing bank or financial institution origin.
2. **Collection Timeline:** Exact timestamp boundaries and duration.
3. **Label Maturity:** Minimum 60–90 day chargeback dispute maturation window to ensure ground-truth labels are complete.
4. **Fraud Prevalence:** Confirmed baseline fraud prevalence (typically $0.10\%$ to $0.50\%$).
5. **Data Access & Compliance:** Confirmed GDPR/banking compliance permitting read-only auditing.

### 4.3 External Generalization Boundary Statement
> [!IMPORTANT]
> **Scientific Finding on Real-World Generalization:**  
> If an independent, uninspected dataset sharing the exact 30 European bank PCA features cannot be acquired, **external real-world generalization cannot currently be established**.  
> Synthetic stress testing (CTGAN, Copula) will be utilized solely for perturbation analysis and must **never** be cited as evidence of real-world generalization.

---

## 5. Frozen Head-to-Head Comparison Protocol

Both candidate pipelines will be evaluated in read-only mode on the exact same transactions:
- **Pipeline 1 (Frozen Production Baseline):** Evaluated strictly via `best_fraud_model.joblib` and `isolation_forest.joblib` using its baseline decision rule.
- **Pipeline 2 (Frozen Candidate `ARCH_C_log_c500`):** Evaluated strictly via `final_logistic_calibrator.joblib` using its calibrated risk decision rule.
- **Zero In-Sample Tuning:** Neither calibrator nor preprocessor will be refitted on evaluation data.

---

## 6. Stratified Paired Bootstrap & Significance Testing Protocol

### 6.1 Stratified Paired Bootstrap Resampling ($B = 10,000$)
Because credit card fraud is severely imbalanced ($\approx 0.17\%$), standard random resampling induces large variance in sampled fraud counts. We enforce **Stratified Paired Resampling by True Class**:

1. **Stratified Partition:**  
   Separate evaluation indices into fraud cases $I_1 = \{i : y_i = 1\}$ ($N_1 = |I_1|$) and legitimate cases $I_0 = \{i : y_i = 0\}$ ($N_0 = |I_0|$).
2. **Replicate Generation ($b = 1, \dots, B$ where $B = 10,000$ for final audit; $B = 1,000$ for preliminary diagnostics):**
   - Resample $N_1$ indices from $I_1$ with replacement $\rightarrow I_1^{(b)}$.
   - Resample $N_0$ indices from $I_0$ with replacement $\rightarrow I_0^{(b)}$.
   - Merge indices: $I^{(b)} = I_1^{(b)} \cup I_0^{(b)}$.
   - Both models evaluate the exact same sampled transactions $I^{(b)}$.
3. **Conditioning on Fraud Prevalence:**
   Because $N_1$ and $N_0$ are resampled separately, every replicate preserves the exact sample fraud prevalence:
   $$\text{Prevalence}^{(b)} = \frac{N_1}{N_0 + N_1}$$
   The resulting confidence intervals **condition on observed fraud prevalence**, eliminating prevalence noise from the metric comparison.
4. **Paired Metric Difference:**
   For each replicate, compute candidate F1 and baseline F1 on the identical transactions:
   $$\Delta \text{F1}^{(b)} = \text{F1}_{\text{cand}}^{(b)} - \text{F1}_{\text{base}}^{(b)}$$
5. **95% Percentile Confidence Interval:**
   Defined deterministically by the $2.5\text{th}$ and $97.5\text{th}$ empirical percentiles of the sorted $\Delta \text{F1}$ array:
   $$\left[ \Delta \text{F1}_{2.5\%}, \ \Delta \text{F1}_{97.5\%} \right]$$

### 6.2 Handling Zero-Predicted-Positive Replicates
- In stratified resampling, positive ground-truth cases are always present ($N_1 > 0$).
- If a model predicts zero positive cases in a replicate ($\hat{y}_i = 0 \ \forall i$):
  - $\text{TP} = 0, \ \text{FP} = 0$.
  - Precision evaluates to $0.0$ and Recall evaluates to $0 / N_1 = 0.0$.
  - Consequently, $\text{F1} = 0.0$ under standard `zero_division=0`.
- **Classification:** These are **valid numerical outcomes ($\text{F1} = 0.0$)**, NOT undefined metrics. They will **not** be classified as undefined replicates or discarded.
- **Reporting:** Replicates where either model predicts zero positives will be tracked and reported separately as $N_{\text{zero\_pos}}$.

### 6.3 Separated Paired McNemar Testing Protocol

Standard overall McNemar testing pools false alarms (false positives on $y = 0$) and missed fraud (false negatives on $y = 1$) into a single aggregate error count. In credit card fraud detection where the class imbalance is severe ($\approx 99.83\%$ legitimate vs. $\approx 0.17\%$ fraud), an unstratified McNemar test is completely dominated by the legitimate class, masking critical regressions in fraud recall.

To isolate the exact mechanism of change, paired classification errors will be evaluated using two strictly decoupled, class-stratified McNemar tests:
1. **Fraud-Only McNemar Test ($y = 1$):** Compares paired classification errors (missed fraud) among confirmed fraud transactions.
2. **Legitimate-Only McNemar Test ($y = 0$):** Compares paired classification errors (false alarms) among confirmed legitimate transactions.

---

#### 6.3.1 Fraud-Only McNemar Test ($y = 1, \ N_{\text{fraud}}$): Detection Discordance & Error Audit

For confirmed fraud transactions ($y = 1$), a classification error is a **False Negative** ($\hat{y} = 0$, missed fraud), whereas correct classification is a **True Positive** ($\hat{y} = 1$, detected fraud). Let the binary error indicators be:
$$E_{\text{base}, i} = \mathbb{I}(\hat{y}_{\text{base}, i} = 0), \qquad E_{\text{cand}, i} = \mathbb{I}(\hat{y}_{\text{cand}, i} = 0)$$

The paired $2 \times 2$ classification error contingency table is defined as:

| Baseline Error \ Candidate Error | Candidate Correct ($E_{\text{cand}} = 0, \ \hat{y}_c = 1$) | Candidate Error ($E_{\text{cand}} = 1, \ \hat{y}_c = 0$) | Total Baseline |
|---|---|---|---|
| **Baseline Correct ($E_{\text{base}} = 0, \ \hat{y}_b = 1$)** | $a$ (Both Detected / Both Correct) | $b$ (Baseline Detected, Candidate Missed) | $a + b$ |
| **Baseline Error ($E_{\text{base}} = 1, \ \hat{y}_b = 0$)** | $c$ (Baseline Missed, Candidate Detected) | $d$ (Both Missed / Both Error) | $c + d$ |
| **Total Candidate** | $a + c$ | $b + d$ | $N_{\text{fraud}}$ |

- **Discordant Pair Definitions:**
  - $b$: Baseline Correct, Candidate Error ($E_{\text{base}} = 0, E_{\text{cand}} = 1$). Confirmed fraud detected by Baseline but missed by Candidate (Candidate degradation / Baseline only detected).
  - $c$: Baseline Error, Candidate Correct ($E_{\text{base}} = 1, E_{\text{cand}} = 0$). Confirmed fraud missed by Baseline but detected by Candidate (Candidate gain / Candidate only detected).
  - Total Discordant Pairs: $n_{\text{disc, fraud}} = b + c$.
- **Directional Discordant Metric:**
  $$\Delta_{\text{fraud\_detect}} = c - b$$
  - $\Delta_{\text{fraud\_detect}} > 0$: Candidate captures more confirmed fraud than Baseline.
  - $\Delta_{\text{fraud\_detect}} < 0$: Candidate misses more confirmed fraud than Baseline.
- **Statistical Hypotheses:**
  - Null Hypothesis $H_0^{\text{fraud}}: P(E_{\text{base}} = 0, E_{\text{cand}} = 1) = P(E_{\text{base}} = 1, E_{\text{cand}} = 0) \iff b = c$.
  - Alternative Hypothesis $H_1^{\text{fraud}}: b \ne c$ (two-sided).
- **Statistical Test Procedure:**
  - If $b + c < 25$: Compute exact two-sided Binomial test under $P \sim \text{Binomial}(b + c, 0.5)$:
    $$p_{\text{fraud}} = 2 \times \sum_{k=0}^{\min(b, c)} \binom{b + c}{k} (0.5)^{b + c}$$
    (If $b = c$, $p_{\text{fraud}} = 1.0$).
  - If $b + c \ge 25$: Compute Edwards continuity-corrected McNemar test statistic:
    $$\chi^2_{\text{fraud}} = \frac{(|b - c| - 1)^2}{b + c}, \qquad p_{\text{fraud}} = P\left(\chi^2_1 \ge \chi^2_{\text{fraud}}\right)$$
  - Significance Threshold: $\alpha = 0.01$ ($p < 0.01$).

---

#### 6.3.1.1 Methodological Distinction: Absence of Significant Degradation vs. Formal Non-Inferiority

A central tenet of biostatistics and safety-critical testing is that **"absence of evidence is not evidence of absence"** (Altman & Bland, 1995). In the fraud-only McNemar test:
- A non-significant result ($p_{\text{fraud}} \ge 0.01$) on $H_0^{\text{fraud}}: b = c$ demonstrates only that the observed sample discordance does not reach statistical significance at $\alpha = 0.01$.
- It **does NOT** demonstrate that fraud recall has been preserved, nor does it establish formal non-inferiority.

To ensure strict scientific accuracy, the evaluation protocol distinguishes two hierarchical conclusions regarding fraud detection:

1. **Conclusion A (Conservative Baseline Standard): "No Statistically Significant Fraud Degradation Detected"**
   - **Condition:** Two-sided $p_{\text{fraud}} \ge 0.01$ (with either $b \le c$, or $b > c$ failing significance at $\alpha = 0.01$).
   - **Mandatory Reporting Language:** The evaluation report must strictly designate this finding as:
     $$\mathbf{\text{“No statistically significant fraud degradation detected (} p_{\text{fraud}} \ge 0.01 \text{)”}}$$
   - **Explicit Prohibition:** The evaluation report is **strictly forbidden** from describing this result as "proven non-inferiority", "proven recall preservation", or "guaranteed equivalence".

2. **Conclusion B (Provisional Research Non-Inferiority): "Provisional Fraud Recall Non-Inferiority Established"**
   - **Paired Fraud Recall Difference:**
     Because baseline and candidate predictions are paired on the identical confirmed fraud transactions ($N_{\text{fraud}}$), the empirical recall difference is:
     $$\Delta \text{Recall} = \text{Recall}_{\text{cand}} - \text{Recall}_{\text{base}} = \frac{a + c}{N_{\text{fraud}}} - \frac{a + b}{N_{\text{fraud}}} = \frac{c - b}{N_{\text{fraud}}}$$
   - **Provisional Research Non-Inferiority Margin ($\delta_{\text{recall}} = 0.030$):**
     - For FraudShield Milestone 2D research analysis, the non-inferiority margin is pre-set at **$\delta_{\text{recall}} = 0.030$ (3.0 percentage points)**.
     - **Explicit Governance Classification:** This margin is explicitly designated as a **provisional research acceptance margin**, NOT an established banking-industry safety standard or regulatory norm.
     - **Operational Trade-Off Nuance:** While an anticipated $> 80\%$ reduction in false positive alert volume significantly relieves analyst queues, **the expected false-alarm reduction alone does NOT prove that a 3-percentage-point recall loss is operationally or financially acceptable**. In banking operations, the acceptability of any recall loss depends heavily on dollar-weighted exposure, loss-given-fraud (LGF), chargeback write-off liability, regulatory compliance thresholds, and brand reputation risks. A 3% drop in detected fraud could correspond to unacceptable monetary losses on high-value transactions.
     - **Supervisory & Domain-Expert Requirement:** Formal **agreement from supervisory authorities, risk management, and enterprise fraud domain experts is desirable and recommended** before making an authoritative operational non-inferiority claim for production deployment.
   - **Paired Confidence Interval Calculation:**
     Calculate the two-sided $95\%$ confidence interval (yielding a $97.5\%$ lower confidence bound, or a nominal $95\%$ one-sided lower bound) for $\Delta \text{Recall}$ via paired stratified bootstrap ($B = 10,000$ replicates of $N_{\text{fraud}}$) or the asymptotic paired score variance (Tang / Newcombe paired score method):
     $$\text{Var}(\Delta \text{Recall}) = \frac{(b + c) - \frac{(c - b)^2}{N_{\text{fraud}}}}{N_{\text{fraud}}^2}$$
     $$\text{LB}_{95\%}(\Delta \text{Recall}) = \Delta \text{Recall} - 1.96 \times \sqrt{\text{Var}(\Delta \text{Recall})}$$
   - **Non-Inferiority Decision Criterion:**
     $$\text{LB}_{95\%}(\Delta \text{Recall}) > -\delta_{\text{recall}} \quad (\text{i.e. } \text{LB}_{95\%} > -0.030)$$
   - **Reporting Rule & Conservative Fallback:**
     - Only when this lower bound condition is satisfied AND the provisional research nature of the margin is explicitly stated may the report claim: **"Provisional Fraud Recall Non-Inferiority Established (Research Margin $\delta = 3.0\%$, Subject to Domain-Expert Agreement)"**.
     - If no formal domain agreement is established, or if $\text{LB}_{95\%}(\Delta \text{Recall}) \le -\delta_{\text{recall}}$, the evaluation report must revert to the conservative Conclusion A:
       $$\mathbf{\text{“No statistically significant fraud degradation detected (} p_{\text{fraud}} \ge 0.01 \text{)”}}$$
     - The report is strictly forbidden from claiming proven operational non-inferiority or proven recall preservation in the absence of verified domain-expert agreement and empirical lower-bound satisfaction.

---

#### 6.3.2 Legitimate-Only McNemar Test ($y = 0, \ N_{\text{legit}}$): False Alarm Discordance & Noise Audit

For confirmed legitimate transactions ($y = 0$), a classification error is a **False Positive** ($\hat{y} = 1$, false alarm / false decline), whereas correct classification is a **True Negative** ($\hat{y} = 0$, transaction cleared). Let the binary error indicators be:
$$E_{\text{base}, i} = \mathbb{I}(\hat{y}_{\text{base}, i} = 1), \qquad E_{\text{cand}, i} = \mathbb{I}(\hat{y}_{\text{cand}, i} = 1)$$

The paired $2 \times 2$ classification error contingency table is defined as:

| Baseline Error \ Candidate Error | Candidate Error ($E_{\text{cand}} = 1, \ \hat{y}_c = 1$) | Candidate Correct ($E_{\text{cand}} = 0, \ \hat{y}_c = 0$) | Total Baseline |
|---|---|---|---|
| **Baseline Error ($E_{\text{base}} = 1, \ \hat{y}_b = 1$)** | $e$ (Both Flagged / Both False Alarms) | $f$ (Baseline Flagged, Candidate Cleared) | $e + f$ |
| **Baseline Correct ($E_{\text{base}} = 0, \ \hat{y}_b = 0$)** | $g$ (Baseline Cleared, Candidate Flagged) | $h$ (Both Cleared / Both Correct) | $g + h$ |
| **Total Candidate** | $e + g$ | $f + h$ | $N_{\text{legit}}$ |

- **Discordant Pair Definitions:**
  - $f$: Baseline Error, Candidate Correct ($E_{\text{base}} = 1, E_{\text{cand}} = 0$). Legitimate transaction false-alarmed by Baseline but correctly cleared by Candidate (Candidate false alarm reduction / Baseline only false alarm).
  - $g$: Baseline Correct, Candidate Error ($E_{\text{base}} = 0, E_{\text{cand}} = 1$). Legitimate transaction cleared by Baseline but false-alarmed by Candidate (Candidate false alarm increase / Candidate only false alarm).
  - Total Discordant Pairs: $n_{\text{disc, legit}} = f + g$.
- **Directional Discordant Metric:**
  $$\Delta_{\text{false\_alarm\_red}} = f - g$$
  - $\Delta_{\text{false\_alarm\_red}} > 0$: Candidate reduces false alarms compared to Baseline.
  - $\Delta_{\text{false\_alarm\_red}} < 0$: Candidate increases false alarms compared to Baseline.
- **Statistical Hypotheses:**
  - Null Hypothesis $H_0^{\text{legit}}: P(E_{\text{base}} = 1, E_{\text{cand}} = 0) = P(E_{\text{base}} = 0, E_{\text{cand}} = 1) \iff f = g$.
  - Alternative Hypothesis $H_1^{\text{legit}}: f \ne g$ (two-sided).
- **Statistical Test Procedure:**
  - If $f + g < 25$: Compute exact two-sided Binomial test under $P \sim \text{Binomial}(f + g, 0.5)$:
    $$p_{\text{legit}} = 2 \times \sum_{k=0}^{\min(f, g)} \binom{f + g}{k} (0.5)^{f + g}$$
  - If $f + g \ge 25$: Compute Edwards continuity-corrected McNemar test statistic:
    $$\chi^2_{\text{legit}} = \frac{(|f - g| - 1)^2}{f + g}, \qquad p_{\text{legit}} = P\left(\chi^2_1 \ge \chi^2_{\text{legit}}\right)$$
  - Significance Threshold: $\alpha = 0.01$ ($p < 0.01$).

---

#### 6.3.3 Mandatory Reporting Schema for Both Tests

The independent evaluation script and audit report must explicitly output all of the following quantities for both classes:
```json
{
  "fraud_test": {
    "total_fraud": N_fraud,
    "concordant_both_detected_a": a,
    "concordant_both_missed_d": d,
    "discordant_baseline_only_detected_b": b,
    "discordant_candidate_only_detected_c": c,
    "total_discordant_pairs": b + c,
    "directional_net_fraud_gain_c_minus_b": c - b,
    "paired_delta_recall": (c - b) / N_fraud,
    "paired_delta_recall_ci_95": [LB_95, UB_95],
    "provisional_research_margin_delta": 0.030,
    "provisional_research_non_inferiority_established": LB_95 > -0.030,
    "domain_expert_agreement_required": true,
    "test_method": "exact_binomial" | "continuity_corrected_chi2",
    "test_statistic": chi2_stat_or_min_count,
    "p_value_exact_two_sided": p_fraud,
    "alpha": 0.01,
    "reject_null": p_fraud < 0.01,
    "statistical_conclusion": "NO_STATISTICALLY_SIGNIFICANT_DEGRADATION_DETECTED" | "SIGNIFICANT_CANDIDATE_GAIN" | "SIGNIFICANT_CANDIDATE_DEGRADATION"
  },
  "legitimate_test": {
    "total_legitimate": N_legit,
    "concordant_both_flagged_e": e,
    "concordant_both_cleared_h": h,
    "discordant_baseline_only_alarm_f": f,
    "discordant_candidate_only_alarm_g": g,
    "total_discordant_pairs": f + g,
    "directional_net_alarm_reduction_f_minus_g": f - g,
    "test_method": "exact_binomial" | "continuity_corrected_chi2",
    "test_statistic": chi2_stat_or_min_count,
    "p_value_exact_two_sided": p_legit,
    "alpha": 0.01,
    "reject_null": p_legit < 0.01,
    "verdict": "SIGNIFICANT_ALARM_REDUCTION" | "NO_SIGNIFICANT_DIFFERENCE" | "SIGNIFICANT_ALARM_INCREASE"
  }
}
```

---

#### 6.3.4 Formal Joint Statistical Superiority Decision Rule

To establish a formal conclusion of **Statistical Superiority**, the evaluation protocol strictly requires **both tests** to support the candidate's intended advantage without evidence of significantly worse performance in either class:

$$\begin{aligned}
\text{Superiority Established} \iff & \left( \text{Intended Advantage Demonstrated at } p < 0.01 \right) \\
& \land \left( \text{Zero Statistically Significant Degradation in Either Class at } p < 0.01 \right)
\end{aligned}$$

Specifically, for candidate **`ARCH_C_log_c500`** (whose primary design objective is massive precision gain while preserving baseline recall):

1. **Condition 1 (Intended Advantage: False Alarm Reduction):**
   - The candidate must achieve a statistically significant net reduction in legitimate false alarms:
     $$f > g \quad \text{AND} \quad p_{\text{legit}} < 0.01$$
2. **Condition 2 (Zero Degradation: Fraud Detection Safety Gate):**
   - The candidate must **NOT** exhibit statistically significant degradation in fraud detection:
     $$\text{NOT } \left( b > c \quad \text{AND} \quad p_{\text{fraud}} < 0.01 \right)$$
   - That is, either the candidate catches more fraud ($c > b$ with $p_{\text{fraud}} < 0.01$), or the difference in fraud capture is statistically non-significant (two-sided $p_{\text{fraud}} \ge 0.01$).
   - **MANDATORY SAFETY GUARDRAIL:** If the candidate misses significantly more fraud than baseline ($b > c$ with $p_{\text{fraud}} < 0.01$), **candidate superiority is definitively REJECTED**, regardless of how many thousands of false alarms are eliminated ($p_{\text{legit}} \ll 10^{-10}$). Fraud recall preservation is an uncompromisable constraint.
3. **Condition 3 (Zero Degradation: Legitimate Clearances):**
   - In any scenario where a candidate's intended advantage is higher fraud recall ($c > b, p_{\text{fraud}} < 0.01$), it must similarly NOT generate significantly more false alarms ($\text{NOT } [g > f \land p_{\text{legit}} < 0.01]$).

#### Joint Decision Matrix:
| Legitimate Test Outcome | Fraud Test Outcome | Non-Inferiority Status | Joint Statistical Verdict | Deployment Decision |
|---|---|---|---|---|
| $f > g, \ p_{\text{legit}} < 0.01$ (Significant alarm cut) | $c > b, \ p_{\text{fraud}} < 0.01$ (Significant fraud gain) | N/A (Candidate Superior) | **Decisive Dual Superiority Established** | Authorized for Canary Cutover (Gate D1–D6 met) |
| $f > g, \ p_{\text{legit}} < 0.01$ (Significant alarm cut) | $p_{\text{fraud}} \ge 0.01$ or $c \ge b$ | $\text{LB}_{95\%} > -0.030$ | **Statistical Superiority Established with Provisional Research Non-Inferiority** | Authorized for Canary Cutover (Gate D1–D6 met; requires supervisor/domain agreement for operational non-inferiority claim) |
| $f > g, \ p_{\text{legit}} < 0.01$ (Significant alarm cut) | $p_{\text{fraud}} \ge 0.01$ or $c \ge b$ | $\text{LB}_{95\%} \le -0.030$ or margin unagreed | **Statistical Superiority Established (No Statistically Significant Fraud Degradation Detected)** | Authorized for Canary Cutover (Gate D1–D6 met; operational recall preservation unproven) |
| $f > g, \ p_{\text{legit}} < 0.01$ (Significant alarm cut) | $b > c, \ p_{\text{fraud}} < 0.01$ (Significant fraud loss) | Failed ($\text{LB} \le -0.030$) | **Superiority Rejected (Safety Breach: Statistically Significant Fraud Degradation Detected)** | Retain Baseline; Reject Cutover |
| $p_{\text{legit}} \ge 0.01$ (Alarm cut not significant) | Any | Any | **Failure to Demonstrate Superiority** | Retain Baseline; Reject Cutover |
| $g > f, \ p_{\text{legit}} < 0.01$ (Significant alarm increase)| Any | Any | **Superiority Rejected (Legitimate Degradation)** | Retain Baseline; Reject Cutover |

---

## 7. Calibration Fairness & Objective Benchmarking

### 7.1 Fair Benchmark: Calibrated Candidate vs. Raw XGBoost Probabilities
To ensure absolute scientific fairness:
1. **Primary Calibration Benchmark:**  
   `ARCH_C_log_c500`'s frozen calibrated probability output ($P_{\text{cal}} \in [0, 1]$) will be compared directly against **raw uncalibrated XGBoost probabilities** ($P_{\text{xgb}} \in [0, 1]$) using Brier score and Quantile ECE.
2. **Heuristic Score as Diagnostic Only:**  
   The baseline heuristic risk score divided by 100 (`val_risk_scores / 100.0`) will be reported strictly as a **secondary diagnostic reference**. It will **not** be treated as a true probability.
3. **No False Claims:** Calibration improvement will **never** be claimed based solely on comparison with the heuristic score, as the heuristic score's step floors ($0.45, 0.70$) inherently distort probability calibration.

### 7.2 Deterministic Quantile ECE & Brier Formulations
- **Quantile ECE:** 10 bins constructed via `np.quantile(probs, np.linspace(0, 1, 11))` with `np.unique` tie handling:
  $$\text{ECE} = \sum_{m=1}^{10} \frac{|B_m|}{N} \left| \overline{p}(B_m) - \overline{y}(B_m) \right|$$
  Empty bins contribute $0.0$. Quantile boundaries are computed separately for each system based on its empirical score distribution.
- **Brier Score:**
  $$\text{Brier} = \frac{1}{N} \sum_{i=1}^N (p_i - y_i)^2$$
- **Provisional Status:** Calibration targets ($\text{ECE} \le 0.0050, \ \text{Brier} \le 0.0010$) remain **provisional targets**, subject to adjustment based on evaluation fraud prevalence.

---

## 8. Statistical Power & Disambiguated Conclusion Language

### 8.1 Exact Binomial Standard-Error Calculation
At an anticipated fraud recall of $p = 0.80$ with $n = 50$ confirmed fraud cases, the exact standard error is:
$$\text{SE}(\hat{p}) = \sqrt{\frac{p(1 - p)}{n}} = \sqrt{\frac{0.80 \times 0.20}{50}} = \sqrt{\frac{0.16}{50}} = \sqrt{0.0032} = \mathbf{5.65685...\% \approx 5.66\%}$$
- Margin of error ($z_{0.975} = 1.96$) is $1.96 \times 5.66\% = \mathbf{\pm 11.09\%}$.
- An observed recall of $80.0\%$ carries a $95\%$ confidence interval spanning $[68.9\%, 91.1\%]$.

### 8.2 Disambiguation of Statistical Decision Language
To prevent improper interpretation of statistical results, the evaluation report will adhere strictly to three distinct categorical outcomes:

```
+---------------------------------------------------------------------------------------------------+
|                            THREE MUTUALLY EXCLUSIVE EVALUATION OUTCOMES                           |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  1. STATISTICAL SUPERIORITY ESTABLISHED:                                                          |
|     - Prerequisites: Sample size is adequate (N >= 20,000, N_fraud >= 50).                         |
|     - Performance: Candidate satisfies all pre-registered acceptance gates (D1 - D6).              |
|     - Significance: Paired bootstrap 95% CI for Delta F1 has lower bound > 0.0 AND                 |
|       Separated McNemar Joint Rule is satisfied (p_legit < 0.01 with f > g, AND                   |
|       no statistically significant fraud degradation [NOT (b > c AND p_fraud < 0.01)]).            |
|     - Rigorous Reporting Nuance on Fraud Recall:                                                  |
|       * If LB_95(Delta Recall) > -0.030: Designated "Statistical Superiority with Provisional     |
|         Research Fraud Recall Non-Inferiority Established (delta = 3.0%)", noting that supervisor |
|         / domain-expert agreement is desirable before operational cutover.                        |
|       * If LB_95(Delta Recall) <= -0.030 or margin unagreed: Strictly designated                  |
|         "Statistical Superiority Established (No Statistically Significant Fraud Degradation      |
|         Detected)". Report strictly forbidden from claiming proven non-inferiority or recall      |
|         preservation.                                                                             |
|     - Action: Candidate authorized for phased production canary deployment.                       |
|                                                                                                   |
|  2. FAILURE TO DEMONSTRATE SUPERIORITY:                                                           |
|     - Prerequisites: Sample size is adequate (N >= 20,000, N_fraud >= 50).                         |
|     - Performance: Candidate fails one or more acceptance gates, OR paired Delta F1 95% CI spans  |
|       zero, OR p_legit >= 0.01, OR statistically significant fraud degradation is detected        |
|       (b > c with p_fraud < 0.01, triggering immediate safety rejection).                         |
|     - Interpretation: The data provides sufficient evidence that candidate superiority is NOT     |
|       demonstrated. (A p-value >= 0.01 is failure to reject H_0, NOT proof of low power).         |
|     - Action: Retain production baseline; reject candidate cutover.                               |
|                                                                                                   |
|  3. INCONCLUSIVE DUE TO INSUFFICIENT INFORMATION:                                                 |
|     - Prerequisites: Sample size is INADEQUATE (N < 20,000 OR N_fraud < 50).                       |
|     - Interpretation: The dataset fails minimum eligibility thresholds. Statistical power is     |
|       insufficient to draw reliable conclusions.                                                  |
|     - Action: No deployment decision or verdict issued. Acceptance criteria will NEVER be         |
|       weakened post-hoc to force a verdict.                                                       |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### 8.3 Pre-Registered Acceptance Criteria (Unweakened)
```
+---------------------------------------------------------------------------------------------------+
|                         PRE-REGISTERED ACCEPTANCE GATES (MILESTONE 2D)                           |
+---------------------------------------------------------------------------------------------------+
| Gate D1: Recall Floor          | Recall >= 78.0% (retains fraud capture under domain shift)       |
| Gate D2: Precision Superiority | Precision >= 85.0% (must decisively exceed baseline 81.1%)       |
| Gate D3: False Positive Rate   | FPR <= 0.020% (less than 1 false alarm per 5,000 transactions)   |
| Gate D4: Calibration Integrity | Quantile ECE <= 0.0050 and Brier Score <= 0.0010 (Provisional)   |
| Gate D5: Paired Significance   | 95% Bootstrap CI for Delta F1 (B=10,000) has lower bound > 0.0   |
|                                | AND Separated McNemar Joint Superiority Rule satisfied (p < 0.01) |
| Gate D6: Review Queue Policy   | Operational Review Queue (ORQ) Volume <= 0.50% total stream      |
+---------------------------------------------------------------------------------------------------+
```

---

## 9. Comprehensive Change Log (v3.0.0 $\rightarrow$ v3.1.0 $\rightarrow$ v3.2.0 $\rightarrow$ v3.3.0 $\rightarrow$ v3.4.0)

### Version 3.4.0 Revisions:
| Section | Exact Revision Applied |
|---|---|
| **Section 6.3.1.1** | Explicitly labeled $\delta_{\text{recall}} = 0.030$ as a **provisional research acceptance margin**, not an established banking-industry safety standard. Explained that expected false-alarm reduction alone does not prove that a 3% recall loss is operationally acceptable (e.g. depending on loss-given-fraud, dollar exposure, regulatory compliance). Recorded that supervisor/domain-expert agreement is desirable before making an operational non-inferiority claim. Preserved paired CI calculation ($\text{LB}_{95\%} > -0.030$) and conservative fallback reporting rule. |
| **Section 6.3.3** | Updated reporting schema with `provisional_research_margin_delta: 0.030`, `domain_expert_agreement_required: true`, and `provisional_research_non_inferiority_established`. |
| **Section 6.3.4** | Refined Joint Decision Matrix to explicitly qualify non-inferiority as provisional research non-inferiority requiring supervisor/domain-expert agreement for operational claims. |
| **Section 8.2** | Synchronized statistical decision language in Outcome 1 with the provisional research margin classification and domain-expert governance requirement. |

### Version 3.3.0 Revisions:
| Section | Exact Revision Applied |
|---|---|
| **Section 6.3.1.1** | Formally distinguished "No statistically significant fraud degradation detected" ($p_{\text{fraud}} \ge 0.01$) from "Formal fraud recall non-inferiority established". Defined paired recall difference $\Delta \text{Recall} = \frac{c - b}{N_{\text{fraud}}}$. Pre-registered maximum allowable loss margin $\delta_{\text{recall}} = 0.030$ ($3.0\%$) and formulated paired $95\%$ CI requirement ($\text{LB}_{95\%} > -0.030$). Enforced strict prohibition against describing a non-significant test as proven non-inferiority or recall preservation when non-inferiority is unestablished. |
| **Section 6.3.3** | Augmented JSON reporting schema with `paired_delta_recall`, `paired_delta_recall_ci_95`, `non_inferiority_margin_delta`, `formal_non_inferiority_established`, and precise `statistical_conclusion`. |
| **Section 6.3.4** | Updated Joint Decision Rule and Joint Decision Matrix to explicitly differentiate between decisive superiority, statistical superiority with formal non-inferiority ($\text{LB} > -0.030$), statistical superiority with no significant degradation detected (non-inferiority unproven), and safety rejection. Preserved mandatory safety rule rejecting candidate cutover if $b > c$ at $p_{\text{fraud}} < 0.01$. |
| **Section 8.2** | Refined statistical decision language in Outcome 1 and Outcome 2 to distinguish non-inferiority from non-significant degradation, codifying reporting nuance. |

### Version 3.2.0 Revisions:
| Section | Exact Revision Applied |
|---|---|
| **Section 6.3.1** | Explicitly defined the Fraud-Only McNemar test ($y = 1$) comparing paired classification errors (missed fraud: $E_i = \mathbb{I}(\hat{y}_i = 0)$). Defined $2 \times 2$ error contingency table ($a, b, c, d$), directional discordant metric $\Delta_{\text{fraud\_detect}} = c - b$, exact two-sided Binomial testing where $b+c < 25$, continuity-corrected $\chi^2$ where $b+c \ge 25$, and significance threshold $\alpha = 0.01$. |
| **Section 6.3.2** | Explicitly defined the Legitimate-Only McNemar test ($y = 0$) comparing paired classification errors (false alarms: $E_i = \mathbb{I}(\hat{y}_i = 1)$). Defined $2 \times 2$ error contingency table ($e, f, g, h$), directional discordant metric $\Delta_{\text{false\_alarm\_red}} = f - g$, exact two-sided Binomial testing where $f+g < 25$, continuity-corrected $\chi^2$ where $f+g \ge 25$, and significance threshold $\alpha = 0.01$. |
| **Section 6.3.3** | Standardized mandatory reporting schema requiring explicit logging of concordant counts, directional discordant counts ($b, c, c-b$ and $f, g, f-g$), test methods, test statistics, and exact two-sided $p$-values. |
| **Section 6.3.4** | Specified the formal **Joint Statistical Superiority Decision Rule**: establishing superiority strictly requires both tests to support the candidate's intended advantage (significant false alarm cut $f > g, p_{\text{legit}} < 0.01$) without evidence of significantly worse performance in either class (fraud recall safety gate: NOT $[b > c \land p_{\text{fraud}} < 0.01]$). Provided comprehensive joint decision matrix. |
| **Section 8** | Synchronized Section 8.2 decision categories and Gate D5 with the formal Joint Separated McNemar testing protocol. |

### Version 3.1.0 Revisions:
| Section | Exact Revision Applied |
|---|---|
| **Section 3** | Explicitly separated binary decision rules: Baseline requires `RiskScore_base >= 50.0 OR P_xgb >= 0.895`; Candidate strictly requires `RiskScore_cand >= 50.0`. Added safeguard ensuring Baseline's `P_xgb < 0.895` condition is never applied to the Candidate. Defined `ORQ` and step-up auth bands separately for both pipelines. |
| **Section 6** | Documented that stratified resampling preserves positive cases ($N_1 > 0$); defined zero predicted positives as valid $\text{F1} = 0.0$ under `zero_division=0` rather than undefined metrics; tracked $N_{\text{zero\_pos}}$ separately; documented conditioning on sample fraud prevalence. |
| **Section 7** | Established raw XGBoost probabilities as the primary calibration benchmark for ECE and Brier score; relegated heuristic risk score to a secondary diagnostic reference only; prohibited claiming calibration improvement based solely on heuristic score comparison. |
| **Section 8** | Disambiguated three formal statistical outcomes: Statistical Superiority, Failure to Demonstrate Superiority, and Inconclusive Due to Insufficient Information. Clarified that $p \ge 0.01$ reflects failure to reject $H_0$, not low power. Retained all acceptance criteria unweakened. |

---

## 10. Strict Execution Boundaries

- This document represents **read-only planning and consistency auditing only**.
- Zero experiments, model evaluations, or calibration refitting will occur.
- Zero parameters or thresholds will be tuned.
- The quarantined test split remains untouched.
- Production code and model artifacts remain frozen.
- Clean stop maintained awaiting review.
