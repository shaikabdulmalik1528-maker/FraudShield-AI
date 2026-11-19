# FraudShield 3.0 — Phase 2, Milestone 3B Independent Technical Audit Report
**Document ID:** `FS3-REV-002`  
**Milestone Reviewed:** Phase 2, Milestone 3B (Streaming Feature Store & Behavioral Velocity)  
**Audit Date:** 2026-11-17  
**Auditor:** FraudShield AI Independent Architecture & Security Review Team  
**Review Scope:** `backend/app/v3/feature_store/`, `backend/tests/test_v3/`, and `documentation/PHASE_2_MILESTONE_3B_IMPLEMENTATION_REPORT.md`  
**Audit Mode:** READ-ONLY Forensic Inspection  

---

## 1. Executive Summary

This independent technical audit provides a rigorous, read-only forensic evaluation of the **FraudShield 3.0 Streaming Feature Store & Behavioral Velocity** implementation delivered in Milestone 3B.

The review examined sliding-window correctness, atomicity, idempotency, feature leakage, monetary correctness, Redis production readiness, geo-spatial travel mathematics, pipeline latency claims, and test suite completeness across all 8 mandated dimensions.

### Audit Summary Matrix
| Audit Dimension | Evaluation Result | Risk Severity | Key Finding Summary |
| :--- | :---: | :---: | :--- |
| **1. Sliding-Window Correctness** | **SATISFACTORY** | Medium | Window slicing is mathematically exact; memory cleanup in Redis is $O(N)$ and not invoked by pipeline. |
| **2. Idempotency & Atomicity** | **DEFICIENT** | **HIGH** | 7-day idempotency TTL vs 30-day feature window enables Day 8 replay; non-atomic check/record creates race condition. |
| **3. Feature Leakage** | **VERIFIED** | Low | Features are strictly computed prior to state persistence; pre-transaction isolation verified. |
| **4. Monetary Correctness** | **DEFICIENT** | **HIGH** | Multi-currency transactions (USD, JPY, EUR) are summed directly without FX conversion, causing 100x baseline distortion. |
| **5. Redis Production Readiness** | **PROVISIONAL** | Medium | Only verified against in-memory mock client; zero live Redis integration testing conducted. |
| **6. Geo-Spatial Correctness** | **SATISFACTORY** | Medium | Haversine formula and CNP bypass are correct; Redis location update unconditionally overwrites on out-of-order events. |
| **7. Pipeline Performance** | **QUALIFIED** | Low | "<1ms" claim reflects single-thread in-memory micro-benchmark on 3 items, not production load or Redis network sockets. |
| **8. Test & Warning Audit** | **ACCEPTABLE** | Low | 78/78 tests pass; 17/18 warnings caused by missing salt fixtures; multi-currency, concurrency, and live Redis tests missing. |

---

## 2. Categorized Findings & Code Locations

```
Finding Summary Breakdown:
  [CRITICAL] : 0
  [HIGH]     : 3
  [MEDIUM]   : 4
  [LOW]      : 3
  Total Findings: 10
```

### 2.1 Critical Findings (0)
*No Critical security vulnerabilities, remote code execution risks, SQL/NoSQL injections, or cleartext PAN exposures were detected. PCI-DSS Level 1 compliance is preserved.*

---

### 2.2 High-Severity Findings (3)

#### Finding CURR-01: Cross-Currency Spend Summation Without Normalization
- **Severity:** High
- **Files Affected:**  
  - [in_memory_store.py#L163-L165](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/in_memory_store.py#L163-L165)  
  - [redis_store.py#L168-L175](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/redis_store.py#L168-L175)
- **Description:**  
  Both `InMemorySlidingWindowStore` and `RedisSlidingWindowStore` record and sum transaction amounts directly without inspecting `tx.currency` or converting to a common base currency (e.g., USD base):
  ```python
  # in_memory_store.py:163
  sum_1h = round(sum(e[1] for e in events_1h), 2)
  sum_24h = round(sum(e[1] for e in events_24h), 2)
  ```
  If a cardholder conducts a transaction in New York for $50.00 USD, and later transacts in Tokyo for ¥10,000 JPY, the store computes:
  $$\text{Spend}_{24\text{h}} = 50.0 + 10,000.0 = 10,050.0$$
  Instead of converting ¥10,000 JPY to approximately $65.00 USD (yielding ~$115.00 USD), the feature store treats JPY as USD. This creates a 100x artificial spend spike, corrupts the 30-day baseline mean ($\mu_{30\text{d}}$), and produces distorted $z$-scores ($Z_{30\text{d}}$).
- **Remediation Required:**  
  Introduce a `CurrencyNormalizer` service that converts all amounts to a configured base currency (USD) at ingestion before recording to sliding windows, or maintain currency-partitioned sliding windows.

---

#### Finding IDEMP-01: Idempotency Window Shorter Than Feature Sliding Window (Day 8 Replay Attack)
- **Severity:** High
- **Files Affected:**  
  - [redis_store.py#L32-L33](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/redis_store.py#L32-L33)  
  - [base.py#L19](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/base.py#L19)
- **Description:**  
  `DEFAULT_IDEMPOTENCY_TTL_SECONDS` is set to 7 days ($604,800\text{s}$), whereas the account baseline sliding window is 30 days ($2,592,000\text{s}$).
  ```python
  DEFAULT_KEY_TTL_SECONDS = 31 * 86400         # 31 days
  DEFAULT_IDEMPOTENCY_TTL_SECONDS = 7 * 86400  # 7 days
  ```
  If a payment gateway or adversary replays transaction $T_1$ on Day 8:
  1. The Redis key `fs3:idemp:{tx_1}` has expired and no longer exists.
  2. `is_duplicate_transaction(tx_1)` returns `False`.
  3. The replayed transaction is treated as a new transaction and accepted.
  4. While Redis ZSET prevents duplicate members with identical member strings, the transaction is processed through the pipeline, generating false alerts and triggering downstream duplicate authorization requests.
- **Remediation Required:**  
  Align the idempotency TTL to at least the maximum feature window: `DEFAULT_IDEMPOTENCY_TTL_SECONDS = 31 * 86400` (31 days).

---

#### Finding RACE-01: Non-Atomic Pre-Check and Registration Race Condition
- **Severity:** High
- **Files Affected:**  
  - [pipeline.py#L46-L50](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/pipeline.py#L46-L50)  
  - [pipeline.py#L117](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/pipeline.py#L117)
- **Description:**  
  In `StreamingFeaturePipeline.enrich()`:
  - Step 1 checks idempotency: `self.store.is_duplicate_transaction(tx.transaction_id)`
  - Steps 2–5 query velocity, impossible travel, and temporal features.
  - Step 6 persists the transaction: `self.store.record_transaction(tx)`.
  
  Under concurrent execution across multiple worker threads or API replicas receiving the exact same `transaction_id`:
  1. Request A and Request B both execute Step 1 concurrently. Both receive `False`.
  2. Both calculate features.
  3. Request A executes `record_transaction()` and succeeds (`SETNX` returns True).
  4. Request B executes `record_transaction()`. Inside `record_transaction()`, `SETNX` returns False.
  5. However, line 117 of `pipeline.py` **discards the return value** of `record_transaction(tx)`:
     ```python
     # Step 6: Persist transaction event into feature store
     self.store.record_transaction(tx)  # Return value ignored!
     ```
  6. Request B returns an `EnrichedFeatureVector` with `is_duplicate=False`, successfully bypassing duplicate detection.
- **Remediation Required:**  
  Capture the return value of `record_transaction(tx)`. If `record_transaction()` returns `False`, mark `is_duplicate=True` on the emitted feature vector. Alternatively, execute atomic reservation (`SETNX`) at the very beginning of the pipeline.

---

### 2.3 Medium-Severity Findings (4)

#### Finding PERF-01: Unbounded Growth & $O(N)$ Scan-Based Eviction in Redis
- **Severity:** Medium
- **Files Affected:**  
  - [redis_store.py#L228-L239](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/redis_store.py#L228-L239)  
  - [pipeline.py#L117](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/pipeline.py#L117)
- **Description:**  
  1. `record_transaction()` in `redis_store.py` never trims expired ZSET elements on write; it only refreshes the key-level TTL. If an active cardholder transacts once every 10 days, the key never expires and the ZSET grows indefinitely.
  2. The cleanup method `prune_expired()` uses `client.scan_iter("fs3:*:txs")` and issues sequential `zremrangebyscore` calls per key from Python. Over 1,000,000 active cards, this causes 1,000,000 sequential network round-trips (~15–20 minutes of Redis CPU load).
  3. `StreamingFeaturePipeline` never invokes `prune_expired()`, meaning `InMemorySlidingWindowStore` also leaks memory monotonically unless externally triggered.
- **Remediation Required:**  
  Perform lightweight write-time trimming on active keys: during `record_transaction()`, add `pipe.zremrangebyscore(card_k, "-inf", f"({epoch - 2592000}")` to the write pipeline.

---

#### Finding GEO-01: Redis Terminal Location Overwritten by Out-of-Order Events
- **Severity:** Medium
- **Files Affected:**  
  - [redis_store.py#L116-L121](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/redis_store.py#L116-L121)  
  - [in_memory_store.py#L82-L89](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/in_memory_store.py#L82-L89)
- **Description:**  
  In `InMemorySlidingWindowStore`:
  ```python
  if current_last is None or tx.timestamp >= current_last.timestamp:
      self._last_locations[tx.card_pan_token] = GeoLocation(...)
  ```
  An out-of-order historical event does NOT overwrite a newer physical location.  
  However, in `RedisSlidingWindowStore`:
  ```python
  pipe.hset(loc_k, mapping=loc_data)  # Unconditional overwrite!
  ```
  An arriving delayed transaction from 3 days ago unconditionally overwrites the card's current physical terminal location in Redis, causing future transactions to compute impossible travel against a 3-day-old location.
- **Remediation Required:**  
  Use a Redis Lua script or read-check to ensure the hash timestamp is only updated if `tx.timestamp >= current_hash_timestamp`.

---

#### Finding TIME-01: Naive Datetime Timezone Ambiguity in Canonical Schema
- **Severity:** Medium
- **Files Affected:**  
  - [canonical.py#L58](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/schemas/canonical.py#L58)
- **Description:**  
  `CanonicalTransaction.timestamp` is defined as `datetime = Field(...)` without an explicit timezone validator. In Python, calling `.timestamp()` on a naive datetime assumes host machine local time (e.g., IST, EST). If transactions with naive datetimes are processed on distributed cluster nodes in different timezones, `epoch` calculations shift by several hours.
- **Remediation Required:**  
  Add `@field_validator("timestamp")` in `canonical.py` that converts naive datetimes to UTC or enforces `tzinfo is not None`.

---

#### Finding RESIL-01: Lack of Mid-Stream Redis Connection Failure Recovery
- **Severity:** Medium
- **Files Affected:**  
  - [pipeline.py#L75-L117](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/pipeline.py#L75-L117)
- **Description:**  
  The factory `get_feature_store('auto')` checks Redis connectivity only at initialization (`client.ping()`). If Redis becomes unreachable during streaming operations, `pipeline.enrich()` will crash with an unhandled `redis.exceptions.ConnectionError` rather than falling back to degraded mode or raising a recoverable error.
- **Remediation Required:**  
  Wrap Redis store operations in circuit-breaker / try-except patterns with structured error logging or transient in-memory buffering.

---

### 2.4 Low-Severity Findings (3)

#### Finding BENCH-01: Unqualified Sub-1ms Benchmark Latency Claim
- **Severity:** Low
- **Files Affected:**  
  - [PHASE_2_MILESTONE_3B_IMPLEMENTATION_REPORT.md:Section 9](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/documentation/PHASE_2_MILESTONE_3B_IMPLEMENTATION_REPORT.md#L307)
- **Description:**  
  The report claims "Transforms CanonicalTransaction into EnrichedFeatureVector in <1ms". This metric was recorded exclusively in unit tests using `InMemorySlidingWindowStore` on timelines containing 1 to 3 items. Under real Redis networking with TCP round-trips, pipelining, and 1,000+ items per ZSET, latency is expected to be 2–5ms.
- **Remediation Required:**  
  Qualify latency metrics as "In-memory micro-benchmark (<1ms); production Redis latency subject to network RTT".

---

#### Finding IDEMP-02: Global Transaction ID Namespace Collision Risk
- **Severity:** Low
- **Files Affected:**  
  - [redis_store.py#L64](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/app/v3/feature_store/redis_store.py#L64)
- **Description:**  
  Idempotency keys are formatted as `fs3:idemp:{tx_id}`. If two independent merchants submit transactions with identical sequential IDs (e.g., `10001`), the second merchant's transaction will be falsely rejected as a duplicate.
- **Remediation Required:**  
  Scope idempotency keys as `fs3:idemp:{merchant_id}:{tx_id}`.

---

#### Finding WARN-01: Pytest RuntimeWarning Noise From Development Salt
- **Severity:** Low
- **Files Affected:**  
  - `backend/tests/test_v3/test_generic_json_adapter.py`  
  - `backend/tests/test_v3/test_ieee_cis_adapter.py`  
  - `backend/tests/test_v3/test_iso8583_adapter.py`
- **Description:**  
  17 of the 18 warnings reported by pytest are `RuntimeWarning: KmsTokenService: Using default development salt. Do not use in production.` because test cases instantiate adapters with `token_service=None`.
- **Remediation Required:**  
  Provide a pytest fixture or conftest setting `FRAUDSHIELD_TOKEN_SALT` environment variable during test sessions.

---

## 3. Mock Versus Real Redis Verification Assessment

### Current Verification Status:
- **Mock Verification:** Completed and passing. [test_redis_store_mock.py](file:///C:/Users/LENOVO/Desktop/FraudShield-AI/backend/tests/test_v3/test_redis_store_mock.py) successfully verifies command sequencing, ZSET score filtering, HASH writes, and pipeline batching against an in-memory dictionary mock.
- **Live Redis Verification:** **NOT CONDUCTED.** No integration test was executed against a real running Redis daemon (`redis-server`).
- **Operational Risk Assessment:**  
  The Redis data structure design (`ZSET`, `SETNX`, `HASH`) is standard and idiomatic. However, live integration testing is required to validate actual Redis server behaviors, such as:
  1. Lua script atomicity.
  2. Memory footprint under high card cardinality.
  3. Connection pool timeouts under concurrent threads.

---

## 4. Test Evidence & Automated Test Audit

Full execution of the test suite confirmed 78/78 passing tests:
```powershell
.\venv\Scripts\python.exe -m pytest backend/tests -v
======================= 78 passed, 18 warnings in 6.02s =======================
```

### Warning Audit Breakdown:
- **Warning 1:** `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated` (Legacy FraudShield 1.0 test suite).
- **Warnings 2–18 (17 warnings):** `RuntimeWarning: KmsTokenService: Using default development salt. Do not use in production.` (Expected behavior when testing with unconfigured environment secret).

### Missing Test Scenarios Identified:
1. `test_multi_currency_card_velocity`: Verify handling when card transacts in mixed currencies (USD + JPY + EUR).
2. `test_concurrent_duplicate_submission_race`: Multi-threaded test asserting atomic deduplication when two identical transactions arrive concurrently.
3. `test_redis_real_server_integration`: Live containerized Redis integration test.
4. `test_day_8_replay_window`: Asserting rejection of transactions replayed between Day 8 and Day 30.

---

## 5. Milestone 3B Acceptance Recommendation

### Verdict: **CONDITIONAL ACCEPTANCE (SAFE AS ARCHITECTURE FOUNDATION)**

The Phase 2, Milestone 3B deliverables provide a well-structured, mathematically verified, and modular streaming feature store architecture.
- **Hexagonal Boundaries:** Clean separation between ports, in-memory adapters, Redis stores, and enrichment pipelines.
- **FraudShield 1.0 Integrity:** Frozen and untouched.
- **Zero Model Contamination:** Quarantined old test split remained unaccessed.
- **Verification:** 100% test pass rate across 78 test cases.

The High-severity findings (CURR-01, IDEMP-01, RACE-01) represent real-time streaming edge cases that must be remediated prior to live banking production deployment.

---

## 6. Phase 3 LightGBM Development Authorization Verdict

### Authorization: **SAFE TO PROCEED TO PHASE 3 (Milestone 3C)**

**Justification:**
1. **IEEE-CIS Dataset Isolation:** Phase 3 involves training LightGBM on the IEEE-CIS benchmark dataset. The IEEE-CIS dataset is denominated in USD (single currency), meaning finding CURR-01 (cross-currency summation) does not impact Phase 3 training.
2. **Offline Batch Extraction:** In Phase 3, features will be generated sequentially or via tabular feature engineering; live Redis network latency, race conditions (RACE-01), and Day 8 replays (IDEMP-01) do not occur in offline training.
3. **Decoupled Architecture:** Remediations for CURR-01, IDEMP-01, and RACE-01 can be cleanly scheduled for **Phase 4 (Milestone 3D: Real-Time Serving API & Redis Integration)** without disrupting Phase 3 modeling.

---

## 7. Required Remediation Roadmap (Phase 4 Backlog)

1. **Remediate CURR-01:** Implement `BaseCurrencyConverter` to convert non-USD amounts to base USD prior to sliding-window summation.
2. **Remediate IDEMP-01:** Increase `DEFAULT_IDEMPOTENCY_TTL_SECONDS` to 31 days to match the 30-day feature aggregation window.
3. **Remediate RACE-01:** Perform atomic `SETNX` reservation in Step 1 of `StreamingFeaturePipeline`, or capture and act on `record_transaction()` return value.
4. **Remediate GEO-01:** Ensure Redis location updates verify `tx.timestamp >= current_timestamp` via Lua script.
5. **Remediate TIME-01:** Enforce UTC timezone validation on `CanonicalTransaction.timestamp`.
