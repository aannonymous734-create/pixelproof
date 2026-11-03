"""Controlled manipulation generator (the "attack lab" for content).

The official standard test names three manipulation groups:
    1. resampled / spliced     2. copy-move     3. generated / inpainted

Every generator has two variant sets:
    "dev"     - used for TRAINING and for the in-distribution test
    "heldout" - different algorithms / shapes / parameters, NEVER seen in training,
                used to rehearse the jury's held-out patches

Every call returns (image, mask, meta). The mask marks manipulated pixels (all ones for a
global resampling). Everything is deterministic given the numpy Generator passed in.
Official data is never modified: generators work on in-memory copies.
"""
from __future__ import annotations

import cv2
import numpy as np
from skimage.restoration import inpaint_biharmonic

from .imageio import jpeg_roundtrip

H = W = 64


# --------------------------------------------------------------------------- masks
def rect_mask(rng, size_range=(12, 26)) -> np.ndarray:
    h = int(rng.integers(*size_range))
    w = int(rng.integers(*size_range))
    y = int(rng.integers(0, H - h))
    x = int(rng.integers(0, W - w))
    m = np.zeros((H, W), bool)
    m[y:y + h, x:x + w] = True
    return m


def poly_mask(rng, radius_range=(7, 14)) -> np.ndarray:
    r = float(rng.uniform(*radius_range))
    cy, cx = rng.uniform(r + 2, H - r - 2, size=2)
    n = int(rng.integers(5, 9))
    ang = np.sort(rng.uniform(0, 2 * np.pi, n))
    rad = r * rng.uniform(0.6, 1.2, n)
    pts = np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], 1).round().astype(np.int32)
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [pts], 1)
    return m.astype(bool)


def _alpha(mask: np.ndarray, feather: float) -> np.ndarray:
    a = mask.astype(np.float32)
    if feather > 0:
        a = cv2.GaussianBlur(a, (0, 0), feather)
    return a[..., None]


def _blend(base: np.ndarray, top: np.ndarray, mask: np.ndarray, feather: float) -> np.ndarray:
    a = _alpha(mask, feather)
    out = base.astype(np.float32) * (1 - a) + top.astype(np.float32) * a
    return np.clip(out.round(), 0, 255).astype(np.uint8)


# ----------------------------------------------------------------- 1a. resampling
def resample(img, rng, variant="dev"):
    if variant == "dev":
        interp, interp_name = cv2.INTER_LINEAR, "bilinear"
        op = rng.choice(["upscale", "down_up", "rotate"])
        f_up, f_down, ang = rng.uniform(1.15, 1.5), rng.uniform(0.7, 0.88), rng.uniform(4, 12)
    else:
        interp, interp_name = (cv2.INTER_CUBIC, "bicubic") if rng.random() < 0.5 else (cv2.INTER_LANCZOS4, "lanczos")
        op = rng.choice(["upscale", "down_up", "rotate"])
        f_up, f_down, ang = rng.uniform(1.6, 2.2), rng.uniform(0.5, 0.65), rng.uniform(15, 35)
    if op == "upscale":
        s = int(round(H * f_up))
        big = cv2.resize(img, (s, s), interpolation=interp)
        y, x = rng.integers(0, s - H + 1, size=2)
        out = big[y:y + H, x:x + W]
        p = {"factor": round(float(f_up), 3)}
    elif op == "down_up":
        s = int(round(H * f_down))
        small = cv2.resize(img, (s, s), interpolation=cv2.INTER_AREA)
        out = cv2.resize(small, (W, H), interpolation=interp)
        p = {"factor": round(float(f_down), 3)}
    else:
        a = float(ang) * (1 if rng.random() < 0.5 else -1)
        M = cv2.getRotationMatrix2D((W / 2, H / 2), a, 1.25)
        out = cv2.warpAffine(img, M, (W, H), flags=interp, borderMode=cv2.BORDER_REFLECT)
        p = {"angle": round(a, 2)}
    return out, np.ones((H, W), bool), {"family": "resample", "op": str(op), "interp": interp_name, **p}


# ------------------------------------------------------------------- 1b. splicing
def splice(img, donor, rng, variant="dev"):
    if variant == "dev":
        mask = rect_mask(rng)
        # v2 recipe: half of the training splices have softly blended (feathered) edges, so the
        # detector cannot rely on hard edges alone (held-out v1 splices are therefore no longer
        # fully unseen; held-out v2 uses Poisson blending, still never seen)
        feather = float(rng.uniform(0.6, 1.5)) if rng.random() < 0.5 else 0.0
        scale, colour_match = 1.0, False
    else:
        mask = poly_mask(rng)
        feather, scale, colour_match = float(rng.uniform(0.8, 1.6)), float(rng.uniform(0.7, 1.4)), True
    src = donor
    if scale != 1.0:
        s = max(H, int(round(H * scale)))
        src = cv2.resize(donor, (s, s), interpolation=cv2.INTER_CUBIC)
        y, x = rng.integers(0, s - H + 1, size=2)
        src = src[y:y + H, x:x + W]
    # take the donor content from a random offset (the pasted region is not co-located)
    dy, dx = rng.integers(-20, 21, size=2)
    src = np.roll(src, (int(dy), int(dx)), axis=(0, 1))
    if colour_match:  # make the paste harder to see: match local mean/std per channel
        m = mask
        src = src.astype(np.float32)
        for c in range(3):
            t, s_ = img[..., c][m].astype(np.float32), src[..., c][m]
            src[..., c] = (src[..., c] - s_.mean()) / (s_.std() + 1e-3) * (t.std() + 1e-3) + t.mean()
        src = np.clip(src, 0, 255).astype(np.uint8)
    out = _blend(img, src, mask, feather)
    return out, mask, {"family": "splice", "shape": "rect" if variant == "dev" else "poly",
                       "feather": round(feather, 2), "scale": round(scale, 3), "colour_match": colour_match}


# ------------------------------------------------------------------- 2. copy-move
def copy_move(img, rng, variant="dev"):
    for _ in range(50):
        if variant == "dev":
            src_mask = rect_mask(rng, (10, 22))
        else:
            src_mask = poly_mask(rng, (6, 12))
        ys, xs = np.nonzero(src_mask)
        hh, ww = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        dy = int(rng.integers(-ys.min(), H - ys.max()))
        dx = int(rng.integers(-xs.min(), W - xs.max()))
        if np.hypot(dy, dx) >= max(hh, ww) * 0.8 + 4:
            break
    patch = img.copy()
    meta = {"family": "copy_move", "shape": "rect" if variant == "dev" else "poly", "shift": [dy, dx]}
    if variant == "heldout":
        cy, cx = ys.mean(), xs.mean()
        ang = float(rng.choice([90, 180, 270, rng.uniform(-25, 25)]))
        sc = float(rng.uniform(0.9, 1.1))
        M = cv2.getRotationMatrix2D((cx, cy), ang, sc)
        patch = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        src_mask = cv2.warpAffine(src_mask.astype(np.uint8), M, (W, H), flags=cv2.INTER_NEAREST).astype(bool)
        noise = rng.normal(0, 1.0, patch.shape)
        patch = np.clip(patch + noise, 0, 255).astype(np.uint8)
        meta.update({"rotate": round(ang, 1), "scale": round(sc, 3), "noise": 1.0})
    moved = np.roll(patch, (dy, dx), axis=(0, 1))
    dst_mask = np.roll(src_mask, (dy, dx), axis=(0, 1))
    feather = 0.0 if variant == "dev" else float(rng.uniform(0.6, 1.2))
    out = _blend(img, moved, dst_mask, feather)
    return out, dst_mask, meta


# ---------------------------------------------------------- 3. generated / inpainted
def _texture_synth(img, mask, rng):
    """Generator-style fill: smooth random field matched to the surrounding statistics.
    Imitates the over-smooth, noise-free texture typical of generative fills."""
    ring = cv2.dilate(mask.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~mask
    out = img.astype(np.float32).copy()
    field = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 3.0)
    field /= field.std() + 1e-6
    for c in range(3):
        mu, sd = img[..., c][ring].mean(), img[..., c][ring].std()
        out[..., c][mask] = (mu + 0.6 * sd * field)[mask]
    return np.clip(out, 0, 255).astype(np.uint8)


def inpaint(img, rng, variant="dev"):
    if variant == "dev":
        mask = rect_mask(rng, (10, 24)) if rng.random() < 0.5 else poly_mask(rng, (6, 12))
        out = cv2.inpaint(img, mask.astype(np.uint8), 3, cv2.INPAINT_TELEA)
        method = "telea"
    else:
        mask = poly_mask(rng, (7, 14))
        method = str(rng.choice(["navier_stokes", "biharmonic", "texture_synth"]))
        if method == "navier_stokes":
            out = cv2.inpaint(img, mask.astype(np.uint8), 5, cv2.INPAINT_NS)
        elif method == "biharmonic":
            out = inpaint_biharmonic(img.astype(np.float64) / 255.0, mask, channel_axis=-1)
            out = np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)
        else:
            out = _texture_synth(img, mask, rng)
    return out, mask, {"family": "inpaint", "method": method}


# ------------------------------------------------- dev_plus: extra TRAINING-only variants
# Added for the candidate detector (results/candidate/). Irregular BLOB shapes and methods that appear in none of the
# held-out sets: v1 = polygons, bicubic/Lanczos, per-channel colour matching, Navier-Stokes/biharmonic/texture synth;
# v2 = ellipses, spline/perspective, Poisson, mirrored copies, exemplar fill; v3 = thin strips, Fourier resampling,
# pyramid blending, multi-clone, push-pull fill. The "dev" functions above are untouched (same pixels as before).
DEV_PLUS_METHODS = ("nearest_upscale", "shear", "blob_hard", "blob_ramp", "blob_gain_clone", "telea_blob",
                    "ring_mean_noise")


def blob_mask(rng, area=(110, 520)) -> np.ndarray:
    """An irregular, compact blob: thresholded smoothed noise around a random centre."""
    yy, xx = np.mgrid[:H, :W]
    for _ in range(40):
        field = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), float(rng.uniform(3, 6)))
        cy, cx = rng.uniform(14, H - 14, size=2)
        r = float(rng.uniform(8, 15))
        field -= ((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * r * r) * field.std() * 3  # favour the centre
        target = int(rng.integers(*area))
        thr = np.partition(field.ravel(), -target)[-target]
        m = (field >= thr).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=4)
        if n > 1:
            k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            m = lab == k
            ys, xs = np.nonzero(m)
            if area[0] <= m.sum() and ys.min() > 0 and xs.min() > 0 and ys.max() < H - 1 and xs.max() < W - 1:
                return m
    return rect_mask(rng)  # practically never reached


def _ramp_alpha(mask: np.ndarray, width: float) -> np.ndarray:
    """Linear edge ramp from the distance to the border (not a Gaussian feather)."""
    d = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    return np.clip(d / width, 0, 1)[..., None]


def resample_plus(img, rng):
    if rng.random() < 0.5:
        f = float(rng.uniform(1.1, 1.6))
        s = int(round(H * f))
        big = cv2.resize(img, (s, s), interpolation=cv2.INTER_NEAREST)
        y, x = rng.integers(0, s - H + 1, size=2)
        out, meta = big[y:y + H, x:x + W], {"method": "nearest_upscale", "factor": round(f, 3)}
    else:
        sh = float(rng.uniform(0.08, 0.25)) * (1 if rng.random() < 0.5 else -1)
        M = np.float32([[1, sh, -sh * H / 2], [0, 1, 0]]) if rng.random() < 0.5 else \
            np.float32([[1, 0, 0], [sh, 1, -sh * W / 2]])
        out = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        meta = {"method": "shear", "shear": round(sh, 3)}
    return out, np.ones((H, W), bool), {"family": "resample", "variant": "dev_plus", **meta}


def splice_plus(img, donor, rng):
    mask = blob_mask(rng)
    dy, dx = rng.integers(-20, 21, size=2)
    src = np.roll(donor, (int(dy), int(dx)), axis=(0, 1)).astype(np.float32)
    # match only the overall brightness (one gain for all channels; v1 matches every channel's mean and std)
    gain = float(np.clip((img[mask].astype(np.float32).mean() + 1) / (src[mask].mean() + 1), 0.75, 1.33))
    src = np.clip(src * gain, 0, 255)
    if rng.random() < 0.5:
        a, method = mask[..., None].astype(np.float32), "blob_hard"
    else:
        a, method = _ramp_alpha(mask, float(rng.uniform(1.5, 3.0))), "blob_ramp"
    out = np.clip(img.astype(np.float32) * (1 - a) + src * a + 0.5, 0, 255).astype(np.uint8)
    return out, mask, {"family": "splice", "variant": "dev_plus", "method": method, "gain": round(float(gain), 3)}


def copy_move_plus(img, rng):
    for _ in range(50):
        src_mask = blob_mask(rng, (80, 320))
        ys, xs = np.nonzero(src_mask)
        dy = int(rng.integers(-ys.min(), H - ys.max()))
        dx = int(rng.integers(-xs.min(), W - xs.max()))
        if np.hypot(dy, dx) >= max(np.ptp(ys), np.ptp(xs)) * 0.8 + 4:
            break
    g = float(rng.uniform(0.92, 1.08))
    moved = np.clip(np.roll(img.astype(np.float32), (dy, dx), axis=(0, 1)) * g, 0, 255)
    dst = np.roll(src_mask, (dy, dx), axis=(0, 1))
    out = img.copy()
    out[dst] = (moved[dst] + 0.5).astype(np.uint8)
    return out, dst, {"family": "copy_move", "variant": "dev_plus", "method": "blob_gain_clone",
                      "shift": [dy, dx], "gain": round(g, 3)}


def inpaint_plus(img, rng):
    mask = blob_mask(rng)
    if rng.random() < 0.5:
        out, method = cv2.inpaint(img, mask.astype(np.uint8), 3, cv2.INPAINT_TELEA), "telea_blob"
    else:
        ring = cv2.dilate(mask.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~mask
        resid = img.astype(np.float32) - cv2.GaussianBlur(img.astype(np.float32), (0, 0), 1.0)
        sigma = float(resid[ring].std())
        out = img.astype(np.float32).copy()
        out[mask] = img[ring].astype(np.float32).mean(0) + rng.normal(0, sigma, (int(mask.sum()), 3))
        out, method = np.clip(out + 0.5, 0, 255).astype(np.uint8), "ring_mean_noise"
    return out, mask, {"family": "inpaint", "variant": "dev_plus", "method": method}


# --------------------------------------------------------------------- laundering
def _webp_roundtrip(img, q):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="WEBP", quality=int(q))
    buf.seek(0)
    return np.asarray(Image.open(buf).convert("RGB"), dtype=np.uint8).copy()


def _jp2_roundtrip(img, rate):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="JPEG2000", quality_mode="rates", quality_layers=[float(rate)])
    buf.seek(0)
    return np.asarray(Image.open(buf).convert("RGB"), dtype=np.uint8).copy()


def _radiometric(img, rng):
    g, c, b = float(rng.uniform(0.7, 1.4)), float(rng.uniform(0.8, 1.25)), float(rng.uniform(-15, 15))
    x = (img.astype(np.float32) / 255.0) ** g
    x = (x - 0.5) * c + 0.5
    return np.clip(x * 255 + b, 0, 255).round().astype(np.uint8), {"gamma": round(g, 2), "contrast": round(c, 2),
                                                                     "brightness": round(b, 1)}


def launder(img, rng, strength="dev"):
    """Benign-looking post-processing applied to the WHOLE patch (authentic and manipulated alike,
    so it is never itself a label). It hides traces AND causes false alarms on authentic patches.

    dev     (training augmentation): 1-2 of {JPEG q40-95, WebP q40-95, Gaussian noise s0.5-4}
            (no blur: interpolation IS low-pass filtering, so "benign blur" would teach the model to
             ignore resampling traces; measured in iteration 3)
    heldout (never seen in training): JPEG 2000 (the codec of Sentinel-2 products, compression
                                      ratio 8-30) and/or radiometric stretch (gamma, contrast, brightness)
    """
    out = img
    if strength == "dev":
        ops = list(rng.choice(["jpeg", "webp", "noise"], size=int(rng.integers(1, 3)), replace=False))
        meta = {"launder": "+".join(ops)}
        for op in ops:
            if op == "jpeg":
                q = int(rng.integers(40, 96))
                out = jpeg_roundtrip(out, q)
                meta["jpeg_q"] = q
            elif op == "webp":
                q = int(rng.integers(40, 96))
                out = _webp_roundtrip(out, q)
                meta["webp_q"] = q
            elif op == "blur":
                s = float(rng.uniform(0.3, 0.8))
                out = cv2.GaussianBlur(out, (0, 0), s)
                meta["blur_sigma"] = round(s, 2)
            else:
                s = float(rng.uniform(0.5, 4.0))
                out = np.clip(out + rng.normal(0, s, out.shape), 0, 255).astype(np.uint8)
                meta["noise_sigma"] = round(s, 2)
        return out, meta
    kind = str(rng.choice(["jpeg2000", "radiometric", "radiometric+jpeg2000"]))
    meta = {"launder": kind}
    if "radiometric" in kind:
        out, rm = _radiometric(out, rng)
        meta.update(rm)
    if "jpeg2000" in kind:
        rate = float(rng.uniform(8, 30))
        out = _jp2_roundtrip(out, rate)
        meta["jp2_rate"] = round(rate, 1)
    return out, meta


# ----------------------------------------------------------------------- dispatch
LABEL_OF = {"authentic": 0, "resample": 1, "splice": 1, "copy_move": 2, "inpaint": 3}


def make(img, donor, rng, family: str, variant: str):
    if family == "authentic":
        return img.copy(), np.zeros((H, W), bool), {"family": "authentic"}
    if variant == "dev_plus":
        plus = {"resample": lambda: resample_plus(img, rng), "splice": lambda: splice_plus(img, donor, rng),
                "copy_move": lambda: copy_move_plus(img, rng), "inpaint": lambda: inpaint_plus(img, rng)}
        return plus[family]()
    if family == "resample":
        return resample(img, rng, variant)
    if family == "splice":
        return splice(img, donor, rng, variant)
    if family == "copy_move":
        return copy_move(img, rng, variant)
    if family == "inpaint":
        return inpaint(img, rng, variant)
    raise ValueError(family)
