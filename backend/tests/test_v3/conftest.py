"""
Pytest configuration and session fixtures for FraudShield 3.0 test suite.
Injects testing token salt to suppress unconfigured dev warnings (WARN-01).
"""

import os
import pytest


@pytest.fixture(autouse=True)
def configure_test_token_salt(monkeypatch):
    """Sets a deterministic secret salt for all test session tokenization."""
    monkeypatch.setenv("FRAUDSHIELD_TOKEN_SALT", "fraudshield-test-suite-secure-salt-2026")
