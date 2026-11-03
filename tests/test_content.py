from pathlib import Path

import numpy as np
import pytest

from pixelproof import manipulations as M
from pixelproof.features import FEATURE_NAMES, copy_move_match, extract, gray, heatmap
from tests.test_trust import textured

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("family", ["authentic", "resample", "splice", "copy_move", "inpaint"])
@pytest.mark.parametrize("variant", ["dev", "heldout"])
def test_generators_are_deterministic_and_masked(family, variant):
    img, donor = textured(1), textured(2)
    a = M.make(img, donor, np.random.default_rng(3), family, variant)
    b = M.make(img, donor, np.random.default_rng(3), family, variant)
    out, mask, meta = a
    assert out.shape == (64, 64, 3) and out.dtype == np.uint8
    assert np.array_equal(out, b[0])
    assert (mask.sum() == 0) == (family == "authentic")
    if family != "authentic":
        assert not np.array_equal(out, img)


@pytest.mark.parametrize("strength", ["dev", "heldout"])
def test_laundering(strength):
    out, meta = M.launder(textured(4), np.random.default_rng(0), strength)
    assert out.shape == (64, 64, 3) and "launder" in meta


def test_features_complete_and_finite():
    f = extract(textured(5))
    assert list(f) == FEATURE_NAMES
    assert all(np.isfinite(v) for v in f.values())


def test_copy_move_is_found():
    img = textured(6)
    out, mask, _ = M.copy_move(img, np.random.default_rng(2), "dev")
    cnt_fake, _, cm_mask, _ = copy_move_match(gray(out))
    cnt_real, _, _, _ = copy_move_match(gray(img))
    assert cnt_fake > 10 * max(cnt_real, 1)
    assert (cm_mask & mask).sum() > 0.5 * mask.sum()


def test_heatmap_shape():
    h = heatmap(textured(7))
    assert h.shape == (64, 64) and 0 <= h.min() and h.max() <= 1.0001


@pytest.mark.skipif(not (ROOT / "models" / "detector.joblib").exists(), reason="train the model first")
def test_detector_output_contract():
    from pixelproof.detector import Detector
    det = Detector.load(ROOT / "models" / "detector.joblib")
    r = det.analyse(textured(8))
    assert set(r["probabilities"]) == {"authentic", "resampled_spliced", "copy_move", "generated_inpainted"}
    assert abs(sum(r["probabilities"].values()) - 1) < 1e-3
    assert r["manipulated"] == (r["manipulation_score"] >= r["threshold"])
