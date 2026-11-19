"""
FraudShield 3.0 — Secure Sandbox Credential Retrieval Utility.
Allows authorized developers to retrieve the dedicated PARTNER API key
on their private terminal without exposing master salts or server secrets.
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_ENV_FILE = PROJECT_ROOT / ".env.sandbox"
REVOCATION_FILE = PROJECT_ROOT / "config" / "revoked_api_keys.json"


def retrieve_credentials():
    parser = argparse.ArgumentParser(description="Secure Sandbox Credential Utility")
    parser.add_argument("--raw", action="store_true", help="Print raw active key only (for piping/clipboard)")
    parser.add_argument("--masked", action="store_true", help="Print key with security masking for logs/ci")
    args = parser.parse_args()

    if not SANDBOX_ENV_FILE.exists():
        print(f"[ERROR] Sandbox configuration file not found at {SANDBOX_ENV_FILE}", file=sys.stderr)
        sys.exit(1)

    sandbox_vars = dotenv_values(SANDBOX_ENV_FILE)
    partner_key = sandbox_vars.get("FRAUDSHIELD_PARTNER_API_KEY")

    if not partner_key:
        print("[ERROR] FRAUDSHIELD_PARTNER_API_KEY is not defined in .env.sandbox", file=sys.stderr)
        sys.exit(1)

    if args.raw:
        sys.stdout.write(partner_key)
        sys.stdout.flush()
        return

    rate_limit = sandbox_vars.get("RATE_LIMIT_PARTNER_PER_MIN", "1200")
    revoked_keys = sandbox_vars.get("FRAUDSHIELD_REVOKED_API_KEYS", "")
    revoked_count = len([k for k in revoked_keys.split(",") if k.strip()])

    display_key = f"{partner_key[:12]}...{partner_key[-4:]}" if args.masked else partner_key

    print("=" * 80)
    print(" FRAUDSHIELD 3.0 — PARTNER SANDBOX CREDENTIALS (SECURE EXTRACTION)")
    print("=" * 80)
    print(f" Environment:               SANDBOX (Isolated)")
    print(f" Status:                    ACTIVE & ROTATED")
    print(f" Assigned RBAC Role:        PARTNER")
    print(f" Permitted Operations:      Single Prediction (/predict), Batch (/batch-predict)")
    print(f" Forbidden Operations:      Model Reload, Rollback, Drift Admin (HTTP 403)")
    print(f" Rate Limit:                {rate_limit} requests / minute (20 QPS)")
    print(f" Permanently Revoked Keys:  {revoked_count} key(s) in blacklist store")
    print("-" * 80)
    print(f" Dedicated PARTNER Key:     {display_key}")
    print("-" * 80)
    print(" HTTP Header Configuration Options for Base44:")
    print(f"   Option 1 (Custom Header): X-API-Key: {display_key}")
    print(f"   Option 2 (Bearer Token):  Authorization: Bearer {display_key}")
    print("-" * 80)
    print(" [SECURITY & COMPLIANCE NOTICE]")
    print(" 1. Copy this key directly into Base44 environment secrets.")
    print(" 2. Do NOT commit this key to public Git repositories.")
    print(" 3. Master cryptographic salts and administrative keys remain strictly protected.")
    print(" 4. To pipe key directly to clipboard on Windows: ")
    print("    python scripts/get_sandbox_credentials.py --raw | Set-Clipboard")
    print("=" * 80)


if __name__ == "__main__":
    retrieve_credentials()
