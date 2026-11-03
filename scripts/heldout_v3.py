"""Held-out set v3 (see pixelproof/heldout_v3.py).

  python scripts/heldout_v3.py freeze                         # render, hash, write results/heldout_v3_manifest.json
  python scripts/heldout_v3.py evaluate --models models --tag shipped
  python scripts/heldout_v3.py evaluate --models models_candidate --tag candidate

Sources: every patch of the test_dev split (never used for training or calibration; held-out v2 uses test_heldout).
Per source: one authentic copy + one manipulated copy (group drawn uniformly, as in v1 and v2).
Splicing donors come from the SAME land-cover class of the same split (v2 used a different class).

A test set stays honest only if it is not used to choose between models. `evaluate` therefore refuses to score the
same model file twice (a second look would let the result steer a further change); pass --again only to re-print a
result after a crash, and say so.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof import heldout_v3 as V  # noqa: E402
from pixelproof.data import list_samples, split_samples  # noqa: E402
from pixelproof.dataset import seed_of  # noqa: E402
from pixelproof.imageio import load_rgb  # noqa: E402

FAMS = {1: ("resample", "splice"), 2: ("copy_move",), 3: ("inpaint",)}
TAG = "heldout_v3"


def jobs(data_dir):
    ss = split_samples(list_samples(data_dir))["test_dev"]
    by_class = {}
    for s in ss:
        by_class.setdefault(s.landcover, []).append(s)
    out = []
    for s in ss:
        rng = np.random.default_rng(seed_of(s.sid, TAG))
        cls = int(rng.integers(1, 4))
        fam = str(rng.choice(FAMS[cls]))
        same = [d for d in by_class[s.landcover] if d.sid != s.sid]
        donor = same[int(rng.integers(len(same)))]
        for family in ("authentic", fam):
            out.append({"sid": s.sid, "landcover": s.landcover, "path": str(s.path), "donor": str(donor.path),
                        "family": family, "label": V.LABEL[family]})
    return out


def render(job):
    img, donor = load_rgb(job["path"]), load_rgb(job["donor"])
    rng = np.random.default_rng(seed_of(job["sid"], TAG, job["family"]))
    return V.make(img, donor, rng, job["family"])


def render_all(js, workers=2):
    with Pool(workers) as p:
        return p.map(render, js, chunksize=64)


def digest(js, rendered):
    h = hashlib.sha256()
    for j, (img, _mask, _meta) in zip(js, rendered):
        h.update(f"{j['sid']}|{j['family']}|{j['label']}|".encode())
        h.update(img.tobytes())
    return h.hexdigest()


def cmd_freeze(a):
    path = Path(a.results) / "heldout_v3_manifest.json"
    if path.exists() and not a.again:
        sys.exit(f"{path} already exists: v3 is frozen. Refusing to re-freeze (it would change the test set).")
    js = jobs(a.data_dir)
    r = render_all(js, a.workers)
    man = {"description": "held-out v3: thin-strip shapes and methods absent from training (dev, dev_plus) and from "
                          "held-out v1 and v2 (see pixelproof/heldout_v3.py)",
           "source_split": "test_dev", "methods": list(V.METHODS),
           "n_patches": len(js), "sha256": digest(js, r),
           "counts": {f: sum(j["family"] == f for j in js) for f in ("authentic", "resample", "splice", "copy_move",
                                                                    "inpaint")},
           "frozen_before_candidate_training": True}
    Path(a.results).mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(man, indent=2))
    print(json.dumps(man, indent=2))


def _feat(img):
    from pixelproof.features import FEATURE_NAMES, extract
    f = extract(img)
    return [f[k] for k in FEATURE_NAMES]


def cmd_evaluate(a):
    from sklearn.metrics import roc_auc_score

    from pixelproof.calibration import adaptive
    from pixelproof.detector import Detector, decide
    man = json.loads((Path(a.results) / "heldout_v3_manifest.json").read_text())
    model_sha = json.loads((Path(a.models) / "detector.json").read_text())["sha256"]
    for prev in Path(a.results).glob("heldout_v3_*.json"):
        if prev.name != "heldout_v3_manifest.json" and not a.again:
            if json.loads(prev.read_text()).get("model_sha256") == model_sha:
                sys.exit(f"this model was already scored on v3 ({prev.name}): a second look is not allowed. "
                         "Use --again only to re-print after a crash.")
    js = jobs(a.data_dir)
    r = render_all(js, a.workers)
    if digest(js, r) != man["sha256"]:
        sys.exit("held-out v3 does not match its frozen hash: refusing to evaluate")
    imgs = np.stack([x[0] for x in r])
    with Pool(a.workers) as p:
        X = np.array(p.map(_feat, list(imgs), chunksize=64))
    det = Detector.load(Path(a.models) / "detector.joblib")
    y = np.array([j["label"] for j in js])
    fam = np.array([j["family"] for j in js])
    lc = np.array([j["landcover"] for j in js])
    meth = np.array([x[2].get("method", "") for x in r])
    res = {"model_sha256": model_sha, "heldout_v3_sha256": man["sha256"], "n": int(len(y)),
           "cnn_tta": bool(getattr(det, "cnn_tta", False)), "models": {}}
    P_g = det.gbm.predict_proba(X)
    g = det.gate_prob(X)
    variants = {"features (GBM)": (P_g, adaptive(g, det.threshold_gbm, det.threshold_proc_gbm)
                                    if det.threshold_proc_gbm is not None else det.threshold_gbm)}
    if det.fused:
        variants["fused"] = (det.proba_from(X, imgs), det.thresholds_for(X))
    for name, (P, thr) in variants.items():
        p = decide(P, thr)
        s = 1 - P[:, 0]
        res["models"][name] = {
            "auc_roc": float(roc_auc_score(y != 0, s)),
            "detection_rate": float((p[y != 0] != 0).mean()),
            "false_alarm_rate": float((p[y == 0] != 0).mean()),
            "type_accuracy_on_detected": float((p[(y != 0) & (p != 0)] == y[(y != 0) & (p != 0)]).mean()),
            "detection_by_family": {f: float((p[fam == f] != 0).mean()) for f in ("resample", "splice", "copy_move",
                                                                                   "inpaint")},
            "detection_by_method": {m: float((p[meth == m] != 0).mean()) for m in sorted(set(meth[y != 0]))},
            "false_alarm_by_landcover": {c: float((p[(lc == c) & (y == 0)] != 0).mean()) for c in sorted(set(lc))},
        }
    out = Path(a.results) / f"heldout_v3_{a.tag}.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("auc_roc", "detection_rate", "false_alarm_rate",
                                                                   "detection_by_family")}
                      for k, v in res["models"].items()}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["freeze", "evaluate"])
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--results", default="results")
    ap.add_argument("--models", default="models")
    ap.add_argument("--tag", default="current")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--again", action="store_true", help="override the once-only guards (say so when you report)")
    a = ap.parse_args()
    {"freeze": cmd_freeze, "evaluate": cmd_evaluate}[a.cmd](a)


if __name__ == "__main__":
    main()
