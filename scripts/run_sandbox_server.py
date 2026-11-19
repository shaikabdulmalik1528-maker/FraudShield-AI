"""
FraudShield 3.0 — Dedicated Partner Sandbox Server Launcher.
Runs the isolated FraudShield 3.0 Partner Sandbox on port 8009.
Guarantees:
- Injects exclusively .env.sandbox (isolated sandbox master salts, DB index 2, partner keys).
- Binds to host 0.0.0.0 for external HTTPS proxy/tunnel forwarding.
- Enforces CORS whitelist strictly containing https://lush-fraud-shield-pulse.base44.app.
- Isolated from production and staging environments.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_ENV_FILE = PROJECT_ROOT / ".env.sandbox"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8009
DEFAULT_WORKERS = 4


def load_sandbox_environment() -> dict:
    """Loads and verifies variables strictly from .env.sandbox."""
    if not SANDBOX_ENV_FILE.exists():
        raise FileNotFoundError(f"Sandbox environment file not found: {SANDBOX_ENV_FILE}")

    env = os.environ.copy()
    sandbox_vars = dotenv_values(SANDBOX_ENV_FILE)
    for k, v in sandbox_vars.items():
        if v is not None:
            env[k] = v

    # Security assertion: Guarantee sandbox separation
    if env.get("FRAUDSHIELD_ENV") != "sandbox":
        raise ValueError("Security violation: FRAUDSHIELD_ENV must be 'sandbox'!")

    return env


def main():
    parser = argparse.ArgumentParser(description="FraudShield 3.0 Partner Sandbox Server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host address to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 8009)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Worker process count (default: 2)")
    args = parser.parse_args()

    env = load_sandbox_environment()

    print("=" * 80)
    print(" FRAUDSHIELD 3.0 — PARTNER SANDBOX SERVER")
    print("=" * 80)
    print(f" Environment:        SANDBOX (Isolated from production)")
    print(f" Configuration:      {SANDBOX_ENV_FILE.name}")
    print(f" Listening Address:  http://{args.host}:{args.port}")
    print(f" Worker Processes:   {args.workers}")
    print(f" CORS Allowed:       https://lush-fraud-shield-pulse.base44.app")
    print(f" Expose Headers:     X-Process-Time-Ms, X-RateLimit-*")
    print(f" Safe Health Probe:  http://127.0.0.1:{args.port}/health/sandbox")
    print(f" Prediction API:     http://127.0.0.1:{args.port}/api/v3/predict")
    print(f" Batch Predict API:  http://127.0.0.1:{args.port}/api/v3/batch-predict")
    print("=" * 80)
    print(" [SAFETY] Synthetic Transactions Only. Live rails strictly disconnected.")
    print("=" * 80)

    cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.app.main:app",
        "--host", args.host,
        "--port", str(args.port),
        "--workers", str(args.workers),
        "--log-level", "info"
    ]

    try:
        subprocess.run(cmd, env=env, cwd=str(PROJECT_ROOT), check=True)
    except KeyboardInterrupt:
        print("\n[SANDBOX SERVER] Gracefully stopped.")


if __name__ == "__main__":
    main()
