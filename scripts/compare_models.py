"""Test the CNN on its own and compare the three detectors on a folder of images.

  python scripts/compare_models.py --input samples/authentic
  python scripts/compare_models.py --input results/examples --limit 12      # includes manipulated examples

For every 64x64 image it prints, side by side:
  features  the gradient-boosting model on the 48 forensic features (own calibrated threshold)
  CNN       the small forensic neural network alone (no calibrated threshold: we show 1 - P(authentic) and its top class)
  fused     what the product really uses: 0.4 * features + 0.6 * CNN, with the calibrated threshold
Then it prints the measured results of the three models from results/metrics.json (read from the file, never typed).
Needs PyTorch for the CNN and fused columns (see docs/HOW_TO_RUN.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from pixelproof import LABELS  # noqa: E402
from pixelproof.detector import Detector  # noqa: E402
from pixelproof.inputs import InputError, load_any  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="folder of images (searched recursively)")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--model", default=str(ROOT / "models" / "detector.joblib"))
    a = ap.parse_args()

    feat = Detector.load(a.model, use_cnn=False)
    fused = Detector.load(a.model, use_cnn=True)
    cnn = None
    if fused.fused:
        from pixelproof.cnn import load as load_cnn, predict_proba
        cnn = load_cnn(Path(a.model).parent / fused.cnn_file)
    else:
        print("PyTorch is not installed (or the CNN file is missing): only the feature model is available.\n"
              "Install it with:  pip install -r requirements-cnn.txt --index-url https://download.pytorch.org/whl/cpu\n")

    files = sorted(p for p in Path(a.input).rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff"))
    files = [p for p in files if "__mask" not in p.name][: a.limit]
    print(f"{'image':46s} {'features':>9s} {'CNN':>7s} {'CNN top class':>22s} {'fused':>7s}  fused says")
    for p in files:
        try:
            img = load_any(p)[0]
        except InputError as e:
            print(f"{p.name[:46]:46s} unreadable: {e}")
            continue
        f = feat.analyse(img, with_heatmap=False)
        u = fused.analyse(img, with_heatmap=False)
        if cnn is not None and img.shape[:2] == (64, 64):
            P = predict_proba(cnn, img[None])[0]
            c_score, c_top = f"{1 - P[0]:.3f}", LABELS[int(np.argmax(P))]
        else:
            c_score, c_top = "n/a", "(only 64x64 patches)"
        verdict = "FLAGGED " + str(u["type"]) if u["manipulated"] else "no traces found"
        print(f"{p.name[:46]:46s} {f['manipulation_score']:9.3f} {c_score:>7s} {c_top:>22s} {u['manipulation_score']:7.3f}  {verdict}")

    m = ROOT / "results" / "metrics.json"
    if m.exists():
        models = json.loads(m.read_text())["models"]
        print("\nMeasured on the evaluation sets (results/metrics.json; detection at the calibrated false-alarm rate):")
        print(f"{'model':18s} {'set':14s} {'detection':>10s} {'false alarms':>13s} {'AUC':>6s}")
        for name, sets in models.items():
            for s in ("test_dev", "test_heldout"):
                r = sets[s]
                print(f"{name:18s} {s:14s} {100 * r['detection_rate']:9.1f}% {100 * r['false_alarm_rate']:12.1f}% {r['auc_roc']:6.3f}")
        print("test_dev = manipulation methods seen in training; test_heldout = methods never seen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
