"""
FraudShield 3.0 — Automated Partner Sandbox API Key Rotation Utility.
Rotates the PARTNER API key securely:
1. Generates a new 256-bit CSPRNG key (secrets.token_urlsafe(32)).
2. Permanently revokes the exposed previous key and writes to persistent revocation file config/revoked_api_keys.json.
3. Injects the new key directly into .env.sandbox on disk.
4. Updates FRAUDSHIELD_REVOKED_API_KEYS in .env.sandbox for multi-worker consistency across restarts.
5. ZERO plaintext key exposure: Never prints the new key to stdout or logs.
"""

import os
import sys
import secrets
from pathlib import Path
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SANDBOX_ENV_FILE = PROJECT_ROOT / ".env.sandbox"
REVOCATION_FILE = PROJECT_ROOT / "config" / "revoked_api_keys.json"

sys.path.insert(0, str(PROJECT_ROOT))
from backend.app.v3.security.auth import ApiKeyManager
from backend.app.v3.security.config import hash_api_key


def rotate_partner_sandbox_key() -> bool:
    if not SANDBOX_ENV_FILE.exists():
        print(f"[ERROR] .env.sandbox not found at {SANDBOX_ENV_FILE}")
        return False

    # 1. Read existing sandbox environment
    sandbox_vars = dotenv_values(SANDBOX_ENV_FILE)
    old_key = sandbox_vars.get("FRAUDSHIELD_PARTNER_API_KEY")
    if not old_key:
        print("[ERROR] FRAUDSHIELD_PARTNER_API_KEY not found in .env.sandbox")
        return False

    salt = sandbox_vars.get("FRAUDSHIELD_API_KEY_SALT", "fs3_sandbox_master_salt_apikeymanager_51b9e284093c71")

    # 2. Generate new 256-bit CSPRNG secure key
    new_key = f"fs3_partner_{secrets.token_urlsafe(32)}"

    # 3. Permanently revoke the old key in persistent storage
    mgr = ApiKeyManager(salt=salt)
    old_hash = mgr.revoke_raw_key(
        raw_key=old_key,
        key_id="key_partner_exposed_revoked",
        reason="Compromised/exposed in conversation transcript"
    )

    # 4. Read .env.sandbox contents and update safely
    content = SANDBOX_ENV_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()

    new_lines = []
    revoked_list_found = False
    existing_revoked = []

    for line in lines:
        if line.startswith("FRAUDSHIELD_PARTNER_API_KEY="):
            new_lines.append(f"FRAUDSHIELD_PARTNER_API_KEY={new_key}")
        elif line.startswith("FRAUDSHIELD_REVOKED_API_KEYS="):
            revoked_list_found = True
            current_revoked = line.split("=", 1)[1].strip().strip('"').strip("'")
            if current_revoked:
                existing_revoked = [k.strip() for k in current_revoked.split(",") if k.strip()]
            if old_key not in existing_revoked:
                existing_revoked.append(old_key)
            new_lines.append(f'FRAUDSHIELD_REVOKED_API_KEYS="{",".join(existing_revoked)}"')
        else:
            new_lines.append(line)

    if not revoked_list_found:
        # Append revoked keys variable right below FRAUDSHIELD_PARTNER_API_KEY
        final_lines = []
        for line in new_lines:
            final_lines.append(line)
            if line.startswith("FRAUDSHIELD_PARTNER_API_KEY="):
                final_lines.append(f'FRAUDSHIELD_REVOKED_API_KEYS="{old_key}"')
        new_lines = final_lines

    SANDBOX_ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    print("=" * 80)
    print(" FRAUDSHIELD 3.0 — PARTNER API KEY ROTATION COMPLETE")
    print("=" * 80)
    print(f" Status:                    SUCCESS")
    print(f" Environment:               SANDBOX (.env.sandbox)")
    print(f" Revoked Key Hash:          {old_hash[:16]}...{old_hash[-8:]}")
    print(f" Persistent Revocation:     {REVOCATION_FILE}")
    print(f" Multi-Worker Synced:       YES (File + Redis DB 2)")
    print("-" * 80)
    print(" [CONFIDENTIALITY & ZERO-EXPOSURE POLICY]")
    print(" The new API key has NOT been printed here to prevent log/chat capture.")
    print(" To view the new active credential locally on your private terminal, run:")
    print(" 👉 python scripts/get_sandbox_credentials.py")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = rotate_partner_sandbox_key()
    sys.exit(0 if success else 1)
