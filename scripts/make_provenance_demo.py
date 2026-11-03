"""Build ready-to-upload files for the Provenance timeline page (jury demonstration).

    python scripts/make_provenance_demo.py            # after quick_demo.py has started (uses its fresh keys)

quick_demo.py creates NEW keys every time it starts, so run this AFTER the server is up. The script asks the running
ground station which public keys it trusts (/api/v1/registry) and signs with the matching private keys: those of
quick_demo.py (runtime/demo/keys) or of a plain `uvicorn pixelproof.api:app` (~/.pixelproof/keys).

One genuine product is signed at "capture" and goes through two genuine processing steps. Each case below is what an
attacker could deliver instead. Every pair is checked with the real verifier before it is written, so the expected
result printed here is what the dashboard will show. Files go to runtime/provenance_demo/ (git-ignored).
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from pixelproof import integrity_attacks as A  # noqa: E402
from pixelproof import manipulations as M  # noqa: E402
from pixelproof.imageio import to_png_bytes  # noqa: E402
from pixelproof.inputs import load_any  # noqa: E402
from pixelproof.provenance import (  # noqa: E402
    Keystore, ProcessorSigner, Registry, SourceSigner, Verifier, b64e, canonical, pixel_digest, pub_b64, sha256_hex,
)

# file stem, what the attacker did, expected integrity status
CASES = [
    ("01_genuine", "nothing: the product as signed and processed", "VERIFIED"),
    ("02_pixels_edited", "erased a region of the image and filled it in (inpainting)", "PIXELS_ALTERED"),
    ("03_date_changed", "moved the capture date one year back, kept the signature", "BAD_SIGNATURE"),
    ("04_forged_step", "edited the pixels and hid it behind a fake processing step 3", "CHAIN_BROKEN"),
    ("05_attacker_key", "changed the date and re-signed with the attacker's own key", "UNKNOWN_KEY"),
    ("06_weak_algorithm", "edited the pixels and claimed an md5 digest to match", "WEAK_ALGORITHM"),
]


CANDIDATES = [  # (private keys, public registry): quick_demo.py's run, then a plain uvicorn server
    (ROOT / "runtime" / "demo" / "keys", ROOT / "runtime" / "demo" / "registry.json"),
    (Path.home() / ".pixelproof" / "keys", ROOT / "runtime" / "registry.json"),
]


def server_registry(url: str) -> dict | None:
    """The public keys the RUNNING ground station trusts (None if it is not reachable)."""
    try:
        with urllib.request.urlopen(f"{url}/api/v1/registry", timeout=3) as r:
            return json.loads(r.read())
    except (OSError, ValueError):
        return None


def matching_keys(trusted: dict) -> Path | None:
    """The keys folder whose sat-01 and proc-01 public keys are the ones the server trusts."""
    for keys, _ in CANDIDATES:
        try:
            ks = Keystore(keys) if (keys / "sat-01.pem").exists() else None
            if ks and all(pub_b64(ks.load(k).public_key()) == trusted.get(k, {}).get("public_key")
                          for k in ("sat-01", "proc-01")):
                return keys
        except (OSError, ValueError):
            continue
    return None


def first_image() -> Path:
    for folder in (ROOT / "samples" / "authentic", ROOT / "data" / "eurosat"):
        for ext in ("*.png", "*.jpg", "*.tif"):
            found = sorted(folder.rglob(ext))
            if found:
                return found[0]
    sys.exit("no image found: pass one with --image")


def forged_step(img: np.ndarray, m: dict, rng) -> tuple[np.ndarray, dict]:
    """Copy-move edit, then append a step 3 that claims to be the trusted processor but is signed by the attacker."""
    out = M.copy_move(img, rng, "dev")[0]
    m2 = copy.deepcopy(m)
    prev = m2["processing"][-1]
    body = {"op": "cloud_mask", "params": {"threshold": 0.3}, "input_digest": prev["output_digest"],
            "output_digest": pixel_digest(out), "key_id": "proc-01", "hash_alg": "sha256", "sig_alg": "ed25519",
            "time": prev["time"], "prev_record": sha256_hex(canonical(prev))}
    m2["processing"].append({**body, "signature": b64e(A._ATTACKER_KEY.sign(canonical(body)))})
    return out, m2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://127.0.0.1:8000", help="running ground station (to match its keys)")
    ap.add_argument("--keys", type=Path, default=None, help="private keys folder (default: the one the server trusts)")
    ap.add_argument("--image", type=Path, default=None, help="genuine patch to sign (default: first sample)")
    ap.add_argument("--out", type=Path, default=ROOT / "runtime" / "provenance_demo")
    a = ap.parse_args()

    trusted = server_registry(a.server)
    if trusted is None:
        sys.exit(f"the ground station at {a.server} is not reachable: start it first (quick_demo.py or uvicorn)")
    keys = a.keys or matching_keys(trusted)
    if keys is None:
        sys.exit("none of the local key folders matches the keys this server trusts.\n"
                 + "\n".join(f"  tried {k}" for k, _ in CANDIDATES) + "\nPass the right folder with --keys.")
    a.keys = keys

    img = load_any(a.image or first_image())[0]
    ks = Keystore(a.keys)
    registry = Registry(trusted)  # verify against exactly what the running server trusts
    now = datetime.now(timezone.utc).replace(microsecond=0)
    product_id = f"S2-DEMO-{now:%Y%m%d-%H%M%S}"  # unique per run, so a previous run is never seen as a replay

    # the genuine product: signed at capture, then two genuine processing steps (pixels unchanged)
    m = SourceSigner("sat-01", ks.load("sat-01"), source="ESA Copernicus (emulated)").capture(
        img, product_id, (now - timedelta(hours=2)).isoformat())
    proc = ProcessorSigner("proc-01", ks.load("proc-01"))
    m = proc.record(m, "eurosat_patch_export", {"format": "uint8 RGB 64x64"}, img)
    m = proc.record(m, "format_conversion", {"to": "png", "lossless": True}, img)

    rng = np.random.default_rng(7)
    built = {
        "01_genuine": (img, m),
        "02_pixels_edited": A.pixel_inpaint(img, m, rng),
        "03_date_changed": A.date_replace(img, m, rng),
        "04_forged_step": forged_step(img, m, rng),
        "05_attacker_key": A.date_replace_resign(img, m, rng),
        "06_weak_algorithm": A.algorithm_downgrade(img, m, rng),
    }

    a.out.mkdir(parents=True, exist_ok=True)
    for old in a.out.glob("*"):
        old.unlink()
    verifier = Verifier(registry)
    lines, ok_all = [], True
    print(f"server: {a.server} (trusts {', '.join(trusted)})\nkeys:   {a.keys}\nproduct: {product_id}\n")
    for stem, what, expected in CASES:
        im, man = built[stem]
        got = verifier.verify(im, man, record=False)
        ok = got.status == expected
        ok_all &= ok
        (a.out / f"{stem}.png").write_bytes(to_png_bytes(im))  # PNG: lossless, the pixels stay exactly as signed
        (a.out / f"{stem}.json").write_text(json.dumps(man, indent=2))
        mark = "ok " if ok else "MISMATCH"
        print(f"  [{mark}] {stem:20s} -> {got.status:15s} ({what})")
        lines.append(f"{stem}.png + {stem}.json  ->  {expected:15s}  {what}")

    (a.out / "README.txt").write_text(
        "Provenance timeline demo files. Upload each PNG with the JSON of the same name.\n"
        f"Signed for product {product_id} with the keys in {a.keys}.\n\n" + "\n".join(lines) + "\n")
    print(f"\n{len(CASES)} pairs written to {a.out}")
    if not ok_all:
        print("Some results differ from what was expected: is the server using the same registry?", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
