"""
Test Uvicorn 4-worker launch on Windows with health polling and stdout inspection.
"""

import subprocess
import sys
import time
import psutil
import httpx

PYTHON = sys.executable
CMD = [
    PYTHON, "-m", "uvicorn",
    "backend.app.main:app",
    "--host", "127.0.0.1",
    "--port", "8008",
    "--workers", "4",
    "--log-level", "info"
]

print("Spawning 4-worker uvicorn on port 8008...")
proc = subprocess.Popen(CMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

success = False
try:
    # Poll for up to 25 seconds
    t0 = time.time()
    while time.time() - t0 < 25:
        try:
            resp = httpx.get("http://127.0.0.1:8008/health/ready", timeout=2.0)
            if resp.status_code == 200:
                print(f"[SUCCESS] Server ready after {time.time()-t0:.2f}s: {resp.json()}")
                success = True
                break
        except Exception:
            pass
        time.sleep(1.0)

    try:
        parent = psutil.Process(proc.pid)
        children = parent.children(recursive=True)
        print(f"Parent PID: {parent.pid}, Child Worker PIDs ({len(children)}): {[c.pid for c in children]}")
    except Exception as e:
        print(f"Error inspecting processes: {e}")

finally:
    print("Terminating cluster...")
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        pass
    stdout, _ = proc.communicate(timeout=5)
    print("\n--- Uvicorn Server Logs ---")
    print(stdout[-2000:])  # Last 2000 chars

if not success:
    sys.exit(1)
