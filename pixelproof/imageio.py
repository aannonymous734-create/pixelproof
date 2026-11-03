"""Image I/O helpers. All images inside PixelProof are uint8 RGB arrays of shape (H, W, 3)."""
from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

MAX_PIXELS = 4096 * 4096  # refuse decompression bombs


def load_rgb(path_or_bytes) -> np.ndarray:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        im = Image.open(io.BytesIO(path_or_bytes))
    else:
        im = Image.open(Path(path_or_bytes))
    if im.size[0] * im.size[1] > MAX_PIXELS:
        raise ValueError("image too large")
    im.load()
    if im.mode != "RGB":
        im = im.convert("RGB")
    return np.asarray(im, dtype=np.uint8).copy()


def to_png_bytes(img: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_roundtrip(img: np.ndarray, quality: int) -> np.ndarray:
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="JPEG", quality=int(quality))
    buf.seek(0)
    return np.asarray(Image.open(buf).convert("RGB"), dtype=np.uint8).copy()
