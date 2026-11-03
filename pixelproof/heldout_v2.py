"""Held-out set v2: manipulation methods that appear NOWHERE in training or in held-out v1.

Created and frozen (SHA-256 recorded in results/heldout_v2_manifest.json) BEFORE any detector
change made after v1, because v1 had been looked at during development. This module is never
imported by training code.

| Group               | v2 method (new)                                                          |
|---------------------|--------------------------------------------------------------------------|
| resampled           | perspective warp or rescale with a biquadratic spline (order 2) kernel   |
| spliced             | Poisson blending (cv2.seamlessClone, normal or mixed) of an elliptical   |
|                     | region taken from a patch of a DIFFERENT land-cover class               |
| copy-move           | elliptical region MIRRORED (horizontal or vertical flip), translated,    |
|                     | softly blended                                                           |
| generated/inpainted | exemplar fill (patch-based, PatchMatch-style texture transfer) plus      |
|                     | injected sensor-like noise, so the region is not unnaturally smooth      |
"""
from __future__ import annotations

import warnings

import cv2
import numpy as np
from skimage.transform import ProjectiveTransform, rescale, warp

H = W = 64


def _ellipse_mask(rng, rmin=7, rmax=13, margin=3):
    ry, rx = rng.uniform(rmin, rmax, size=2)
    cy = rng.uniform(ry + margin, H - ry - margin)
    cx = rng.uniform(rx + margin, W - rx - margin)
    ang = rng.uniform(0, 180)
    m = np.zeros((H, W), np.uint8)
    cv2.ellipse(m, (int(round(cx)), int(round(cy))), (int(round(rx)), int(round(ry))), ang, 0, 360, 1, -1)
    return m.astype(bool)


def _blend(base, top, mask, feather):
    a = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), feather)[..., None] if feather > 0 else mask[..., None]
    return np.clip(base * (1 - a) + top * a + 0.5, 0, 255).astype(np.uint8)


def resample_v2(img, rng):
    if rng.random() < 0.5:
        src = np.array([[0, 0], [W, 0], [W, H], [0, H]], float)
        dst = src + rng.uniform(-9, 9, size=src.shape)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t = ProjectiveTransform()
            t.estimate(src, dst)
            out = warp(img / 255.0, t.inverse, order=2, mode="reflect")
        meta = {"method": "perspective_order2"}
    else:
        f = float(rng.uniform(1.25, 1.8))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            big = rescale(img / 255.0, f, order=2, channel_axis=-1, anti_aliasing=False)
        y, x = rng.integers(0, big.shape[0] - H + 1, size=2)
        out = big[y:y + H, x:x + W]
        meta = {"method": "rescale_order2", "factor": round(f, 3)}
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8), np.ones((H, W), bool), meta


def splice_v2(img, donor, rng):
    mask = _ellipse_mask(rng)
    ys, xs = np.nonzero(mask)
    cy, cx = int((ys.min() + ys.max()) // 2), int((xs.min() + xs.max()) // 2)
    mode = cv2.NORMAL_CLONE if rng.random() < 0.5 else cv2.MIXED_CLONE
    m8 = (mask * 255).astype(np.uint8)
    try:
        out = cv2.seamlessClone(donor, img, m8, (cx, cy), mode)
    except cv2.error:
        out = _blend(img.astype(np.float32), donor.astype(np.float32), mask, 1.0)
    return out, mask, {"method": "poisson_" + ("normal" if mode == cv2.NORMAL_CLONE else "mixed")}


def copy_move_v2(img, rng):
    for _ in range(100):
        mask = _ellipse_mask(rng, 6, 11)
        ys, xs = np.nonzero(mask)
        dy = int(rng.integers(-ys.min(), H - ys.max()))
        dx = int(rng.integers(-xs.min(), W - xs.max()))
        if np.hypot(dy, dx) > max(np.ptp(ys), np.ptp(xs)) + 6:
            break
    flip = int(rng.integers(0, 2))  # 0 vertical, 1 horizontal
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    region = img[y0:y1, x0:x1]
    rmask = mask[y0:y1, x0:x1]
    region, rmask = np.flip(region, axis=flip), np.flip(rmask, axis=flip)
    top = img.astype(np.float32).copy()
    dmask = np.zeros((H, W), bool)
    top[y0 + dy:y1 + dy, x0 + dx:x1 + dx] = region
    dmask[y0 + dy:y1 + dy, x0 + dx:x1 + dx] = rmask
    out = _blend(img.astype(np.float32), top, dmask, 0.8)
    return out, dmask, {"method": "mirrored_" + ("vertical" if flip == 0 else "horizontal"), "shift": [dy, dx]}


def inpaint_v2(img, rng):
    mask = _ellipse_mask(rng, 7, 13)
    out = img.astype(np.float32).copy()
    known = ~cv2.dilate(mask.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    cand = [(y, x) for y in range(0, H - 8) for x in range(0, W - 8) if known[y:y + 8, x:x + 8].all()]
    ys, xs = np.nonzero(mask)
    for y in range(ys.min() - ys.min() % 4, ys.max() + 1, 4):
        for x in range(xs.min() - xs.min() % 4, xs.max() + 1, 4):
            if not mask[y:y + 4, x:x + 4].any() or not cand:
                continue
            hh, ww = out[y:y + 4, x:x + 4].shape[:2]
            cur, w = out[y:y + hh, x:x + ww], (~mask[y:y + hh, x:x + ww])[..., None]
            # among 24 random exemplars, keep the one that best matches the already-known pixels
            best, bestd = None, np.inf
            for k in rng.choice(len(cand), size=min(24, len(cand)), replace=False):
                cy, cx = cand[k]
                d = float((((img[cy:cy + hh, cx:cx + ww].astype(np.float32) - cur) ** 2) * w).sum())
                if d < bestd:
                    best, bestd = (cy, cx), d
            cy, cx = best
            m = mask[y:y + hh, x:x + ww]
            out[y:y + hh, x:x + ww][m] = img[cy:cy + hh, cx:cx + ww].astype(np.float32)[m]
    resid = img.astype(np.float32) - cv2.GaussianBlur(img.astype(np.float32), (0, 0), 1.0)
    sigma = float(resid[known].std())
    out[mask] += rng.normal(0, sigma, (int(mask.sum()), 3))
    out = _blend(img.astype(np.float32), out, mask, 0.7)
    return out, mask, {"method": "exemplar_fill_noise", "noise_sigma": round(sigma, 2)}


LABEL = {"authentic": 0, "resample": 1, "splice": 1, "copy_move": 2, "inpaint": 3}


def make(img, donor, rng, family):
    if family == "authentic":
        return img.copy(), np.zeros((H, W), bool), {"method": "none"}
    if family == "resample":
        return resample_v2(img, rng)
    if family == "splice":
        return splice_v2(img, donor, rng)
    if family == "copy_move":
        return copy_move_v2(img, rng)
    if family == "inpaint":
        return inpaint_v2(img, rng)
    raise ValueError(family)
