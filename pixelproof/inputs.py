"""Robust input handling for the jury's patches (any size and common EO formats).

load_any()     reads PNG/JPEG/WebP/BMP/TIFF and GeoTIFF, including:
                 * EuroSAT-MS 13-band (or 12-band L2A) GeoTIFF -> bands B04, B03, B02 (true colour)
                 * 16-bit data: Sentinel-2 digital numbers (reflectance x 10000) are mapped with
                   255/3000 (0-30% reflectance -> 0-255, the usual true-colour stretch); other 16-bit
                   images are divided by 257
                 * float images in [0, 1], grayscale (replicated to 3 channels), RGBA/palette (alpha dropped)
               Corrupted or unsupported files raise InputError with a readable message.

analyse_any()  never RESIZES (resizing would itself create resampling traces). Images larger than
               64x64 are cut into 64x64 tiles (the last row/column aligned to the border) and every
               tile is analysed. To keep the image-level false-alarm rate at the 5% budget, the tile
               threshold is raised for n tiles: per-tile rate a' = 1 - (1 - 0.05)^(1/n), read from the
               stored distribution of clean validation scores. Images smaller than 64x64 are padded by
               edge replication and flagged as lower-confidence.

Caveat (stated in the report): the detector is calibrated on the EuroSAT RGB release (8-bit JPEG).
Multispectral and 16-bit inputs are converted, but their false-alarm rate has not been measured.
"""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

MAX_PIXELS = 4096 * 4096
T = 64


class InputError(ValueError):
    pass


def _to_uint8(a: np.ndarray, info: dict) -> np.ndarray:
    if a.dtype == np.uint8:
        return a
    a = a.astype(np.float64)
    mx = float(np.nanmax(a)) if a.size else 0.0
    p99 = float(np.nanpercentile(a, 99)) if a.size else 0.0  # robust to a few bright cloud pixels
    if mx <= 1.0 and a.dtype.kind == "f":
        info["scaling"] = "float [0,1] x 255"
        a = a * 255.0
    elif mx <= 255:
        info["scaling"] = "integer values already in 0-255"
    elif p99 <= 12000:
        info["scaling"] = "Sentinel-2 digital numbers x 255/3000 (approximate true-colour stretch)"
        a = a * 255.0 / 3000.0
    else:
        info["scaling"] = "16-bit / 257"
        a = a / 257.0
    return np.clip(np.nan_to_num(a) + 0.5, 0, 255).astype(np.uint8)


def _to_rgb(a: np.ndarray, info: dict) -> np.ndarray:
    if a.ndim == 2:
        info["channels"] = "grayscale replicated to RGB"
        a = np.stack([a] * 3, -1)
    elif a.ndim == 3:
        if a.shape[0] in (4, 12, 13) and a.shape[2] > 13:  # channels-first GeoTIFF
            a = np.moveaxis(a, 0, -1)
        c = a.shape[2]
        if c in (12, 13):
            info["channels"] = f"{c}-band Sentinel-2: B04, B03, B02 used as RGB"
            a = a[..., [3, 2, 1]]
        elif c == 4:
            info["channels"] = "4 channels: first 3 used (alpha/NIR dropped)"
            a = a[..., :3]
        elif c == 1:
            a = np.repeat(a, 3, -1)
            info["channels"] = "grayscale replicated to RGB"
        elif c != 3:
            raise InputError(f"unsupported number of channels: {c}")
    else:
        raise InputError(f"unsupported array shape {a.shape}")
    return a


def load_any(src) -> tuple[np.ndarray, dict]:
    """Return (uint8 RGB array, info dict describing every conversion applied)."""
    try:
        data = bytes(src) if isinstance(src, (bytes, bytearray)) else Path(src).read_bytes()
    except OSError as e:
        raise InputError(f"cannot read file: {e}") from None
    info: dict = {}
    try:
        if data[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
            import tifffile
            a = tifffile.imread(io.BytesIO(data))
            info["format"] = "TIFF"
        else:
            im = Image.open(io.BytesIO(data))
            if im.size[0] * im.size[1] > MAX_PIXELS:
                raise InputError("image larger than 16 megapixels")
            im.load()
            info["format"] = im.format
            if im.mode in ("RGBA", "LA", "P", "PA", "CMYK", "YCbCr", "1"):
                info["converted_from"] = im.mode
                im = im.convert("RGB")
            a = np.asarray(im)
    except InputError:
        raise
    except Exception as e:  # corrupted or unknown file
        raise InputError(f"not a decodable image ({type(e).__name__})") from None
    if a.ndim >= 2 and a.shape[0] * a.shape[1] > MAX_PIXELS:
        raise InputError("image larger than 16 megapixels")
    a = _to_rgb(a, info)
    return np.ascontiguousarray(_to_uint8(a, info)), info


def tiles(img: np.ndarray) -> list[tuple[int, int]]:
    h, w = img.shape[:2]
    ys = sorted(set(list(range(0, max(h - T, 0) + 1, T)) + [max(h - T, 0)]))
    xs = sorted(set(list(range(0, max(w - T, 0) + 1, T)) + [max(w - T, 0)]))
    return [(y, x) for y in ys for x in xs]


def tile_threshold(det, n: int) -> float | None:
    """Score a clean tile exceeds with probability a' = 1 - (1 - target)^(1/n)."""
    q = (getattr(det, "score_quantiles", None) or {}).get("fused" if det.fused else "gbm")
    if q is None or n <= 1:
        return None
    a = 1 - (1 - det.target_fpr) ** (1.0 / n)
    return float(np.interp(1 - a, np.linspace(0, 1, len(q)), q))


def analyse_any(det, img: np.ndarray, with_heatmap: bool = True) -> dict:
    from . import LABELS
    h, w = img.shape[:2]
    note = []
    if h < T or w < T:
        img = np.pad(img, ((0, max(0, T - h)), (0, max(0, T - w)), (0, 0)), mode="edge")
        note.append(f"image {w}x{h} smaller than 64x64: padded, lower confidence")
    if img.shape[:2] == (T, T):
        r = det.analyse(img, with_heatmap=with_heatmap)
        r["tiles"] = 1
        if note:
            r["input_note"] = "; ".join(note)
            if with_heatmap:
                r["heatmap"] = r["heatmap"][:h, :w]
        return r
    pos = tiles(img)
    t_n = tile_threshold(det, len(pos))
    results = []
    for y, x in pos:
        r = det.analyse(img[y:y + T, x:x + T], with_heatmap=with_heatmap)
        thr = max(r["threshold"], t_n) if t_n is not None else r["threshold"]
        results.append((r["manipulation_score"] - thr, r, thr, (y, x)))
    margin, best, thr, (by, bx) = max(results, key=lambda z: z[0])
    alarm = margin >= 0
    p = best["probabilities"]
    out = {
        "manipulation_score": best["manipulation_score"],
        "threshold": round(thr, 4),
        "reencoding_probability": best.get("reencoding_probability"),
        "manipulated": bool(alarm),
        "type": max(LABELS[1:], key=lambda k: p[k]) if alarm else "authentic",
        "probabilities": p,
        "evidence": (best["evidence"] + [f"strongest evidence in the 64x64 tile at x={bx}, y={by}"]) if alarm else [],
        "model": best["model"],
        "tiles": len(pos),
        "tiles_alarmed": int(sum(m >= 0 for m, *_ in results)),
        "input_note": "; ".join(note + [f"{w}x{h} image analysed as {len(pos)} tiles of 64x64 without resizing; "
                                        f"tile threshold corrected for {len(pos)} tests"]),
    }
    if with_heatmap:
        hm = np.zeros(img.shape[:2], np.float32)
        for _, r, _, (y, x) in results:
            hm[y:y + T, x:x + T] = np.maximum(hm[y:y + T, x:x + T], r["heatmap"])
        out["heatmap"] = hm[:h, :w]
    return out
