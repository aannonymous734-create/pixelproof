"""Jury-input robustness: formats, bit depths, band counts, sizes and corrupted files."""
import io

import numpy as np
import pytest
import tifffile
from PIL import Image

from pixelproof import LABELS
from pixelproof.inputs import InputError, analyse_any, load_any, tile_threshold, tiles
from tests.test_trust import textured


def _png(arr, mode=None):
    buf = io.BytesIO()
    Image.fromarray(arr, mode=mode).save(buf, format="PNG")
    return buf.getvalue()


def _tif(arr):
    buf = io.BytesIO()
    tifffile.imwrite(buf, arr, photometric="rgb" if arr.ndim == 3 and arr.shape[-1] == 3 else "minisblack")
    return buf.getvalue()


def test_rgb_png_is_unchanged():
    img = textured(1)
    out, info = load_any(_png(img))
    assert np.array_equal(out, img) and "scaling" not in info


def test_grayscale_and_rgba():
    g = textured(2)[..., 0]
    out, info = load_any(_png(g))
    assert out.shape == (64, 64, 3) and np.array_equal(out[..., 1], g)
    rgba = np.dstack([textured(3), np.full((64, 64), 200, np.uint8)])
    out, info = load_any(_png(rgba))
    assert np.array_equal(out, textured(3)) and info["converted_from"] == "RGBA"


def test_eurosat_ms_13_band_geotiff_uses_b04_b03_b02():
    rng = np.random.default_rng(0)
    ms = rng.integers(0, 3000, size=(64, 64, 13)).astype(np.uint16)
    out, info = load_any(_tif(ms))
    assert out.shape == (64, 64, 3) and out.dtype == np.uint8
    expect = np.clip(ms[..., [3, 2, 1]] * 255.0 / 3000.0 + 0.5, 0, 255).astype(np.uint8)
    assert np.array_equal(out, expect)
    assert "B04, B03, B02" in info["channels"] and "Sentinel-2" in info["scaling"]
    # channels-first layout, as rasterio writes it
    out2, _ = load_any(_tif(np.moveaxis(ms, -1, 0)))
    assert np.array_equal(out2, out)


def test_16bit_and_float():
    a16 = (textured(4).astype(np.uint16) * 257)
    out, info = load_any(_tif(a16))
    assert np.abs(out.astype(int) - textured(4)).max() <= 1 and "257" in info["scaling"]
    f = textured(5).astype(np.float32) / 255
    out, info = load_any(_tif(f))
    assert np.abs(out.astype(int) - textured(5)).max() <= 1


@pytest.mark.parametrize("data", [b"", b"not an image at all", _png(textured(6))[:200], b"II*\x00garbage"])
def test_corrupted_files_raise_a_readable_error(data):
    with pytest.raises(InputError):
        load_any(data)


def test_unsupported_band_count():
    with pytest.raises(InputError):
        load_any(_tif(np.zeros((64, 64, 7), np.uint8)))


def test_tiles_cover_the_image_without_resizing():
    assert tiles(np.zeros((64, 64, 3))) == [(0, 0)]
    pos = tiles(np.zeros((100, 130, 3)))
    assert (0, 0) in pos and (36, 66) in pos and len(pos) == 2 * 3
    cover = np.zeros((100, 130), bool)
    for y, x in pos:
        cover[y:y + 64, x:x + 64] = True
    assert cover.all()


class StubDetector:
    """Scores each tile by its mean brightness, so the test controls which tile alarms."""
    target_fpr, fused = 0.05, True

    def __init__(self):
        self.score_quantiles = {"fused": np.linspace(0, 1, 2001)}  # clean scores ~ Uniform(0, 1)

    def analyse(self, img, with_heatmap=True):
        assert img.shape == (64, 64, 3)
        s = float(img.mean() / 255)
        p = {k: (1 - s if k == "authentic" else s / 3) for k in LABELS}
        r = {"manipulation_score": s, "threshold": 0.5, "reencoding_probability": 0.0, "manipulated": s >= 0.5,
             "type": "copy_move" if s >= 0.5 else "authentic", "probabilities": p, "evidence": ["x"],
             "model": "stub"}
        if with_heatmap:
            r["heatmap"] = np.full((64, 64), s, np.float32)
        return r


def test_tile_threshold_controls_image_level_false_alarms():
    det = StubDetector()
    assert tile_threshold(det, 1) is None
    t4 = tile_threshold(det, 4)
    # with Uniform clean scores, P(max of 4 > t4) must equal the 5% budget
    assert abs((1 - t4 ** 4) - 0.05) < 1e-3


def test_large_image_is_tiled_and_threshold_corrected():
    det = StubDetector()
    img = np.full((128, 128, 3), 140, np.uint8)  # every tile scores 0.55 > 0.5 single-tile threshold
    r = analyse_any(det, img)
    assert r["tiles"] == 4 and not r["manipulated"]  # corrected threshold (~0.987) suppresses the alarm
    img[64:, 64:] = 255  # one tile far above the corrected threshold
    r = analyse_any(det, img)
    assert r["manipulated"] and r["tiles_alarmed"] == 1 and "x=64, y=64" in r["evidence"][-1]
    assert r["heatmap"].shape == (128, 128)


def test_small_image_is_padded_and_flagged():
    r = analyse_any(StubDetector(), np.full((40, 50, 3), 10, np.uint8))
    assert r["tiles"] == 1 and "smaller than 64x64" in r["input_note"] and r["heatmap"].shape == (40, 50)
