# FraudShield 3.0 — Phase 2, Milestone 3B Implementation Report
**Document ID:** `FS3-REP-002`  
**Milestone:** Phase 2, Milestone 3B (Streaming Feature Store & Behavioral Velocity)  
**Date:** 2026-11-17  
**Status:** COMPLETE & VERIFIED  
**Authors:** FraudShield AI Engineering Team  
**Governing Plan:** `FRAUDSHIELD_3_ARCHITECTURE_PLAN.md` & `FRAUDSHIELD_3_IMPLEMENTATION_ROADMAP.md`  

---

## 1. Executive Summary

Milestone 3B delivers the production-grade, streaming feature store and behavioral velocity engineering layer for FraudShield 3.0. Following the formal sign-off of Phase 1 (Milestone 3A) and the resolution of all identified architectural review findings, this milestone implements the real-time stateful computation engine that bridges raw normalized transactions with downstream risk scoring.

The feature store is engineered with a **dual-backend strategy**:
1. **Thread-Safe In-Memory Store (`InMemorySlidingWindowStore`)**: A zero-external-dependency, deterministic engine leveraging bisect-sorted timelines and reader-writer locks, providing microsecond latencies for standalone test suites, offline batch pipelines, and developer environments.
2. **Production Redis Store (`RedisSlidingWindowStore`)**: A horizontally scalable, Redis-backed implementation utilizing Sorted Sets (`ZSET`) keyed by card and merchant tokens, atomic `SETNX` idempotency registries, and 31-day key TTLs for memory leak prevention.

Both implementations adhere to the unified abstract port (`BaseFeatureStore`), ensuring drop-in equivalence across development, testing, and production runtime environments.

### Key Milestones & Metrics Summary
- **Sliding-Window Aggregations:** 1 hour, 24 hours, 7 days, and 30 days.
- **Card-Level Velocity Metrics:** Transaction frequency ($N_{\text{tx}, 1\text{h}}, N_{\text{tx}, 24\text{h}}, N_{\text{tx}, 7\text{d}}, N_{\text{tx}, 30\text{d}}$), rolling spend sums ($\sum_{1\text{h}}, \sum_{24\text{h}}, \sum_{7\text{d}}$), 30-day baseline spend mean ($\mu_{30\text{d}}$) and standard deviation ($\sigma_{30\text{d}}$), ratio to 30-day mean spend, and spend $z$-score deviation.
- **Merchant-Level Velocity Metrics:** Total transaction frequency (1h, 24h) and unique cardholder diversity in 1h ($N_{\text{distinct\_cards}, 1\text{h}}$).
- **Geo-Spatial Impossible Travel Detection:** Great-circle Haversine formula calculation on physical POS/ATM transactions; speed $> 900\text{ km/h}$ flagged as impossible travel. Card-Not-Present (e-commerce) channels systematically bypass physical travel alerts.
- **Continuous Cyclical Temporal Encodings:** Orthogonal continuous sine/cosine transformations for hour of day and day of week ($\sin^2 + \cos^2 = 1.0$).
- **Event Ordering & Idempotency:** Event-timestamp sorted insertion guarantees robust handling of out-of-order event arrivals and network jitter; atomic idempotency keys reject duplicate submissions and prevent velocity inflation.
- **Milestone 3A Review Refinements:** SEC-01 (KMS salt configuration & production enforcement), SEC-02 (Pydantic `@field_serializer` PAN masking), DOM-02 (ISO 4217 minor currency exponent scaling table for JPY, KWD, USD), and DATA-01 (IEEE-CIS card composite tokenization with `addr1` disambiguation).
- **Test Suite Verification:** 78/78 tests passing (100% green), including 20 legacy tests and 58 v3 unit and integration tests.

---

## 2. Architecture & Data Flow

The Milestone 3B streaming feature store operates directly downstream of the Phase 1 schema adapters, enriching validated `CanonicalTransaction` instances into model-ready `EnrichedFeatureVector` instances.

```
+-------------------------------------------------------------------------------+
|                       FRAUDSHIELD 3.0 STREAMING ENGINE                        |
+-------------------------------------------------------------------------------+

 Raw Message Payload       [ ISO 8583 / IEEE-CIS Tabular / Generic JSON ]
          |
          v
   Schema Adapters         [ Iso8583Adapter / IeeeCisAdapter / GenericJsonAdapter ]
          |                (KmsTokenService: Luhn, HMAC Tokenization, Salt Secret)
          v
 Canonical Transaction     [ CanonicalTransaction (PCI-DSS Tokenized, Immutable) ]
          |
          +------------------------------------------+
          |                                          |
          v                                          v
+------------------------+                +------------------------+
|   Pre-Tx Velocity      |                |   Idempotency Check    |
|   Query & Baseline     |                |   SETNX with TTL       |
+------------------------+                +------------------------+
          |                                          |
          +--------------------+---------------------+
                               |
                               v
               +-------------------------------+
               |   Geo-Spatial Travel Check    |
               |   Haversine Speed > 900 km/h? |
               |   (Physical POS / ATM Only)   |
               +-------------------------------+
                               |
                               v
               +-------------------------------+
               |   Cyclical Temporal Encoding  |
               |   sin / cos of Hour and DOW   |
               +-------------------------------+
                               |
                               v
               +-------------------------------+
               |   Feature Store Persistence   |
               |   ZADD Card & Merchant ZSETs  |
               |   Update Last Known Location  |
               +-------------------------------+
                               |
                               v
                     EnrichedFeatureVector
             (Ready for Downstream Scoring & Storage)
```

---

## 3. Sliding-Window Behavioral Velocity Engine

### 3.1 Time Window Specifications
The feature store supports four standard sliding-window intervals computed relative to the incoming transaction's UTC event timestamp ($t_{\text{ref}}$):
- **1-Hour Window ($W_{1\text{h}}$):** $t \in [t_{\text{ref}} - 3,600\text{s},\, t_{\text{ref}})$ — Detects rapid burst attacks and card testing.
- **24-Hour Window ($W_{24\text{h}}$):** $t \in [t_{\text{ref}} - 86,400\text{s},\, t_{\text{ref}})$ — Captures daily spend spikes and velocity clustering.
- **7-Day Window ($W_{7\text{d}}$):** $t \in [t_{\text{ref}} - 604,800\text{s},\, t_{\text{ref}})$ — Tracks weekly behavioral patterns.
- **30-Day Window ($W_{30\text{d}}$):** $t \in [t_{\text{ref}} - 2,592,000\text{s},\, t_{\text{ref}})$ — Establishes account baseline spend profiling.

### 3.2 Cardholder Behavioral Metrics
For each transaction with card token $K_{\text{card}}$ and authorized amount $A$:
1. **Transaction Counts:**
   $$N_{\text{tx}, 1\text{h}} = \sum_{i \in W_{1\text{h}}} 1, \quad N_{\text{tx}, 24\text{h}} = \sum_{i \in W_{24\text{h}}} 1, \quad N_{\text{tx}, 7\text{d}} = \sum_{i \in W_{7\text{d}}} 1, \quad N_{\text{tx}, 30\text{d}} = \sum_{i \in W_{30\text{d}}} 1$$
2. **Cumulative Spend Sums:**
   $$\text{Spend}_{1\text{h}} = \sum_{i \in W_{1\text{h}}} A_i, \quad \text{Spend}_{24\text{h}} = \sum_{i \in W_{24\text{h}}} A_i, \quad \text{Spend}_{7\text{d}} = \sum_{i \in W_{7\text{d}}} A_i$$
3. **30-Day Spend Baseline & Deviation:**
   - **Baseline Mean:** $\mu_{30\text{d}} = \frac{1}{N_{30\text{d}}} \sum_{i \in W_{30\text{d}}} A_i$ (if $N_{30\text{d}} \ge 1$, else $0.0$)
   - **Baseline Standard Deviation:** $\sigma_{30\text{d}} = \sqrt{\frac{1}{N_{30\text{d}}} \sum_{i \in W_{30\text{d}}} (A_i - \mu_{30\text{d}})^2}$ (if $N_{30\text{d}} \ge 1$, else $0.0$)
   - **Spend Ratio:** $R_{30\text{d}} = \frac{A}{\max(\mu_{30\text{d}},\, 0.01)}$ (if $N_{30\text{d}} \ge 1$, else $1.0$)
   - **Spend $Z$-Score:** $Z_{30\text{d}} = \frac{A - \mu_{30\text{d}}}{\sigma_{30\text{d}}}$ (if $\sigma_{30\text{d}} > 10^{-4}$, else $0.0$)

### 3.3 Merchant Diversity Metrics
For each merchant identifier $M$:
- **Merchant Transaction Volume:** $N_{\text{merch}, 1\text{h}}$ and $N_{\text{merch}, 24\text{h}}$.
- **Unique Cardholder Diversity:** $N_{\text{distinct\_cards}, 1\text{h}} = |\bigcup_{i \in W_{1\text{h}}} \{K_{\text{card}, i}\}|$.
  - Rapid spikes in distinct cards at an atypical merchant pinpoint compromised merchant terminals or bot-driven credential stuffing.

---

## 4. Geo-Spatial Impossible Travel Detection

### 4.1 Great-Circle Haversine Formula
For consecutive physical transactions (POS chip, swipe, contactless, ATM) on the same card token with coordinates $(\phi_1, \lambda_1)$ at $t_1$ and $(\phi_2, \lambda_2)$ at $t_2$:
$$\Delta \phi = \phi_2 - \phi_1, \quad \Delta \lambda = \lambda_2 - \lambda_1$$
$$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)$$
$$c = 2 \cdot \text{atan2}(\sqrt{a}, \sqrt{1 - a})$$
$$d = R_{\text{Earth}} \cdot c \quad \text{where } R_{\text{Earth}} = 6,371.0\text{ km}$$

### 4.2 Velocity Calculation & Thresholding
$$\text{Speed}_{\text{km/h}} = \frac{d}{\Delta t_{\text{hours}}} = \frac{d}{(t_2 - t_1) / 3,600.0}$$
$$\text{Impossible Travel Flag} = \begin{cases} \text{True} & \text{if } \text{Speed}_{\text{km/h}} > 900.0\text{ km/h} \text{ and } \text{Channel} \in \text{Physical} \\ \text{False} & \text{otherwise} \end{cases}$$

### 4.3 Channel Integrity & Bypass
- **Card-Not-Present (E-Commerce / MOTO) Bypass:** Online transactions do not require cardholder physical presence at merchant servers. Triggering impossible travel on e-commerce transactions would generate massive false alarms; therefore, CNP transactions systematically bypass physical travel checks.
- **Concurrent Anomaly Handling:** If $\Delta t = 0$ and $d > 50\text{ meters}$, velocity is flagged as instantaneous cloning ($\text{speed} = 999,999\text{ km/h}$).

---

## 5. Cyclical Temporal Encodings

Time features exhibit strong circular periodicity. Linear numerical representations (e.g., hour $23$ and hour $0$) create artificial discontinuities for machine learning algorithms. FraudShield 3.0 maps timestamps onto the unit trigonometric circle:

1. **Continuous Hour of Day ($h \in [0, 24)$):**
   $$h_{\text{cont}} = \text{Hour} + \frac{\text{Minute}}{60.0}$$
   $$\text{hour\_sin} = \sin\left(\frac{2\pi \cdot h_{\text{cont}}}{24.0}\right), \quad \text{hour\_cos} = \cos\left(\frac{2\pi \cdot h_{\text{cont}}}{24.0}\right)$$
2. **Day of Week ($w \in [0, 6]$ where Monday=0, Sunday=6):**
   $$\text{dow\_sin} = \sin\left(\frac{2\pi \cdot w}{7.0}\right), \quad \text{dow\_cos} = \cos\left(\frac{2\pi \cdot w}{7.0}\right)$$

**Orthogonality Proof:**
$$\text{hour\_sin}^2 + \text{hour\_cos}^2 = 1.0 \pm 10^{-4}, \quad \text{dow\_sin}^2 + \text{dow\_cos}^2 = 1.0 \pm 10^{-4}$$

---

## 6. Event Ordering, Idempotency & Freshness

### 6.1 Out-of-Order Timeline Ingestion
Network latency, gateway retries, and batch replays frequently cause transactions to arrive out of order.
- **In-Memory Store:** Uses `bisect.insort` to insert events into card and merchant history arrays ordered strictly by `timestamp.timestamp()`. Range queries use `bisect_left` for exact interval slicing.
- **Redis Store:** Uses Redis Sorted Sets (`ZSET`) where `score = timestamp.timestamp()`. `ZADD` inherently places elements at their exact chronological score position, ensuring queries over `ZRANGEBYSCORE` reflect true historical chronology regardless of ingestion arrival sequence.

### 6.2 Idempotency & Replay Attack Defense
Every transaction must supply or generate a deterministic `transaction_id`.
- **Atomic Reservation:** `SET fs3:idemp:{tx_id} 1 NX EX 604800` (7-day TTL).
- **Duplicate Handling:** If `SETNX` returns `False`, the transaction is flagged with `is_duplicate = True`. Downstream feature pipelines return the feature vector with the duplicate flag set, preventing double-counting or velocity corruption.

### 6.3 Memory Reclamation & Expiration
- **Redis TTLs:** Key expiration (`EXPIRE 2678400`) is refreshed on every read/write cycle (31 days). Inactive cards naturally evict without background cron leaks.
- **Sliding-Window Maintenance:** `prune_expired()` removes sorted-set scores older than 30 days (`ZREMRANGEBYSCORE key -inf (now - 30d)`).

---

## 7. Resolution of Milestone 3A Independent Review Findings

| Review Finding | Severity | Problem Description | Milestone 3B Resolution |
| :--- | :--- | :--- | :--- |
| **SEC-01** | High | `KmsTokenService` defaulted to hardcoded dev salt without enforcement. | Added `enforce_configured_salt: bool` and production environment check (`FRAUDSHIELD_ENV=production`); raises `RuntimeError` if explicit KMS provider or secret is omitted. |
| **SEC-02** | High | `Iso8583ParsedPayload` had unmasked `pan` field risk upon logging. | Added Pydantic `@field_serializer("pan")` that automatically masks PAN as `4532XXXXXXXX0366` on `.model_dump()` and `.model_dump_json()`. |
| **DOM-02** | High | Fixed divisor of 100 in ISO 8583 adapter corrupted JPY and KWD amounts. | Created `ISO_CURRENCY_EXPONENTS` lookup dictionary. JPY (392) uses scale $10^0 = 1$ ($5000 \to 5000.0$); KWD (414) uses $10^3 = 1000$ ($5000 \to 5.000$); USD/EUR use $10^2 = 100$ ($5000 \to 50.00$). |
| **DATA-01** | High | IEEE-CIS card tokenization from `card1-3` caused account collision. | Expanded card composite to include billing address region: `f"ieee_{card1}_{card2}_{card3}_{addr1}"`. Eliminates cross-account collisions for cards at the same issuing bank. |

---

## 8. Verification & Test Suite Results

### 8.1 Automated Test Execution Summary
Full test execution across all legacy and v3 modules:

```powershell
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\LENOVO\Desktop\FraudShield-AI
collected 78 items

backend/tests/test_backend.py ...........                                [ 14%]
backend/tests/test_ml.py .........                                       [ 25%]
backend/tests/test_v3/test_canonical_schema.py ......                    [ 33%]
backend/tests/test_v3/test_currency_exponent_normalization.py ....        [ 38%]
backend/tests/test_v3/test_dual_engine_router.py ....                    [ 43%]
backend/tests/test_v3/test_feature_store_sliding_window.py ....          [ 48%]
backend/tests/test_v3/test_generic_json_adapter.py ...                   [ 52%]
backend/tests/test_v3/test_geo_velocity.py ......                        [ 60%]
backend/tests/test_v3/test_idempotency_and_ordering.py ...               [ 64%]
backend/tests/test_v3/test_ieee_cis_adapter.py .....                     [ 70%]
backend/tests/test_v3/test_iso8583_adapter.py ........                   [ 80%]
backend/tests/test_v3/test_redis_store_mock.py .                         [ 82%]
backend/tests/test_v3/test_scaffolding_refinements.py ...                [ 85%]
backend/tests/test_v3/test_streaming_feature_pipeline.py ....            [ 91%]
backend/tests/test_v3/test_token_service.py .......                      [100%]

======================= 78 passed, 18 warnings in 6.02s =======================
```

### 8.2 Detailed Test Coverage Matrix (Milestone 3B Additions)

| Test Module | Test Cases | Scope / Functionality Verified | Status |
| :--- | :---: | :--- | :---: |
| `test_feature_store_sliding_window.py` | 4 | 1h, 24h, 7d, 30d windows; rolling spend sums; 30d baseline mean & std; spend ratio & $z$-score; merchant volume & distinct cards; 30d eviction pruning. | PASSED |
| `test_idempotency_and_ordering.py` | 3 | Duplicate rejection; replay attack mitigation; out-of-order arrival chronological sorting; window boundary inclusion. | PASSED |
| `test_geo_velocity.py` | 6 | Great-circle Haversine distance accuracy; velocity calculation; physical terminal speed $>900\text{ km/h}$ flagged; realistic travel cleared; e-commerce bypass; missing coordinates handling. | PASSED |
| `test_currency_exponent_normalization.py` | 4 | JPY (exponent 0), USD (exponent 2), KWD (exponent 3), EUR (exponent 2) minor unit conversion. | PASSED |
| `test_scaffolding_refinements.py` | 3 | SEC-01 KMS production salt enforcement; SEC-02 Pydantic model serialization PAN masking; DATA-01 IEEE-CIS `addr1` card disambiguation. | PASSED |
| `test_streaming_feature_pipeline.py` | 4 | Real-time velocity accumulation; cyclical temporal encodings ($\sin^2 + \cos^2 = 1$); duplicate transaction flag handling; impossible travel end-to-end integration. | PASSED |
| `test_redis_store_mock.py` | 1 | Redis keyspace conventions; pipeline execution; atomic SETNX idempotency; ZSET score slicing; HASH terminal location persistence. | PASSED |
| **Total Milestone 3B Tests** | **25** | **Comprehensive Behavioral Velocity & Feature Store Coverage** | **PASSED** |

---

## 9. Deliverables Inventory

1. **Schemas:** [schemas.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/schemas.py)
   - `GeoLocation`, `CardVelocityStats`, `MerchantVelocityStats`, `EnrichedFeatureVector`.
2. **Abstract Port:** [base.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/base.py)
   - `BaseFeatureStore`, window intervals (`WINDOW_1H_SECONDS`, `WINDOW_24H_SECONDS`, `WINDOW_7D_SECONDS`, `WINDOW_30D_SECONDS`).
3. **In-Memory Store:** [in_memory_store.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/in_memory_store.py)
   - Thread-safe, bisect-sorted timelines, sub-millisecond query execution.
4. **Redis Store:** [redis_store.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/redis_store.py)
   - Production Redis implementation utilizing `ZSET`, `SETNX`, `HASH`, and TTL eviction.
5. **Geo-Spatial Engine:** [geo.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/geo.py)
   - Great-circle Haversine formula, velocity computation, e-commerce bypass.
6. **Feature Pipeline:** [pipeline.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/pipeline.py)
   - Ingestion, pre-transaction velocity querying, cyclical temporal encoding, transaction persistence.
7. **Package Facade:** [__init__.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/__init__.py)
   - `get_feature_store()` auto-resolving factory.
8. **Test Suite:** 7 new test suites under [backend/tests/test_v3/](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/tests/test_v3/).

---

## 10. Boundaries & Next Milestone Handoff

### 10.1 Adherence to Strict Constraints
- **FraudShield 1.0:** Frozen and untouched. `backend/app/ml/`, `backend/app/models/`, `backend/app/routes/`, `backend/app/schemas/`, `backend/app/services/` contain zero v3 code.
- **Production Artifacts:** `optimal_threshold.json` strictly verified at `0.895`.
- **Model Training:** Zero models trained or evaluated in this milestone.
- **External Quarantined Data:** Quarantined old benchmark test split was not accessed.
- **Stop Condition:** Phase 2, Milestone 3B execution is fully complete. Work halts here. Phase 3 (LightGBM modern feature training) is NOT started and awaits explicit supervisor authorization.
