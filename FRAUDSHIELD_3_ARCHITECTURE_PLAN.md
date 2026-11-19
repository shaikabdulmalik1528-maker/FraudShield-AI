# FraudShield 3.0: Next-Generation Fraud Detection Engine Architecture Plan

**Document Version:** 3.0.0-DRAFT (Strategic Planning Document)  
**Status:** DRAFT / PROPOSED (STRICT PLANNING ONLY)  
**Author:** Senior Machine Learning Systems Architect & Lead AI Auditor  
**Date:** November 17, 2026  
**Target Systems:** Dual-Engine FraudShield Infrastructure (Preserved v1.0 + Modernized v3.0)  
**Deliverable File:** `FRAUDSHIELD_3_ARCHITECTURE_PLAN.md`  

---

## Executive Summary & Strategic Rationale

In **Milestones 1 through 2D**, the FraudShield AI project demonstrated that while the 2013 European banking benchmark model achieved competitive in-sample validation performance ($F_1 = 0.828$, calibrated false alarm reduction $> 85\%$), the system is fundamentally constrained by an insurmountable data barrier: its 28 latent features ($V_1$ through $V_{28}$) were produced via a proprietary Worldline Principal Component Analysis (PCA) projection matrix $\mathbf{W}_{\text{PCA}}$ that was destroyed/withheld under European banking secrecy laws. Consequently, **no external raw transaction dataset can be projected into this latent space**, permanently blocking external out-of-distribution evaluation and enterprise production scaling.

**FraudShield 3.0** represents a comprehensive architectural modernization that transitions the platform from a closed, PCA-dependent research benchmark into an **enterprise-grade, raw-schema transaction intelligence system**.

### Key Architectural Pillars of FraudShield 3.0:
1. **Zero-Touch Preservation of FraudShield 1.0:** The legacy PCA pipeline remains 100% frozen, versioned under `/api/v1/`, ensuring zero regression in existing capabilities.
2. **Hexagonal Schema Adapter Architecture:** Decoupled ingestion supporting ISO 8583 financial messages, IEEE-CIS payment transactions, and open e-commerce schemas.
3. **Real-Time Streaming Feature Store:** Sliding-window behavioral aggregations (velocity, cardholder profile deviations, impossible travel speed).
4. **Modern Gradient Boosting + Deep Anomaly Detection:** LightGBM / CatBoost native categorical handling combined with Empirical Cumulative Distribution (ECOD) and Variational Autoencoder (VAE) anomaly detectors.
5. **Calibrated Multi-Tier Risk Scoring:** Continuous probability calibration mapping directly into enterprise action bands (Low, Friction/Step-up, Manual Review Queue, Immediate Block).
6. **Leakage-Safe Out-of-Time (OOT) Validation:** Purged, embargoed temporal splits pre-registering paired bootstrap and separated McNemar statistical gates.
7. **Sub-25ms Production SLA & Sub-5ms TreeSHAP Explainability:** Fast inference with transparent reason codes for fraud review analysts.

```
+---------------------------------------------------------------------------------------------------+
|                        FRAUDSHIELD 3.0 HIGH-LEVEL SYSTEM ARCHITECTURE                             |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|  [ INGESTION LAYER ]                                                                              |
|    +------------------------+  +--------------------------+  +-------------------------------+    |
|    | ISO 8583 Acquirer Feed |  | IEEE-CIS Tabular Streams |  | E-Commerce REST API Payloads  |    |
|    +------------------------+  +--------------------------+  +-------------------------------+    |
|                 |                            |                               |                    |
|                 +----------------------------+-------------------------------+                    |
|                                              |                                                    |
|                                              v                                                    |
|  [ ADAPTER & CANONICALIZATION LAYER ] (Hexagonal Architecture)                                    |
|    +-----------------------------------------------------------------------------------------+    |
|    | BaseTransactionAdapter -> CanonicalTransaction (Tokenized PAN, MCC, Geo, Amount, UTC)  |    |
|    +-----------------------------------------------------------------------------------------+    |
|                                              |                                                    |
|                                              v                                                    |
|  [ FEATURE STORE & STREAM ENGINE ]                                                                |
|    +-----------------------------------------------------------------------------------------+    |
|    | Redis Sliding Windows: 1h/24h/7d Card Velocity, Merchant Hopping, Impossible Travel,     |    |
|    | Amount Ratios, Out-of-Fold Target Encodings, Cyclical Temporal Features                 |    |
|    +-----------------------------------------------------------------------------------------+    |
|                                              |                                                    |
|                                              v                                                    |
|  [ DUAL INFERENCE ENGINE ]                                                                        |
|    +-------------------------------------+     +---------------------------------------------+    |
|    | Supervised Tree (LightGBM/CatBoost) |     | Unsupervised Anomaly (ECOD + VAE / Deep SVDD|    |
|    | Outputs: P_raw(Fraud | X)           |     | Outputs: S_anomaly(X)                       |    |
|    +-------------------------------------+     +---------------------------------------------+    |
|                       \                                       /                                   |
|                        \                                     /                                    |
|                         v                                   v                                     |
|  [ META-CALIBRATOR & RISK SCORER ]                                                                |
|    +-----------------------------------------------------------------------------------------+    |
|    | Nested Logistic Meta-Calibrator: P_cal = sigma(w1*logit(P_raw) + w2*S_anomaly + b)      |    |
|    | Calibrated Risk Score: Score = 100.0 * P_cal  [0.0 - 100.0]                             |    |
|    +-----------------------------------------------------------------------------------------+    |
|                                              |                                                    |
|                                              v                                                    |
|  [ OPERATIONAL DECISION & EXPLAINABILITY LAYER ]                                                  |
|    +-----------------------------------------------------------------------------------------+    |
|    | Sub-5ms TreeSHAP Attribution -> Natural Language Reason Codes -> Human Review Queue     |    |
|    | Tiers: LOW (<30) | FRICTION (30-50: 3DS/OTP) | MEDIUM (50-75: Analyst) | HIGH (>=75)    |    |
|    +-----------------------------------------------------------------------------------------+    |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

---

## 1. Preservation & Versioning of the FraudShield 1.0 System

To maintain absolute stability and backward compatibility, the existing FraudShield 1.0 PCA system will be preserved without modification.

### 1.1 Structural Isolation Policy
1. **Zero Modification to v1 Code:** All existing files in `backend/app/` will remain completely untouched during initial v3 planning and development.
2. **Directory Namespace Separation:**
   ```
   backend/
   |-- app/
   |   |-- v1/                          <-- Existing FraudShield 1.0 preserved
   |   |   |-- ml/                      <-- Existing preprocessing, anomaly, explainability
   |   |   |-- routes/predict.py        <-- Preserved /api/v1/predict
   |   |   |-- schemas/transaction.py   <-- Preserved 30-feature schema
   |   |   |-- services/fraud_engine.py <-- Preserved HybridFraudEngine
   |   |-- v3/                          <-- New FraudShield 3.0 architecture
   |   |   |-- adapters/                <-- Hexagonal raw transaction adapters
   |   |   |-- feature_store/           <-- Streaming aggregations & feature pipeline
   |   |   |-- ml/                      <-- LightGBM, ECOD, VAE, Calibrators
   |   |   |-- routes/predict.py        <-- New /api/v3/predict
   |   |   |-- schemas/canonical.py     <-- Canonical raw transaction schema
   |   |   |-- services/engine_v3.py    <-- Next-gen modern fraud engine
   ```
3. **Model Artifact Versioning:**
   - Legacy: `backend/artifacts/v1/` contains `best_fraud_model.joblib`, `isolation_forest.joblib`, `preprocessor.joblib`, and `optimal_threshold.json` (0.895).
   - Modernized: `backend/artifacts/v3/` will house `lightgbm_fraud_model.joblib`, `ecod_detector.joblib`, `vae_detector.pt`, `feature_pipeline.joblib`, and `v3_meta_calibrator.joblib`.
4. **API Gateway Routing:**
   - Requests to `/api/v1/predict` are routed strictly to the legacy PCA pipeline.
   - Requests to `/api/v3/predict` are routed to the modernized raw-schema pipeline.
   - Incoming requests can specify version via URI path (`/api/v3/predict`) or header (`X-FraudShield-Version: 3.0`).

---

## 2. Hexagonal Raw Transaction Schema Adapter Architecture

In production environments, payment systems receive transactions from disparate payment gateways, core banking mainframes, and merchant integrations. FraudShield 3.0 implements the **Hexagonal (Ports and Adapters) Pattern** to decouple ingestion from inference.

### 2.1 The Canonical Transaction Model
Regardless of origin, every transaction is transformed into a validated, immutable internal structure:

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime

class CanonicalTransaction(BaseModel):
    """Normalized, vendor-neutral transaction representation."""
    transaction_id: str = Field(..., description="Unique idempotency transaction ID")
    timestamp: datetime = Field(..., description="UTC timestamp of transaction authorization")
    amount: float = Field(..., gt=0.0, description="Authorized amount in primary currency units")
    currency: str = Field(default="USD", description="ISO 4217 3-letter currency code")
    
    # Card & Account Identifiers (PCI-DSS Tokenized)
    card_pan_token: str = Field(..., description="HMAC-SHA256 salted token of Card PAN")
    card_bin: str = Field(..., min_length=6, max_length=8, description="First 6-8 digits for Issuer ID")
    card_last4: str = Field(..., min_length=4, max_length=4, description="Last 4 digits of card")
    card_network: str = Field(..., description="VISA, MASTERCARD, AMEX, DISCOVER, etc.")
    card_type: str = Field(default="DEBIT", description="DEBIT, CREDIT, PREPAID")
    
    # Merchant & Channel Attributes
    merchant_id: str = Field(..., description="Unique Merchant Terminal/Account ID")
    mcc: str = Field(..., min_length=4, max_length=4, description="ISO 18245 4-digit Merchant Category Code")
    merchant_country: str = Field(..., min_length=2, max_length=3, description="ISO Country Code")
    channel: str = Field(..., description="POS_CHIP, POS_CONTACTLESS, ECOMMERCE, MOTO, ATM")
    pos_entry_mode: str = Field(default="05", description="ISO 8583 DE 22 entry mode code")
    
    # Device & Network Context
    ip_address_hash: Optional[str] = Field(None, description="Hashed client IP address")
    device_fingerprint: Optional[str] = Field(None, description="Browser/Device hardware hash")
    billing_shipping_match: Optional[bool] = Field(None, description="Address Verification System match")
    cvv_result_code: Optional[str] = Field(None, description="M=Match, N=No Match, P=Not Processed")
    
    # Extensible Metadata Bag
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 2.2 Abstract Adapter Interface
```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTransactionAdapter(ABC):
    """Port interface for transaction ingestion."""
    
    @abstractmethod
    def validate_payload(self, raw_data: Dict[str, Any]) -> bool:
        """Validate raw incoming payload structure against vendor schema."""
        pass
        
    @abstractmethod
    def adapt(self, raw_data: Dict[str, Any]) -> CanonicalTransaction:
        """Transform raw vendor payload into CanonicalTransaction."""
        pass
```

---

## 3. Support for IEEE-CIS and Compatible Raw-Schema Datasets

The **IEEE-CIS Fraud Detection Benchmark** (Vesta Corporation) serves as the primary open development and pre-training dataset for FraudShield 3.0:

### 3.1 Dataset Profile & Mapping
- **Volume:** 590,540 training transactions + 506,691 test transactions ($N = 1,097,231$).
- **Ground Truth:** Confirmed fraud labels ($3.5\%$ prevalence) based on matured 120-day chargeback dispute windows.
- **Feature Extraction & Mapping Strategy:**
  1. `TransactionDT` $\rightarrow$ Converted to synthetic UTC timestamp sliding window ($t_0 + \Delta t$).
  2. `TransactionAmt` $\rightarrow$ `CanonicalTransaction.amount`.
  3. `card1` (Issuer Bank ID) $\rightarrow$ `CanonicalTransaction.card_bin`.
  4. `card4` (Card Network: Visa, Mastercard) $\rightarrow$ `CanonicalTransaction.card_network`.
  5. `card6` (Card Type: debit, credit) $\rightarrow$ `CanonicalTransaction.card_type`.
  6. `ProductCD` $\rightarrow$ High-level merchant category proxy.
  7. `addr1`, `addr2` $\rightarrow$ Billing zip/country proxies.
  8. `C1`–`C14` $\rightarrow$ Pre-calculated counting features (cross-validated against sliding-window store).
  9. `D1`–`D15` $\rightarrow$ Timedeltas since previous cardholder interactions.
  10. `M1`–`M9` $\rightarrow$ Match flags (cardholder name match, billing address match).
  11. `DeviceInfo`, `id_30` (OS), `id_31` (Browser) $\rightarrow$ Normalized device fingerprint.

### 3.2 Secondary Benchmark Integration
- **Sparkov Credit Card Simulator:** Open-source streaming dataset (~1.8M transactions) utilized for dynamic load testing, high-throughput message parsing, and impossible-travel stress tests.

---

## 4. ISO 8583-Inspired Transaction-Message Ingestion Design

ISO 8583 is the international standard governing card-originated financial transactions. FraudShield 3.0 introduces an ISO 8583-compliant ingestion parser.

### 4.1 Message Type Identifier (MTI) Handling
- `0100` (Authorization Request): Ingested in real-time ($< 25\text{ms}$ SLA). Engine returns approve, step-up challenge, or decline.
- `0110` (Authorization Response): Logged to update sliding-window state.
- `0200` (Financial Transaction Presentment): Confirms cleared transaction amount.
- `0420` (Reversal / Chargeback Alert): Ingested asynchronously to immediately flag compromised card tokens.

### 4.2 Primary Data Element (DE) Extraction Mapping
```
+---------------------------------------------------------------------------------------------------+
| ISO 8583 DE | Field Name                 | Extraction & Sanitization Method                       |
+-------------+----------------------------+--------------------------------------------------------+
| DE 2        | Primary Account Number     | HMAC-SHA256 Tokenization + BIN extraction (DE 2[:6])   |
| DE 3        | Processing Code            | Transaction Type (00 = Purchase, 01 = Cash Advance)    |
| DE 4        | Amount, Transaction        | Minor units divided by currency base (e.g. cents -> $) |
| DE 7        | Transmission Date and Time | Converted to ISO 8601 UTC timestamp                    |
| DE 11       | Systems Trace Audit Number | STAN tracked for transaction deduplication             |
| DE 18       | Merchant Category Code     | 4-digit MCC parsed as categorical feature              |
| DE 19       | Acquirer Country Code      | Mapped to ISO 3166-1 country code                      |
| DE 22       | POS Entry Mode Code        | Extracted: 05=Chip, 07=Contactless, 01=Manual/Keyed    |
| DE 41       | Terminal ID                | Acquirer terminal hardware identifier                  |
| DE 42       | Merchant ID                | Core merchant identification code                      |
| DE 43       | Card Acceptor Location     | City, state, country parsed for geo-velocity           |
| DE 49       | Currency Code              | ISO 4217 3-digit numeric code                          |
+---------------------------------------------------------------------------------------------------+
```

### 4.3 Security & PCI-DSS Compliance
- **Zero Raw PAN Storage:** Primary Account Numbers are tokenized in memory using an ephemeral HMAC-SHA256 key stored in a secure Key Management Service (KMS). Cleartext PANs never touch disk, logs, or databases.
- **CVV/PIN Omission:** CVV2 codes and PIN blocks are processed exclusively by payment hardware security modules (HSM) and are never ingested into FraudShield.

---

## 5. Schema Validation & Real-Time Feature Engineering

Fraud detection accuracy is heavily driven by **behavioral velocity** and **contextual deviations** rather than static transaction amounts alone.

### 5.1 Real-Time Streaming Feature Store (Redis-Backed)
A dual Redis sliding-window cache maintains dynamic state per card token and per merchant:

```
+---------------------------------------------------------------------------------------------------+
|                                 REAL-TIME BEHAVIORAL FEATURE SET                                  |
+---------------------------------------------------------------------------------------------------+
| Feature Name              | Window     | Calculation / Logic                                      |
+---------------------------+------------+----------------------------------------------------------+
| `card_tx_count_1h`        | 1 Hour     | Number of transactions on card token in rolling 1h       |
| `card_tx_count_24h`       | 24 Hours   | Number of transactions on card token in rolling 24h      |
| `card_amount_sum_24h`     | 24 Hours   | Cumulative spend on card token in rolling 24h            |
| `card_amount_ratio_30d`   | 30 Days    | Amount / Mean(Amount of card over 30d)                   |
| `card_amount_zscore_30d`  | 30 Days    | (Amount - Mean_30d) / Std_30d                            |
| `card_distinct_mcc_24h`   | 24 Hours   | Count of unique MCCs transacted in last 24h              |
| `merchant_velocity_1h`    | 1 Hour     | Number of distinct card tokens at merchant in 1h         |
| `merchant_decline_rate_1h`| 1 Hour     | Failed authorization ratio at merchant terminal          |
| `impossible_travel_speed` | Sequential | Distance(Loc_curr, Loc_prev) / Delta_t (km/h)            |
| `hour_sin`, `hour_cos`    | Instant    | Cyclical hour-of-day encoding: sin/cos(2*pi*hour/24)     |
| `dow_sin`, `dow_cos`      | Instant    | Cyclical day-of-week encoding: sin/cos(2*pi*dow/7)       |
+---------------------------------------------------------------------------------------------------+
```

### 5.2 Impossible Travel Detection Formula
For consecutive transactions $i-1$ and $i$ on the same card token occurring at coordinates $(\text{lat}_1, \text{lon}_1)$ and $(\text{lat}_2, \text{lon}_2)$:
$$\text{Distance} = 2 R \arcsin \left( \sqrt{\sin^2\left(\frac{\Delta \text{lat}}{2}\right) + \cos(\text{lat}_1)\cos(\text{lat}_2)\sin^2\left(\frac{\Delta \text{lon}}{2}\right)} \right)$$
$$\text{Speed} = \frac{\text{Distance}}{\Delta t} \quad [\text{km/h}]$$
If $\text{Speed} > 900\text{ km/h}$ and $\text{channel} \in \{\text{POS\_CHIP}, \text{POS\_CONTACTLESS}\}$, transaction is immediately flagged for card-present geographical spoofing.

---

## 6. Supervised & Anomaly-Detection Model Architecture

FraudShield 3.0 upgrades both the supervised and unsupervised components to state-of-the-art architectures designed for tabular streaming data.

```
+---------------------------------------------------------------------------------------------------+
|                                 DUAL MODEL INFERENCE ARCHITECTURE                                 |
+---------------------------------------------------------------------------------------------------+
|                                                                                                   |
|                              Canonical Transaction Features (X)                                   |
|                                       /              \                                            |
|                                      /                \                                           |
|                                     v                  v                                          |
|                +-------------------------+      +-------------------------+                       |
|                |   Supervised Learner    |      |   Unsupervised Learner  |                       |
|                |      (LightGBM)         |      |    (ECOD + Deep VAE)    |                       |
|                +-------------------------+      +-------------------------+                       |
|                             |                                |                                    |
|                             v                                v                                    |
|                   P_raw(Fraud | X)                   S_anomaly(X)                                 |
|                   [0.0000 - 1.0000]                [0.0000 - 1.0000]                              |
|                             \                                /                                    |
|                              \                              /                                     |
|                               v                            v                                      |
|                     +------------------------------------------------+                            |
|                     |       Nested Logistic Meta-Calibrator          |                            |
|                     |  P_cal = sigma(w1*logit(P_raw) + w2*S_anom + b)|                            |
|                     +------------------------------------------------+                            |
|                                              |                                                    |
|                                              v                                                    |
|                                     Calibrated Risk Score                                         |
|                                     RiskScore = 100 * P_cal                                       |
|                                                                                                   |
+---------------------------------------------------------------------------------------------------+
```

### 6.1 Supervised Model: LightGBM / CatBoost
- **Algorithmic Selection:** Transition from standard XGBoost to **LightGBM** (with CatBoost as candidate alternative):
  - **Native Categorical Handling:** Automatically optimizes split points on categorical features (`card_bin`, `mcc`, `channel`, `card_network`) using integer fisher optimal split partitioning, eliminating sparse high-cardinality one-hot encoding matrices.
  - **Inference Latency:** Optimized C++ tree evaluation routines deliver P99 single-row latency under **$3.5\text{ms}$**.
  - **Monotonic Feature Constraints:** Enforces strict business domain rules:
    - $\frac{\partial P_{\text{fraud}}}{\partial (\text{card\_tx\_count\_1h})} \ge 0$ (Higher velocity can never decrease fraud probability).
    - $\frac{\partial P_{\text{fraud}}}{\partial (\text{impossible\_travel\_speed})} \ge 0$ (Higher velocity can never decrease fraud probability).

### 6.2 Unsupervised Anomaly Model: ECOD + Variational Autoencoder (VAE)
- **Primary Fast Detector:** **ECOD (Empirical Cumulative Distribution Functions for Outlier Detection)**:
  - Fast, non-parametric, parameter-free anomaly detector. Computes outlier scores by measuring the joint empirical tail probability across all continuous velocity and amount dimensions.
  - Sub-millisecond inference time ($< 1.0\text{ms}$).
- **Secondary Zero-Day Detector:** **Variational Autoencoder (VAE)**:
  - Neural network trained exclusively on verified legitimate transactions ($y = 0$).
  - Encoder compresses $\mathbf{x} \in \mathbb{R}^K$ to latent distribution $\mathcal{N}(\boldsymbol{\mu}_z, \boldsymbol{\sigma}_z^2) \in \mathbb{R}^{16}$.
  - Decoder reconstructs $\hat{\mathbf{x}} = D(\mathbf{z})$.
  - Anomaly score is the normalized reconstruction error: $\mathcal{L}_{\text{recon}} = \|\mathbf{x} - \hat{\mathbf{x}}\|^2$. Novel fraud schemes that violate legitimate spending manifolds produce large reconstruction errors.

---

## 7. Hybrid Risk Scoring & Probability Calibration

A core finding from Milestone 2C and 2D was that raw model probabilities are uncalibrated under severe class imbalance ($\approx 0.17\% - 3.5\%$), and arbitrary heuristic score combinations create artificial probability floors.

### 7.1 Nested Meta-Calibrator Formulation
FraudShield 3.0 adopts the verified **Architecture C** meta-calibration design:
$$\text{logit}(P_{\text{raw}}) = \ln \left( \frac{P_{\text{raw}} + \epsilon}{1 - P_{\text{raw}} + \epsilon} \right)$$
$$z = w_0 + w_1 \cdot \text{logit}(P_{\text{raw}}) + w_2 \cdot S_{\text{anomaly}} + w_3 \cdot \ln(1 + \text{Velocity}_{1\text{h}})$$
$$P_{\text{cal}} = \sigma(z) = \frac{1}{1 + e^{-z}}$$
$$\text{RiskScore}_{\text{cal}} = 100.0 \times P_{\text{cal}} \quad \in [0.0, 100.0]$$

Weights $\mathbf{w} = [w_0, w_1, w_2, w_3]$ are fitted via $L_2$-regularized Logistic Regression strictly on out-of-fold cross-validation predictions.

### 7.2 Calibrated Action Tiers
```
+---------------------------------------------------------------------------------------------------+
|                              FRAUDSHIELD 3.0 OPERATIONAL ACTION TIERS                             |
+---------------------------------------------------------------------------------------------------+
| Tier Name       | Calibrated Score | Implied Fraud Prob | Operational Action                      |
+-----------------+------------------+--------------------+-----------------------------------------+
| LOW             | [0.0, 30.0)      | < 0.30             | Automated Instant Approval (Pass)       |
| FRICTION        | [30.0, 50.0)     | 0.30 - 0.49        | Step-Up Auth (Passive 3DS / SMS OTP)    |
| MEDIUM (ORQ)    | [50.0, 75.0)     | 0.50 - 0.74        | Operational Review Queue (Analyst Hold) |
| HIGH            | [75.0, 100.0]    | >= 0.75            | High-Priority Alert / Hard Card Block   |
+---------------------------------------------------------------------------------------------------+
```

---

## 8. Leakage-Safe Out-of-Time Training, Validation & Testing

Credit card transaction data is intrinsically non-stationary and subject to temporal drift. Standard random K-Fold cross-validation leaks future information into past predictions, resulting in overly optimistic evaluation.

### 8.1 Purged, Embargoed Grouped Time-Series Cross-Validation
FraudShield 3.0 enforces strict temporal partitioning:

```
Timeline: |---- Fold 1 Train ----|--Embargo--|-- Val 1 --|
          |-------- Fold 2 Train --------|--Embargo--|-- Val 2 --|
          |------------ Fold 3 Train ------------|--Embargo--|-- Val 3 --|
          |---------------- Full Training Window ----------------|--Embargo--|-- Held-Out OOT Test --|
```

1. **Purging:** Any transaction occurring between authorization and final chargeback maturity (e.g. within 60–90 days) is purged from evaluation splits if dispute status is unsettled.
2. **Embargo Period:** A mandatory 14-day gap is enforced between training folds and validation folds to prevent short-term card-reuse leakage.
3. **Out-of-Time (OOT) Split:** The final test set represents an uninspected future time window (e.g., Months $T+5$ and $T+6$), ensuring true forward-looking generalization.

### 8.2 Pre-Registered Statistical Evaluation Protocol
All candidate models in FraudShield 3.0 will be evaluated against the pre-registered protocol codified in **Milestone 2D Version 3.4.0**:
- **Paired Stratified Bootstrap ($B = 10,000$):** Resamples fraud and legitimate transactions separately, reporting 95% confidence intervals for $\Delta F_1 = F_{1, \text{cand}} - F_{1, \text{base}}$.
- **Separated McNemar Tests:** Decoupled fraud error discordance ($y = 1$) and false alarm discordance ($y = 0$) tested at $\alpha = 0.01$.
- **Provisional Non-Inferiority Verification:** Pre-registered margin $\delta_{\text{recall}} = 0.030$ requiring $\text{LB}_{95\%}(\Delta \text{Recall}) > -0.030$, with explicit domain-expert agreement required before operational non-inferiority claims.

---

## 9. Model Monitoring, Drift Detection & Explainability

### 9.1 Drift Detection Architecture
Fraud patterns evolve rapidly through adversary adaptation. FraudShield 3.0 embeds automated drift monitors:
- **Population Stability Index (PSI):**
  $$\text{PSI} = \sum_{b=1}^B \left( P_{\text{actual}}(b) - P_{\text{expected}}(b) \right) \ln \left( \frac{P_{\text{actual}}(b)}{P_{\text{expected}}(b)} \right)$$
  - $\text{PSI} < 0.10$: Stable distribution (Normal).
  - $0.10 \le \text{PSI} < 0.25$: Moderate drift (Warning alert logged to Prometheus).
  - $\text{PSI} \ge 0.25$: Significant distribution shift (Triggers automated canary retraining workflow).
- **Two-Sample Kolmogorov-Smirnov (KS) Test:** Run daily on top 20 continuous features.
- **Concept Drift Monitor:** Tracks the 7-day rolling fraud rate against baseline expectations to detect sudden attack campaigns.

### 9.2 Real-Time Explainability Engine (Fast TreeSHAP)
Fraud analysts require actionable reason codes to review flagged transactions within regulatory deadlines:
- **Fast TreeSHAP Integration:** Computes exact Shapley values for the LightGBM model in under **$4.0\text{ms}$**.
- **Automated Reason Code Generator:**
  Maps top positive SHAP contributors into standardized banking reason codes:
  - `RC_01_HIGH_VELOCITY`: Transaction frequency on card exceeds 99th percentile of 30-day history.
  - `RC_02_GEO_MISMATCH`: IP address location deviates from merchant terminal country.
  - `RC_03_AMOUNT_DEVIATION`: Amount is $> 4.2\times$ standard deviation above cardholder median.
  - `RC_04_UNUSUAL_MCC`: Cardholder has zero prior transactions in MCC 5732 (High-Risk Electronics).

---

## 10. Backend, API, Dashboard & Deployment Integration

### 10.1 Microservice / Modular Monolith Architecture
FraudShield 3.0 is built as a high-throughput, asynchronous service using modern Python 3.12:

```
backend/
|-- app/
|   |-- core/
|   |   |-- config.py                 <-- Pydantic v2 settings & KMS secrets
|   |   |-- security.py               <-- JWT auth, API key hashing, HMAC-SHA256
|   |-- v1/                           <-- Frozen FraudShield 1.0 (PCA)
|   |-- v3/                           <-- Modernized FraudShield 3.0
|   |   |-- adapters/                 <-- ISO 8583, IEEE-CIS, REST adapters
|   |   |-- feature_store/            <-- Redis sliding-window aggregators
|   |   |-- ml/                       <-- LightGBM, ECOD, VAE, Meta-Calibrator
|   |   |-- models/                   <-- SQLAlchemy 2.0 async database models
|   |   |-- routes/                   <-- /api/v3/predict, /api/v3/review-queue
|   |   |-- schemas/                  <-- Canonical schemas & SHAP response models
|   |   |-- services/                 <-- FraudEngineV3, StreamService, AuditService
```

### 10.2 Production Performance SLA
- **Target Single-Transaction Latency:**
  - P50: $< 8\text{ms}$
  - P95: $< 16\text{ms}$
  - P99: $< 25\text{ms}$
- **Batch Processing Throughput:** $> 2,500$ transactions per second via asynchronous worker pools (Celery / Redis Streams).

### 10.3 Next-Gen Analyst Review Dashboard (React + Vite)
- **Live WebSocket Alert Stream:** Instant delivery of `MEDIUM` and `HIGH` risk alerts to analysts.
- **Interactive SHAP Waterfall Visualizer:** Displays feature-by-feature force plot explaining exactly why a transaction was flagged.
- **One-Click Dispositioning:** Approve, Confirm Fraud (initiates automated chargeback), Step-Up Challenge, or Whitelist.

---

## 11. Dataset Provenance, Governance & Licensing

| Dataset Asset | Source Entity | License / Terms | Operational Role | Governance Classification |
|---|---|---|---|---|
| **IEEE-CIS Fraud Detection** | Vesta Corporation / IEEE CIS | Open Competition License | Supervised model pre-training & feature engineering | Research & Development Authorized |
| **Sparkov Synthetic Dataset** | Brandon Harris (Open Source) | MIT License | High-throughput load testing & geo-velocity simulation | Fully Permissive Open Source |
| **PaySim Financial Simulator**| Blekinge Institute of Tech | CC BY-SA 4.0 | Anomaly detector stress testing | Attribution Permitted |
| **Future Banking Partner Stream**| Issuing / Acquirer Bank | Enterprise Commercial NDA | Production evaluation & fine-tuning | Proprietary / Confidential |

---

## 12. Strict Execution Boundaries & Compliance Confirmation

- **No Code Modifications:** Existing files in `backend/app/`, `backend/artifacts/`, and `data/` remain 100% frozen.
- **No Access to Quarantined Split:** `data/raw/creditcard.csv` test indices remain completely untouched.
- **No False Generalization Claims:** FraudShield 3.0 is documented strictly as an architectural plan and modernization blueprint. No claims of external real-world validation will be made until live independent evaluation is authorized and executed under pre-registered gates.
- **Approval Prerequisite:** This document represents planning and architectural design only. All development work remains halted awaiting user authorization.
