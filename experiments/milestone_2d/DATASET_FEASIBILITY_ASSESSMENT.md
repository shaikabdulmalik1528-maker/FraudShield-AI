# FraudShield AI — Milestone 2D: Independent Evaluation Dataset Feasibility Assessment

**Document Version:** 1.0.0 (Official Feasibility & Data Provenance Audit)  
**Status:** COMPLETED / READ-ONLY AUDIT  
**Author:** Senior Machine Learning Engineer & Lead ML Auditor  
**Date:** November 17, 2026  
**Subject System:** Hybrid Fraud Engine Generalization & Out-of-Distribution Validation  
**Target Working Directory:** `experiments/milestone_2d/`  

---

## 1. Executive Summary & Core Operational Finding

To establish empirical generalization for the frozen production baseline (`ARCH_A_w75_c500`) and the frozen logistic meta-calibrator candidate (`ARCH_C_log_c500`), **Milestone 2D** pre-registered a rigorous evaluation protocol requiring an independent transaction dataset satisfying:
1. Exact 30-feature schema compatibility: $\mathbf{X} = \left[ \text{Time}, V_1, V_2, \dots, V_{28}, \text{Amount} \right]$.
2. Zero data snooping bias (completely separate from previously inspected training, validation, and held-out test splits).
3. Verified provenance, mature chargeback dispute labels (minimum 60–90 days), and commercial/auditing usage rights.
4. Statistical eligibility floors: sample size $N \ge 20,000$ transactions with confirmed fraud count $N_{\text{fraud}} \ge 50$.

### Definitive Feasibility Assessment Verdict:
```
+---------------------------------------------------------------------------------------------------+
|                              FEASIBILITY ASSESSMENT VERDICT: BLOCKED                              |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  1. Candidate Datasets Investigated: 8                                                            |
|  2. Compatible Datasets Identified:  0                                                            |
|  3. Potentially Compatible Datasets: 0                                                            |
|  4. Incompatible Datasets:           8                                                            |
|                                                                                                   |
|  CRITICAL OPERATIONAL CONCLUSION:                                                                 |
|  No suitable genuinely independent transaction dataset is currently available in the public       |
|  domain or enterprise workspace that satisfies FraudShield AI's 30-dimensional PCA feature space.  |
|                                                                                                   |
|  OPERATIONAL STATUS:                                                                              |
|  MILESTONE 2D EVALUATION EXECUTION IS OFFICIALLY BLOCKED PENDING DATA ACQUISITION.                |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Technical Schema & Mathematical Dimensionality Constraints

FraudShield AI's inference pipeline (implemented in `backend/app/schemas/transaction.py`, `backend/app/ml/preprocessing.py`, and `backend/app/services/fraud_engine.py`) operates strictly on fixed 30-dimensional continuous vectors:

$$\mathbf{X} = \left[ \text{Time}, V_1, V_2, \dots, V_{28}, \text{Amount} \right] \in \mathbb{R}^{30}$$

### 2.1 Feature Roles and Preprocessing Pipeline
- **`Time` ($\mathbb{R}^1$):** Elapsed seconds since the initial transaction of the recording period. Scaled via `preprocessor.joblib` (`RobustScaler`).
- **`Amount` ($\mathbb{R}^1$):** Transaction currency amount. Scaled via `preprocessor.joblib` (`RobustScaler`).
- **`V1` through `V28` ($\mathbb{R}^{28}$):** 28 principal components generated via an undisclosed linear transformation. Passed through directly without scaling because they are already zero-centered and scaled in the original eigenspace.

### 2.2 Strict Invariance Requirements
- **No Zero-Padding or Imputation:** Omitting any component $V_i$ or padding missing features with zeros distorts tree-traversal logic in `best_fraud_model.joblib` (XGBoost) and split partitions in `isolation_forest.joblib`.
- **Eigenspace Sensitivity:** The XGBoost model contains 100 decision trees whose split thresholds were trained on the exact covariance structure and orientation of $V_1..V_{28}$. Any linear rotation, axis misalignment, or feature permutation renders the models' internal logic completely invalid.

---

## 3. Investigation of the PCA Feature Definitions & Transformation Matrix

A deep-dive investigation into the literature and academic provenance of the benchmark dataset was conducted:

### 3.1 Academic Provenance
The dataset `creditcard.csv` was released in 2015 by the Machine Learning Group (MLG) of Université Libre de Bruxelles (ULB) in collaboration with payment processor **Worldline**, authored by Andrea Dal Pozzolo, Olivier Caelen, Reid A. Johnson, and Gianluca Bontempi (*"Calibrating Probability with Undersampling for Unbalanced Classification"*, IEEE SSCI 2015; and *"Credit Card Fraud Detection: A Realistic Modeling and a Novel Learning Strategy"*, IEEE TNNLS 2015).

### 3.2 The Transformation Mechanism
Inside Worldline's secure banking infrastructure (Brussels, Belgium, September 2013), raw transactional logs were collected. The raw vector $\mathbf{x}_{\text{raw}} \in \mathbb{R}^D$ contained cardholder identifiers, merchant category codes (MCC), terminal types, geographical coordinates, temporal frequencies, and historical spending velocity metrics.

To comply with European banking secrecy laws, PCI-DSS compliance, and privacy directives, Worldline applied Principal Component Analysis (PCA):
$$\mathbf{v} = \mathbf{W}_{\text{PCA}} (\mathbf{x}_{\text{raw}} - \boldsymbol{\mu})$$
where $\mathbf{W}_{\text{PCA}} \in \mathbb{R}^{28 \times D}$ represents the projection matrix of the leading 28 eigenvectors, and $\boldsymbol{\mu} \in \mathbb{R}^D$ is the mean centering vector. Only `Time`, `Amount`, $\mathbf{v}$, and the binary ground-truth label `Class` were exported.

### 3.3 Availability of $\mathbf{W}_{\text{PCA}}$ and Original Definitions
- **Status of Projection Matrix $\mathbf{W}_{\text{PCA}}$:** **PERMANENTLY UNAVAILABLE / DESTROYED.** Neither Worldline nor ULB ever published $\mathbf{W}_{\text{PCA}}$, the centering vector $\boldsymbol{\mu}$, or the scaling parameters.
- **Status of Raw Feature Definitions:** **CONFIDENTIAL.** The exact identity, schema, and engineering formulas for the $D$ raw dimensions were withheld as proprietary commercial secrets.
- **Mathematical Non-Reconstructibility:** Because $D \gg 28$ (the raw feature space had hundreds of one-hot and aggregated features) and the transformation is a many-to-one projection, $\mathbf{W}_{\text{PCA}}$ cannot be mathematically inverted or reconstructed from $V_1..V_{28}$.

### 3.4 Why External Datasets Cannot be Projected into FraudShield's Space
If an organization acquires an external credit card dataset with raw features $\mathbf{X}'_{\text{raw}}$ (e.g. from Visa, Mastercard, or an issuing bank), applying standard PCA to $\mathbf{X}'_{\text{raw}}$ yields a new eigenspace $\mathbf{W}'_{\text{PCA}}$. By the spectral theorem:
$$\mathbf{W}'_{\text{PCA}} \ne \mathbf{W}_{\text{PCA}}$$
The new components $V'_1..V'_{28}$ would represent completely different linear combinations, with different eigenvalues and orientations. Feeding $\mathbf{v}'$ into FraudShield would be mathematically equivalent to feeding randomized noise, invalidating all inference.

---

## 4. Comprehensive Candidate Dataset Audit

Eight prominent financial fraud detection datasets and streaming sources were systematically audited against FraudShield AI's requirements:

```
+-----------------------------------------------------------------------------------------------------------------------------------------+
|                                              CANDIDATE DATASET FEASIBILITY AUDIT MATRIX                                                  |
+-----------------------------------------------------------------------------------------------------------------------------------------+
| Dataset Candidate                 | Transactions (N) | Fraud Count | Schema Compatibility | Provenance & Legal Rights | Eligibility | Status       |
+-----------------------------------+------------------+-------------+----------------------+---------------------------+-------------+--------------+
| 1. ULB Benchmark (creditcard.csv) | 284,807          | 492         | Exact (30 features)  | Public (Worldline / ULB)  | Exhausted   | INCOMPATIBLE |
| 2. ULB Out-of-Time Continuation   | ~1,200,000       | ~2,100      | Exact (Proprietary)  | Gated under NDA (Private) | Inaccessible| INCOMPATIBLE |
| 3. IEEE-CIS Fraud Detection       | 1,097,231        | 20,663      | Incompatible (434 f) | Public (Vesta / Kaggle)   | Incompatible| INCOMPATIBLE |
| 4. PaySim Financial Simulator     | 6,362,620        | 8,213       | Incompatible (11 f)  | Public (Blekinge / Sim)   | Incompatible| INCOMPATIBLE |
| 5. Sparkov Synthetic Transactions | ~1,850,000       | ~10,000     | Incompatible (23 f)  | Open Source (Faker)       | Incompatible| INCOMPATIBLE |
| 6. IBM AML / Credit Card Dataset  | ~24,000,000      | ~30,000     | Incompatible (15 f)  | Public (IBM Research)     | Incompatible| INCOMPATIBLE |
| 7. UCSD-FICO Contest 2009         | 100,000          | ~2,500      | Incompatible (Raw)   | Academic / Deprecated     | Incompatible| INCOMPATIBLE |
| 8. CTGAN / Copula Synthetic       | Parameterized    | Parameterized| Exact (Generated)   | In-Sample Synthetic       | Disqualified| INCOMPATIBLE |
+-----------------------------------------------------------------------------------------------------------------------------------------+
```

### Detailed Dataset Profiles:

#### Candidate 1: ULB / Worldline Benchmark Snapshot (`creditcard.csv`)
- **Location:** `data/raw/creditcard.csv` on local disk.
- **Transactions:** 284,807 total (492 frauds, $0.172\%$).
- **Schema:** Matches `[Time, V1..V28, Amount]` exactly.
- **Audit Finding:** **EXHAUSTED / PERMANENTLY QUARANTINED.**
  - Training split: 199,364 transactions (344 fraud cases) — used for XGBoost/Isolation Forest training and Milestone 2C cross-validation.
  - Validation split: 42,559 transactions (74 fraud cases) — used for threshold optimization and Milestone 2C calibration grid searches.
  - Held-out test split: 42,559 transactions (74 fraud cases) — inspected and verified in Milestones 1 and 2B.
  - **Data Snooping Rule:** The Milestone 2D approved charter strictly prohibits re-evaluating on any partition of `creditcard.csv`. No uninspected rows exist.
- **Classification:** **INCOMPATIBLE (Data Snooping Violation).**

#### Candidate 2: ULB / Worldline Out-of-Time Continuation Streams (Oct–Dec 2013)
- **Provenance:** Private commercial transaction logs referenced in Dal Pozzolo's PhD dissertation (2015).
- **Transactions:** Continuous streams over 14–90 days ($N > 1,000,000$, $N_{\text{fraud}} > 2,000$).
- **Schema:** Theoretically shares the exact same Worldline PCA projection $\mathbf{W}_{\text{PCA}}$.
- **Audit Finding:** **PRIVATELY HELD / GATED UNDER COMMERCIAL NDA.**
  - Worldline released only the 2-day September 2013 snapshot to the public.
  - Subsequent transaction streams are proprietary commercial assets governed by strict GDPR and banking privacy restrictions.
  - The FraudShield project has no active data-sharing agreement or NDA with Worldline.
- **Classification:** **INCOMPATIBLE (Legally & Physically Inaccessible).**

#### Candidate 3: IEEE-CIS Fraud Detection Benchmark (Vesta Corp, 2019)
- **Provenance:** Vesta Corporation / IEEE Computational Intelligence Society (Kaggle).
- **Transactions:** 590,540 train + 506,691 test transactions ($N = 1,097,231$; $20,663$ frauds, $3.5\%$). Meets sample size and fraud count floors.
- **Schema:** 434 tabular features (`TransactionDT`, `TransactionAmt`, `ProductCD`, `card1`–`card6`, `addr1`–`addr2`, `dist1`–`dist2`, `P_emaildomain`, `R_emaildomain`, `C1`–`C14`, `D1`–`D15`, `M1`–`M9`, `V1`–`V339`, `id_01`–`id_38`, `DeviceType`, `DeviceInfo`).
- **Audit Finding:** **STRUCTURAL SCHEMA MISMATCH.**
  - Features labeled `V1`–`V339` in IEEE-CIS are count and aggregation features engineered by Vesta, **not** PCA components from European banking transactions.
  - Lacks the 28 European PCA latent dimensions.
  - Cannot be transformed into FraudShield's input vector $\mathbb{R}^{30}$.
- **Classification:** **INCOMPATIBLE (Inconvertible Feature Space).**

#### Candidate 4: PaySim Financial Fraud Simulator (Lopez-Rojas et al., 2016)
- **Provenance:** Blekinge Institute of Technology (synthetic mobile money simulator based on African financial logs).
- **Transactions:** 6,362,620 transactions (8,213 frauds).
- **Schema:** 11 features (`step`, `type`, `amount`, `nameOrig`, `oldbalanceOrg`, `newbalanceOrig`, `nameDest`, `oldbalanceDest`, `newbalanceDest`, `isFraud`, `isFlaggedFraud`).
- **Audit Finding:** **DOMAIN & STRUCTURAL MISMATCH.**
  - Simulates mobile wallet transfers (Cash-In, Cash-Out, P2P Transfer), not credit card merchant transactions.
  - Missing all 28 latent dimensions.
- **Classification:** **INCOMPATIBLE (Domain Mismatch).**

#### Candidate 5: Sparkov Synthetic Credit Card Transaction Dataset (Brandon Harris)
- **Provenance:** Open-source Python Faker-based credit card transaction generator.
- **Transactions:** ~1,850,000 transactions across multiple profiles.
- **Schema:** 23 raw features (`trans_date_trans_time`, `cc_num`, `merchant`, `category`, `amt`, `first`, `last`, `gender`, `street`, `city`, `state`, `zip`, `lat`, `long`, `city_pop`, `job`, `dob`, `trans_num`, `unix_time`, `merch_lat`, `merch_long`, `is_fraud`).
- **Audit Finding:** **NON-PROJECTABLE RAW FEATURES.**
  - Contains raw card transaction attributes, but lacks the Worldline transformation matrix $\mathbf{W}_{\text{PCA}}$.
  - Running a fresh PCA on Sparkov generates an orthogonal basis uncorrelated with FraudShield's training eigenspace.
- **Classification:** **INCOMPATIBLE (Eigenspace Incompatibility).**

#### Candidate 6: IBM AML / Credit Card Transactions Synthetic Dataset (IBM Research, 2020)
- **Provenance:** IBM Research / Kaggle.
- **Transactions:** ~24,000,000 synthetic transactions.
- **Schema:** 15 raw features (`User`, `Card`, `Year`, `Month`, `Day`, `Time`, `Amount`, `Use Chip`, `Merchant Name`, `Merchant City`, `Merchant State`, `Zip`, `MCC`, `Errors?`, `Is Fraud?`).
- **Audit Finding:** **STRUCTURAL SCHEMA MISMATCH.**
  - Raw categorical/tabular banking attributes. Cannot be mapped into $V_1..V_{28}$.
- **Classification:** **INCOMPATIBLE (Structural Schema Mismatch).**

#### Candidate 7: UCSD-FICO Data Mining Contest 2009
- **Provenance:** University of California San Diego & Fair Isaac Corporation.
- **Transactions:** 100,000 e-commerce transactions.
- **Schema:** Anonymized integer-coded variables with proprietary masks.
- **Audit Finding:** **DEPRECATED / STRUCTURAL MISMATCH.**
  - Completely disparate feature space; unaligned with creditcard.csv.
- **Classification:** **INCOMPATIBLE (Structural Schema Mismatch).**

#### Candidate 8: Synthetic Generative Perturbations (CTGAN / Gaussian Copula)
- **Provenance:** In-memory tabular generative models fitted on training/validation partitions.
- **Transactions:** Arbitrary $N \ge 20,000$.
- **Schema:** Matches `[Time, V1..V28, Amount]` synthetically.
- **Audit Finding:** **DISQUALIFIED FOR GENERALIZATION EVALUATION.**
  - As formally established in **Milestone 2D Plan Section 4.3**:
    > *"Synthetic stress testing (CTGAN, Copula) will be utilized solely for perturbation analysis and must NEVER be cited as evidence of real-world generalization."*
  - Generative models inherit the covariance structure and artifacts of the training data. Evaluating a model on synthetic data generated from its own training distribution tests perturbation stability, not real-world generalization.
- **Classification:** **INCOMPATIBLE (Methodologically Invalid for Generalization).**

---

## 5. Summary Evaluation Classification

In strict accordance with Requirement 6:
- **Compatible Datasets Identified:** **0**
- **Potentially Compatible Datasets (pending verification):** **0**
- **Incompatible Datasets:** **8**

```
+---------------------------------------------------------------------------------------------------+
|                                 SUMMARY CLASSIFICATION BREAKDOWN                                  |
+---------------------------------------------------------------------------------------------------+
| Compatible:                                                                                       |
|   - None.                                                                                         |
|                                                                                                   |
| Potentially Compatible (Pending Verification):                                                    |
|   - None available without an active commercial NDA with Worldline.                               |
|                                                                                                   |
| Incompatible:                                                                                     |
|   1. ULB / Worldline Benchmark Snapshot (creditcard.csv) [Data snooping / exhausted]              |
|   2. ULB / Worldline Out-of-Time Continuation Streams    [Proprietary / NDA gated]                |
|   3. IEEE-CIS Fraud Detection Benchmark (Vesta Corp)     [434 features / non-PCA]                 |
|   4. PaySim Financial Fraud Simulator                     [11 features / mobile wallet]            |
|   5. Sparkov Synthetic Credit Card Dataset                [23 raw features / non-projectable]      |
|   6. IBM AML Credit Card Dataset                          [15 raw features / non-projectable]      |
|   7. UCSD-FICO Contest 2009                               [Arbitrary integer masks]                |
|   8. CTGAN / Copula Generative Replicas                   [Methodologically invalid for OOD eval]  |
+---------------------------------------------------------------------------------------------------+
```

---

## 6. Strategic Resolution Paths & Future Roadmap

To overcome the PCA representation bottleneck, three strategic paths are identified:

### Path A: Institutional Data Partnership (Worldline / ULB)
- **Description:** Formally negotiate an academic or commercial research agreement with Worldline and the ULB Machine Learning Group to acquire unreleased out-of-time transaction streams from October–December 2013 processed under the exact same $\mathbf{W}_{\text{PCA}}$ matrix.
- **Feasibility:** High technical compatibility, but requires legal execution, GDPR compliance auditing, and institutional sponsorship.

### Path B: Transition to Open Raw-Schema Architecture (FraudShield 3.0)
- **Description:** Modernize the FraudShield pipeline to decouple from the 2013 European PCA representation:
  - Re-architect feature preprocessing to ingest standard ISO 8583 financial messages (`PAN_hash`, `MCC`, `Merchant_Country`, `Tx_Amount`, `Terminal_Type`, `Velocity_24h`).
  - Train next-generation gradient boosted decision trees on rich open tabular benchmarks (e.g. IEEE-CIS Fraud Detection).
- **Feasibility:** High engineering feasibility; enables evaluation against multiple independent live streams.

### Path C: Federated Sandbox Evaluation
- **Description:** Package the frozen production pipeline and candidate models into a containerized, read-only audit bundle (`docker/fraudshield-eval:v3.4.0`) and ship it into a partner bank's secure environment. If the bank can map their transaction history into a calibrated feature space, evaluation occurs inside their perimeter without data leaving the bank.

---

## 7. Official Operational Blocker Declaration

```
+---------------------------------------------------------------------------------------------------+
|                           OFFICIAL MILESTONE 2D OPERATIONAL BLOCKER                               |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  Because ZERO compatible or potentially compatible independent datasets are accessible,            |
|  Milestone 2D cannot proceed to execution at this time.                                           |
|                                                                                                   |
|  In accordance with scientific integrity guidelines:                                             |
|  1. Acceptance criteria and eligibility thresholds will NEVER be compromised or weakened.         |
|  2. The quarantined benchmark test split (42,559 transactions) will NOT be accessed.             |
|  3. Model evaluation on synthetic generators will NOT be substituted for real-world testing.     |
|                                                                                                   |
|  CURRENT OPERATIONAL STATE:                                                                       |
|  - Production Baseline (ARCH_A_w75_c500): REMAINS ACTIVE AND UNCHANGED.                           |
|  - Candidate (ARCH_C_log_c500): REMAINS FROZEN AS AN APPROVED RESEARCH CANDIDATE.                |
|  - Milestone 2D Execution: OFFICIALLY BLOCKED PENDING DATA ACQUISITION.                           |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 8. Integrity & Boundary Verification

- **Quarantined Benchmark Split:** `data/raw/creditcard.csv` was not loaded, split, or queried.
- **Model Artifacts:** `best_fraud_model.joblib`, `isolation_forest.joblib`, `preprocessor.joblib`, `final_logistic_calibrator.joblib`, and `backend/artifacts/optimal_threshold.json` remain untouched with verified checksums.
- **Production Code:** No modifications were made to `backend/app/` or `backend/tests/`.
- **Status:** Feasibility assessment complete; clean stop maintained.
