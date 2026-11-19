"""
FraudShield 3.0 — Secure HTTPS Cloudflare Tunnel Launcher for Partner Sandbox.
Establishes a temporary, secure HTTPS tunnel to local port 8009.
Guarantees:
- Connects exclusively to port 8009 (exposes zero other local ports or filesystem files).
- Utilizes Cloudflare Anycast edge with valid SSL/TLS certificates.
- Discovers and outputs the live HTTPS Base URL for Base44 configuration.
- Persists active tunnel metadata to logs/sandbox_tunnel_url.txt.
"""

import sys
import os
import re
import time
import subprocess
from pathlib import Path
import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLOUDFLARED_BIN = PROJECT_ROOT / "tools" / "cloudflared.exe"
TUNNEL_URL_FILE = PROJECT_ROOT / "logs" / "sandbox_tunnel_url.txt"
SANDBOX_PORT = 8009


def check_sandbox_server(port: int = SANDBOX_PORT) -> bool:
    """Verifies that the local sandbox server is up and answering health requests."""
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health/sandbox", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def main():
    print("=" * 80)
    print(" FRAUDSHIELD 3.0 — PARTNER SANDBOX SECURE HTTPS TUNNEL")
    print("=" * 80)

    if not CLOUDFLARED_BIN.exists():
        print(f"[ERROR] cloudflared binary not found at {CLOUDFLARED_BIN}")
        sys.exit(1)

    print(f" Checking local sandbox server on port {SANDBOX_PORT}...", end="", flush=True)
    if not check_sandbox_server(SANDBOX_PORT):
        print(" [WARNING]")
        print(f" Local sandbox server is not currently running on port {SANDBOX_PORT}.")
        print(f" Please run 'python scripts/run_sandbox_server.py --port {SANDBOX_PORT}' in another terminal.")
        print(" Starting tunnel anyway (requests will be forwarded once server starts)...")
    else:
        print(" [ONLINE - HEALTHY]")

    cmd = [
        str(CLOUDFLARED_BIN),
        "tunnel",
        "--url", f"http://127.0.0.1:{SANDBOX_PORT}",
        "--protocol", "http2",
        "--no-autoupdate"
    ]

    print("[TUNNEL] Initializing Cloudflare Anycast edge connection...")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    tunnel_url = None
    url_pattern = re.compile(r'https://[a-zA-Z0-9\-]+\.trycloudflare\.com')

    # Monitor output for the generated tunnel URL
    t0 = time.time()
    try:
        for line in proc.stdout:
            sys.stdout.write(f"  {line}")
            sys.stdout.flush()
            if not tunnel_url:
                match = url_pattern.search(line)
                if match:
                    tunnel_url = match.group(0)
                    TUNNEL_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
                    TUNNEL_URL_FILE.write_text(tunnel_url, encoding="utf-8")
                    print("\n" + "=" * 80)
                    print(f" [SUCCESS] PUBLIC HTTPS BASE URL ESTABLISHED:")
                    print(f" 👉 {tunnel_url}")
                    print("=" * 80)
                    print(f" Safe Health URL:    {tunnel_url}/health/sandbox")
                    print(f" Predict Endpoint:   {tunnel_url}/api/v3/predict")
                    print(f" Batch Endpoint:     {tunnel_url}/api/v3/batch-predict")
                    print(f" Allowed Origin:     https://lush-fraud-shield-pulse.base44.app")
                    print("=" * 80)
                    print(" Press CTRL+C to stop the tunnel.\n")
    except KeyboardInterrupt:
        print("\n[TUNNEL] Stopping Cloudflare Tunnel...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        if TUNNEL_URL_FILE.exists():
            TUNNEL_URL_FILE.unlink(missing_ok=True)
        print("[TUNNEL] Stopped.")


if __name__ == "__main__":
    main()
