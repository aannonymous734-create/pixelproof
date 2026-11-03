"""End-to-end attack campaign on the trust layer + content detector (no network needed).

For N genuine EuroSAT patches: the emulated source signs each capture, a ground processing
step is recorded, then every attack in pixelproof.integrity_attacks is applied in transit and
the ground station verifies. Also measures the security overhead (sign/verify time, bytes).

Also runs the "faked BEFORE signing" case (a compromised payload signs a manipulated patch):
integrity says VERIFIED, so only the content detector can raise the alarm.

Usage: python scripts/run_attack_campaign.py --data-dir data/eurosat [--n 200] [--model models/detector.joblib]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof import manipulations as M  # noqa: E402
from pixelproof.data import list_samples, split_samples  # noqa: E402
from pixelproof.imageio import load_rgb, to_png_bytes  # noqa: E402
from pixelproof.integrity_attacks import ATTACKS  # noqa: E402
from pixelproof.provenance import Verifier, canonical, demo_setup  # noqa: E402
from pixelproof.verdict import combine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--model", default="models/detector.joblib")
    ap.add_argument("--out", default="results/integrity_campaign.json")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    det = None
    if Path(args.model).exists():
        from pixelproof.detector import Detector
        det = Detector.load(args.model)
    samples = split_samples(list_samples(args.data_dir))["test_heldout"]
    rng = np.random.default_rng(args.seed)
    pick = [samples[i] for i in rng.choice(len(samples), args.n, replace=False)]

    with tempfile.TemporaryDirectory() as keys:
        _, reg, src, proc = demo_setup(keys)
        ver = Verifier(reg)
        t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
        sign_ms, verify_ms, man_bytes, png_bytes = [], [], [], []
        delivered = []
        outcomes = defaultdict(Counter)
        verdicts = defaultdict(Counter)
        for i, s in enumerate(pick):
            img = load_rgb(s.path)
            t = time.perf_counter()
            m = src.capture(img, f"EUROSAT-{s.sid}", (t0 + timedelta(minutes=10 * i)).isoformat(timespec="seconds"))
            m = proc.record(m, "eurosat_patch_export", {"format": "uint8 RGB 64x64"}, img)
            sign_ms.append((time.perf_counter() - t) * 1000)
            man_bytes.append(len(canonical(m)))
            png_bytes.append(len(to_png_bytes(img)))
            t = time.perf_counter()
            r = ver.verify(img, m)
            verify_ms.append((time.perf_counter() - t) * 1000)
            outcomes["genuine"][r.status] += 1
            delivered.append((img, m))
        for name, (fn, expected, _) in ATTACKS.items():
            for i, (img, m) in enumerate(delivered):
                arng = np.random.default_rng(args.seed * 1000 + i)
                other = delivered[(i + 1) % len(delivered)][0]
                a_img, a_m = fn(img, m, arng, other=other)
                r = ver.verify(a_img, a_m)
                outcomes[name][r.status] += 1
                if det is not None and name in ("strip_manifest", "lsb_embed", "pixel_inpaint"):
                    verdicts[name][combine(r, det.analyse(a_img, with_heatmap=False))["verdict"]] += 1
        # faked before signing: compromised payload signs a manipulated patch
        if det is not None:
            for i, s in enumerate(pick):
                img = load_rgb(s.path)
                fake = M.inpaint(img, np.random.default_rng(i), "dev")[0]
                m = src.capture(fake, f"FAKE-{s.sid}", (t0 + timedelta(days=1, minutes=i)).isoformat(timespec="seconds"))
                r = ver.verify(fake, m)
                verdicts["signed_fake_before_capture"][combine(r, det.analyse(fake, with_heatmap=False))["verdict"]] += 1
                verdicts["signed_genuine"][combine(ver.verify(img, src.capture(
                    img, f"GEN-{s.sid}", (t0 + timedelta(days=2, minutes=i)).isoformat(timespec="seconds"))),
                    det.analyse(img, with_heatmap=False))["verdict"]] += 1

    rows = []
    for name, (fn, expected, desc) in [("genuine", (None, "VERIFIED", "untouched signed product")), *ATTACKS.items()]:
        c = outcomes[name]
        rows.append({"attack": name, "description": desc, "expected": expected,
                     "caught_as_expected": c[expected] / args.n, "observed": dict(c)})
    res = {
        "n_products": args.n,
        "attacks": rows,
        "two_axis_verdicts": {k: dict(v) for k, v in verdicts.items()},
        "overhead": {
            "sign_ms_p50": float(np.median(sign_ms)), "sign_ms_p95": float(np.percentile(sign_ms, 95)),
            "verify_ms_p50": float(np.median(verify_ms)), "verify_ms_p95": float(np.percentile(verify_ms, 95)),
            "manifest_bytes_mean": float(np.mean(man_bytes)), "png_bytes_mean": float(np.mean(png_bytes)),
            "overhead_percent_of_png": float(100 * np.mean(man_bytes) / np.mean(png_bytes)),
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2))
    for r in rows:
        print(f"{r['attack']:22s} expected {r['expected']:15s} rate {r['caught_as_expected']:.3f}  {r['observed']}")
    print(json.dumps(res["two_axis_verdicts"], indent=1))
    print(json.dumps(res["overhead"], indent=1))


if __name__ == "__main__":
    main()
