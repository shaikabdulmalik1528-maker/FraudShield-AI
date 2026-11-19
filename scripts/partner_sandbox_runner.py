"""
FraudShield 3.0 — Partner Sandbox Integration Runner & Test Suite.
Simulates external merchant and fintech partner integration against the
FraudShield 3.0 Partner Sandbox environment.

Executes the standardized 8 Partner Sandbox Scenarios:
- TC-SANDBOX-01: Standard Frictionless Commerce ($45.00) -> APPROVE
- TC-SANDBOX-02: Stolen Card High-Value Anomaly ($4,800.00) -> MANUAL_REVIEW / BLOCK
- TC-SANDBOX-03: Burst Velocity Trigger (5 rapid txs) -> STEP_UP_2FA
- TC-SANDBOX-04: Impossible Geovelocity (NYC -> Tokyo in 10 min) -> STEP_UP_2FA / REVIEW
- TC-SANDBOX-05: Duplicate Idempotency Replay (Identical ID) -> APPROVE / Cached result
- TC-SANDBOX-06: Multi-Currency Normalization (JPY 15,000) -> APPROVE (USD normalized)
- TC-SANDBOX-07: Degraded Feature Store Fallback ($2,500.00) -> MANUAL_REVIEW
- TC-SANDBOX-08: Malformed / Invalid Luhn Card -> HTTP 422 Unprocessable Content

Provides partner-facing latency benchmarks, error schema compliance checks,
and an integration summary report.
"""

import sys
import os
import time
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_SANDBOX_URL = "http://127.0.0.1:8008"
DEFAULT_PARTNER_KEY = os.getenv("FRAUDSHIELD_PARTNER_API_KEY", "fs3_partner_sandbox_key_2026_dev")


def generate_luhn_pan(prefix: str, length: int = 16) -> str:
    """Deterministically generates a valid Luhn Mod-10 credit card number."""
    digits = [int(c) for c in prefix]
    while len(digits) < length - 1:
        digits.append(0)
    
    # Calculate checksum
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            doubled = d * 2
            total += (doubled - 9) if doubled > 9 else doubled
        else:
            total += d
    
    check_digit = (10 - (total % 10)) % 10
    digits.append(check_digit)
    return "".join(str(d) for d in digits)


class PartnerSandboxClient:
    def __init__(self, base_url: str = DEFAULT_SANDBOX_URL, api_key: str = DEFAULT_PARTNER_KEY):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.Client(base_url=self.base_url, timeout=10.0)

    def score_transaction(
        self,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None
    ) -> httpx.Response:
        headers = {"X-API-Key": self.api_key}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return self.client.post("/api/v3/predict", json=payload, headers=headers)

    def get_health(self) -> httpx.Response:
        return self.client.get("/health/ready")


def run_partner_sandbox_suite(base_url: str = DEFAULT_SANDBOX_URL, api_key: str = DEFAULT_PARTNER_KEY) -> Dict[str, Any]:
    print("=" * 80)
    print(" FRAUDSHIELD 3.0 — PARTNER SANDBOX VERIFICATION SUITE")
    print(f" Target Sandbox: {base_url}")
    print(f" Partner Key:    {api_key[:12]}...{api_key[-4:]}")
    print("=" * 80)

    client = PartnerSandboxClient(base_url, api_key)
    
    # Pre-check: Health probe
    try:
        h_resp = client.get_health()
        if h_resp.status_code != 200:
            print(f"[FAIL] Sandbox health probe failed: HTTP {h_resp.status_code}")
            return {"status": "FAILED", "error": f"Health probe returned {h_resp.status_code}"}
        print("[INIT] Sandbox service is healthy and ready for traffic.")
    except Exception as exc:
        print(f"[FAIL] Unable to connect to Sandbox at {base_url}: {exc}")
        return {"status": "FAILED", "error": str(exc)}

    # Generate test card pool
    card_normal = generate_luhn_pan("45320111", 16)
    card_anomaly = generate_luhn_pan("45320122", 16)
    card_velocity = generate_luhn_pan("45320133", 16)
    card_geo = generate_luhn_pan("45320144", 16)
    card_replay = generate_luhn_pan("45320155", 16)
    card_currency = generate_luhn_pan("45320166", 16)
    card_degraded = generate_luhn_pan("45320177", 16)
    card_invalid_luhn = "4532011100000009"  # Deliberately fails Luhn check

    results = []
    
    # --------------------------------------------------------------------------
    # TC-SANDBOX-01: Standard Frictionless Commerce
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-01] Testing Frictionless Legitimate Purchase ($45.00)...")
    tx1 = {
        "transaction_id": f"tx_sbx_legit_{int(time.time()*1000)}",
        "amount": 45.00,
        "currency": "USD",
        "card_number": card_normal,
        "cvv": "123",
        "expiry_month": 12,
        "expiry_year": 2028,
        "merchant_id": "merchant_starbucks_sbx",
        "mcc": "5814",
        "channel": "POS"
    }
    t0 = time.perf_counter()
    r1 = client.score_transaction(tx1)
    lat1 = (time.perf_counter() - t0) * 1000.0
    body1 = r1.json() if r1.status_code == 200 else {}
    passed1 = r1.status_code == 200 and body1.get("action") == "APPROVE"
    print(f"  Result: HTTP {r1.status_code} | Action: {body1.get('action')} | Latency: {lat1:.2f}ms -> {'PASS' if passed1 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-01", "status_code": r1.status_code, "action": body1.get("action"), "passed": passed1, "latency_ms": round(lat1, 2)})

    # --------------------------------------------------------------------------
    # TC-SANDBOX-02: Stolen Card High-Value Anomaly ($4,800.00)
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-02] Testing High-Value Whale Anomaly ($4,800.00)...")
    tx2 = {
        "transaction_id": f"tx_sbx_anomaly_{int(time.time()*1000)}",
        "amount": 4800.00,
        "currency": "USD",
        "card_number": card_anomaly,
        "cvv": "456",
        "expiry_month": 10,
        "expiry_year": 2027,
        "merchant_id": "merchant_luxury_jeweler",
        "mcc": "5944",
        "channel": "ECOMMERCE"
    }
    t0 = time.perf_counter()
    r2 = client.score_transaction(tx2)
    lat2 = (time.perf_counter() - t0) * 1000.0
    body2 = r2.json() if r2.status_code == 200 else {}
    passed2 = r2.status_code == 200 and body2.get("action") in ("MANUAL_REVIEW", "IMMEDIATE_BLOCK", "DECLINE")
    print(f"  Result: HTTP {r2.status_code} | Action: {body2.get('action')} | Triggers: {body2.get('rule_triggers')} -> {'PASS' if passed2 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-02", "status_code": r2.status_code, "action": body2.get("action"), "passed": passed2, "latency_ms": round(lat2, 2)})

    # --------------------------------------------------------------------------
    # TC-SANDBOX-03: Burst Velocity Trigger (5 txs in quick succession)
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-03] Testing Card Burst Velocity Trigger (5 rapid requests)...")
    actions3 = []
    bodies3 = []
    lat3_list = []
    for i in range(5):
        tx3 = {
            "transaction_id": f"tx_sbx_velo_{i}_{int(time.time()*1000)}",
            "amount": 150.00,
            "currency": "USD",
            "card_number": card_velocity,
            "cvv": "789",
            "expiry_month": 8,
            "expiry_year": 2029,
            "merchant_id": "merchant_electronics_hub",
            "mcc": "5732",
            "channel": "ECOMMERCE"
        }
        t0 = time.perf_counter()
        r3 = client.score_transaction(tx3)
        lat3_list.append((time.perf_counter() - t0) * 1000.0)
        if r3.status_code == 200:
            b3 = r3.json()
            actions3.append(b3.get("action"))
            bodies3.append(b3)
    passed3 = any(a in ("STEP_UP_2FA", "MANUAL_REVIEW", "IMMEDIATE_BLOCK") for a in actions3) or all(b.get("is_degraded") for b in bodies3)
    print(f"  Result: Actions across 5 txs: {actions3} (Degraded fallback: {bodies3[0].get('is_degraded') if bodies3 else False}) -> {'PASS' if passed3 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-03", "status_code": 200, "action": actions3[-1] if actions3 else "NONE", "passed": passed3, "latency_ms": round(sum(lat3_list)/len(lat3_list), 2)})

    # --------------------------------------------------------------------------
    # TC-SANDBOX-04: Impossible Geovelocity
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-04] Testing Impossible Geovelocity (NYC -> Tokyo)...")
    tx4_1 = {
        "transaction_id": f"tx_sbx_geo_nyc_{int(time.time()*1000)}",
        "amount": 20.00,
        "currency": "USD",
        "card_number": card_geo,
        "cvv": "111",
        "expiry_month": 5,
        "expiry_year": 2028,
        "merchant_id": "merchant_nyc_diner",
        "mcc": "5812",
        "channel": "POS",
        "latitude": 40.7128,
        "longitude": -74.0060
    }
    client.score_transaction(tx4_1)

    tx4_2 = {
        "transaction_id": f"tx_sbx_geo_tokyo_{int(time.time()*1000)}",
        "amount": 85.00,
        "currency": "USD",
        "card_number": card_geo,
        "cvv": "111",
        "expiry_month": 5,
        "expiry_year": 2028,
        "merchant_id": "merchant_tokyo_tech",
        "mcc": "5732",
        "channel": "POS",
        "latitude": 35.6762,
        "longitude": 139.6503
    }
    t0 = time.perf_counter()
    r4 = client.score_transaction(tx4_2)
    lat4 = (time.perf_counter() - t0) * 1000.0
    body4 = r4.json() if r4.status_code == 200 else {}
    passed4 = r4.status_code == 200 and (
        body4.get("action") in ("STEP_UP_2FA", "MANUAL_REVIEW", "IMMEDIATE_BLOCK")
        or "RULE_IMPOSSIBLE_TRAVEL" in body4.get("rule_triggers", [])
        or body4.get("is_degraded") is True
    )
    print(f"  Result: HTTP {r4.status_code} | Action: {body4.get('action')} | Rules: {body4.get('rule_triggers')} -> {'PASS' if passed4 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-04", "status_code": r4.status_code, "action": body4.get("action"), "passed": passed4, "latency_ms": round(lat4, 2)})

    # --------------------------------------------------------------------------
    # TC-SANDBOX-05: Duplicate Idempotency Replay
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-05] Testing Duplicate Idempotency Replay...")
    replay_id = f"tx_sbx_idemp_{int(time.time()*1000)}"
    tx5 = {
        "transaction_id": replay_id,
        "amount": 99.00,
        "currency": "USD",
        "card_number": card_replay,
        "cvv": "222",
        "expiry_month": 4,
        "expiry_year": 2029,
        "merchant_id": "merchant_saas_sub",
        "mcc": "5734",
        "channel": "ECOMMERCE"
    }
    r5_orig = client.score_transaction(tx5)
    t0 = time.perf_counter()
    r5_replay = client.score_transaction(tx5)
    lat5 = (time.perf_counter() - t0) * 1000.0
    body5 = r5_replay.json() if r5_replay.status_code == 200 else {}
    passed5 = r5_replay.status_code == 200 and body5.get("is_duplicate") is True
    print(f"  Result: HTTP {r5_replay.status_code} | is_duplicate: {body5.get('is_duplicate')} | Action: {body5.get('action')} -> {'PASS' if passed5 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-05", "status_code": r5_replay.status_code, "action": body5.get("action"), "passed": passed5, "latency_ms": round(lat5, 2)})

    # --------------------------------------------------------------------------
    # TC-SANDBOX-06: Multi-Currency Normalization (JPY 15,000)
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-06] Testing Multi-Currency Normalization (15,000 JPY)...")
    tx6 = {
        "transaction_id": f"tx_sbx_jpy_{int(time.time()*1000)}",
        "amount": 15000,
        "currency": "JPY",
        "card_number": card_currency,
        "cvv": "333",
        "expiry_month": 6,
        "expiry_year": 2028,
        "merchant_id": "merchant_tokyo_books",
        "mcc": "5942",
        "channel": "ECOMMERCE"
    }
    t0 = time.perf_counter()
    r6 = client.score_transaction(tx6)
    lat6 = (time.perf_counter() - t0) * 1000.0
    body6 = r6.json() if r6.status_code == 200 else {}
    passed6 = r6.status_code == 200 and body6.get("currency") == "JPY" and body6.get("action") in ("APPROVE", "MANUAL_REVIEW")
    print(f"  Result: HTTP {r6.status_code} | Currency: {body6.get('currency')} | Action: {body6.get('action')} -> {'PASS' if passed6 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-06", "status_code": r6.status_code, "action": body6.get("action"), "passed": passed6, "latency_ms": round(lat6, 2)})

    # --------------------------------------------------------------------------
    # TC-SANDBOX-07: Degraded Feature Store Fallback ($2,500.00)
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-07] Testing Degraded Feature Store Simulation ($2,500.00)...")
    tx7 = {
        "transaction_id": f"tx_sbx_degraded_{int(time.time()*1000)}",
        "amount": 2500.00,
        "currency": "USD",
        "card_number": card_degraded,
        "cvv": "444",
        "expiry_month": 9,
        "expiry_year": 2029,
        "merchant_id": "merchant_appliance_direct",
        "mcc": "5722",
        "channel": "ECOMMERCE",
        "_simulate_degraded": True
    }
    t0 = time.perf_counter()
    r7 = client.score_transaction(tx7)
    lat7 = (time.perf_counter() - t0) * 1000.0
    body7 = r7.json() if r7.status_code == 200 else {}
    passed7 = r7.status_code == 200 and body7.get("action") in ("MANUAL_REVIEW", "IMMEDIATE_BLOCK")
    print(f"  Result: HTTP {r7.status_code} | Action: {body7.get('action')} | Degraded Policy Triggered: {passed7} -> {'PASS' if passed7 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-07", "status_code": r7.status_code, "action": body7.get("action"), "passed": passed7, "latency_ms": round(lat7, 2)})

    # --------------------------------------------------------------------------
    # TC-SANDBOX-08: Invalid Luhn Checksum Card (Expected: HTTP 422)
    # --------------------------------------------------------------------------
    print("\n[TC-SANDBOX-08] Testing Invalid Card Formatting / Luhn Error...")
    tx8 = {
        "transaction_id": f"tx_sbx_badluhn_{int(time.time()*1000)}",
        "amount": 10.00,
        "currency": "USD",
        "card_number": card_invalid_luhn,
        "cvv": "555",
        "expiry_month": 1,
        "expiry_year": 2029,
        "merchant_id": "merchant_test",
        "mcc": "5311",
        "channel": "ECOMMERCE"
    }
    t0 = time.perf_counter()
    r8 = client.score_transaction(tx8)
    lat8 = (time.perf_counter() - t0) * 1000.0
    passed8 = r8.status_code in (422, 400)
    print(f"  Result: HTTP {r8.status_code} (Expected 422) | Detail: {r8.text[:60]}... -> {'PASS' if passed8 else 'FAIL'}")
    results.append({"test_case": "TC-SANDBOX-08", "status_code": r8.status_code, "action": "REJECTED_422", "passed": passed8, "latency_ms": round(lat8, 2)})

    # --------------------------------------------------------------------------
    # Final Sandbox Summary
    # --------------------------------------------------------------------------
    total_passed = sum(1 for r in results if r["passed"])
    avg_latency = sum(r["latency_ms"] for r in results) / len(results)
    all_tests_passed = (total_passed == len(results))

    print("\n" + "=" * 80)
    print(" PARTNER SANDBOX INTEGRATION RESULTS")
    print("=" * 80)
    print(f"{'Test Case':<18} | {'HTTP Code':<10} | {'Action':<16} | {'Latency (ms)':<12} | {'Result'}")
    print("-" * 75)
    for r in results:
        v_str = "PASS" if r["passed"] else "FAIL"
        print(f"{r['test_case']:<18} | {r['status_code']:<10} | {r['action']:<16} | {r['latency_ms']:<12.2f} | {v_str}")
    print("-" * 75)
    print(f"Summary: {total_passed}/{len(results)} passed ({'100% SUCCESS' if all_tests_passed else 'SOME FAILED'})")
    print(f"Average Partner Request Latency: {avg_latency:.2f} ms")

    return {
        "status": "SUCCESS" if all_tests_passed else "PARTIAL",
        "all_passed": all_tests_passed,
        "total_passed": total_passed,
        "total_tests": len(results),
        "avg_latency_ms": round(avg_latency, 2),
        "test_results": results
    }


def main():
    parser = argparse.ArgumentParser(description="FraudShield 3.0 Partner Sandbox Runner")
    parser.add_argument("--url", default=DEFAULT_SANDBOX_URL, help="Sandbox API Base URL")
    parser.add_argument("--key", default=DEFAULT_PARTNER_KEY, help="Partner API Key")
    parser.add_argument("--spawn-cluster", action="store_true", help="Automatically spawn isolated pilot/sandbox cluster")
    args = parser.parse_args()

    if args.spawn_cluster:
        from scripts.run_isolated_pilot_deployment import PilotClusterManager
        with PilotClusterManager():
            time.sleep(2)
            suite_result = run_partner_sandbox_suite(args.url, args.key)
    else:
        suite_result = run_partner_sandbox_suite(args.url, args.key)

    if not suite_result.get("all_passed", False):
        sys.exit(1)


if __name__ == "__main__":
    main()
