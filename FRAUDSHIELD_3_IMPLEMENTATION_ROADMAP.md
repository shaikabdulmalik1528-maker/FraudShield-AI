# FraudShield 3.0: 10-Week Implementation Roadmap & Operational Execution Blueprint

**Document Version:** 1.0.0 (Implementation Planning Document)  
**Status:** DRAFT / PROPOSED (STRICT PLANNING ONLY)  
**Author:** Senior Machine Learning Systems Architect & Technical Program Lead  
**Date:** November 17, 2026  
**Target Duration:** 10 Weeks (Phased Agile Sprint Architecture)  
**Deliverable File:** `FRAUDSHIELD_3_IMPLEMENTATION_ROADMAP.md`  

---

## Executive Summary & Program Objectives

This document establishes the official 10-week technical implementation roadmap for **FraudShield 3.0: Architecture Modernization**. The program transitions FraudShield from a legacy PCA-dependent prototype into an enterprise raw-schema transaction intelligence system, while strictly preserving FraudShield 1.0 in a frozen, backwards-compatible operational state.

### Key Program Milestones:
- **Milestone 3A (Weeks 1–2):** Dual-Engine Infrastructure, Hexagonal Schema Adapters & ISO 8583 Ingestion.
- **Milestone 3B (Weeks 3–4):** Streaming Feature Store, Sliding-Window Velocity Aggregations & Preprocessing.
- **Milestone 3C (Weeks 5–6):** Dual Model Training: Supervised LightGBM + Unsupervised ECOD/VAE Anomaly Detection.
- **Milestone 3D (Weeks 7–8):** Out-of-Time Cross-Validation, Probability Meta-Calibration & Gate Auditing.
- **Milestone 3E (Weeks 9–10):** Fast TreeSHAP Explainability, Shadow Deployment & Final Production Readiness.

```
+---------------------------------------------------------------------------------------------------+
|                            FRAUDSHIELD 3.0 IMPLEMENTATION TIMELINE (10 WEEKS)                     |
+---------------------------------------------------------------------------------------------------+
| Week:   W1    W2    W3    W4    W5    W6    W7    W8    W9    W10                                 |
+-------+-----+-----+-----+-----+-----+-----+-----+-----+-----+-----+                               |
| M3A   |===========|                                               | Dual-Engine & Ingestion       |
| M3B   |           |===========|                                   | Streaming Feature Store       |
| M3C   |                       |===========|                       | LightGBM + ECOD Training      |
| M3D   |                                   |===========|           | Calibration & Gate Audits     |
| M3E   |                                               |===========| Shadow Deploy & Governance    |
+---------------------------------------------------------------------------------------------------+
```

---

## Phase-by-Phase Work Breakdown Structure (WBS)

### Phase 1: Dual-Engine Infrastructure & Ingestion Adapters (Weeks 1–2)
**Goal:** Establish the isolated `v3` architecture namespace and build decoupled ingestion adapters for ISO 8583 and raw tabular payment schemas.

#### Detailed Tasks:
1. **Repository & Directory Structure Initialization:**
   - Establish `backend/app/v3/` namespace.
   - Verify that `backend/app/v1/` preserves all legacy PCA code and artifacts without interference.
2. **Canonical Schema Definition:**
   - Implement `CanonicalTransaction` schema in `backend/app/v3/schemas/canonical.py`.
   - Implement tokenization utility (`KmsTokenService`) using HMAC-SHA256 for zero-raw-PAN compliance.
3. **Hexagonal Adapter Layer Implementation:**
   - Author `BaseTransactionAdapter` abstract interface in `backend/app/v3/adapters/base.py`.
   - Implement `Iso8583Adapter` with bitmap parsing for MTI `0100`, `0110`, `0200`, and `0420`.
   - Implement `IeeeCisAdapter` to ingest Kaggle/Vesta tabular records.
   - Implement `GenericJsonAdapter` for modern e-commerce REST payloads.
4. **Unit & Contract Testing Suite:**
   - Author contract tests asserting identical canonical outputs across multiple payload variants.

#### Exit Gate & Acceptance Criteria (Milestone 3A):
- [ ] 100% of unit tests pass for ISO 8583 and IEEE-CIS adapters.
- [ ] Ingestion throughput exceeds $5,000$ payloads/sec with zero memory leaks.
- [ ] Security audit confirms zero plaintext PAN or CVV elements written to disk or logs.
- [ ] Legacy FraudShield 1.0 test suite passes 20/20 with zero modifications.

---

### Phase 2: Streaming Feature Store & Behavioral Velocity (Weeks 3–4)
**Goal:** Construct real-time Redis-backed sliding-window state aggregators and behavioral feature transformers.

#### Detailed Tasks:
1. **Redis Sliding-Window Feature Store:**
   - Deploy high-performance Redis cluster configuration in Docker environment.
   - Implement rolling card-level velocity aggregators: $N_{\text{tx}, 1\text{h}}$, $N_{\text{tx}, 24\text{h}}$, and spend sum in rolling $24\text{h}$.
   - Implement merchant-level risk aggregators: distinct card count in $1\text{h}$, authorization decline rate in rolling $1\text{h}$.
2. **Contextual & Geo-Spatial Feature Engineering:**
   - Implement haversine-based impossible travel speed calculation: $\text{Speed} = \frac{\text{Distance}}{\Delta t}$.
   - Implement cyclical temporal encoders ($\sin / \cos$ for hour-of-day and day-of-week).
   - Implement ratio and $z$-score transforms comparing current amount to cardholder's 30-day baseline.
3. **Batch-to-Stream Parity Pipeline:**
   - Create unified transformer `v3/feature_store/pipeline.py` that computes identical features during offline batch training and online real-time inference.

#### Exit Gate & Acceptance Criteria (Milestone 3B):
- [ ] Real-time feature retrieval latency is $< 4.0\text{ms}$ at P99 under load.
- [ ] Batch-to-online feature parity test verifies $< 10^{-6}$ numerical discrepancy across 50,000 transactions.
- [ ] Feature store handles out-of-order and network-delayed events without race conditions.

---

### Phase 3: Dual Model Architecture Training & Optimization (Weeks 5–6)
**Goal:** Train next-generation supervised LightGBM and unsupervised ECOD/VAE anomaly detection models on the raw-schema benchmark.

#### Detailed Tasks:
1. **Data Pipeline & Temporal Split Setup:**
   - Ingest IEEE-CIS Fraud Detection dataset ($1,097,231$ transactions).
   - Enforce purged, embargoed time-series split: Months 1–4 (Train), Month 5 (Validation), Month 6 (Held-Out Out-of-Time Test).
2. **Supervised Model Training (LightGBM):**
   - Configure native categorical splits on `card_bin`, `mcc`, `channel`, and `merchant_country`.
   - Enforce monotonic constraints on velocity and impossible travel speed.
   - Execute Bayesian hyperparameter optimization (Optuna) minimizing binary cross-entropy on validation fold.
3. **Unsupervised Anomaly Model Training:**
   - Fit Empirical Cumulative Distribution (ECOD) detector on continuous feature dimensions.
   - Train Variational Autoencoder (VAE) on verified legitimate transactions ($y = 0$) to learn the normal spending manifold.
4. **Model Checksum & Artifact Serialization:**
   - Save candidate artifacts to `backend/artifacts/v3/` with SHA-256 integrity manifests.

#### Exit Gate & Acceptance Criteria (Milestone 3C):
- [ ] LightGBM achieves validation PR-AUC $\ge 0.860$ and ROC-AUC $\ge 0.940$.
- [ ] Single-thread inference latency for LightGBM is $< 3.5\text{ms}$ at P99.
- [ ] ECOD anomaly score distribution clearly separates injected synthetic zero-day perturbations.

---

### Phase 4: Calibration, Out-of-Time Evaluation & Milestone Gates (Weeks 7–8)
**Goal:** Fit the nested logistic meta-calibrator, establish calibrated risk action tiers, and execute pre-registered statistical gate audits.

#### Detailed Tasks:
1. **Out-of-Fold Probability Calibration:**
   - Generate out-of-fold predictions using 5-fold purged time-series cross-validation.
   - Fit $L_2$-regularized Logistic Meta-Calibrator:
     $$P_{\text{cal}} = \sigma\left( w_0 + w_1 \cdot \text{logit}(P_{\text{raw}}) + w_2 \cdot S_{\text{anom}} + w_3 \cdot \ln(1 + \text{Velocity}) \right)$$
   - Verify Quantile ECE $\le 0.0050$ and Brier Score $\le 0.0010$.
2. **Threshold & Action Tier Mapping:**
   - Map continuous calibrated probabilities into operational action tiers:
     - `LOW`: $[0.0, 30.0)$
     - `FRICTION`: $[30.0, 50.0)$
     - `MEDIUM` (Operational Review Queue): $[50.0, 75.0)$
     - `HIGH`: $[75.0, 100.0]$
3. **Statistical Significance & Superiority Testing:**
   - Execute paired stratified bootstrap ($B = 10,000$ replicates) comparing FraudShield 3.0 against baseline benchmarks.
   - Run separated McNemar tests for confirmed fraud ($y = 1$) and legitimate ($y = 0$) transactions at $\alpha = 0.01$.
   - Evaluate provisional non-inferiority margin $\delta_{\text{recall}} = 0.030$.

#### Exit Gate & Acceptance Criteria (Milestone 3D):
- [ ] Calibrated candidate satisfies all pre-registered acceptance gates on held-out Out-of-Time test window.
- [ ] Legitimate McNemar test rejects $H_0$ ($p < 0.01$) confirming significant false alarm reduction.
- [ ] Fraud McNemar test confirms zero statistically significant fraud degradation.
- [ ] Comprehensive audit report generated at `experiments/fraudshield_3/EVALUATION_REPORT.md`.

---

### Phase 5: Fast Explainability, Monitoring & Shadow Deployment (Weeks 9–10)
**Goal:** Integrate TreeSHAP real-time explainability, drift detection telemetry, and deploy FraudShield 3.0 in dark shadow mode alongside v1.

#### Detailed Tasks:
1. **Real-Time TreeSHAP Engine:**
   - Integrate C-optimized TreeSHAP calculating local feature importances in $< 4.0\text{ms}$.
   - Build rule-based reason code translator emitting standardized analyst narratives.
2. **Production Telemetry & Drift Monitoring:**
   - Implement Prometheus metrics exporting PSI, KS statistics, and rolling fraud rates.
   - Configure Grafana alert dashboards for distribution drift ($\text{PSI} \ge 0.10$).
3. **Dark Shadow Deployment Integration:**
   - Deploy dual routing proxy in FastAPI: incoming requests evaluate both v1 and v3 concurrently.
   - In shadow mode, v1 returns live customer decisions while v3 logs predictions asynchronously for live parity comparison.
4. **Analyst Review Dashboard Updates:**
   - Update React dashboard to render interactive SHAP waterfall force plots and review queue workflows.

#### Exit Gate & Acceptance Criteria (Milestone 3E):
- [ ] End-to-end P99 response time is $< 22.0\text{ms}$ under 2,000 concurrent virtual users.
- [ ] Shadow mode operates over 7 consecutive days with zero latency degradation to v1 traffic.
- [ ] Live telemetry verifies $< 0.01$ PSI drift across live shadow traffic.
- [ ] Final compliance, PCI-DSS, and model governance audit signed off.

---

## Resource Allocation & Team Composition

```
+---------------------------------------------------------------------------------------------------+
|                                 STAFFING & RESOURCE ALLOCATION MATRIX                             |
+---------------------------------------------------------------------------------------------------+
| Role                              | Headcount | Primary Responsibilities                          |
+-----------------------------------+-----------+---------------------------------------------------+
| Lead ML Systems Architect (Lead)  | 1.0 FTE   | Architecture governance, calibration & gate audit |
| Senior ML Engineer (Models)       | 1.0 FTE   | LightGBM, ECOD, VAE training & feature pipeline   |
| Senior Backend Engineer (Systems) | 1.0 FTE   | FastAPI, Redis sliding windows & ISO 8583 parser  |
| Frontend / Fullstack Engineer     | 0.5 FTE   | React dashboard, SHAP force visualizer, WebSockets|
| QA & Compliance Specialist        | 0.5 FTE   | PCI-DSS audit, test automation & shadow validation|
+---------------------------------------------------------------------------------------------------+
```

---

## Critical Path & Dependency Graph

```
[M3A: Ingestion & Adapters] 
       |
       v
[M3B: Redis Feature Store] 
       |
       v
[M3C: LightGBM / ECOD Training] 
       |
       v
[M3D: Calibration & Gates] 
       |
       v
[M3E: Shadow Deployment & Sign-off]
```

- **Critical Path Bottleneck:** Phase 2 (Feature Store) $\rightarrow$ Phase 3 (Model Training). Model training cannot begin until the offline batch feature pipeline perfectly mirrors the online streaming feature store.
- **Buffer Allocation:** A 2-week contingency buffer is built into the 10-week schedule (extensible to 12 weeks) to accommodate edge-case data pipeline reconciliations.

---

## Risk Management & Mitigation Matrix

```
+-----------------------------------------------------------------------------------------------------------------------------------+
|                                                  RISK MANAGEMENT & MITIGATION MATRIX                                              |
+-----------------------------------------------------------------------------------------------------------------------------------+
| Risk Description                      | Severity | Likelihood | Mitigation Strategy                                               |
+---------------------------------------+----------+------------+-------------------------------------------------------------------+
| 1. Redis sliding-window latency spike | High     | Medium     | Use Redis memory-optimized pipelines, local L1 cache & cluster    |
| 2. Concept drift on real-time stream  | High     | High       | Automated PSI monitoring with 7-day scheduled retraining workflow |
| 3. High cardinality categorical lag   | Medium   | Medium     | Integer frequency encoding + LightGBM native Fisher split grouping|
| 4. Regression in legacy v1 service    | Critical | Very Low   | Complete directory and runtime process isolation between v1 & v3  |
| 5. PCI-DSS compliance failure         | Critical | Very Low   | Salted HMAC-SHA256 tokenization; zero cleartext PAN written to disk|
+-----------------------------------------------------------------------------------------------------------------------------------+
```

---

## Canary Rollout & Shadow Deployment Protocol

When implementation is approved, FraudShield 3.0 will transition into production via a 4-stage phased rollout:

1. **Stage 1 — Dark Shadow Mode (Weeks 9–10):**
   - $100\%$ of production traffic routed to FraudShield 1.0 (authoritative).
   - $100\%$ of production traffic replicated asynchronously to FraudShield 3.0 (shadow).
   - Zero customer impact; predictions compared offline to measure operational divergence.
2. **Stage 2 — Low-Risk Pilot Canary (Week 11):**
   - $5\%$ of live traffic routed to FraudShield 3.0 for authoritative decisions on low-risk transaction channels (e.g. domestic debit POS chip).
   - $95\%$ retained on FraudShield 1.0.
   - P99 latency and false alarm rates monitored 24/7.
3. **Stage 3 — Graduated Ramp-Up (Week 12):**
   - Authoritative traffic shifted: $5\% \rightarrow 25\% \rightarrow 50\% \rightarrow 100\%$ over 14 days, conditioned on zero safety gate breaches.
4. **Stage 4 — Full Production Cutover & v1 Deprecation Notice:**
   - FraudShield 3.0 becomes primary production system.
   - FraudShield 1.0 retained in frozen read-only status for historical auditing and backward-compatible v1 API clients.

---

## Strict Execution Boundaries & Compliance Confirmation

- **No Code Modifications:** Existing files in `backend/app/`, `backend/artifacts/`, and `data/` remain 100% frozen.
- **No Access to Quarantined Split:** `data/raw/creditcard.csv` test indices remain completely untouched.
- **Planning Only:** This roadmap is a technical design and scheduling blueprint. Zero implementation commands, model training, or deployment actions will occur without explicit authorization.
