"""Held-out set v3: manipulation methods that appear NOWHERE in training (dev, dev_plus) or in held-out v1/v2.

Held-out v2 was used to measure the detector changes made after v1, so it is no longer unbiased for any FURTHER change
(docs/KNOWN_LIMITATIONS.md #14). v3 was created and frozen (SHA-256 in results/heldout_v3_manifest.json) BEFORE the
candidate detector of results/candidate/ was trained. This module is never imported by training code.

The shapes are thin, elongated strips (roads, rivers, field boundaries), a family absent from every other set
(rectangles in dev, polygons in v1, ellipses in v2, irregular blobs in dev_plus).

| Group               | v3 method (new)                                                                        |
|---------------------|----------------------------------------------------------------------------------------|
| resampled           | Fourier (sinc) resampling, anisotropic: different scale factors along the two axes     |
| spliced             | thin strip from a patch of the SAME land-cover class, Laplacian-pyramid blended        |
| copy-move           | three small strip clones of one source region, pasted with hard edges                  |
| generated/inpainted | strip removed and filled by push-pull multiscale interpolation, plus sensor-like grain |
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.signal import resample as fourier_resample

H = W = 64


def strip_mask(rng, length=(30, 56), width=(3, 7)) -> np.ndarray:
    """A thin rotated bar (road / river / field boundary), fully inside the patch."""
    m = np.zeros((H, W), np.uint8)
    for _ in range(50):
        ln = float(rng.uniform(*length))
        wd = float(rng.uniform(*width))
        ang = float(rng.uniform(0, 180))
        cx, cy = rng.uniform(12, W - 12, size=2)
        box = cv2.boxPoints(((float(cx), float(cy)), (ln, wd), ang))
        if box.min() >= 1 and box[:, 0].max() <= W - 2 and box[:, 1].max() <= H - 2:
            break
    cv2.fillPoly(m, [np.round(box).astype(np.int32)], 1)
    return m.astype(bool)


def resample_v3(img, rng):
    """Spectral (sinc) interpolation: zero-padding in the Fourier domain, a kernel no other set uses."""
    for _ in range(20):
        fy, fx = rng.uniform(1.2, 1.75, size=2)
        if abs(fy - fx) >= 0.15:  # anisotropic on purpose
            break
    big = fourier_resample(img.astype(np.float64), int(round(H * fy)), axis=0)
    big = fourier_resample(big, int(round(W * fx)), axis=1)
    y = int(rng.integers(0, big.shape[0] - H + 1))
    x = int(rng.integers(0, big.shape[1] - W + 1))
    out = np.clip(big[y:y + H, x:x + W] + 0.5, 0, 255).astype(np.uint8)
    return out, np.ones((H, W), bool), {"method": "fourier_anisotropic", "fy": round(float(fy), 3),
                                         "fx": round(float(fx), 3)}


def _pyramid_blend(base: np.ndarray, top: np.ndarray, mask: np.ndarray, levels: int = 3) -> np.ndarray:
    """Classic Laplacian-pyramid blending (Burt & Adelson): each frequency band is blended with a mask
    smoothed at the matching scale."""
    ga, gb, gm = [base.astype(np.float32)], [top.astype(np.float32)], [mask.astype(np.float32)]
    for _ in range(levels):
        ga.append(cv2.pyrDown(ga[-1]))
        gb.append(cv2.pyrDown(gb[-1]))
        gm.append(cv2.pyrDown(gm[-1]))
    out = gb[-1] * gm[-1][..., None] + ga[-1] * (1 - gm[-1][..., None])
    for i in range(levels - 1, -1, -1):
        size = (ga[i].shape[1], ga[i].shape[0])
        la = ga[i] - cv2.pyrUp(ga[i + 1], dstsize=size)
        lb = gb[i] - cv2.pyrUp(gb[i + 1], dstsize=size)
        m = gm[i][..., None]
        out = cv2.pyrUp(out, dstsize=size) + lb * m + la * (1 - m)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def splice_v3(img, donor, rng):
    mask = strip_mask(rng)
    # two levels only, and the blend is kept within 2 px of the strip: on a 64x64 patch a deeper pyramid spreads a
    # visible low-frequency halo far beyond the pasted region, which would make the set unrealistically easy
    blended = _pyramid_blend(img, donor, mask, levels=2)
    near = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    out = np.where(near[..., None], blended, img)
    return out, mask, {"method": "strip_pyramid_blend"}


def copy_move_v3(img, rng):
    """One small strip region cloned three times to different places, hard-edged (no blending)."""
    src = strip_mask(rng, length=(12, 21), width=(3, 6))
    ys, xs = np.nonzero(src)
    out = img.copy()
    dmask = np.zeros((H, W), bool)
    clones = 0
    for _ in range(200):
        dy = int(rng.integers(-ys.min(), H - ys.max()))
        dx = int(rng.integers(-xs.min(), W - xs.max()))
        ty, tx = ys + dy, xs + dx
        moved = np.zeros((H, W), bool)
        moved[ty, tx] = True
        if np.hypot(dy, dx) < 8 or (moved & (dmask | src)).any():
            continue  # keep clones apart from the source and from each other
        out[ty, tx] = img[ys, xs]
        dmask |= moved
        clones += 1
        if clones == 3:
            break
    return out, dmask, {"method": "multi_strip_clone", "clones": clones}


def _push_pull(img: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Fill unknown pixels by multiscale interpolation: average the known pixels down a pyramid
    (push), then fill each level's holes from the coarser level (pull)."""
    vals, wts = [img.astype(np.float32) * known[..., None]], [known.astype(np.float32)]
    while vals[-1].shape[0] > 2:
        vals.append(cv2.resize(vals[-1], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
        wts.append(cv2.resize(wts[-1], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
    filled = vals[-1] / np.maximum(wts[-1], 1e-6)[..., None]
    for i in range(len(vals) - 2, -1, -1):
        size = (vals[i].shape[1], vals[i].shape[0])
        up = cv2.resize(filled, size, interpolation=cv2.INTER_LINEAR)
        w = np.clip(wts[i], 0, 1)[..., None]
        here = vals[i] / np.maximum(wts[i], 1e-6)[..., None]
        filled = w * here + (1 - w) * up
    return filled


def inpaint_v3(img, rng):
    mask = strip_mask(rng, length=(28, 50), width=(4, 8))
    out = img.astype(np.float32).copy()
    fill = _push_pull(img, ~mask)
    resid = img.astype(np.float32) - cv2.GaussianBlur(img.astype(np.float32), (0, 0), 1.0)
    sigma = float(resid[~mask].std())
    out[mask] = fill[mask] + rng.normal(0, sigma, (int(mask.sum()), 3))
    return np.clip(out + 0.5, 0, 255).astype(np.uint8), mask, {"method": "push_pull_grain",
                                                                 "noise_sigma": round(sigma, 2)}


LABEL = {"authentic": 0, "resample": 1, "splice": 1, "copy_move": 2, "inpaint": 3}
METHODS = ("fourier_anisotropic", "strip_pyramid_blend", "multi_strip_clone", "push_pull_grain")


def make(img, donor, rng, family):
    if family == "authentic":
        return img.copy(), np.zeros((H, W), bool), {"method": "none"}
    if family == "resample":
        return resample_v3(img, rng)
    if family == "splice":
        return splice_v3(img, donor, rng)
    if family == "copy_move":
        return copy_move_v3(img, rng)
    if family == "inpaint":
        return inpaint_v3(img, rng)
    raise ValueError(family)
