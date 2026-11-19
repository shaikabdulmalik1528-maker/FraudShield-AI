"""
FraudShield 3.0 Multi-Tier Decision Engine & Policy Service.
Translates continuous model fraud probabilities, behavioral velocity features,
and deterministic security rules into 4 distinct operational actions:
APPROVE, STEP_UP_2FA, MANUAL_REVIEW, and IMMEDIATE_BLOCK.
Guarantees:
- Strict separation between raw model probability, normalized risk score (0-100), and final business decision.
- Transparent decision reasons and evidence preservation for auditor inspection.
- Prohibits irreversible automatic payment cancellation without human or secondary review.
"""

import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from backend.app.v3.feature_store.schemas import EnrichedFeatureVector

logger = logging.getLogger(__name__)


class DecisionAction(str, Enum):
    APPROVE = "APPROVE"
    STEP_UP_2FA = "STEP_UP_2FA"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    IMMEDIATE_BLOCK = "IMMEDIATE_BLOCK"


class DecisionConfig(BaseModel):
    """Configurable probability cutoffs and behavioral thresholds for risk action routing."""
    tau_approve_max: float = Field(default=0.30, description="Upper bound for automated approval")
    tau_review_min: float = Field(default=0.70, description="Calibrated optimal fraud boundary (tau*)")
    tau_block_min: float = Field(default=0.90, description="Threshold for immediate authorization rejection")
    # Rule thresholds
    burst_1h_threshold: int = Field(default=8, description="Transactions per hour triggering velocity alert")
    amount_ratio_threshold: float = Field(default=10.0, description="Spend ratio over 30d baseline triggering review")
    speed_threshold_kmh: float = Field(default=900.0, description="Impossible travel speed boundary")
    # Degraded mode fail-safe thresholds
    degraded_amount_threshold: float = Field(default=500.0, description="Amount boundary triggering escalation when feature store is degraded")
    degraded_prob_threshold: float = Field(default=0.150, description="Model probability boundary triggering escalation when feature store is degraded")
    degraded_failsafe_enabled: bool = Field(default=True, description="Enforces strict non-approval when feature store is uncoordinated")


class DecisionResult(BaseModel):
    """Structured decision outcome preserving reasoning and empirical evidence."""
    action: DecisionAction
    fraud_probability: float = Field(..., ge=0.0, le=1.0)
    risk_score: float = Field(..., ge=0.0, le=100.0)
    is_fraud_flagged: bool
    decision_reasons: List[str] = Field(default_factory=list)
    rule_triggers: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)


class FraudDecisionEngine:
    """
    Evaluates calibrated ML inference outputs against enterprise policy bands and deterministic rules.
    """

    def __init__(self, config: Optional[DecisionConfig] = None):
        self.config = config or DecisionConfig()

    def evaluate(
        self,
        fraud_probability: float,
        features: EnrichedFeatureVector,
        optimal_threshold: float = 0.700
    ) -> DecisionResult:
        """
        Computes final business action with full reason codes and evidence trail.
        """
        prob = max(0.0, min(1.0, float(fraud_probability)))
        risk_score = round(prob * 100.0, 1)
        is_fraud = bool(prob >= optimal_threshold)

        reasons: List[str] = []
        rules: List[str] = []
        evidence: Dict[str, Any] = {
            "model_probability": round(prob, 4),
            "calibrated_threshold": optimal_threshold,
            "card_tx_count_1h": features.card_tx_count_1h,
            "card_amount_ratio_30d": features.card_amount_ratio_30d,
            "impossible_travel_flag": features.impossible_travel_flag,
            "speed_kmh": features.speed_kmh,
            "distance_km": features.distance_km,
            "channel": features.channel,
            "is_duplicate": features.is_duplicate,
            "is_degraded": getattr(features, "is_degraded", False),
            "features_imputed": getattr(features, "features_imputed", [])
        }

        # Handle Replay / Duplicate Transaction
        if features.is_duplicate:
            rules.append("RULE_DUPLICATE_IDEMP_REPLAY")
            reasons.append("Duplicate transaction payload detected within active retention window.")
            return DecisionResult(
                action=DecisionAction.IMMEDIATE_BLOCK,
                fraud_probability=prob,
                risk_score=risk_score,
                is_fraud_flagged=True,
                decision_reasons=reasons,
                rule_triggers=rules,
                evidence=evidence
            )

        # Baseline tier by calibrated probability
        if prob < self.config.tau_approve_max:
            action = DecisionAction.APPROVE
            reasons.append(f"Model probability ({prob:.3f}) is below approval cutoff ({self.config.tau_approve_max}).")
        elif prob < self.config.tau_review_min:
            action = DecisionAction.STEP_UP_2FA
            reasons.append(f"Moderate risk probability ({prob:.3f}); stepped-up cardholder authentication required.")
        elif prob < self.config.tau_block_min:
            action = DecisionAction.MANUAL_REVIEW
            reasons.append(f"High risk probability ({prob:.3f}) exceeds threshold ({self.config.tau_review_min}); routed to Fraud Analyst queue.")
        else:
            action = DecisionAction.IMMEDIATE_BLOCK
            reasons.append(f"Critical risk probability ({prob:.3f}) exceeds block threshold ({self.config.tau_block_min}).")

        # Deterministic Policy Rule Overrides & Escalations

        # Rule 1: Geo-Spatial Impossible Travel
        if features.impossible_travel_flag:
            rules.append("RULE_IMPOSSIBLE_TRAVEL")
            reasons.append(f"Physical velocity ({features.speed_kmh:.1f} km/h over {features.distance_km:.1f} km) violates physics.")
            # Impossible travel escalates immediately to BLOCK or MANUAL_REVIEW
            action = DecisionAction.IMMEDIATE_BLOCK

        # Rule 2: Burst Velocity Surge
        if features.card_tx_count_1h >= self.config.burst_1h_threshold:
            rules.append("RULE_BURST_VELOCITY_1H")
            reasons.append(f"Card authorization velocity in past 1 hour ({features.card_tx_count_1h}) exceeds threshold ({self.config.burst_1h_threshold}).")
            if action == DecisionAction.APPROVE:
                action = DecisionAction.STEP_UP_2FA
            elif action == DecisionAction.STEP_UP_2FA:
                action = DecisionAction.MANUAL_REVIEW

        # Rule 3: Extreme Spend Baseline Deviation
        if features.card_amount_ratio_30d >= self.config.amount_ratio_threshold:
            rules.append("RULE_EXTREME_SPEND_RATIO")
            reasons.append(f"Transaction spend is {features.card_amount_ratio_30d:.1f}x higher than 30-day cardholder baseline.")
            if action == DecisionAction.APPROVE:
                action = DecisionAction.STEP_UP_2FA
            elif action == DecisionAction.STEP_UP_2FA:
                action = DecisionAction.MANUAL_REVIEW

        # Rule 4: Degraded Feature Store Fail-Safe Policy
        if getattr(features, "is_degraded", False) and self.config.degraded_failsafe_enabled:
            rules.append("RULE_DEGRADED_FEATURE_STORE_FAILSAFE")
            if features.amount >= self.config.degraded_amount_threshold or prob >= self.config.degraded_prob_threshold:
                if features.amount >= 2000.0 or prob >= 0.50:
                    action = DecisionAction.MANUAL_REVIEW
                    reasons.append(
                        f"High-exposure transaction (${features.amount:.2f}, p={prob:.3f}) during degraded feature store; "
                        "automated approval withheld and escalated to Fraud Analyst queue."
                    )
                else:
                    if action == DecisionAction.APPROVE:
                        action = DecisionAction.STEP_UP_2FA
                    reasons.append(
                        f"Automated approval withheld during degraded feature store operation (amount=${features.amount:.2f}, p={prob:.3f}); "
                        "step-up 2FA verification required."
                    )

        return DecisionResult(
            action=action,
            fraud_probability=prob,
            risk_score=risk_score,
            is_fraud_flagged=is_fraud,
            decision_reasons=reasons,
            rule_triggers=rules,
            evidence=evidence
        )
