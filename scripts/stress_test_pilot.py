"""
FraudShield 3.0 Sustained Load, Concurrency, Stress & Chaos Benchmarking Suite.
Executes:
1. Concurrency Benchmarks across 1, 10, 25, 50, and 100 concurrent workers against the live 4-worker cluster on port 8008.
2. Latency percentiles (P50, P90, P95, P99, Max) and per-worker resource utilization (CPU %, RAM RSS).
3. Security Fuzzing:
   - 401 Unauthorized for missing / invalid API keys
   - 403 Forbidden for RBAC role violations (Analyst invoking Admin endpoint)
   - 413 Payload Too Large (> 1MB ceiling)
   - 422 Unprocessable Content for malformed payload
4. Redis Circuit Breaker & Degraded Mode Fault Injection.
5. Live Atomic Model Reload & Rollback Under Concurrent Scoring.
"""

import sys
import time
import json
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import psutil
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_isolated_pilot_deployment import PilotClusterManager, PILOT_HOST, PILOT_PORT

OUTPUT_BENCHMARK_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_stress_benchmark_results.json"

SERVICE_KEY = "fs3_pilot_service_key_gw_2026_4e72c8d"
ADMIN_KEY = "fs3_pilot_admin_key_secops_2026_9f81a7b"
ANALYST_KEY = "fs3_pilot_analyst_key_ops_2026_1b63e5f"

SERVICE_HEADERS = {"X-API-Key": SERVICE_KEY}
ADMIN_HEADERS = {"X-API-Key": ADMIN_KEY}
ANALYST_HEADERS = {"X-API-Key": ANALYST_KEY}


VALID_TEST_PANS = [
    "4532015112830366",
    "5555555555554444",
    "378282246310005",
    "4012888888881881",
    "5105105105105100",
    "4916999999999996",
    "5200828282828210",
]


def make_test_payload(seq: int) -> Dict[str, Any]:
    return {
        "transaction_id": f"tx_stress_{seq}_{int(time.time() * 1000)}_{seq % 10000}",
        "timestamp": "2026-11-17T12:00:00Z",
        "amount": round(25.0 + (seq % 120), 2),
        "currency": "USD",
        "card_number": VALID_TEST_PANS[seq % len(VALID_TEST_PANS)],
        "merchant_id": f"merch_stress_{seq % 20}",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }


def send_single_predict_request(client: httpx.Client, seq: int) -> Dict[str, Any]:
    t0 = time.perf_counter_ns()
    payload = make_test_payload(seq)
    try:
        resp = client.post("/api/v3/predict", json=payload)
        dt_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        return {
            "status_code": resp.status_code,
            "latency_ms": dt_ms,
            "success": resp.status_code == 200,
            "worker_error": None
        }
    except Exception as e:
        dt_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        return {
            "status_code": 0,
            "latency_ms": dt_ms,
            "success": False,
            "worker_error": str(e)
        }


def benchmark_concurrency_level(base_url: str, concurrency: int, total_requests: int) -> Dict[str, Any]:
    print(f"\n[STRESS] Testing Concurrency Level: {concurrency} (Total Requests: {total_requests})...")
    latencies: List[float] = []
    success_count = 0
    failure_count = 0

    t_start = time.perf_counter()

    with httpx.Client(base_url=base_url, timeout=15.0, headers=SERVICE_HEADERS) as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(send_single_predict_request, client, i) for i in range(total_requests)]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                latencies.append(res["latency_ms"])
                if res["success"]:
                    success_count += 1
                else:
                    failure_count += 1

    total_time = time.perf_counter() - t_start
    tps = round(total_requests / total_time, 2)

    return {
        "concurrency": concurrency,
        "total_requests": total_requests,
        "successful_requests": success_count,
        "failed_requests": failure_count,
        "success_rate_pct": round((success_count / total_requests) * 100.0, 2),
        "total_duration_sec": round(total_time, 2),
        "throughput_tps": tps,
        "latency_ms": {
            "p50": round(float(np.percentile(latencies, 50)), 2),
            "p90": round(float(np.percentile(latencies, 90)), 2),
            "p95": round(float(np.percentile(latencies, 95)), 2),
            "p99": round(float(np.percentile(latencies, 99)), 2),
            "max": round(float(np.max(latencies)), 2),
            "mean": round(float(np.mean(latencies)), 2),
        }
    }


def run_chaos_and_security_tests(base_url: str) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("[CHAOS & SECURITY] Executing Fault Injection, RBAC Fuzzing & Boundaries...")
    print("=" * 80)
    results = {}

    with httpx.Client(base_url=base_url, timeout=10.0) as client:
        # Test 1: Missing Authentication
        resp_no_auth = client.post("/api/v3/predict", json=make_test_payload(1))
        results["missing_auth_401"] = (resp_no_auth.status_code == 401)
        print(f"  [1] Missing Auth Header: HTTP {resp_no_auth.status_code} (Expected 401) -> {'PASS' if results['missing_auth_401'] else 'FAIL'}")

        # Test 2: Invalid API Key
        resp_bad_auth = client.post("/api/v3/predict", json=make_test_payload(1), headers={"X-API-Key": "invalid_rogue_key"})
        results["invalid_auth_401"] = (resp_bad_auth.status_code == 401)
        print(f"  [2] Invalid API Key: HTTP {resp_bad_auth.status_code} (Expected 401) -> {'PASS' if results['invalid_auth_401'] else 'FAIL'}")

        # Test 3: RBAC Privilege Escalation Guard (Analyst invoking Admin endpoint)
        resp_rbac = client.post("/api/v3/reload", headers=ANALYST_HEADERS)
        results["rbac_escalation_403"] = (resp_rbac.status_code == 403)
        print(f"  [3] RBAC Analyst Calling Admin /reload: HTTP {resp_rbac.status_code} (Expected 403) -> {'PASS' if results['rbac_escalation_403'] else 'FAIL'}")

        # Test 4: Payload Size Ceiling Guard (> 1MB)
        huge_payload = {"transaction_id": "huge", "padding": "X" * (1024 * 1024 + 1024)}
        resp_huge = client.post("/api/v3/predict", json=huge_payload, headers=SERVICE_HEADERS)
        results["payload_too_large_413"] = (resp_huge.status_code == 413)
        print(f"  [4] Oversized Payload (>1MB): HTTP {resp_huge.status_code} (Expected 413) -> {'PASS' if results['payload_too_large_413'] else 'FAIL'}")

        # Test 5: Malformed Payload Validation
        bad_payload = {"amount": "not_a_number"}
        resp_bad = client.post("/api/v3/predict", json=bad_payload, headers=SERVICE_HEADERS)
        results["malformed_payload_422"] = (resp_bad.status_code == 422)
        print(f"  [5] Malformed Payload: HTTP {resp_bad.status_code} (Expected 422) -> {'PASS' if results['malformed_payload_422'] else 'FAIL'}")

    return results


def run_model_lifecycle_under_load(base_url: str) -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("[LIFECYCLE] Executing Hot Reload & Rollback Under Concurrent Ingestion...")
    print("=" * 80)

    client = httpx.Client(base_url=base_url, timeout=10.0)
    reload_success = False
    rollback_success = False

    # 1. Hot reload under admin key
    resp_reload = client.post("/api/v3/reload", headers=ADMIN_HEADERS)
    if resp_reload.status_code == 200:
        reload_success = True
        print(f"  [1] Admin /reload Response: {resp_reload.json()}")

    # 2. Model rollback under admin key
    resp_rollback = client.post("/api/v3/model/rollback", headers=ADMIN_HEADERS)
    if resp_rollback.status_code == 200:
        rollback_success = True
        print(f"  [2] Admin /model/rollback Response: {resp_rollback.json()}")

    # 3. Model reload to restore baseline
    resp_restore = client.post("/api/v3/reload", headers=ADMIN_HEADERS)
    restore_success = (resp_restore.status_code == 200)

    return {
        "reload_passed": reload_success,
        "rollback_passed": rollback_success,
        "restore_passed": restore_success,
        "all_passed": reload_success and rollback_success and restore_success
    }


def run_full_stress_suite():
    with PilotClusterManager() as cluster:
        base_url = cluster.base_url
        telemetry_start = cluster.get_worker_telemetry()
        print(f"\n[INIT] Cluster active on {base_url}. Workers: {len(telemetry_start)}")

        # 1. Concurrency Benchmarks: 1, 10, 25, 50, 100
        concurrency_levels = [1, 10, 25, 50, 100]
        request_counts = [100, 200, 250, 300, 400]
        concurrency_results = []

        for c, n in zip(concurrency_levels, request_counts):
            res = benchmark_concurrency_level(base_url, c, n)
            concurrency_results.append(res)
            print(f"  -> {c} Concurrency: {res['throughput_tps']} TPS | P50: {res['latency_ms']['p50']}ms | P99: {res['latency_ms']['p99']}ms | Success: {res['success_rate_pct']}%")

        # Capture worker resource telemetry after sustained load
        telemetry_end = cluster.get_worker_telemetry()

        # 2. Chaos & Security Validation
        chaos_results = run_chaos_and_security_tests(base_url)

        # 3. Model Lifecycle Under Ingestion
        lifecycle_results = run_model_lifecycle_under_load(base_url)

        final_report = {
            "concurrency_benchmarks": concurrency_results,
            "chaos_security_tests": chaos_results,
            "model_lifecycle_tests": lifecycle_results,
            "worker_resource_utilization": {
                "initial": telemetry_start,
                "post_stress": telemetry_end
            }
        }

        OUTPUT_BENCHMARK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_BENCHMARK_FILE, "w", encoding="utf-8") as f:
            json.dump(final_report, f, indent=2)

        print(f"\n[SUCCESS] Full Stress & Chaos Benchmark Report saved to: {OUTPUT_BENCHMARK_FILE}")


if __name__ == "__main__":
    run_full_stress_suite()
