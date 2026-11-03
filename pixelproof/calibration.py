"""Condition-aware alarm thresholds (protects authentic patches that were merely re-encoded).

Problem measured in the robustness sweep: an authentic EuroSAT patch that is simply re-saved as
JPEG/WebP carries codec traces that a forensic detector also sees in manipulated patches, so one
global threshold either accuses re-encoded authentic patches or misses manipulations in clean ones.

Solution: a small "re-encoding gate" g(x) in [0, 1] (gradient boosting on the same 48 features,
trained to recognise patches that went through JPEG/WebP/noise AFTER capture, whatever their
manipulation label) and a threshold that moves between two calibrated values:

    threshold(x) = c + g(x) * (p - c)

  c : calibrated so that <= target_fpr of CLEAN validation authentic patches raise an alarm
  p : calibrated so that <= target_fpr of RE-ENCODED validation authentic patches raise an alarm
Both are found by bisection under the soft rule, so the stated false-alarm budget holds for both
populations seen in validation. Unseen processing (JPEG 2000, radiometric stretch) is NOT covered
and is reported separately.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier


def train_gate(X: np.ndarray, reencoded: np.ndarray, seed: int = 0) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31, min_samples_leaf=30,
                                          early_stopping=True, validation_fraction=0.1, n_iter_no_change=30,
                                          random_state=seed).fit(X, reencoded.astype(int))


def adaptive(g: np.ndarray, c: float, p: float) -> np.ndarray:
    return c + np.asarray(g) * (p - c)


def _solve(s, g, fixed, solve_for, target, other_is_c):
    """Find the value v such that mean(s >= threshold) == target, threshold = c + g(p - c)."""
    lo, hi = -1.0, 2.0
    for _ in range(60):
        mid = (lo + hi) / 2
        c, p = (fixed, mid) if other_is_c else (mid, fixed)
        fa = float((s >= adaptive(g, c, p)).mean())
        if fa > target:
            lo = mid
        else:
            hi = mid
    return hi


def fit_thresholds(s_clean, g_clean, s_proc, g_proc, target: float) -> tuple[float, float]:
    """Return (c, p) giving <= target false alarms on clean AND on re-encoded authentic patches."""
    c = float(np.quantile(s_clean, 1 - target))
    p = float(np.quantile(s_proc, 1 - target))
    for _ in range(5):  # alternate: each population mostly constrains its own end point
        p = _solve(s_proc, g_proc, c, "p", target, other_is_c=True)
        c = _solve(s_clean, g_clean, p, "c", target, other_is_c=False)
    return c, p


def calibrate_detector(det, X, y, is_train, is_val, reencoded, P_gbm, P_fused=None, log=print):
    """Train the gate on training rows and set (c, p) for the feature model and the fused model.
    Returns the gate probability for every row."""
    det.gate = train_gate(X[is_train], reencoded[is_train])
    g = det.gate.predict_proba(X)[:, 1]
    clean_auth = is_val & (y == 0) & ~reencoded
    proc_auth = is_val & (y == 0) & reencoded
    acc = float(((g[is_val] >= 0.5) == reencoded[is_val]).mean())
    log(f"re-encoding gate: validation accuracy {acc:.3f}")
    pairs = [("gbm", P_gbm)] + ([("fused", P_fused)] if P_fused is not None else [])
    det.score_quantiles = {}
    for name, P in pairs:
        s = 1 - P[:, 0]
        det.score_quantiles[name] = np.quantile(s[clean_auth], np.linspace(0, 1, 2001))
        c, p = fit_thresholds(s[clean_auth], g[clean_auth], s[proc_auth], g[proc_auth], det.target_fpr)
        setattr(det, f"threshold_{name}", c)
        setattr(det, f"threshold_proc_{name}", p)
        log(f"{name}: threshold clean {c:.4f}, re-encoded {p:.4f}")
    return g
