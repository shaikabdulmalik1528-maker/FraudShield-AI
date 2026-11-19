"""
Unit tests for FraudShield 3.0 Multi-Tier Decision Engine.
Verifies the four policy outcomes (APPROVE, STEP_UP_2FA, MANUAL_REVIEW, IMMEDIATE_BLOCK),
separation of probability vs risk score, and policy rule triggers.
"""

import pytest
from typing import Optional
from datetime import datetime, timezone
from backend.app.v3.feature_store.schemas import EnrichedFeatureVector
from backend.app.v3.services.decision_engine import (
    FraudDecisionEngine,
    DecisionConfig,
    DecisionAction,
    DecisionResult
)


def make_dummy_features(
    tx_id: str = "tx_dec_01",
    burst_1h: int = 0,
    amount_ratio: float = 1.0,
    impossible_travel: bool = False,
    speed_kmh: Optional[float] = None,
    distance_km: Optional[float] = None,
    is_duplicate: bool = False
) -> EnrichedFeatureVector:
    return EnrichedFeatureVector(
        transaction_id=tx_id,
        timestamp=datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        amount=100.0,
        currency="USD",
        card_pan_token="tok_v3_dummy_card",
        card_bin="453201",
        card_last4="0366",
        card_network="VISA",
        card_type="CREDIT",
        merchant_id="merch_dummy",
        mcc="5411",
        merchant_country="USA",
        channel="POS_CHIP",
        card_tx_count_1h=burst_1h,
        card_amount_ratio_30d=amount_ratio,
        impossible_travel_flag=impossible_travel,
        speed_kmh=speed_kmh,
        distance_km=distance_km,
        hour_sin=0.0,
        hour_cos=1.0,
        dow_sin=0.0,
        dow_cos=1.0,
        is_duplicate=is_duplicate
    )


def test_decision_approve_low_risk():
    """Probability < 0.30 produces APPROVE action."""
    engine = FraudDecisionEngine()
    feats = make_dummy_features()
    res = engine.evaluate(fraud_probability=0.08, features=feats)

    assert res.action == DecisionAction.APPROVE
    assert res.risk_score == 8.0
    assert res.is_fraud_flagged is False
    assert len(res.rule_triggers) == 0


def test_decision_step_up_2fa_medium_risk():
    """0.30 <= Probability < 0.70 produces STEP_UP_2FA action."""
    engine = FraudDecisionEngine()
    feats = make_dummy_features()
    res = engine.evaluate(fraud_probability=0.45, features=feats)

    assert res.action == DecisionAction.STEP_UP_2FA
    assert res.risk_score == 45.0
    assert res.is_fraud_flagged is False


def test_decision_manual_review_high_risk():
    """0.70 <= Probability < 0.90 produces MANUAL_REVIEW action and flags fraud."""
    engine = FraudDecisionEngine()
    feats = make_dummy_features()
    res = engine.evaluate(fraud_probability=0.78, features=feats)

    assert res.action == DecisionAction.MANUAL_REVIEW
    assert res.risk_score == 78.0
    assert res.is_fraud_flagged is True


def test_decision_immediate_block_critical_risk():
    """Probability >= 0.90 produces IMMEDIATE_BLOCK action."""
    engine = FraudDecisionEngine()
    feats = make_dummy_features()
    res = engine.evaluate(fraud_probability=0.94, features=feats)

    assert res.action == DecisionAction.IMMEDIATE_BLOCK
    assert res.risk_score == 94.0
    assert res.is_fraud_flagged is True


def test_rule_impossible_travel_forces_immediate_block():
    """Impossible travel trigger overrides low probability to IMMEDIATE_BLOCK."""
    engine = FraudDecisionEngine()
    feats = make_dummy_features(impossible_travel=True, speed_kmh=1200.0, distance_km=6000.0)

    res = engine.evaluate(fraud_probability=0.10, features=feats)

    assert res.action == DecisionAction.IMMEDIATE_BLOCK
    assert "RULE_IMPOSSIBLE_TRAVEL" in res.rule_triggers


def test_rule_velocity_burst_escalates_tier():
    """Burst velocity >= 8 escalates low probability from APPROVE to STEP_UP_2FA."""
    engine = FraudDecisionEngine()
    feats = make_dummy_features(burst_1h=12)

    res = engine.evaluate(fraud_probability=0.15, features=feats)

    assert res.action == DecisionAction.STEP_UP_2FA
    assert "RULE_BURST_VELOCITY_1H" in res.rule_triggers


def test_rule_duplicate_replay_blocks_immediately():
    """Duplicate replay flag triggers IMMEDIATE_BLOCK."""
    engine = FraudDecisionEngine()
    feats = make_dummy_features(is_duplicate=True)

    res = engine.evaluate(fraud_probability=0.05, features=feats)

    assert res.action == DecisionAction.IMMEDIATE_BLOCK
    assert "RULE_DUPLICATE_IDEMP_REPLAY" in res.rule_triggers
