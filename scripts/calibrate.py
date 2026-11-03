"""Fit the re-encoding gate and condition-aware thresholds on an already trained detector
(the same step runs at the end of scripts/train.py). Updates models/detector.joblib and adds the
p_gate column to results/predictions.csv.gz.

  python scripts/calibrate.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof.calibration import calibrate_detector  # noqa: E402
from pixelproof.detector import Detector  # noqa: E402
from pixelproof.features import FEATURE_NAMES  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="results/features.csv.gz")
    ap.add_argument("--predictions", default="results/predictions.csv.gz")
    ap.add_argument("--model", default="models/detector.joblib")
    a = ap.parse_args()
    df = pd.read_csv(a.features)
    pr = pd.read_csv(a.predictions)
    assert (df[["set", "sid", "family"]].to_numpy() == pr[["set", "sid", "family"]].to_numpy()).all()
    det = Detector.load(a.model, use_cnn=False)
    X = df[FEATURE_NAMES].to_numpy(np.float64)
    y = df["label"].to_numpy(int)
    P_gbm = pr[[f"p_gbm_{i}" for i in range(4)]].to_numpy()
    P_f = pr[[f"p_fused_{i}" for i in range(4)]].to_numpy() if "p_fused_0" in pr else None
    g = calibrate_detector(det, X, y, (df["set"] == "train").to_numpy(), (df["set"] == "val").to_numpy(),
                           (df["launder"] != "none").to_numpy(), P_gbm, P_f)
    pr["p_gate"] = g
    pr.to_csv(a.predictions, index=False, compression="gzip")
    print("model sha256", det.save(a.model))


if __name__ == "__main__":
    main()
