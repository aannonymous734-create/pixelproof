"""Command-line interface.

  python -m pixelproof.cli detect   --input DIR --output predictions.csv      # jury's held-out patches
  python -m pixelproof.cli analyse  --image patch.png [--manifest m.json] [--registry r.json]
  python -m pixelproof.cli keys-init --keys ~/.pixelproof/keys --registry runtime/registry.json
  python -m pixelproof.cli fingerprints --registry runtime/registry.json   # compare on both machines
  python -m pixelproof.cli sign     --image patch.png --product-id P1 --time 2026-09-01T10:00:00+00:00 --out m.json
  python -m pixelproof.cli verify   --image patch.png --manifest m.json --registry runtime/registry.json
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import LABELS


def cmd_detect(a):
    from .detector import Detector
    from .inputs import InputError, load_any
    det = Detector.load(a.model)
    files = sorted(p for p in Path(a.input).rglob("*")
                   if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"))
    with open(a.output, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "manipulated", "type", "manipulation_score", "threshold", *[f"p_{l}" for l in LABELS],
                    "tiles", "input_note"])
        errors = 0
        for p in files:
            try:
                img, info = load_any(p)
                r = det.analyse(img, with_heatmap=False)
            except InputError as e:  # unreadable file: report it, do not crash the batch
                errors += 1
                w.writerow([str(p), "error", str(e)[:120], *[""] * (2 + len(LABELS)), "", ""])
                continue
            note = "; ".join([*(f"{k}: {v}" for k, v in info.items() if k != "format"),
                              *([r["input_note"]] if r.get("input_note") else [])])
            w.writerow([str(p), int(r["manipulated"]), r["type"], r["manipulation_score"], r["threshold"],
                        *[r["probabilities"][l] for l in LABELS], r.get("tiles", 1), note])
    print(f"{len(files)} files -> {a.output} ({errors} unreadable; model: {'features+cnn' if det.fused else 'features'})")


def cmd_analyse(a):
    from .inputs import load_any
    from .service import GroundStation
    gsn = GroundStation(model_path=a.model, registry_path=a.registry, ledger_path=a.ledger)
    man = json.loads(Path(a.manifest).read_bytes()) if a.manifest else None  # bytes: tolerates a Windows UTF-8 BOM
    img, info = load_any(a.image)
    r = gsn.process(img, man, live=False, source="cli")
    if info:
        r["input_conversion"] = info
    hm = r.pop("heatmap_png_b64")
    if a.heatmap:
        import base64
        Path(a.heatmap).write_bytes(base64.b64decode(hm))
    print(json.dumps(r, indent=2))


def cmd_keys_init(a):
    from .provenance import demo_setup
    _, reg, _, _ = demo_setup(a.keys)
    Path(a.registry).parent.mkdir(parents=True, exist_ok=True)
    reg.save(a.registry)
    print(f"private keys in {a.keys} (keep secret, never commit); public registry -> {a.registry}")


def cmd_fingerprints(a):
    """Print the SHA-256 fingerprint of every PUBLIC key in a registry file. Run it on the satellite and on the
    ground station and compare by eye: that comparison is the out-of-band check that the ground station trusts the
    satellite's real key and not an attacker's."""
    from .provenance import Registry, b64d, sha256_hex
    reg = Registry.load(a.registry)
    if not reg.keys:
        print("the registry is empty")
        return
    for key_id, k in reg.keys.items():
        print(f"{key_id:10s} {k['role']:10s} {sha256_hex(b64d(k['public_key']))}")


def cmd_sign(a):
    from .inputs import load_any
    from .provenance import Keystore, SourceSigner
    ks = Keystore(a.keys)
    s = SourceSigner(a.key_id, ks.load(a.key_id), source=a.source)
    s.seq = a.seq - 1
    m = s.capture(load_any(a.image)[0], a.product_id, a.time)
    Path(a.out).write_text(json.dumps(m, indent=2))
    print(f"manifest -> {a.out}")


def cmd_verify(a):
    from .inputs import load_any
    from .provenance import Registry, Verifier
    r = Verifier(Registry.load(a.registry)).verify(load_any(a.image)[0], json.loads(Path(a.manifest).read_bytes()),
                                                   record=False)
    print(json.dumps({"status": r.status, "ok": r.ok, "reasons": r.reasons}, indent=2))
    sys.exit(0 if r.ok else 1)


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(prog="pixelproof")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("detect", help="content analysis of every image in a folder -> CSV")
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="predictions.csv")
    p.add_argument("--model", default=str(root / "models" / "detector.joblib"))
    p.set_defaults(fn=cmd_detect)
    p = sub.add_parser("analyse", help="full two-axis verdict for one image")
    p.add_argument("--image", required=True)
    p.add_argument("--manifest")
    p.add_argument("--registry", default=str(root / "runtime" / "registry.json"))
    p.add_argument("--model", default=str(root / "models" / "detector.joblib"))
    p.add_argument("--ledger", default=str(root / "runtime" / "ledger.jsonl"))
    p.add_argument("--heatmap", help="write the evidence overlay PNG here")
    p.set_defaults(fn=cmd_analyse)
    p = sub.add_parser("keys-init", help="create demo source/processor keys + public registry")
    p.add_argument("--keys", default=str(Path.home() / ".pixelproof" / "keys"))
    p.add_argument("--registry", default=str(root / "runtime" / "registry.json"))
    p.set_defaults(fn=cmd_keys_init)
    p = sub.add_parser("fingerprints", help="print the SHA-256 fingerprint of each public key in a registry")
    p.add_argument("--registry", default=str(root / "runtime" / "registry.json"))
    p.set_defaults(fn=cmd_fingerprints)
    p = sub.add_parser("sign", help="sign a capture (source side)")
    p.add_argument("--image", required=True)
    p.add_argument("--product-id", required=True)
    p.add_argument("--time", required=True, help="ISO 8601 capture time, e.g. 2026-09-01T10:00:00+00:00")
    p.add_argument("--keys", default=str(Path.home() / ".pixelproof" / "keys"))
    p.add_argument("--key-id", default="sat-01")
    p.add_argument("--source", default="ESA Copernicus (emulated)")
    p.add_argument("--seq", type=int, default=1)
    p.add_argument("--out", default="manifest.json")
    p.set_defaults(fn=cmd_sign)
    p = sub.add_parser("verify", help="integrity check only")
    p.add_argument("--image", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--registry", default=str(root / "runtime" / "registry.json"))
    p.set_defaults(fn=cmd_verify)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
