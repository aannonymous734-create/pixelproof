"""Robustness sweep: apply ONE benign-looking operation at a time to authentic and manipulated
test patches and measure false alarms and detection. Shows exactly where the detector breaks.

  python scripts/robustness_sweep.py --data-dir data/eurosat [--n 600]
Outputs results/robustness.json, results/figures/robustness.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import cv2  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof import manipulations as M  # noqa: E402
from pixelproof.data import list_samples, split_samples  # noqa: E402
from pixelproof.calibration import adaptive  # noqa: E402
from pixelproof.dataset import jobs_for_split, render  # noqa: E402
from pixelproof.detector import Detector, decide  # noqa: E402
from pixelproof.features import FEATURE_NAMES, extract  # noqa: E402
from pixelproof.imageio import jpeg_roundtrip  # noqa: E402


def gamma(img, g):
    return np.clip(((img / 255.0) ** g) * 255 + 0.5, 0, 255).astype(np.uint8)


CONDITIONS = [  # (label, seen-in-training?, function)
    ("none", True, lambda x: x),
    ("JPEG q90", True, lambda x: jpeg_roundtrip(x, 90)),
    ("JPEG q70", True, lambda x: jpeg_roundtrip(x, 70)),
    ("JPEG q45", True, lambda x: jpeg_roundtrip(x, 45)),
    ("JPEG q25", False, lambda x: jpeg_roundtrip(x, 25)),
    ("WebP q60", True, lambda x: M._webp_roundtrip(x, 60)),
    ("blur 0.6", False, lambda x: cv2.GaussianBlur(x, (0, 0), 0.6)),
    ("blur 1.2", False, lambda x: cv2.GaussianBlur(x, (0, 0), 1.2)),
    ("noise 3", True, lambda x: np.clip(x + np.random.default_rng(0).normal(0, 3, x.shape), 0, 255).astype(np.uint8)),
    ("noise 6", False, lambda x: np.clip(x + np.random.default_rng(0).normal(0, 6, x.shape), 0, 255).astype(np.uint8)),
    ("JPEG2000 r10", False, lambda x: M._jp2_roundtrip(x, 10)),
    ("JPEG2000 r30", False, lambda x: M._jp2_roundtrip(x, 30)),
    ("gamma 0.8", False, lambda x: gamma(x, 0.8)),
    ("gamma 1.3", False, lambda x: gamma(x, 1.3)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--model", default="models/detector.joblib")
    ap.add_argument("--n", type=int, default=600, help="source patches (each gives 1 authentic + 1 manipulated)")
    ap.add_argument("--results", default="results")
    ap.add_argument("--replot", action="store_true", help="only redraw the figure from robustness.json")
    a = ap.parse_args()
    if a.replot:
        rb = json.loads((Path(a.results) / "robustness.json").read_text())
        seen = {n: sflag for n, sflag, _ in CONDITIONS}
        for r in rb["rows"]:
            r["seen_in_training"] = seen[r["condition"]]
        (Path(a.results) / "robustness.json").write_text(json.dumps(rb, indent=2))
        plot(rb["rows"], 0.05, Path(a.results))
        return
    det = Detector.load(a.model)
    jobs = [j for j in jobs_for_split("test_dev", split_samples(list_samples(a.data_dir))["test_dev"])
            if j["set"] == "test_dev"][:2 * a.n]
    base = [(render(j)[0], j["label"]) for j in jobs]
    y = np.array([b[1] for b in base])
    rows = []
    for name, seen, fn in CONDITIONS:
        imgs = np.stack([fn(b[0]) for b in base])
        X = np.array([[f[k] for k in FEATURE_NAMES] for f in map(extract, imgs)])
        P = det.proba_from(X, imgs)
        p = decide(P, det.thresholds_for(X))
        Pg = det.gbm.predict_proba(X)
        pg = decide(Pg, adaptive(det.gate_prob(X), det.threshold_gbm, det.threshold_proc_gbm)
                    if det.threshold_proc_gbm is not None else det.threshold_gbm)
        r = {"condition": name, "seen_in_training": seen,
             "false_alarm_rate": float((p[y == 0] != 0).mean()), "detection_rate": float((p[y != 0] != 0).mean()),
             "false_alarm_rate_features_only": float((pg[y == 0] != 0).mean()),
             "detection_rate_features_only": float((pg[y != 0] != 0).mean())}
        rows.append(r)
        print(f"{name:14s} seen={seen!s:5s} FA {r['false_alarm_rate']:.3f}  DET {r['detection_rate']:.3f}", flush=True)
    out = Path(a.results)
    (out / "robustness.json").write_text(json.dumps({"model": "features+cnn" if det.fused else "features",
                                                     "n_sources": a.n, "rows": rows}, indent=2))
    plot(rows, det.target_fpr, out)


def plot(rows, budget, out):
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x = np.arange(len(rows))
    ax.bar(x - 0.2, [r["detection_rate"] for r in rows], 0.4, label="detection rate (manipulated)", color="#4a7fb5")
    ax.bar(x + 0.2, [r["false_alarm_rate"] for r in rows], 0.4, label="false-alarm rate (authentic)", color="#d9822b")
    ax.set_xticks(x, [r["condition"] + ("" if r["seen_in_training"] else " *") for r in rows], rotation=35, ha="right")
    ax.set_ylim(0, 1.18)
    ax.set_yticks([0, .2, .4, .6, .8, 1.0])
    ax.axhline(budget, color="#d9822b", lw=0.8, ls="--", label=f"{budget:.0%} false-alarm budget")
    ax.set_title("Effect of one operation applied to every patch (* = operation never seen in training)")
    ax.legend(fontsize=8, loc="upper center", ncol=3, frameon=False)
    fig.tight_layout()
    (out / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "figures" / "robustness.png", dpi=150, metadata={"Software": None})


if __name__ == "__main__":
    main()
