"""Build the controlled evaluation sets from official EuroSAT patches and extract features.
The recipe for every set is in pixelproof/dataset.py.

Usage:
  python scripts/build_features.py --data-dir data/eurosat --out results/features.csv.gz [--quick]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof import LABELS  # noqa: E402
from pixelproof.data import list_samples, split_samples  # noqa: E402
from pixelproof.dataset import jobs_for_split, meta_json, recipe_path, render  # noqa: E402
from pixelproof.features import extract  # noqa: E402


def run_job(job):
    out, mask, meta = render(job)
    t = time.perf_counter()
    f = extract(out)
    ms = (time.perf_counter() - t) * 1000
    row = {k: job[k] for k in ("set", "split", "sid", "landcover", "family", "variant", "label")}
    row.update({"launder": meta.get("launder", "none"), "mask_frac": float(mask.mean()),
                "meta": meta_json(meta), "feat_ms": ms})
    row.update(f)
    return row, (out, mask) if job.get("keep_image") else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--out", default="results/features.csv.gz")
    ap.add_argument("--quick", action="store_true", help="use 1/5 of the source patches (fast check)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--examples", default="results/examples", help="folder for example patches + masks")
    ap.add_argument("--train-variants", default="dev",
                    help='manipulation variants for train/val, e.g. "dev,dev_plus" (the shipped model used "dev")')
    args = ap.parse_args()
    variants = tuple(v.strip() for v in args.train_variants.split(",") if v.strip())

    samples = list_samples(args.data_dir)
    splits = split_samples(samples)
    jobs = []
    for split in ("train", "val", "test_dev", "test_heldout"):
        ss = splits[split]
        if args.quick:
            ss = ss[::5]
        jobs += jobs_for_split(split, ss, train_variants=variants)
    # train.py must re-render exactly these jobs: record the recipe next to the features file
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    recipe_path(args.out).write_text(json.dumps({"train_variants": list(variants), "quick": args.quick}, indent=2))
    # keep a few images per (set, family) for figures and the demo folder
    seen = {}
    for j in jobs:
        key = (j["set"], j["family"])
        if j["set"] in ("test_dev", "test_heldout") and seen.get(key, 0) < 6:
            j["keep_image"] = True
            seen[key] = seen.get(key, 0) + 1
    print(f"{len(samples)} official patches -> {len(jobs)} evaluation patches, {args.workers} workers", flush=True)

    t0 = time.time()
    rows = []
    ex_dir = Path(args.examples)
    ex_dir.mkdir(parents=True, exist_ok=True)
    with Pool(args.workers) as pool:
        for k, (row, kept) in enumerate(pool.imap(run_job, jobs, chunksize=64)):
            rows.append(row)
            if kept is not None:
                img, mask = kept
                stem = f"{row['set']}__{row['family']}__{row['sid']}"
                Image.fromarray(img).save(ex_dir / f"{stem}.png")
                Image.fromarray((mask * 255).astype(np.uint8)).save(ex_dir / f"{stem}__mask.png")
            if (k + 1) % 5000 == 0:
                print(f"  {k + 1}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, compression="gzip")
    print(f"wrote {args.out}: {len(df)} rows in {time.time() - t0:.0f}s")
    print(df.groupby(["set", "label"]).size().unstack(fill_value=0).rename(columns=dict(enumerate(LABELS))))


if __name__ == "__main__":
    main()
