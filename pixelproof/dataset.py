"""Deterministic construction of the evaluation sets (shared by the feature model and the CNN).

Sets (every source patch belongs to exactly ONE split, so there is no leakage):
  train            authentic + DEV manipulations, 50% with DEV laundering (JPEG/WebP/noise)
  val              same recipe as train; used only to calibrate thresholds and fusion weight
  test_dev         authentic + DEV manipulations (in-distribution test)
  test_heldout     authentic + HELD-OUT manipulations (algorithms/shapes never seen in training)
  test_dev_laundered / test_heldout_laundered
                   the two test sets after HELD-OUT laundering (JPEG 2000 and/or radiometric
                   stretch: operations never used in training), applied to every patch, authentic too

Each job is fully determined by (source id, split, family): re-running gives identical pixels.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from . import manipulations as M
from .imageio import load_rgb

FAMILY_FOR_CLASS = {1: ("resample", "splice"), 2: ("copy_move",), 3: ("inpaint",)}
SETS = ("train", "val", "test_dev", "test_heldout", "test_dev_laundered", "test_heldout_laundered")


def seed_of(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


def jobs_for_split(split, samples, aug_frac=0.5, train_variants=("dev",)):
    """One authentic + one manipulated patch per source patch.

    train_variants: manipulation variants used in train/val (e.g. ("dev", "dev_plus") for the candidate detector).
    The choice uses its OWN random stream, so the default ("dev",) reproduces the original jobs exactly. The test
    sets never change (test_dev stays "dev", test_heldout stays "heldout")."""
    variant = "heldout" if split == "test_heldout" else "dev"
    jobs = []
    n = len(samples)
    for i, s in enumerate(samples):
        rng = np.random.default_rng(seed_of(s.sid, split))
        donor = samples[int(rng.integers(0, n - 1) + i + 1) % n]  # another patch of the SAME split
        cls = int(rng.integers(1, 4))
        fam = str(rng.choice(FAMILY_FOR_CLASS[cls]))
        if split in ("train", "val") and len(train_variants) > 1:
            vrng = np.random.default_rng(seed_of(s.sid, split, "variant"))
            variant = str(train_variants[int(vrng.integers(len(train_variants)))])
        for family in ("authentic", fam):
            base = dict(split=split, sid=s.sid, path=str(s.path), landcover=s.landcover, donor=str(donor.path),
                        family=family, variant=variant if family != "authentic" else "-",
                        label=M.LABEL_OF[family])
            if split in ("train", "val"):
                lrng = np.random.default_rng(seed_of(s.sid, split, family, "launder"))
                jobs.append({**base, "set": split, "launder": "dev" if lrng.random() < aug_frac else None})
            else:
                jobs.append({**base, "set": split, "launder": None})
                jobs.append({**base, "set": f"{split}_laundered", "launder": "heldout"})
    return jobs


def render(job):
    """Return (image uint8 64x64x3, mask bool 64x64, meta dict) for one job."""
    rng = np.random.default_rng(seed_of(job["sid"], job["split"], job["family"]))
    img = load_rgb(job["path"])
    donor = load_rgb(job["donor"])
    variant = job["variant"] if job["variant"] != "-" else "dev"
    out, mask, meta = M.make(img, donor, rng, job["family"], variant)
    if job["launder"]:
        out, lmeta = M.launder(out, np.random.default_rng(seed_of(job["sid"], job["set"], job["family"], "L")),
                               job["launder"])
        meta = {**meta, **lmeta}
    return out, mask, meta


def meta_json(meta) -> str:
    return json.dumps(meta, default=str)


def recipe_path(features_file) -> "Path":
    """`results/features.csv.gz` -> `results/features.recipe.json` (written by build_features.py)."""
    from pathlib import Path
    p = Path(features_file)
    return p.with_name(p.name.split(".")[0] + ".recipe.json")


def load_recipe(features_file) -> dict:
    """The recipe used to build a features file. A file without one is the shipped recipe (dev only)."""
    p = recipe_path(features_file)
    return json.loads(p.read_text()) if p.exists() else {"train_variants": ["dev"]}
