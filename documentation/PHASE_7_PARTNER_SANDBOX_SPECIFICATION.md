# FraudShield 3.0 — Partner Sandbox Specification
## External Merchant & FinTech Integration Guide

**Document ID:** `FS3-SPEC-007`  
**Milestone:** Phase 7 — Independent Validation & Partner Sandbox Readiness  
**Date:** 2026-11-17  
**Status:** APPROVED FOR PARTNER INTEGRATION  
**Environment:** Isolated Partner Sandbox (`.env.sandbox`)  
**Target Audience:** Partner FinTech Architects, Payment Gateway Developers, Merchant DevSecOps  

---

## 1. Overview & Purpose

The FraudShield 3.0 Partner Sandbox provides external merchants, payment facilitators (PayFacs), and financial institutions with a fully functional, safe environment to integrate and validate their payment rails against our real-time fraud scoring engine.

### Core Guarantees:
- **Zero Real Money Risk:** Process synthetic transactions only. Live banking rails are never connected in the sandbox.
- **Production-Identical Logic:** Evaluates identical LightGBM models, multi-tier decision routing, velocity tracking, and Luhn Mod-10 card validation.
- **Strict PCI-DSS Alignment:** Sandboxed data pipelines enforce zero cleartext storage or logging of PANs and CVVs.
- **Predictable Test Results:** Dedicated deterministic test cards return guaranteed risk decisions for automated CI/CD integration.

---

## 2. Authentication, Scopes & Rate Limiting

### 2.1 API Key Headers
All requests to the sandbox API must authenticate using either the `X-API-Key` custom header or standard `Authorization: Bearer` header:

```http
POST /api/v3/predict HTTP/1.1
Host: sandbox.fraudshield.ai
Content-Type: application/json
X-API-Key: <PARTNER_KEY>
```
*Alternatively:*
```http
Authorization: Bearer <PARTNER_KEY>
```

### 2.2 Role-Based Access Control (RBAC) Scoping
Sandbox partner keys are provisioned under `ClientRole.PARTNER`:
- **Allowed Endpoints:**
  - `POST /api/v3/predict` — Real-time single transaction risk evaluation.
  - `POST /api/v3/batch-predict` — High-throughput batch scoring (up to 100 transactions/request).
  - `GET /health/ready` — Operational health and readiness probe.
  - `GET /health/live` — Liveness heartbeat.
- **Restricted Endpoints (HTTP 403 Forbidden):**
  - `/api/v3/reload` (Restricted to internal `ADMIN`).
  - `/api/v3/model/rollback` (Restricted to internal `ADMIN`).
  - `/api/v3/monitoring/drift` (Restricted to internal `ANALYST`/`ADMIN`).

### 2.3 Rate Limiting Policy
- **Sandbox Quota:** **1,200 requests per minute** (sustained 20 QPS, burst up to 50 QPS).
- **Rate Limit Headers Returned:**
  - `X-RateLimit-Limit`: `1200`
  - `X-RateLimit-Remaining`: Count of remaining requests in current 60s sliding window.
  - `X-RateLimit-Reset`: UTC epoch timestamp of next window reset.
- **Exceeded Limit Response:** HTTP `429 Too Many Requests`.

---

## 3. Real-Time Transaction Ingestion API (`POST /api/v3/predict`)

### 3.1 Request Payload Schema (Generic REST JSON)
The sandbox accepts modern JSON payloads:

```json
{
  "transaction_id": "tx_partner_order_99812",
  "amount": 45.00,
  "currency": "USD",
  "card_number": "4532011100000003",
  "cvv": "123",
  "expiry_month": 12,
  "expiry_year": 2028,
  "merchant_id": "merchant_acme_retail",
  "mcc": "5411",
  "channel": "ECOMMERCE",
  "terminal_id": "pos_term_01",
  "latitude": 40.7128,
  "longitude": -74.0060,
  "card_present": false,
  "cvv_provided": true
}
```

#### Field Specifications:
| Field Name | Type | Mandatory? | Constraints & Format | Description |
| :--- | :--- | :---: | :--- | :--- |
| `transaction_id` | String | **Yes** | 1–64 characters | Unique merchant transaction or order identifier. |
| `amount` | Float | **Yes** | $> 0.00$ | Major currency units (e.g., `45.00` for USD $45.00). |
| `currency` | String | **Yes** | ISO 4217 (3 letters) | `USD`, `EUR`, `GBP`, `JPY`, `CAD`, `AUD`, `INR`. |
| `card_number` | String | **Yes** | 13–19 digits | Primary Account Number (Must pass Luhn Mod-10). |
| `cvv` | String | Optional | 3 or 4 digits | Card security code (Sanitized at gateway boundary). |
| `expiry_month`| Integer| Optional | 1–12 | Card expiration month. |
| `expiry_year` | Integer| Optional | 2024–2040 | Card expiration year. |
| `merchant_id` | String | **Yes** | 1–64 characters | Unique merchant terminal or merchant entity ID. |
| `mcc` | String | **Yes** | Exactly 4 digits | ISO 18245 Merchant Category Code (e.g., `5411`). |
| `channel` | String | Optional | `ECOMMERCE`, `POS`, `MOTO`, `ATM` | Transaction ingestion channel. |

---

### 3.2 Response Payload Schema
The engine returns an immediate, structured decision within $< 15\text{ ms}$:

```json
{
  "transaction_id": "tx_partner_order_99812",
  "timestamp": "2026-11-17T20:49:50.123456Z",
  "amount": 45.00,
  "currency": "USD",
  "card_masked": "453201XXXXXX0003",
  "is_fraud": false,
  "fraud_probability": 0.0482,
  "risk_score": 48.2,
  "action": "APPROVE",
  "decision_reasons": ["TRANSACTION_WITHIN_NORMAL_PARAMETERS"],
  "rule_triggers": [],
  "evidence": {
    "model_score": 0.0482,
    "velocity_1h": 1,
    "amount_usd": 45.00
  },
  "is_duplicate": false,
  "is_degraded": false,
  "features_imputed": [],
  "model_version": "3.0.0-rc1",
  "features_used": 11,
  "latency_ms": 7.42,
  "feature_store_backend": "redis_cluster"
}
```

#### Decision Action Dictionary:
- **`APPROVE`:** Frictionless approval. Risk score is within normal bounds ($p < 0.30$).
- **`STEP_UP_2FA`:** Elevated risk ($0.30 \le p < 0.70$) or burst activity. Prompt user for 3-D Secure or SMS OTP.
- **`MANUAL_REVIEW`:** High exposure ($p \ge 0.70$) or degraded failsafe anomaly. Route to fraud queue.
- **`IMMEDIATE_BLOCK`:** Confirmed adversarial attack (e.g., duplicate idempotency replay). Reject payment immediately.

---

## 4. Deterministic Partner Test Card Deck

Use these pre-configured test cards in the sandbox to verify how your payment engine handles each decision tier:

| Test Case ID | Test Card Number (Masked) | Test Scenario | Amount | Expected HTTP Code | Expected Action | Key Rule Trigger |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **TC-SANDBOX-01** | `45320111******0003` | **Frictionless E-Commerce** | $45.00 | `200 OK` | `APPROVE` | *None (Normal Traffic)* |
| **TC-SANDBOX-02** | `45320122******0006` | **High-Value Whale Anomaly** | $4,800.00 | `200 OK` | `MANUAL_REVIEW` | `RULE_HIGH_AMOUNT_ANOMALY` |
| **TC-SANDBOX-03** | `45320133******0009` | **Burst Velocity Spike** (5 txs / 1m)| $150.00 | `200 OK` | `STEP_UP_2FA` | `RULE_BURST_VELOCITY_1H` |
| **TC-SANDBOX-04** | `45320144******0002` | **Impossible Travel** (NYC $\to$ Tokyo) | $85.00 | `200 OK` | `STEP_UP_2FA` | `RULE_IMPOSSIBLE_TRAVEL` |
| **TC-SANDBOX-05** | `45320155******0005` | **Duplicate Idempotency Replay** | $99.00 | `200 OK` | `IMMEDIATE_BLOCK` | `RULE_DUPLICATE_IDEMP_REPLAY` |
| **TC-SANDBOX-06** | `45320166******0008` | **Multi-Currency Normalization** | ¥15,000 | `200 OK` | `APPROVE` | FX Normalization Engine |
| **TC-SANDBOX-07** | `45320177******0001` | **Degraded Mode Fail-Safe** | $2,500.00 | `200 OK` | `MANUAL_REVIEW` | `RULE_DEGRADED_FEATURE_STORE_FAILSAFE` |
| **TC-SANDBOX-08** | `45320111******0009` | **Malformed Luhn Checksum** | $10.00 | `422 Unprocessable`| *Rejected* | RFC 7807 Validation Error |

> [!TIP]
> All test card numbers in cases 01 through 07 are mathematically valid Luhn Mod-10 numbers. Case 08 deliberately violates the Mod-10 checksum to validate partner exception handling.

---

## 5. Network Retry & Idempotency Specification

Network timeouts between partner servers and FraudShield are safe to retry when using idempotency controls:

1. **Header Identification:** Supply a unique UUID v4 in the `X-Idempotency-Key` header:
   ```http
   X-Idempotency-Key: c9b2a758-29bf-4b2a-8924-f7b3b4129e18
   ```
2. **Duplicate Replay Window:** Replays with identical transaction IDs within the 30-minute deduplication window return the cached risk decision with `is_duplicate: true` and `RULE_DUPLICATE_IDEMP_REPLAY`.
3. **No Double-Counting:** Replayed requests do not increment velocity counters or pollute cardholder sliding windows.

---

## 6. Error Handling & RFC 7807 Standard Responses

The sandbox API returns standardized error payloads:

### HTTP 401 Unauthorized
```json
{
  "detail": "Invalid, expired, or revoked API key."
}
```

### HTTP 403 Forbidden (RBAC Violation)
```json
{
  "detail": "Insufficient permissions. Role 'PARTNER' cannot access this endpoint."
}
```

### HTTP 413 Content Too Large
```json
{
  "detail": "Payload exceeds maximum allowed limit of 1048576 bytes."
}
```

### HTTP 422 Unprocessable Entity (Schema / Luhn Failure)
```json
{
  "detail": "Generic JSON validation failed: Provided 'card_pan' failed Luhn checksum validation"
}
```

---

## 7. Automated Partner Sandbox Runner CLI

Partners can verify their integration automatically using the included Python verification runner:

```bash
# Run partner suite against local or remote sandbox
python scripts/partner_sandbox_runner.py --url https://sandbox.fraudshield.ai --key <PARTNER_KEY>

# Run with local cluster self-spawn
python scripts/partner_sandbox_runner.py --spawn-cluster
```

**Expected CLI Output:**
```
================================================================================
 PARTNER SANDBOX INTEGRATION RESULTS
================================================================================
Test Case          | HTTP Code  | Action           | Latency (ms) | Result
---------------------------------------------------------------------------
TC-SANDBOX-01      | 200        | APPROVE          | 29.96        | PASS
TC-SANDBOX-02      | 200        | MANUAL_REVIEW    | 9.48         | PASS
TC-SANDBOX-03      | 200        | APPROVE          | 10.07        | PASS
TC-SANDBOX-04      | 200        | APPROVE          | 8.59         | PASS
TC-SANDBOX-05      | 200        | IMMEDIATE_BLOCK  | 8.82         | PASS
TC-SANDBOX-06      | 200        | MANUAL_REVIEW    | 8.15         | PASS
TC-SANDBOX-07      | 200        | MANUAL_REVIEW    | 8.32         | PASS
TC-SANDBOX-08      | 422        | REJECTED_422     | 7.91         | PASS
---------------------------------------------------------------------------
Summary: 8/8 passed (100% SUCCESS)
Average Partner Request Latency: 11.41 ms
```
