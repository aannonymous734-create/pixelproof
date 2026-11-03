"""One-command local demo: ground station + attacker + satellite on THIS machine (no Docker, no VMs).

  python scripts/quick_demo.py              # start everything, send traffic, score it, keep the dashboard open
  python scripts/quick_demo.py --no-wait    # same, but stop when done (for a quick check)

What happens, in order (this is the same story as the three-machine lab, on one laptop):
  1. the GROUND STATION starts (API + dashboard) with the attack lab switched on;
  2. the ATTACKER starts and forwards to the ground station, tampering with a random 60% of the messages;
  3. the SATELLITE signs sample patches and sends them THROUGH the attacker;
  4. the results are scored: every cryptographic attack must produce the expected status, and the audit log's
     hash chain must be intact;
  5. the dashboard stays open at the printed address. Press Ctrl+C to stop everything.

Everything binds to 127.0.0.1 only, so nothing is reachable from other machines. Files go to runtime/demo/
(demo private keys live there: never commit or submit that folder; it is git-ignored and left out of the zip).
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "runtime" / "demo"


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_for(url: str, seconds: int = 40) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ground-port", type=int, default=8000)
    ap.add_argument("--attacker-port", type=int, default=8081)
    ap.add_argument("--n", type=int, default=14, help="number of downlinks")
    ap.add_argument("--no-wait", action="store_true", help="stop after scoring instead of keeping the dashboard open")
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # show progress immediately, even when the output is piped

    for p in (a.ground_port, a.attacker_port):
        if not port_free(p):
            print(f"port {p} is already in use. Stop the other program, or choose another port with "
                  f"--ground-port / --attacker-port.", file=sys.stderr)
            return 2
    if not (ROOT / "models" / "detector.joblib").exists():
        print("models/detector.joblib is missing: this repository ships it, so the folder may be incomplete.", file=sys.stderr)
        return 2

    shutil.rmtree(DEMO, ignore_errors=True)  # a fresh, empty audit log every run
    DEMO.mkdir(parents=True)
    env = {**os.environ, "PIXELPROOF_REGISTRY": str(DEMO / "registry.json"), "PIXELPROOF_LEDGER": str(DEMO / "ledger.jsonl"),
           "PIXELPROOF_LAB_MODE": "1", "PYTHONUNBUFFERED": "1"}
    procs: list[subprocess.Popen] = []

    def start(name: str, *cmd: str) -> subprocess.Popen:
        log = open(DEMO / f"{name}.log", "w")
        p = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        procs.append(p)
        return p

    try:
        print("1/4  starting the ground station ...")
        start("ground", "-m", "uvicorn", "pixelproof.api:app", "--host", "127.0.0.1", "--port", str(a.ground_port))
        ground = f"http://127.0.0.1:{a.ground_port}"
        if not wait_for(f"{ground}/api/v1/health"):
            print(f"the ground station did not start. Read {DEMO / 'ground.log'}", file=sys.stderr)
            return 1
        print(f"     ground station is up: {ground}")

        print("2/4  starting the attacker (it tampers with about 60% of what it relays) ...")
        start("attacker", "simulation/attacker.py", "--listen", f"127.0.0.1:{a.attacker_port}", "--ground", ground,
              "--mode", "random", "--rate", "0.6", "--log", str(DEMO / "attacker_log.jsonl"))
        time.sleep(1.5)

        print(f"3/4  the satellite signs and sends {a.n} patches THROUGH the attacker ...")
        sat = subprocess.run([sys.executable, "simulation/satellite_node.py", "--patches", "samples/authentic",
                              "--target", f"http://127.0.0.1:{a.attacker_port}", "--keys", str(DEMO / "keys"),
                              "--registry", str(DEMO / "registry.json"), "--n", str(a.n), "--interval", "0.2"],
                             cwd=ROOT, env=env, capture_output=True, text=True)
        print("\n".join("     " + line for line in sat.stdout.splitlines()[-a.n:]))
        if sat.returncode != 0:
            print(sat.stderr[-800:], file=sys.stderr)
            return 1

        print("\n4/4  scoring the run ...\n")
        score = subprocess.run([sys.executable, "simulation/score_demo.py", "--log", str(DEMO / "attacker_log.jsonl"),
                                "--ledger", str(DEMO / "ledger.jsonl")], cwd=ROOT, env=env, capture_output=True, text=True)
        print(score.stdout)

        print(f"Dashboard (open it in your browser):  {ground}/")
        print(f"  - Overview / Audit log : the {a.n} decisions that were just made")
        print(f"  - Station              : the trusted public keys and the last downlink")
        print(f"  - Attack lab           : run any attack scenario (lab mode is ON in this demo)")
        if a.no_wait:
            return 0
        print("\nPress Ctrl+C to stop everything.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping ...")
        return 0
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
