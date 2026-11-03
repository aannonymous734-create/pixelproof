"""Copy a small, fixed set of OFFICIAL EuroSAT patches into samples/authentic/ (unmodified files).

The attack lab, the VM lab and the tests need real satellite patches, but the jury should not need the
2 GB dataset just to try them. We take 3 patches per land-cover class from the `test_heldout` split (so none of
them was used for training or tuning) and choose them by a hash of their id, so the choice is reproducible and
not hand-picked.

  python scripts/make_samples.py --data-dir data/eurosat [--per-class 3]
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pixelproof.data import OFFICIAL_COUNTS, list_samples, split_samples  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--per-class", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "samples" / "authentic"))
    a = ap.parse_args()
    held = split_samples(list_samples(a.data_dir))["test_heldout"]
    out = Path(a.out)
    for cls in sorted(OFFICIAL_COUNTS):
        pool = sorted((s for s in held if s.landcover == cls), key=lambda s: hashlib.sha256(s.sid.encode()).hexdigest())
        (out / cls).mkdir(parents=True, exist_ok=True)
        for s in pool[: a.per_class]:
            shutil.copyfile(s.path, out / cls / s.path.name)
            print(f"{cls}/{s.path.name}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
