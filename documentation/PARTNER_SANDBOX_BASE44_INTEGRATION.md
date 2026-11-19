# FraudShield 3.0 — Partner Sandbox Base44 External HTTPS Integration Report

**Date:** November 17, 2026  
**System Status:** Operational & Externally Accessible  
**Target Client Origin:** `https://lush-fraud-shield-pulse.base44.app`  
**Active Tunnel Protocol:** HTTP/2 over TLS 1.3 (Cloudflare Edge Anycast)  

---

## 1. Executive Summary & Verification

The FraudShield 3.0 Partner Sandbox has been prepared, secured, and deployed for staging access from the Base44 application origin (`https://lush-fraud-shield-pulse.base44.app`).

### Verified Milestones
1. **Isolated Sandbox Server (`port 8009`):** Binds strictly to `.env.sandbox`, isolated Redis DB 2, running genuine 4-worker Uvicorn cluster with rate limits and cryptographic tokenization.
2. **CORS Hardening:** Configured in `backend/app/config.py` and `backend/app/main.py` to allow exclusively `https://lush-fraud-shield-pulse.base44.app` without insecure wildcard permissions (`allow_credentials=True`). Exposes `X-Process-Time-Ms` and `X-RateLimit-*`.
3. **PARTNER Role Scoping:**
   - Allowed: `POST /api/v3/predict`, `POST /api/v3/batch-predict`, `GET /health/sandbox`, `GET /api/v3/sandbox/health`.
   - Forbidden: `POST /api/v3/reload`, `POST /api/v3/model/rollback`, `GET /api/v3/monitoring/drift`, `GET /api/v3/status` (all strictly return HTTP 403 Forbidden).
4. **Sanitized Health Endpoint:** `/health/sandbox` and `/api/v3/sandbox/health` return safe, non-leaking JSON status (`{"status":"HEALTHY","service":"FraudShield 3.0 Partner Sandbox","environment":"sandbox"}`).
5. **Secure HTTPS Tunnel:** Cloudflare Anycast Edge tunnel established using `--protocol http2` to avoid ISP QUIC blocking.
6. **Zero Leakage:** Master salts, production `.env`, and full card PANs/CVVs are strictly guarded (PANs masked as `453201XXXXXX0005`, zero CVVs stored).
7. **Regression Suite:** All **176 tests passing** (100% green across unit, ML, security, and staging suites).

---

## 2. Core Access Parameters

| Parameter | Configuration Value |
|---|---|
| **Public HTTPS Base URL** | `https://meter-deborah-northern-audit.trycloudflare.com` |
| **Local Sandbox Port** | `8009` (`http://127.0.0.1:8009`) |
| **Whitelisted CORS Origin** | `https://lush-fraud-shield-pulse.base44.app` |
| **Dedicated PARTNER Key** | `<RETRIEVE_VIA_CLI_HELPER>` (Rotated & Protected) |
| **Header Format 1** | `X-API-Key: <ACTIVE_PARTNER_KEY>` |
| **Header Format 2** | `Authorization: Bearer <ACTIVE_PARTNER_KEY>` |
| **PARTNER Rate Limit** | 1,200 requests/min (20 QPS burst) |

---

## 3. Operational Runbook

### Starting the Sandbox Server
```powershell
.\venv\Scripts\python scripts/run_sandbox_server.py --port 8009
```

### Starting the Secure HTTPS Tunnel
```powershell
.\venv\Scripts\python scripts/run_sandbox_tunnel.py
```
*Note: The script outputs the live HTTPS Base URL and writes it to `logs/sandbox_tunnel_url.txt`.*

### Secure Credential Retrieval
```powershell
.\venv\Scripts\python scripts/get_sandbox_credentials.py
```

### Stopping the Services
- Terminate the tunnel: `Ctrl + C` in the tunnel terminal.
- Terminate the server: `Ctrl + C` in the server terminal, or kill task.

---

## 4. Live External Verification Results

### A. Health Probe
```http
GET https://meter-deborah-northern-audit.trycloudflare.com/health/sandbox HTTP/1.1
```
**Response (HTTP 200 OK):**
```json
{
  "status": "HEALTHY",
  "service": "FraudShield 3.0 Partner Sandbox",
  "environment": "sandbox"
}
```

### B. CORS Preflight (OPTIONS)
```http
OPTIONS https://meter-deborah-northern-audit.trycloudflare.com/api/v3/predict HTTP/1.1
Host: meter-deborah-northern-audit.trycloudflare.com
Origin: https://lush-fraud-shield-pulse.base44.app
Access-Control-Request-Method: POST
Access-Control-Request-Headers: X-API-Key, Content-Type
```
**Response (HTTP 200 OK):**
```http
access-control-allow-origin: https://lush-fraud-shield-pulse.base44.app
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY
access-control-allow-headers: X-API-Key, Content-Type
access-control-allow-credentials: true
```

### C. Live Prediction Test
```http
POST https://meter-deborah-northern-audit.trycloudflare.com/api/v3/predict HTTP/1.1
Host: meter-deborah-northern-audit.trycloudflare.com
Origin: https://lush-fraud-shield-pulse.base44.app
Content-Type: application/json
X-API-Key: <ACTIVE_PARTNER_KEY>

{
  "transaction_id": "tx_base44_tunnel_verify_002",
  "amount": 75.00,
  "currency": "USD",
  "card_number": "4532011100000005",
  "cvv": "123",
  "expiry_month": 12,
  "expiry_year": 2028,
  "merchant_id": "merch_base44_demo",
  "mcc": "5411",
  "channel": "ECOMMERCE"
}
```
**Response (HTTP 200 OK):**
```json
{
  "transaction_id": "tx_base44_tunnel_verify_002",
  "action": "APPROVE",
  "fraud_score": null,
  "decision_reasons": ["Model probability (0.002) is below approval cutoff (0.3)."],
  "model_version": "3.0.0-rc1"
}
```
*Response Headers:* `access-control-allow-origin: https://lush-fraud-shield-pulse.base44.app`, `x-process-time-ms: 14.05`

### D. RBAC Admin Protection (Security Assertion)
```http
GET https://meter-deborah-northern-audit.trycloudflare.com/api/v3/monitoring/drift HTTP/1.1
Host: meter-deborah-northern-audit.trycloudflare.com
X-API-Key: <ACTIVE_PARTNER_KEY>
```
**Response:** `HTTP 403 Forbidden` (`{"detail": "Operation requires ADMIN role"}`)

---

## 5. Security & Isolation Safeguards
1. **Zero Real Financial Data:** Only synthetic test cards (e.g. Luhn-valid sandbox prefix `453201...`) and test merchants may be used.
2. **Ephemeral Tunnel Architecture:** Cloudflare Tunnel operates strictly as an on-demand staging proxy. Permanent production deployments require dedicated multi-region cloud infrastructure and custom domain TLS certificates.
3. **Redacted Master Salts:** `.env.sandbox` salts and administrative encryption master keys remain isolated on the host server and are never delivered over the wire.
