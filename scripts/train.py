"""Train the feature model + forensic CNN, fuse them, calibrate on validation, save models and
per-patch predictions for every evaluation set.

Usage:
  python scripts/train.py --data-dir data/eurosat --features results/features.csv.gz
         [--epochs 8] [--no-cnn] [--target-fpr 0.05] [--models DIR --out FILE] [--overwrite]
It REFUSES to overwrite the shipped model unless you pass --overwrite or write elsewhere (--models / --out).
Outputs:
  models/detector.joblib (+ .json model card)   models/pixelnet.pt
  results/predictions.csv.gz                     results/train_log.txt
"""
from __future__ import annotations

import argparse
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof.data import list_samples, split_samples  # noqa: E402
from pixelproof.calibration import calibrate_detector  # noqa: E402
from pixelproof.dataset import jobs_for_split, load_recipe, render  # noqa: E402
from pixelproof.detector import build, decide, threshold_for, train_gbm  # noqa: E402
from pixelproof.features import FEATURE_NAMES  # noqa: E402


def _render_img(job):
    return render(job)[0]


def render_all(df, data_dir, workers, quick, train_variants=("dev",)):
    """Re-create the exact pixels of every feature row (deterministic recipe)."""
    splits = split_samples(list_samples(data_dir))
    jobs = []
    for split in ("train", "val", "test_dev", "test_heldout"):
        ss = splits[split][::5] if quick else splits[split]
        jobs += jobs_for_split(split, ss, train_variants=train_variants)
    key = {(j["set"], j["sid"], j["family"]): j for j in jobs}
    ordered = [key[(r.set, r.sid, r.family)] for r in df[["set", "sid", "family"]].itertuples(index=False)]
    with Pool(workers) as pool:
        imgs = pool.map(_render_img, ordered, chunksize=256)
    return np.stack(imgs).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--features", default="results/features.csv.gz")
    ap.add_argument("--models", default="models")
    ap.add_argument("--out", default="results/predictions.csv.gz")
    ap.add_argument("--epochs", type=int, default=8, help="CNN epochs. The shipped model was trained with 8 (make train)")
    ap.add_argument("--target-fpr", type=float, default=0.05)
    ap.add_argument("--no-cnn", action="store_true")
    ap.add_argument("--quick", action="store_true", help="features were built with --quick")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--overwrite", action="store_true",
                    help="allow replacing an existing model and predictions (the SHIPPED ones by default)")
    # candidate-detector options; the defaults reproduce how the shipped model was trained
    ap.add_argument("--width", type=int, default=16, help="CNN width (16 = shipped, about 74k parameters)")
    ap.add_argument("--dropout", type=float, default=0.0)
    ap.add_argument("--label-smoothing", type=float, default=0.0)
    ap.add_argument("--select", choices=["acc", "recall"], default="acc",
                    help="keep the epoch with the best validation accuracy (shipped) or recall at the target FPR")
    ap.add_argument("--patience", type=int, default=None, help="early stopping after N epochs without improvement")
    ap.add_argument("--tta", action="store_true", help="test-time averaging over 8 flips/rotations (CNN)")
    args = ap.parse_args()

    # Safety: the defaults point at the shipped model and its predictions. Replacing them silently makes the
    # results/ files and the report describe a different model than the one in models/ (this happened once).
    existing = [p for p in (Path(args.models) / "detector.joblib", Path(args.out)) if p.exists()]
    if existing and not args.overwrite:
        sys.exit("refusing to overwrite existing outputs: " + ", ".join(map(str, existing)) + "\n"
                 "  To experiment, train into another folder:\n"
                 "      python scripts/train.py --models results/my_model --out results/my_model/predictions.csv.gz\n"
                 "  To replace the shipped model on purpose, add --overwrite, and then re-run evaluate.py, heldout_v2.py,\n"
                 "  robustness_sweep.py, run_attack_campaign.py and update the report (python scripts/check_numbers.py).")

    Path(args.models).mkdir(parents=True, exist_ok=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    log_f = open(Path(args.out).parent / "train_log.txt", "w")

    def log(*a):
        msg = " ".join(str(x) for x in a)
        print(msg, flush=True)
        log_f.write(msg + "\n")
        log_f.flush()

    df = pd.read_csv(args.features)
    X = df[FEATURE_NAMES].to_numpy(np.float64)
    y = df["label"].to_numpy(int)
    tr, va = (df["set"] == "train").to_numpy(), (df["set"] == "val").to_numpy()
    # thresholds are calibrated on CLEAN validation authentics: the stated operating point
    # ("<= target_fpr false alarms on authentic EuroSAT patches") then holds on untouched data
    cal = va & (y == 0) & (df["launder"] == "none").to_numpy()

    t = time.time()
    gbm = train_gbm(X[tr], y[tr])
    P_gbm = gbm.predict_proba(X)
    thr_gbm = threshold_for(1 - P_gbm[cal, 0], args.target_fpr)
    log(f"feature model: {gbm.n_iter_} trees, {time.time() - t:.1f}s, threshold {thr_gbm:.4f}")
    out = df[["set", "split", "sid", "landcover", "family", "variant", "label", "launder", "mask_frac", "meta",
              "feat_ms"]].copy()
    for i in range(4):
        out[f"p_gbm_{i}"] = P_gbm[:, i]

    cnn_file, w, thr_fused = None, 1.0, None
    if not args.no_cnn:
        import torch
        from pixelproof import cnn
        torch.set_num_threads(args.workers)
        t = time.time()
        recipe = load_recipe(args.features)
        imgs = render_all(df, args.data_dir, args.workers, args.quick, tuple(recipe["train_variants"]))
        log(f"rendered {len(imgs)} patches in {time.time() - t:.0f}s (train variants: {recipe['train_variants']})")
        log(f"CNN: width {args.width}, dropout {args.dropout}, label smoothing {args.label_smoothing}, "
            f"select {args.select}, patience {args.patience}, max epochs {args.epochs}, tta {args.tta}")
        t = time.time()
        net = cnn.train(imgs[tr], y[tr], imgs[va], y[va], epochs=args.epochs, log=log, width=args.width,
                        dropout=args.dropout, label_smoothing=args.label_smoothing, select=args.select,
                        val_clean_authentic=cal[va], target_fpr=args.target_fpr, patience=args.patience)
        log(f"CNN trained in {(time.time() - t) / 60:.1f} min "
            f"({sum(p.numel() for p in net.parameters() if p.requires_grad):,} parameters)")
        cnn_file = "pixelnet.pt"
        cnn.save(net, Path(args.models) / cnn_file)
        t = time.time()
        P_cnn = cnn.predict_proba(net, imgs, tta=args.tta)
        log(f"CNN inference on {len(imgs)} patches: {(time.time() - t) * 1000 / len(imgs):.2f} ms/patch")
        for i in range(4):
            out[f"p_cnn_{i}"] = P_cnn[:, i]
        # fusion weight: maximise validation recall at the target false-alarm rate
        best = (-1, 1.0, None)
        for w_ in np.linspace(0, 1, 11):
            P = w_ * P_gbm + (1 - w_) * P_cnn
            th = threshold_for(1 - P[cal, 0], args.target_fpr)
            rec = float((decide(P[va], th)[y[va] != 0] != 0).mean())
            log(f"  fusion w_features={w_:.1f}: val recall at {args.target_fpr:.0%} FPR = {rec:.4f}")
            if rec > best[0]:
                best = (rec, float(w_), th)
        _, w, thr_fused = best
        log(f"chosen fusion weight w_features={w:.1f}, threshold {thr_fused:.4f}")
        if args.tta:  # the same selection without test-time averaging, so the choice is made on validation only
            P_plain = cnn.predict_proba(net, imgs[va])
            cal_v = cal[va]
            recs = []
            for w_ in np.linspace(0, 1, 11):
                P = w_ * P_gbm[va] + (1 - w_) * P_plain
                th = threshold_for(1 - P[cal_v, 0], args.target_fpr)
                recs.append(float((decide(P, th)[y[va] != 0] != 0).mean()))
            log(f"without test-time averaging: best val recall at {args.target_fpr:.0%} FPR = {max(recs):.4f} "
                f"(w_features={np.linspace(0, 1, 11)[int(np.argmax(recs))]:.1f}); with it: {best[0]:.4f}")
        P_f = w * P_gbm + (1 - w) * P_cnn
        for i in range(4):
            out[f"p_fused_{i}"] = P_f[:, i]

    det = build(gbm, X[tr], y[tr], args.target_fpr, thr_gbm, w, thr_fused, cnn_file,
                {"n_train": int(tr.sum()), "n_val": int(va.sum())}, cnn_tta=bool(cnn_file and args.tta))
    # condition-aware thresholds: do not accuse authentic patches that were merely re-encoded
    out["p_gate"] = calibrate_detector(det, X, y, tr, va, (df["launder"] != "none").to_numpy(), P_gbm,
                                       (w * P_gbm + (1 - w) * P_cnn) if cnn_file else None, log=log)
    digest = det.save(Path(args.models) / "detector.joblib")
    log(f"saved {Path(args.models) / 'detector.joblib'} sha256={digest}")
    out.to_csv(args.out, index=False, compression="gzip")
    log(f"wrote {args.out}")


if __name__ == "__main__":
    main()
