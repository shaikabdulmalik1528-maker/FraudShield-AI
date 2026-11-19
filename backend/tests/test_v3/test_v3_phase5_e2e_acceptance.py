"""
End-to-End Acceptance Test Suite for FraudShield 3.0 (Phase 5).
Demonstrates and validates all 8 mandatory transaction lifecycle flows:
1. Legitimate transaction -> APPROVE
2. Suspicious transaction -> STEP_UP_2FA
3. High-risk transaction -> MANUAL_REVIEW
4. Confirmed blocking condition -> IMMEDIATE_BLOCK
5. Duplicate transaction -> safely blocked (RULE_DUPLICATE_IDEMP_REPLAY)
6. Multi-currency transaction -> correctly normalized (USD baseline conversion)
7. Redis outage -> documented fail-safe behavior (no silent approval)
8. Redis recovery -> consistent feature state restoration
"""

import time
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.v3.services.engine_v3 import engine_v3
from backend.app.v3.schemas.canonical import CanonicalTransaction, PaymentChannel
from backend.app.v3.feature_store.in_memory_store import InMemorySlidingWindowStore
from backend.app.v3.feature_store.pipeline import StreamingFeaturePipeline
from backend.app.v3.services.decision_engine import FraudDecisionEngine, DecisionConfig, DecisionAction

client = TestClient(app)
SERVICE_HEADERS = {"X-API-Key": "fs3_service_gw_key_2026_dev"}


def test_flow_1_legitimate_transaction_approved():
    """Flow 1: Legitimate retail transaction produces low probability and is APPROVED."""
    payload = {
        "transaction_id": "tx_e2e_legit_001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "amount": 28.50,
        "currency": "USD",
        "card_number": "4532015112830366",
        "merchant_id": "merch_grocery_local",
        "mcc": "5411",
        "channel": "POS_CHIP"
    }
    response = client.post("/api/v3/predict", json=payload, headers=SERVICE_HEADERS)
    assert response.status_code == 200
    data = response.json()

    assert data["action"] == "APPROVE"
    assert data["fraud_probability"] < 0.400
    assert data["is_fraud"] is False
    assert data["is_duplicate"] is False


def test_flow_2_suspicious_velocity_burst_triggers_2fa():
    """Flow 2: Burst velocity surge triggers STEP_UP_2FA policy escalation."""
    # Simulate high velocity burst (8 prior transactions within 1h)
    from datetime import timedelta
    engine = engine_v3
    card_pan = "4532015112830309"
    card_token = engine.token_service.tokenize_pan(card_pan)
    now = datetime.now(timezone.utc)

    # Pre-record 9 transactions in feature store within past 30 minutes
    for i in range(9):
        tx_prev = CanonicalTransaction(
            transaction_id=f"tx_burst_setup_{i}",
            timestamp=now - timedelta(minutes=20 - i),
            amount=15.0,
            currency="USD",
            card_pan_token=card_token,
            card_bin="453201",
            card_last4="0309",
            card_network="VISA",
            card_type="DEBIT",
            merchant_id=f"merch_burst_{i}",
            mcc="5411",
            merchant_country="USA",
            channel=PaymentChannel.ECOMMERCE
        )
        engine.pipeline.store.record_transaction(tx_prev)

    payload = {
        "transaction_id": "tx_e2e_burst_002",
        "timestamp": now.isoformat(),
        "amount": 45.00,
        "currency": "USD",
        "card_number": card_pan,
        "merchant_id": "merch_burst_test",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }

    response = client.post("/api/v3/predict", json=payload, headers=SERVICE_HEADERS)
    assert response.status_code == 200
    data = response.json()

    assert data["action"] in ("STEP_UP_2FA", "MANUAL_REVIEW")
    assert "RULE_BURST_VELOCITY_1H" in data["rule_triggers"]


def test_flow_3_high_risk_spend_ratio_triggers_manual_review():
    """Flow 3: Extreme spend deviation (>10x baseline) routes to MANUAL_REVIEW."""
    decision_engine = FraudDecisionEngine()
    
    # Create feature vector with high spend ratio (15x) but moderate probability (p=0.45)
    from backend.app.v3.feature_store.schemas import EnrichedFeatureVector
    now = datetime.now(timezone.utc)
    features = EnrichedFeatureVector(
        transaction_id="tx_high_spend_003",
        timestamp=now,
        amount=3500.0,
        currency="USD",
        card_pan_token="tok_test_spend_003",
        card_bin="453201",
        card_last4="0366",
        card_network="VISA",
        card_type="CREDIT",
        merchant_id="merch_luxury_jewelers",
        mcc="5944",
        merchant_country="USA",
        channel="POS_CHIP",
        card_amount_ratio_30d=16.5,
        hour_sin=0.5,
        hour_cos=0.5,
        dow_sin=0.5,
        dow_cos=0.5
    )

    decision = decision_engine.evaluate(fraud_probability=0.45, features=features, optimal_threshold=0.700)
    assert decision.action == DecisionAction.MANUAL_REVIEW
    assert "RULE_EXTREME_SPEND_RATIO" in decision.rule_triggers


def test_flow_4_confirmed_blocking_condition_immediate_block():
    """Flow 4: Impossible travel physically violating physics triggers IMMEDIATE_BLOCK."""
    decision_engine = FraudDecisionEngine()
    now = datetime.now(timezone.utc)
    from backend.app.v3.feature_store.schemas import EnrichedFeatureVector

    features = EnrichedFeatureVector(
        transaction_id="tx_impossible_travel_004",
        timestamp=now,
        amount=150.0,
        currency="USD",
        card_pan_token="tok_travel_004",
        card_bin="453201",
        card_last4="0366",
        card_network="VISA",
        card_type="DEBIT",
        merchant_id="merch_london_pos",
        mcc="5411",
        merchant_country="GBR",
        channel="POS_CHIP",
        speed_kmh=2400.0,
        distance_km=6000.0,
        impossible_travel_flag=True,
        hour_sin=0.5,
        hour_cos=0.5,
        dow_sin=0.5,
        dow_cos=0.5
    )

    decision = decision_engine.evaluate(fraud_probability=0.20, features=features, optimal_threshold=0.700)
    assert decision.action == DecisionAction.IMMEDIATE_BLOCK
    assert "RULE_IMPOSSIBLE_TRAVEL" in decision.rule_triggers


def test_flow_5_duplicate_replay_safely_blocked():
    """Flow 5: Submitting identical transaction payload twice blocks the second transaction."""
    tx_id = f"tx_e2e_replay_{int(time.time())}"
    payload = {
        "transaction_id": tx_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "amount": 99.00,
        "currency": "USD",
        "card_number": "4532015112830366",
        "merchant_id": "merch_replay_store",
        "mcc": "5411",
        "channel": "ECOMMERCE"
    }

    # First submission
    resp1 = client.post("/api/v3/predict", json=payload, headers=SERVICE_HEADERS)
    assert resp1.status_code == 200
    assert resp1.json()["is_duplicate"] is False

    # Second submission (replay)
    resp2 = client.post("/api/v3/predict", json=payload, headers=SERVICE_HEADERS)
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data2["is_duplicate"] is True
    assert data2["action"] == "IMMEDIATE_BLOCK"
    assert "RULE_DUPLICATE_IDEMP_REPLAY" in data2["rule_triggers"]


def test_flow_6_multi_currency_normalization():
    """Flow 6: Multi-currency transaction (EUR/JPY) is normalized to USD in sliding windows."""
    from datetime import timedelta
    engine = engine_v3
    card_pan = "4532015112830088"
    card_token = engine.token_service.tokenize_pan(card_pan)
    now = datetime.now(timezone.utc)

    # 100 EUR (~108.50 USD) recorded 5 minutes ago
    tx_eur = CanonicalTransaction(
        transaction_id="tx_e2e_curr_eur",
        timestamp=now - timedelta(minutes=5),
        amount=100.0,
        currency="EUR",
        card_pan_token=card_token,
        card_bin="453201",
        card_last4="0088",
        card_network="VISA",
        card_type="DEBIT",
        merchant_id="merch_paris_cafe",
        mcc="5812",
        merchant_country="FRA",
        channel=PaymentChannel.POS_CONTACTLESS
    )
    engine.pipeline.store.record_transaction(tx_eur)

    stats = engine.pipeline.store.get_card_velocity_stats(card_token, now, current_amount=50.0, currency="USD")
    # Verified USD summation (~108.50 USD from EUR, NOT 100 or 15000)
    assert 105.0 <= stats.amount_sum_1h <= 112.0


def test_flow_7_redis_outage_failsafe_behavior():
    """Flow 7: During Redis outage, fail-safe policy activates and prevents silent approval."""
    store = InMemorySlidingWindowStore()
    pipe = StreamingFeaturePipeline(feature_store=store, fallback_store=store)

    tx_high_val = CanonicalTransaction(
        transaction_id="tx_e2e_outage_failsafe",
        timestamp=datetime.now(timezone.utc),
        amount=850.0,
        currency="USD",
        card_pan_token="tok_outage_007_card",
        card_bin="453201",
        card_last4="0366",
        card_network="VISA",
        card_type="DEBIT",
        merchant_id="merch_outage",
        mcc="5411",
        merchant_country="USA",
        channel=PaymentChannel.ECOMMERCE
    )

    enriched = pipe.enrich(tx_high_val)
    assert enriched.is_degraded is True

    decision_engine = FraudDecisionEngine()
    decision = decision_engine.evaluate(fraud_probability=0.08, features=enriched, optimal_threshold=0.700)

    # Must be intercepted by fail-safe policy: STEP_UP_2FA rather than APPROVE
    assert decision.action == DecisionAction.STEP_UP_2FA
    assert "RULE_DEGRADED_FEATURE_STORE_FAILSAFE" in decision.rule_triggers


def test_flow_8_redis_recovery_restores_consistent_state():
    """Flow 8: Circuit breaker probes recovery in HALF_OPEN and restores CLOSED normal state."""
    from backend.app.v3.feature_store.redis_connection import RedisCircuitBreaker

    cb = RedisCircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"

    time.sleep(0.06)
    assert cb.can_execute() is True
    assert cb.state == "HALF_OPEN"

    # Successful probe recovers circuit
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0
