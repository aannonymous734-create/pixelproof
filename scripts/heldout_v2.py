"""Held-out set v2 (see pixelproof/heldout_v2.py).

  python scripts/heldout_v2.py freeze                    # render, hash, write results/heldout_v2_manifest.json
  python scripts/heldout_v2.py evaluate --tag current    # score a model on v2 (checks the hash first)

Sources: every patch of the test_heldout split (never used for training or calibration).
Per source: one authentic copy + one manipulated copy (group drawn uniformly, as in v1).
Splicing donors come from a DIFFERENT land-cover class of the same split.
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
from pixelproof import heldout_v2 as V  # noqa: E402
from pixelproof.data import list_samples, split_samples  # noqa: E402
from pixelproof.dataset import seed_of  # noqa: E402
from pixelproof.imageio import load_rgb  # noqa: E402

FAMS = {1: ("resample", "splice"), 2: ("copy_move",), 3: ("inpaint",)}


def jobs(data_dir):
    ss = split_samples(list_samples(data_dir))["test_heldout"]
    by_class = {}
    for s in ss:
        by_class.setdefault(s.landcover, []).append(s)
    out = []
    for s in ss:
        rng = np.random.default_rng(seed_of(s.sid, "heldout_v2"))
        cls = int(rng.integers(1, 4))
        fam = str(rng.choice(FAMS[cls]))
        others = [c for c in sorted(by_class) if c != s.landcover]
        dc = others[int(rng.integers(len(others)))]
        donor = by_class[dc][int(rng.integers(len(by_class[dc])))]
        for family in ("authentic", fam):
            out.append({"sid": s.sid, "landcover": s.landcover, "path": str(s.path), "donor": str(donor.path),
                        "family": family, "label": V.LABEL[family]})
    return out


def render(job):
    img, donor = load_rgb(job["path"]), load_rgb(job["donor"])
    rng = np.random.default_rng(seed_of(job["sid"], "heldout_v2", job["family"]))
    out, mask, meta = V.make(img, donor, rng, job["family"])
    return out, mask, meta


def render_all(js, workers=2):
    with Pool(workers) as p:
        return p.map(render, js, chunksize=64)


def digest(js, rendered):
    h = hashlib.sha256()
    for j, (img, mask, _) in zip(js, rendered):
        h.update(f"{j['sid']}|{j['family']}|{j['label']}|".encode())
        h.update(img.tobytes())
    return h.hexdigest()


def cmd_freeze(a):
    js = jobs(a.data_dir)
    r = render_all(js)
    man = {"description": "held-out v2: methods absent from training and from held-out v1 "
                          "(see pixelproof/heldout_v2.py)",
           "n_patches": len(js), "sha256": digest(js, r),
           "counts": {f: sum(j["family"] == f for j in js) for f in ("authentic", "resample", "splice", "copy_move",
                                                                    "inpaint")},
           "frozen_before_detector_changes": True}
    Path(a.results).mkdir(parents=True, exist_ok=True)
    (Path(a.results) / "heldout_v2_manifest.json").write_text(json.dumps(man, indent=2))
    print(json.dumps(man, indent=2))


def _feat(img):
    from pixelproof.features import FEATURE_NAMES, extract
    f = extract(img)
    return [f[k] for k in FEATURE_NAMES]


def cmd_evaluate(a):
    from sklearn.metrics import roc_auc_score
    from pixelproof.detector import Detector, decide
    man = json.loads((Path(a.results) / "heldout_v2_manifest.json").read_text())
    js = jobs(a.data_dir)
    r = render_all(js)
    if digest(js, r) != man["sha256"]:
        sys.exit("held-out v2 does not match its frozen hash: refusing to evaluate")
    imgs = np.stack([x[0] for x in r])
    with Pool(2) as p:
        X = np.array(p.map(_feat, list(imgs), chunksize=64))
    det = Detector.load(Path(a.models) / "detector.joblib")
    y = np.array([j["label"] for j in js])
    fam = np.array([j["family"] for j in js])
    lc = np.array([j["landcover"] for j in js])
    meth = np.array([x[2].get("method", "") for x in r])
    res = {"model_sha256": json.loads((Path(a.models) / "detector.json").read_text())["sha256"],
           "heldout_v2_sha256": man["sha256"], "n": int(len(y)), "models": {}}
    from pixelproof.calibration import adaptive
    P_g = det.gbm.predict_proba(X)
    g = det.gate_prob(X)
    variants = {"features (GBM)": (P_g, adaptive(g, det.threshold_gbm, det.threshold_proc_gbm)
                                    if det.threshold_proc_gbm is not None else det.threshold_gbm)}
    if det.fused:
        P_f = det.proba_from(X, imgs)
        variants["fused"] = (P_f, det.thresholds_for(X))
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
    out = Path(a.results) / f"heldout_v2_{a.tag}.json"
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("auc_roc", "detection_rate", "false_alarm_rate",
                                                                   "detection_by_family")}
                      for k, v in res["models"].items()}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["freeze", "evaluate"])
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--results", default="results")
    ap.add_argument("--models", default="models")
    ap.add_argument("--tag", default="current")
    a = ap.parse_args()
    {"freeze": cmd_freeze, "evaluate": cmd_evaluate}[a.cmd](a)


if __name__ == "__main__":
    main()
