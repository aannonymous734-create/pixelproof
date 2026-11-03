"""Emulated Sentinel-2 payload: signs each EuroSAT patch at "capture" and downlinks it.

  python simulation/satellite_node.py --data-dir data/eurosat --target http://ATTACKER_OR_GROUND:8081 \
         --keys ~/.pixelproof/keys --registry runtime/registry.json --n 40 --interval 1.5

  --patches DIR   use any folder of patches instead of the full EuroSAT tree (the VM lab ships a
                  small folder of held-out authentic patches)

The private keys never leave this machine/container; only the public registry is shared with
the ground station.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof.data import list_samples, split_samples  # noqa: E402
from pixelproof.imageio import load_rgb, to_png_bytes  # noqa: E402
from pixelproof.provenance import demo_setup  # noqa: E402


def post(url, payload, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--target", default="http://localhost:8081")
    ap.add_argument("--keys", default=str(Path.home() / ".pixelproof" / "keys"))
    ap.add_argument("--registry", default="runtime/registry.json")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--interval", type=float, default=1.5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--patches", default=None, help="folder of patches (overrides --data-dir)")
    args = ap.parse_args()

    _, reg, src, proc = demo_setup(args.keys)
    # the on-board counter survives restarts (like a real payload), so a second run is not a replay
    state = Path(args.keys) / "downlink_state.json"
    if state.exists():
        st = json.loads(state.read_text())
        src.seq, src.head = int(st["seq"]), st["head"]
    Path(args.registry).parent.mkdir(parents=True, exist_ok=True)
    reg.save(args.registry)  # publish PUBLIC keys for the ground station
    if args.patches:
        files = sorted(p for p in Path(args.patches).rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
        samples = [SimpleNamespace(path=p, sid=p.stem, landcover=p.parent.name) for p in files]
    else:
        samples = split_samples(list_samples(args.data_dir))["test_heldout"]
    rng = np.random.default_rng(args.seed)
    t0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=2 * args.n)
    for i, k in enumerate(rng.choice(len(samples), min(args.n, len(samples)), replace=False)):
        s = samples[k]
        img = load_rgb(s.path)
        m = src.capture(img, f"S2-{s.sid}-{src.seq + 1:06d}", (t0 + timedelta(seconds=60 * i)).isoformat())
        state.write_text(json.dumps({"seq": src.seq, "head": src.head}))
        m = proc.record(m, "eurosat_patch_export", {"format": "uint8 RGB 64x64"}, img)
        payload = {"image_png_b64": base64.b64encode(to_png_bytes(img)).decode(), "manifest": m}
        for attempt in range(30):
            try:
                r = post(f"{args.target.rstrip('/')}/api/v1/ingest", payload)
                break
            except OSError:
                time.sleep(2)
        else:
            sys.exit("target unreachable")
        print(f"[satellite] {m['product_id']} ({s.landcover}) -> {r.get('verdict')} / {r.get('integrity', {}).get('status')}",
              flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
