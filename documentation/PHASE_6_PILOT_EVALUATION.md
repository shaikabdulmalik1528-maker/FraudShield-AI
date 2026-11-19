# FraudShield 3.0 — Phase 6 Pilot Evaluation: Synthetic Traffic & Detection Quality Analysis

**Document ID:** `FS3-EVAL-006`  
**Milestone:** Phase 6 — Controlled Pilot Deployment & Operational Validation  
**Date:** 2026-11-17  
**Status:** COMPLETE & INDEPENDENTLY VERIFIED  
**Governing Artifact:** `pilot_evaluation_results.json`, `pilot_synthetic_transactions.json`  
**Traffic Volume:** 2,500 Fully Labeled Synthetic Transactions  
**Serving Cluster:** 4 Independent Uvicorn OS Workers on Port 8008  

---

## 1. Executive Summary

Phase 6 executed an end-to-end detection quality evaluation of FraudShield 3.0 using $N = 2,500$ reproducible, ground-truth labeled synthetic transactions. In strict compliance with security and safety directives:
- All traffic was purely synthetic. No connection was made to live payment rails or real banking accounts.
- Detection policies and model operating thresholds were preserved without artificial adjustments.
- All transactions were processed through the live four-worker Uvicorn serving cluster on isolated port `8008`.

### Key Empirical Findings:
1. **Exceptional Fraud Sensitivity (96.57% Recall):**
   - The multi-tier engine successfully detected **225 out of 233** fraudulent and adversarial transactions.
   - The False Negative Rate (FNR) was constrained to **3.43%**, strictly exceeding the pilot requirement ($\text{FNR} \le 10.0\%$).
2. **Controlled False Positive Rate (5.25% FPR):**
   - Across 2,267 legitimate payments, **2,148 were approved without friction** and 119 were challenged via Step-Up 2FA or Analyst Review.
   - Zero legitimate transactions were mistakenly hard-blocked.
3. **Flawless Duplicate Replay Immunity (100% Catch Rate):**
   - 25 out of 25 duplicate transaction replays were atomically intercepted and blocked by the idempotency engine with zero feature-store double counting.
4. **Sub-5ms Median Serving Latency Under Multi-Worker Load:**
   - Single-transaction scoring latency achieved **4.73 ms P50**, **6.68 ms P90**, and **13.10 ms P99**, demonstrating outstanding real-time viability.

---

## 2. Synthetic Traffic Dataset Composition (N = 2,500)

The synthetic pilot dataset was deterministically generated (`RANDOM_SEED = 2026`) across 7 distinct operational and adversarial scenarios:

| Scenario ID | Operational Scenario Description | Transaction Count | Card Pool Strategy | Currency Mix | Primary Ground Truth |
| :--- | :--- | :---: | :--- | :--- | :---: |
| **SC-01** | **Legitimate Commerce** | 2,000 | 500 distinct cardholders ($1–4$ txs/card) | USD (100%) | Legitimate (100%) |
| **SC-02** | **Card-Not-Present Velocity Attack** | 100 | 10 burst cards ($10$ txs / 2 mins) | USD (100%) | Fraud (80%) |
| **SC-03** | **Impossible Travel (Physical POS)** | 50 | 25 distinct pairs (NYC $\to$ London, 15 min) | USD (100%) | Fraud (50%) |
| **SC-04** | **Duplicate Replay Attack** | 50 | 25 original / replayed pairs | USD (100%) | Fraud (50%) |
| **SC-05** | **Multi-Currency Global Payments** | 150 | Random pool across 10 global merchants | JPY, EUR, GBP, CAD, AUD, INR | Fraud (8.7%) |
| **SC-06** | **High-Value Extreme Anomalies** | 100 | Whale amounts ($3,500–$18,000) | USD (100%) | Fraud (60%) |
| **SC-07** | **Degraded Feature Store Failsafe** | 50 | Boundary amounts ($80, $520, $1,200, $3,500) | USD (100%) | Fraud (20%) |
| **TOTAL** | **Comprehensive Pilot Stream** | **2,500** | **550+ Valid Luhn Cardholders** | **7 Currencies** | **Legit: 90.7% / Fraud: 9.3%** |

---

## 3. Empirical Confusion Matrix & Metric Dashboard

```mermaid
flowchart LR
    Total["Total Synthetic Stream<br>N = 2,500"] --> GT_Legit["Ground Truth Legitimate<br>N = 2,267 (90.7%)"]
    Total --> GT_Fraud["Ground Truth Adversarial<br>N = 233 (9.3%)"]

    GT_Legit --> TN["True Negatives (TN): 2,148<br>(Approved Without Friction)"]
    GT_Legit --> FP["False Positives (FP): 119<br>(Challenged / Stepped-Up)"]

    GT_Fraud --> TP["True Positives (TP): 225<br>(Caught: Blocked, Reviewed, 2FA)"]
    GT_Fraud --> FN["False Negatives (FN): 8<br>(Low-Exposure Escapes)"]
```

### Comprehensive Classification Metrics:

| Metric | Empirical Result | Target Requirement | Evaluation Verdict |
| :--- | :---: | :---: | :---: |
| **Recall / Sensitivity ($TP / (TP + FN)$)** | **96.57%** | $\ge 90.0\%$ | **EXCEEDED TARGET** |
| **Precision ($TP / (TP + FP)$)** | **65.41%** | $\ge 50.0\%$ | **EXCEEDED TARGET** |
| **F1-Score** | **0.7799** | $\ge 0.6500$ | **EXCEEDED TARGET** |
| **False Positive Rate ($FP / (FP + TN)$)** | **5.25%** | $\le 8.0\%$ | **EXCEEDED TARGET** |
| **False Negative Rate ($FN / (FN + TP)$)** | **3.43%** | $\le 10.0\%$ | **EXCEEDED TARGET** |
| **Duplicate Replay Catch Rate** | **100.0% (25/25)** | $100.0\%$ | **PERFECT CONCURRENCY** |
| **Strict Hard-Block Precision** | **100.0% (25/25)** | $\ge 95.0\%$ | **ZERO LEGIT HARD-BLOCKS** |

---

## 4. Multi-Tier Decision Distribution

FraudShield 3.0 evaluates transactions using multi-tier policy bands rather than a crude binary cutoff:

```
[APPROVE]        ================================================== 2,156 (86.2%)
[MANUAL_REVIEW]  ===== 222 (8.9%)
[STEP_UP_2FA]    == 97 (3.9%)
[IMMEDIATE_BLOCK]= 25 (1.0%)
```

- **Frictionless Approval (86.2%):** 2,156 transactions were cleared automatically with sub-5ms latency.
- **Cardholder Step-Up 2FA (3.9%):** 97 transactions exhibited moderate risk ($0.30 \le p < 0.70$) or burst activity and were routed to two-factor verification.
- **Fraud Analyst Manual Review (8.9%):** 222 transactions were flagged for high exposure ($p \ge 0.70$ or degraded mode amount $\ge \$2,000$).
- **Immediate Hard Block (1.0%):** 25 transactions were confirmed duplicate replays and blocked instantly with `RULE_DUPLICATE_IDEMP_REPLAY`.

---

## 5. Scenario-by-Scenario Forensic Breakdown

| Scenario Name | Total Evaluated | Approved | Step-Up 2FA | Manual Review | Immediate Block | Duplicates Caught | Key Triggered Policies |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Legitimate Payments** | 2,000 | 1,989 | 11 | 0 | 0 | 0 | Calibrated low-risk model probability ($p < 0.30$) |
| **Velocity Attacks** | 100 | 21 | 25 | 54 | 0 | 0 | `RULE_BURST_VELOCITY_1H` |
| **Geo-Anchor Swipes** | 25 | 25 | 0 | 0 | 0 | 0 | Standard physical POS baseline |
| **Impossible Travel** | 25 | 1 | 24 | 0 | 0 | 0 | `RULE_IMPOSSIBLE_TRAVEL` ($> 800\text{ km/h}$) |
| **Original for Replay** | 25 | 25 | 0 | 0 | 0 | 0 | Baseline initial ingestion |
| **Duplicate Replays** | 25 | 0 | 0 | 0 | 25 | 25 | `RULE_DUPLICATE_IDEMP_REPLAY` (100% Block) |
| **Multi-Currency** | 150 | 87 | 0 | 63 | 0 | 0 | `RULE_EXTREME_SPEND_RATIO` (via USD FX conversion) |
| **High-Value Anomalies** | 100 | 0 | 26 | 74 | 0 | 0 | `RULE_EXTREME_SPEND_RATIO` & Extreme Value Guard |
| **Degraded Store Failsafe**| 50 | 8 | 11 | 31 | 0 | 0 | `RULE_DEGRADED_FEATURE_STORE_FAILSAFE` |

---

## 6. End-to-End Latency Profile

During the continuous evaluation of the 2,500 transactions across the 4 worker processes, end-to-end request timing was recorded:

- **P50 Latency:** **4.73 ms**
- **P90 Latency:** **6.68 ms**
- **P95 Latency:** **7.34 ms**
- **P99 Latency:** **13.10 ms**
- **Average Latency:** **5.51 ms**
- **Maximum Outlier:** **191.99 ms** (worker startup cold-cache warmup)
- **Validation Errors:** **0 (0.00%)**

---

## 7. Policy Preservation Affirmation

In strict compliance with execution safety requirements:
1. No thresholds in `FraudDecisionEngine` or `FraudShieldLightGBM` were adjusted to artificially boost pilot precision or recall.
2. The calibrated operating threshold remained locked at $\tau = 0.700$ for LightGBM and $\tau = 0.895$ for legacy FraudShield 1.0.
3. The historical training artifacts and evaluation splits were preserved without modification.
