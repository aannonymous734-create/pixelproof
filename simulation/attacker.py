"""Man-in-the-middle attacker between the satellite and the ground station.

Run it on a separate machine (e.g. a Kali or Ubuntu VM) or in the `attacker` container:
  python simulation/attacker.py --listen 0.0.0.0:8081 --ground http://GROUND:8000 --mode random --rate 0.6

Modes: passthrough | random | one attack name from pixelproof.integrity_attacks.ATTACKS
Every decision is written to runtime/attacker_log.jsonl (the ground truth for scoring the demo).
For the security of the host, run this only inside a VM/container on an isolated network.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof.imageio import load_rgb, to_png_bytes  # noqa: E402
from pixelproof.integrity_attacks import ATTACKS  # noqa: E402

STATE = {"history": [], "rng": np.random.default_rng(13), "lock": threading.Lock()}
MAX_BODY = 4 * 1024 * 1024


def forward(ground, payload):
    req = urllib.request.Request(f"{ground}/api/v1/ingest", data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read()


class Handler(BaseHTTPRequestHandler):
    args = None

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        if self.path != "/api/v1/ingest" or n > MAX_BODY:
            self.send_error(404 if self.path != "/api/v1/ingest" else 413)
            return
        msg = json.loads(self.rfile.read(n))
        a = self.args
        with STATE["lock"]:
            rng = STATE["rng"]
            hist = STATE["history"]
            choice = "passthrough"
            if a.mode != "passthrough" and rng.random() < a.rate:
                choice = a.mode if a.mode != "random" else str(rng.choice(list(ATTACKS)))
            if choice in ("replay", "manifest_swap") and not hist:
                choice = "passthrough"
            img = load_rgb(base64.b64decode(msg["image_png_b64"]))
            man = msg.get("manifest")
            if choice == "replay":
                img, man = hist[int(rng.integers(len(hist)))]
                out = {"image_png_b64": base64.b64encode(to_png_bytes(img)).decode(), "manifest": man}
            elif choice != "passthrough":
                other = hist[-1][0] if hist else img
                img2, man2 = ATTACKS[choice][0](img, man, rng, other=other)
                out = {"image_png_b64": base64.b64encode(to_png_bytes(img2)).decode(), "manifest": man2}
            else:
                out = msg
            hist.append((load_rgb(base64.b64decode(msg["image_png_b64"])), msg.get("manifest")))
            del hist[:-20]
        status, body = forward(a.ground.rstrip("/"), out)
        res = json.loads(body)
        rec = {"product_id": (msg.get("manifest") or {}).get("product_id"), "attack": choice,
               "expected_integrity": ATTACKS[choice][1] if choice in ATTACKS else "VERIFIED",
               "ground_verdict": res.get("verdict"), "ground_integrity": res.get("integrity", {}).get("status")}
        with open(a.log, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"[attacker] {rec['product_id']}: {choice:20s} -> ground says {rec['ground_verdict']} "
              f"({rec['ground_integrity']})", flush=True)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="0.0.0.0:8081")
    ap.add_argument("--ground", default="http://localhost:8000")
    ap.add_argument("--mode", default="random", choices=["passthrough", "random", *ATTACKS])
    ap.add_argument("--rate", type=float, default=0.6, help="fraction of messages attacked")
    ap.add_argument("--log", default="runtime/attacker_log.jsonl")
    args = ap.parse_args()
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    Handler.args = args
    host, port = args.listen.rsplit(":", 1)
    print(f"[attacker] listening on {args.listen}, forwarding to {args.ground}, mode={args.mode}", flush=True)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
