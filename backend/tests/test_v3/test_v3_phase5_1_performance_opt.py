"""
Performance Optimization and Equivalence Test Suite for FraudShield 3.0 (Phase 5.1).
Validates that fast-path feature vectorization and booster inference produce mathematically
equivalent fraud probabilities to the legacy DataFrame path while executing in sub-5ms SLA.
"""

import time
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timezone

from backend.app.v3.services.engine_v3 import engine_v3
from backend.app.v3.schemas.canonical import CanonicalTransaction


def make_test_canonical(seq: int, amt: float = 125.0) -> CanonicalTransaction:
    return CanonicalTransaction(
        transaction_id=f"tx_perf_opt_{seq}_{int(time.time()*1000)}",
        timestamp=datetime.now(timezone.utc),
        amount=amt,
        currency="USD",
        card_pan_token=f"tok_perf_opt_card_{seq:04d}_pci_dss",
        card_bin="453201",
        card_last4="0366",
        card_network="VISA",
        card_type="CREDIT",
        merchant_id=f"merch_perf_{seq % 10}",
        mcc="5411",
        channel="ECOMMERCE",
        latitude=40.7128,
        longitude=-74.0060
    )


def test_fast_path_probability_equivalence_with_legacy_path():
    """
    Verifies that fast-path transform_single_enriched produces identical or within
    floating-point tolerance (1e-4) probabilities compared to slow DataFrame transformation.
    """
    bundle = engine_v3._bundle
    assert bundle is not None
    assert engine_v3.is_loaded is True

    test_amounts = [15.50, 75.00, 250.00, 850.00, 2500.00]
    for idx, amt in enumerate(test_amounts):
        canonical_tx = make_test_canonical(idx, amt=amt)
        enriched = engine_v3.pipeline.enrich(canonical_tx)

        # 1. Legacy slow DataFrame path
        raw_row = engine_v3._build_model_row(enriched)
        trans_df = bundle.preprocessor.transform(raw_row)
        if "amount_ratio_baseline" in trans_df.columns:
            trans_df["amount_ratio_baseline"] = enriched.card_amount_ratio_30d
        if "card_tx_count_historical" in trans_df.columns:
            trans_df["card_tx_count_historical"] = enriched.card_tx_count_1h
        p_slow = float(bundle.model.predict_proba(trans_df)[0, 1])

        # 2. Fast-path vector path
        feature_arr = bundle.preprocessor.transform_single_enriched(enriched)
        p_fast = float(bundle.model.model_.booster_.predict(feature_arr)[0])

        assert abs(p_slow - p_fast) < 1e-4, f"Mismatch for amt={amt}: slow={p_slow:.6f} vs fast={p_fast:.6f}"


def test_fast_path_latency_sla_under_5ms():
    """
    Verifies that fast-path single-transaction feature generation + booster inference
    consistently executes in under 5.0ms (P50 < 1.0ms).
    """
    bundle = engine_v3._bundle
    assert bundle is not None

    canonical_tx = make_test_canonical(99, amt=199.99)
    enriched = engine_v3.pipeline.enrich(canonical_tx)

    # Warmup
    for _ in range(10):
        arr = bundle.preprocessor.transform_single_enriched(enriched)
        _ = bundle.model.model_.booster_.predict(arr)

    latencies_ms = []
    for _ in range(100):
        t0 = time.perf_counter_ns()
        arr = bundle.preprocessor.transform_single_enriched(enriched)
        prob = float(bundle.model.model_.booster_.predict(arr)[0])
        dt_ms = (time.perf_counter_ns() - t0) / 1_000_000.0
        latencies_ms.append(dt_ms)

    p50 = float(np.percentile(latencies_ms, 50))
    p95 = float(np.percentile(latencies_ms, 95))
    p99 = float(np.percentile(latencies_ms, 99))

    assert p50 < 1.0, f"P50 latency {p50:.2f}ms exceeds 1.0ms SLA"
    assert p99 < 5.0, f"P99 latency {p99:.2f}ms exceeds 5.0ms SLA"


def test_end_to_end_scoring_performance():
    """
    Verifies that full engine_v3.score_transaction (adapter + feature store + model + decision engine)
    completes in under 15ms total per transaction on single-thread.
    """
    canonical_tx = make_test_canonical(100, amt=85.00)

    # Warmup
    for _ in range(5):
        engine_v3.score_transaction(canonical_tx)

    latencies = []
    for _ in range(30):
        t0 = time.perf_counter_ns()
        res = engine_v3.score_transaction(canonical_tx)
        dt = (time.perf_counter_ns() - t0) / 1_000_000.0
        latencies.append(dt)
        assert "action" in res
        assert "fraud_probability" in res

    p50 = float(np.percentile(latencies, 50))
    assert p50 < 10.0, f"End-to-end P50 latency {p50:.2f}ms exceeds 10ms target"
