"""
Root pytest configuration for FraudShield AI test suites.
Guarantees baseline artifact immutability across test runs.
"""

import json
from pathlib import Path
import pytest

THRESHOLD_FILE = Path(__file__).resolve().parent.parent / "artifacts" / "optimal_threshold.json"

BASELINE_THRESHOLD = {
    "model_name": "XGBoost",
    "optimal_threshold": 0.895,
    "f1_score": 0.8447,
    "precision": 0.9459,
    "recall": 0.7630,
    "updated_at": "2026-11-16T12:00:00+00:00"
}


@pytest.fixture(autouse=True, scope="session")
def preserve_baseline_threshold():
    """Restores baseline optimal_threshold.json to 0.895 after test suite completes."""
    yield
    if THRESHOLD_FILE.exists():
        with open(THRESHOLD_FILE, "w") as f:
            json.dump(BASELINE_THRESHOLD, f, indent=2)
