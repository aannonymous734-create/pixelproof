"""Guards for the candidate-detector work (results/candidate/): the shipped model and its data recipe must not change,
the new training edits and held-out v3 must stay separate, and test-time averaging must be sound."""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pixelproof import heldout_v3 as V3
from pixelproof import manipulations as M
from pixelproof.dataset import jobs_for_split, render

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "eurosat"
needs_data = pytest.mark.skipif(not DATA.exists(), reason="EuroSAT not downloaded")

V1_METHODS = {"bicubic", "lanczos", "navier_stokes", "biharmonic", "texture_synth"}
V2_METHODS = {"perspective_order2", "rescale_order2", "poisson_normal", "poisson_mixed", "mirrored_vertical",
              "mirrored_horizontal", "exemplar_fill_noise"}
DEV_METHODS = {"bilinear", "telea"}


def _rgb(seed):
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 200, (64, 64, 3)).astype(np.float32)
    import cv2
    return np.clip(cv2.GaussianBlur(base, (0, 0), 2) + rng.normal(0, 3, base.shape), 0, 255).astype(np.uint8)


def _splits():
    from pixelproof.data import list_samples, split_samples
    return split_samples(list_samples(DATA))


# ------------------------------------------------------------------ separation of training and test methods
def test_new_training_and_v3_methods_are_disjoint_from_every_other_set():
    plus, v3 = set(M.DEV_PLUS_METHODS), set(V3.METHODS)
    assert not plus & v3
    for other in (V1_METHODS, V2_METHODS, DEV_METHODS):
        assert not plus & other and not v3 & other


@pytest.mark.parametrize("family", ["resample", "splice", "copy_move", "inpaint"])
def test_dev_plus_and_v3_are_deterministic_and_well_formed(family):
    img, donor = _rgb(1), _rgb(2)
    for gen in (lambda r: M.make(img, donor, r, family, "dev_plus"), lambda r: V3.make(img, donor, r, family)):
        a, b = gen(np.random.default_rng(5)), gen(np.random.default_rng(5))
        assert (a[0] == b[0]).all() and (a[1] == b[1]).all()
        out, mask, _ = a
        assert out.shape == (64, 64, 3) and out.dtype == np.uint8 and mask.shape == (64, 64) and mask.any()
        assert (out != img).any()


def test_held_out_v3_is_never_imported_by_training_code():
    for f in ("scripts/train.py", "scripts/build_features.py", "pixelproof/dataset.py", "pixelproof/manipulations.py",
              "pixelproof/detector.py", "pixelproof/cnn.py", "pixelproof/calibration.py"):
        tree = ast.parse((ROOT / f).read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any("heldout_v3" in x for x in names | mods), f


# ---------------------------------------------------------------- the shipped recipe and model are unchanged
@needs_data
def test_default_recipe_is_unchanged_by_the_train_variants_option():
    splits = _splits()
    for split in ("train", "val", "test_dev", "test_heldout"):
        ss = splits[split][:200]
        old, new = jobs_for_split(split, ss), jobs_for_split(split, ss, train_variants=("dev",))
        assert old == new
        mixed = jobs_for_split(split, ss, train_variants=("dev", "dev_plus"))
        if split.startswith("test"):
            assert mixed == old  # the test sets never change
        else:
            assert {j["variant"] for j in mixed} >= {"dev_plus"}


@needs_data
def test_shipped_training_pixels_are_reproduced_exactly():
    """Features stored in results/features.csv.gz when the shipped model was trained must be recomputed exactly."""
    from pixelproof.features import FEATURE_NAMES, extract
    df = pd.read_csv(ROOT / "results" / "features.csv.gz", nrows=40000)
    splits = _splits()
    for set_ in ("train", "val"):
        rows = df[(df["set"] == set_) & (df["family"] != "authentic")].head(4)
        jobs = {(j["set"], j["sid"], j["family"]): j for j in jobs_for_split(set_, splits[set_])}
        for r in rows.itertuples(index=False):
            f = extract(render(jobs[(r.set, r.sid, r.family)])[0])
            assert np.allclose([f[k] for k in FEATURE_NAMES], [getattr(r, k) for k in FEATURE_NAMES], atol=1e-6)


@needs_data
def test_shipped_detector_gives_the_stored_fused_probabilities():
    """The code changes (tta option, width inference, dropout module) leave the shipped model's output identical."""
    pytest.importorskip("torch")
    from pixelproof.detector import Detector
    from pixelproof.features import FEATURE_NAMES
    det = Detector.load(ROOT / "models" / "detector.joblib")
    assert det.fused and det.cnn_tta is False
    pred = pd.read_csv(ROOT / "results" / "predictions.csv.gz")
    feats = pd.read_csv(ROOT / "results" / "features.csv.gz")
    rows = pred[pred["set"] == "test_dev"].head(12)
    jobs = {(j["set"], j["sid"], j["family"]): j for j in jobs_for_split("test_dev", _splits()["test_dev"])}
    imgs = np.stack([render(jobs[(r.set, r.sid, r.family)])[0] for r in rows.itertuples(index=False)])
    key = feats.set_index(["set", "sid", "family"])
    X = np.array([key.loc[(r.set, r.sid, r.family), FEATURE_NAMES].to_numpy(float) for r in rows.itertuples()])
    P = det.proba_from(X, imgs)
    stored = rows[[f"p_fused_{i}" for i in range(4)]].to_numpy()
    assert np.allclose(P, stored, atol=1e-4)


# ------------------------------------------------------------------------------- test-time averaging
def test_tta_is_a_probability_and_invariant_to_flips_and_rotations():
    torch = pytest.importorskip("torch")
    from pixelproof import cnn
    torch.manual_seed(0)
    net = cnn.PixelNet(width=8)
    imgs = np.stack([_rgb(s) for s in range(3)])
    P = cnn.predict_proba(net, imgs, tta=True)
    assert P.shape == (3, 4) and np.allclose(P.sum(1), 1, atol=1e-5)
    for t in (lambda a: a[:, :, ::-1], lambda a: a[:, ::-1], lambda a: np.rot90(a, 1, (1, 2))):
        assert np.allclose(cnn.predict_proba(net, np.ascontiguousarray(t(imgs)), tta=True), P, atol=1e-5)


def test_cnn_width_is_read_from_the_file(tmp_path):
    pytest.importorskip("torch")
    from pixelproof import cnn
    for w in (8, 32):
        cnn.save(cnn.PixelNet(width=w), tmp_path / f"n{w}.pt")
        assert cnn.load(tmp_path / f"n{w}.pt").b1[0].out_channels == w
    shipped = ROOT / "models" / "pixelnet.pt"
    if shipped.exists():
        assert cnn.load(shipped).b1[0].out_channels == 16
