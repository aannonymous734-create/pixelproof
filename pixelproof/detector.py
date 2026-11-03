"""Content detector (Deliverable 4: AI or statistical detection).

Two complementary models, fused:
  * FEATURE MODEL  gradient-boosted trees (scikit-learn HistGradientBoostingClassifier) on the
                   48 explainable forensic features of pixelproof.features
  * PIXEL MODEL    a small forensic CNN with a fixed high-pass front end (pixelproof.cnn)
  Fused class probabilities:  P = w * P_features + (1 - w) * P_cnn   (w chosen on validation)

Classes: authentic / resampled_spliced / copy_move / generated_inpainted.

Decision rule (false alarms are controlled explicitly, as the jury tests authentic imagery):
  1. manipulation score  s = 1 - P(authentic)
  2. alarm if s >= threshold(x) = c + g(x) (p - c), where g(x) is the probability that the patch was
     re-encoded after capture, c gives <= target_fpr (5%) false alarms on clean validation authentic
     patches and p the same on re-encoded ones (pixelproof.calibration)
  3. if alarmed, type = argmax over the three manipulation classes

If PyTorch or the CNN file is unavailable, the detector falls back to the feature model with
its own calibrated threshold.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from . import LABELS, __version__
from .features import FEATURE_NAMES, extract, heatmap

PLAIN = {
    "rs": "periodic interpolation pattern (resampling trace)",
    "fq": "unusual frequency spectrum",
    "nz": "inconsistent or missing sensor noise",
    "cc": "broken cross-channel noise correlation",
    "cm": "duplicated regions inside the patch (copy-move)",
    "cs": "a region whose colour or noise does not match the rest (splicing)",
}

GBM_PARAMS = dict(max_iter=600, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=30,
                  l2_regularization=1.0, early_stopping=True, validation_fraction=0.1,
                  n_iter_no_change=40)


def train_gbm(X, y, seed=0, **hp) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(**{**GBM_PARAMS, "random_state": seed, **hp}).fit(X, y)


def threshold_for(scores_authentic: np.ndarray, target_fpr: float) -> float:
    return float(np.quantile(scores_authentic, 1 - target_fpr))


def decide(P: np.ndarray, threshold: float) -> np.ndarray:
    s = 1.0 - P[:, 0]
    return np.where(s >= threshold, 1 + P[:, 1:].argmax(1), 0)


@dataclass
class Detector:
    gbm: HistGradientBoostingClassifier
    features: list[str]
    target_fpr: float
    threshold_gbm: float
    w_gbm: float = 1.0
    threshold_fused: float | None = None
    cnn_file: str | None = None
    auth_mean: np.ndarray | None = None
    auth_std: np.ndarray | None = None
    info: dict = field(default_factory=dict)
    gate: HistGradientBoostingClassifier | None = None   # "was this patch re-encoded?" (calibration.py)
    threshold_proc_gbm: float | None = None
    threshold_proc_fused: float | None = None
    score_quantiles: dict | None = None  # clean validation authentic scores, for multi-tile images
    cnn_tta: bool = False  # average the CNN over 8 flips/rotations (models saved before this field load as False)
    _cnn: object = field(default=None, repr=False, compare=False)

    # ----------------------------------------------------------------- inference
    @property
    def fused(self) -> bool:
        return self._cnn is not None and self.threshold_fused is not None

    @property
    def threshold(self) -> float:
        """Threshold for clean (not re-encoded) patches."""
        return self.threshold_fused if self.fused else self.threshold_gbm

    def gate_prob(self, X: np.ndarray) -> np.ndarray:
        return self.gate.predict_proba(X)[:, 1] if self.gate is not None else np.zeros(len(X))

    def thresholds_for(self, X: np.ndarray) -> np.ndarray:
        """Per-patch threshold: moves from the clean to the re-encoded calibration point (calibration.py)."""
        p = self.threshold_proc_fused if self.fused else self.threshold_proc_gbm
        if p is None or self.gate is None:
            return np.full(len(X), self.threshold)
        from .calibration import adaptive
        return adaptive(self.gate_prob(X), self.threshold, p)

    def proba_from(self, X: np.ndarray, imgs: np.ndarray | None = None) -> np.ndarray:
        P = self.gbm.predict_proba(X)
        if self.fused and imgs is not None:
            from .cnn import predict_proba
            P = self.w_gbm * P + (1 - self.w_gbm) * predict_proba(self._cnn, imgs, tta=self.cnn_tta)
        return P

    def explain(self, x: np.ndarray, k: int = 3) -> list[str]:
        z = (x - self.auth_mean) / self.auth_std
        out = []
        for i in np.argsort(-np.abs(z))[:k]:
            if abs(z[i]) >= 2.5:
                name = self.features[i]
                out.append(f"{PLAIN[name.split('_')[0]]} ({name}, {abs(z[i]):.1f} sd from authentic patches)")
        return out

    def analyse(self, img: np.ndarray, with_heatmap: bool = True) -> dict:
        if img.shape[:2] != (64, 64):
            # never resize (it would add resampling traces): tile, with a corrected threshold
            from .inputs import analyse_any
            return analyse_any(self, img, with_heatmap=with_heatmap)
        f = extract(img)
        x = np.array([[f[n] for n in self.features]], dtype=np.float64)
        p = self.proba_from(x, img[None])[0]
        s = float(1 - p[0])
        thr = float(self.thresholds_for(x)[0])
        g = float(self.gate_prob(x)[0])
        alarm = s >= thr
        evidence = self.explain(x[0]) if alarm else []
        if g >= 0.5:
            evidence.append(f"patch appears re-encoded after capture (p={g:.2f}); threshold raised to {thr:.2f} "
                            "to avoid accusing benign re-compression")
        out = {
            "manipulation_score": round(s, 4),
            "threshold": round(thr, 4),
            "reencoding_probability": round(g, 4),
            "manipulated": bool(alarm),
            "type": LABELS[int(1 + p[1:].argmax())] if alarm else "authentic",
            "probabilities": {LABELS[i]: round(float(v), 4) for i, v in enumerate(p)},
            "evidence": evidence,
            "model": "features+cnn" if self.fused else "features",
        }
        if with_heatmap:
            out["heatmap"] = heatmap(img)
        return out

    # ------------------------------------------------------------------ persistence
    def save(self, path: str | Path) -> str:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cnn, self._cnn = self._cnn, None
        joblib.dump(self, path)
        self._cnn = cnn
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        card = {"sha256": digest, "target_fpr": self.target_fpr, "threshold_gbm": self.threshold_gbm,
                "threshold_fused": self.threshold_fused, "threshold_proc_gbm": self.threshold_proc_gbm,
                "threshold_proc_fused": self.threshold_proc_fused, "w_gbm": self.w_gbm, "cnn_file": self.cnn_file,
                "cnn_tta": self.cnn_tta, "features": self.features, **self.info}
        path.with_suffix(".json").write_text(json.dumps(card, indent=2, default=str))
        return digest

    @staticmethod
    def load(path: str | Path, use_cnn: bool = True) -> "Detector":
        """Only load model files you produced or whose SHA-256 you verified (joblib can run code)."""
        path = Path(path)
        det: Detector = joblib.load(path)
        if det.features != FEATURE_NAMES:
            raise ValueError("model was trained with a different feature set")
        det._cnn = None
        if use_cnn and det.cnn_file and (path.parent / det.cnn_file).exists():
            try:
                from .cnn import load as load_cnn
                det._cnn = load_cnn(path.parent / det.cnn_file)
            except ImportError:  # PyTorch not installed: feature model only
                det._cnn = None
        return det


def build(gbm, X_train, y_train, target_fpr, threshold_gbm, w_gbm=1.0, threshold_fused=None, cnn_file=None,
          info=None, cnn_tta=False) -> Detector:
    auth = X_train[y_train == 0]
    return Detector(gbm, list(FEATURE_NAMES), target_fpr, threshold_gbm, w_gbm, threshold_fused, cnn_file,
                    auth.mean(0), auth.std(0) + 1e-6, {"version": __version__, "labels": LABELS, **(info or {})},
                    cnn_tta=cnn_tta)
