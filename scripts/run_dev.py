"""
FraudShield AI - Developer Runner Script
Allows launching backend, frontend, or both with clear status logs.
Usage:
  python scripts/run_dev.py --backend
  python scripts/run_dev.py --frontend
  python scripts/run_dev.py --all
"""

import sys
import subprocess
import argparse
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def run_backend():
    print("[INFO] Starting FastAPI Backend on http://localhost:8000 ...")
    python_exe = BASE_DIR / "venv" / "Scripts" / "python.exe"
    cmd = [str(python_exe), "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR))

def run_frontend():
    print("[INFO] Starting React + Vite Frontend on http://localhost:5173 ...")
    cmd = ["npm", "run", "dev"]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR / "frontend"), shell=True)

def main():
    parser = argparse.ArgumentParser(description="FraudShield AI Service Runner")
    parser.add_argument("--backend", action="store_true", help="Launch FastAPI backend")
    parser.add_argument("--frontend", action="store_true", help="Launch React frontend")
    parser.add_argument("--all", action="store_true", help="Launch both backend and frontend")
    args = parser.parse_args()

    procs = []
    if args.backend or args.all or (not args.frontend and not args.backend and not args.all):
        procs.append(run_backend())
    if args.frontend or args.all:
        procs.append(run_frontend())

    print("\n[SUCCESS] Services launched. Press Ctrl+C to terminate.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Terminating background processes...")
        for p in procs:
            p.terminate()

if __name__ == "__main__":
    main()
