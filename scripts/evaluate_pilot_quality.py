"""
FraudShield 3.0 Detection Quality & Evaluation Engine.
Evaluates the real-time serving cluster on 2,500 labeled synthetic pilot transactions.
Calculates:
- Confusion Matrix (Binary Flagged vs Approved): True Positives (TP), False Positives (FP), True Negatives (TN), False Negatives (FN).
- Classification Metrics: Precision, Recall, F1 Score, False Positive Rate (FPR), False Negative Rate (FNR).
- Strict Hard-Block Confusion Matrix: Blocked (DECLINE / IMMEDIATE_BLOCK) vs Non-Blocked.
- Multi-tier Decision Breakdown: APPROVE, STEP_UP_2FA, MANUAL_REVIEW, DECLINE, IMMEDIATE_BLOCK.
- Scenario-by-Scenario Forensic Breakdown across all 7 operational scenarios.
- End-to-end Latency percentiles across all 4 worker processes.
"""

import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_isolated_pilot_deployment import PilotClusterManager, PILOT_HOST, PILOT_PORT

DATA_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_synthetic_transactions.json"
RESULTS_FILE = PROJECT_ROOT / "data" / "processed" / "pilot_evaluation_results.json"
SERVICE_HEADERS = {"X-API-Key": "fs3_pilot_service_key_gw_2026_4e72c8d"}


def evaluate_dataset(base_url: str = f"http://{PILOT_HOST}:{PILOT_PORT}") -> Dict[str, Any]:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Synthetic dataset not found at {DATA_FILE}")

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        dataset: List[Dict[str, Any]] = json.load(f)

    print(f"\n[EVALUATION] Commencing Quality Benchmark across {len(dataset)} labeled transactions...")
    print(f"Target API Endpoint: {base_url}/api/v3/predict")

    client = httpx.Client(base_url=base_url, timeout=10.0, headers=SERVICE_HEADERS)

    # Primary Metric: Suspicious / Intervened (DECLINE, BLOCK, 2FA, REVIEW) vs Approved
    tp = 0
    fp = 0
    tn = 0
    fn = 0

    # Strict Block Metric: IMMEDIATE_BLOCK or DECLINE vs Allowed/Challenged
    strict_tp = 0
    strict_fp = 0
    strict_tn = 0
    strict_fn = 0

    actions_count: Dict[str, int] = {}
    latencies_ms: List[float] = []
    scenario_stats: Dict[str, Dict[str, Any]] = {}
    validation_errors = 0

    t_start = time.perf_counter()

    for idx, tx in enumerate(dataset):
        ground_truth = tx["ground_truth"]
        is_fraud_gt = ground_truth["is_fraud"]
        scenario = ground_truth["scenario"]

        if scenario not in scenario_stats:
            scenario_stats[scenario] = {
                "total": 0,
                "tp": 0,
                "fp": 0,
                "tn": 0,
                "fn": 0,
                "approved": 0,
                "step_up_2fa": 0,
                "manual_review": 0,
                "immediate_block": 0,
                "decline": 0,
                "duplicates_detected": 0
            }

        payload = {k: v for k, v in tx.items() if k != "ground_truth"}

        t0 = time.perf_counter_ns()
        resp = client.post("/api/v3/predict", json=payload)
        dt_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        latencies_ms.append(dt_ms)

        if resp.status_code != 200:
            validation_errors += 1
            print(f"[ERROR] Transaction {tx['transaction_id']} failed with HTTP {resp.status_code}: {resp.text}")
            continue

        pred = resp.json()
        action = pred.get("action", "DECLINE")
        actions_count[action] = actions_count.get(action, 0) + 1

        is_duplicate = pred.get("is_duplicate", False)
        is_intervened = (action != "APPROVE")
        is_strictly_blocked = action in ("DECLINE", "IMMEDIATE_BLOCK")

        scenario_stats[scenario]["total"] += 1
        if is_duplicate:
            scenario_stats[scenario]["duplicates_detected"] += 1

        if action == "APPROVE":
            scenario_stats[scenario]["approved"] += 1
        elif action == "STEP_UP_2FA":
            scenario_stats[scenario]["step_up_2fa"] += 1
        elif action == "MANUAL_REVIEW":
            scenario_stats[scenario]["manual_review"] += 1
        elif action == "IMMEDIATE_BLOCK":
            scenario_stats[scenario]["immediate_block"] += 1
        elif action == "DECLINE":
            scenario_stats[scenario]["decline"] += 1

        # Primary Matrix (Intervened vs Approved)
        if is_fraud_gt and is_intervened:
            tp += 1
            scenario_stats[scenario]["tp"] += 1
        elif not is_fraud_gt and is_intervened:
            fp += 1
            scenario_stats[scenario]["fp"] += 1
        elif not is_fraud_gt and not is_intervened:
            tn += 1
            scenario_stats[scenario]["tn"] += 1
        elif is_fraud_gt and not is_intervened:
            fn += 1
            scenario_stats[scenario]["fn"] += 1

        # Strict Block Matrix
        if is_fraud_gt and is_strictly_blocked:
            strict_tp += 1
        elif not is_fraud_gt and is_strictly_blocked:
            strict_fp += 1
        elif not is_fraud_gt and not is_strictly_blocked:
            strict_tn += 1
        elif is_fraud_gt and not is_strictly_blocked:
            strict_fn += 1

        if (idx + 1) % 500 == 0:
            print(f"  Processed {idx + 1}/{len(dataset)} transactions ({dt_ms:.2f}ms last)...")

    total_eval_time = time.perf_counter() - t_start

    # Metrics calculation
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

    strict_precision = strict_tp / (strict_tp + strict_fp) if (strict_tp + strict_fp) > 0 else 0.0
    strict_recall = strict_tp / (strict_tp + strict_fn) if (strict_tp + strict_fn) > 0 else 0.0
    strict_f1 = 2 * (strict_precision * strict_recall) / (strict_precision + strict_recall) if (strict_precision + strict_recall) > 0 else 0.0

    p50_lat = float(np.percentile(latencies_ms, 50))
    p90_lat = float(np.percentile(latencies_ms, 90))
    p95_lat = float(np.percentile(latencies_ms, 95))
    p99_lat = float(np.percentile(latencies_ms, 99))
    max_lat = float(np.max(latencies_ms))
    avg_lat = float(np.mean(latencies_ms))

    results = {
        "summary": {
            "total_transactions": len(dataset),
            "validation_errors": validation_errors,
            "eval_duration_seconds": round(total_eval_time, 2),
            "avg_throughput_tps": round(len(dataset) / total_eval_time, 2),
        },
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn,
        },
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
        },
        "strict_block_metrics": {
            "true_positives": strict_tp,
            "false_positives": strict_fp,
            "true_negatives": strict_tn,
            "false_negatives": strict_fn,
            "precision": round(strict_precision, 4),
            "recall": round(strict_recall, 4),
            "f1_score": round(strict_f1, 4),
        },
        "action_distribution": actions_count,
        "latency_percentiles_ms": {
            "p50": round(p50_lat, 2),
            "p90": round(p90_lat, 2),
            "p95": round(p95_lat, 2),
            "p99": round(p99_lat, 2),
            "max": round(max_lat, 2),
            "mean": round(avg_lat, 2),
        },
        "scenario_breakdown": scenario_stats,
    }

    print("\n" + "=" * 80)
    print("FRAUDSHIELD 3.0 — PILOT DETECTION QUALITY REPORT")
    print("=" * 80)
    print(f"Total Transactions Evaluated: {len(dataset)} (Errors: {validation_errors})")
    print(f"Confusion Matrix: TP={tp}, FP={fp}, TN={tn}, FN={fn}")
    print(f"Precision:            {precision * 100:.2f}%")
    print(f"Recall (Sensitivity): {recall * 100:.2f}%")
    print(f"F1-Score:             {f1:.4f}")
    print(f"False Positive Rate:  {fpr * 100:.2f}%")
    print(f"False Negative Rate:  {fnr * 100:.2f}%")
    print(f"\nStrict Block Metrics (DECLINE / IMMEDIATE_BLOCK):")
    print(f"  TP={strict_tp}, FP={strict_fp}, TN={strict_tn}, FN={strict_fn}")
    print(f"  Precision: {strict_precision * 100:.2f}% | Recall: {strict_recall * 100:.2f}% | F1: {strict_f1:.4f}")
    print(f"\nDecision Tier Distribution:")
    for act, cnt in actions_count.items():
        print(f"  - {act:15s}: {cnt:5d} ({cnt / len(dataset) * 100:.1f}%)")
    print(f"\nServing Latency Profile:")
    print(f"  - P50: {p50_lat:.2f} ms | P90: {p90_lat:.2f} ms | P95: {p95_lat:.2f} ms | P99: {p99_lat:.2f} ms | Max: {max_lat:.2f} ms")

    print("\nScenario Breakdown:")
    for sc, stats in scenario_stats.items():
        print(f"  [{sc}] Total: {stats['total']} | Approved: {stats['approved']} | Step-Up: {stats['step_up_2fa']} | Review: {stats['manual_review']} | Blocked: {stats['immediate_block'] + stats['decline']} | Dups: {stats['duplicates_detected']}")

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n[SUCCESS] Results written to: {RESULTS_FILE}")

    return results


def main():
    with PilotClusterManager() as cluster:
        evaluate_dataset(base_url=cluster.base_url)


if __name__ == "__main__":
    main()
