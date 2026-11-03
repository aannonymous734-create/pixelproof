"""Forensic feature extraction (Deliverable 3: signal / image processing).

Six groups, matching the slide "frequency, resampling and forensic features":

  rs_*  resampling traces   - periodic correlations left by interpolation
  fq_*  frequency profile   - radial power spectrum, high-frequency deficit, JPEG grid
  nz_*  noise residual      - SRM high-pass "sensor grain", local inconsistency, over-smooth areas
  cc_*  channel coherence   - cross-channel noise correlation broken by edits
  cm_*  copy-move           - duplicated 8x8 blocks sharing one shift vector, and (cm_d4_*) copies
                              that were rotated by 90/180/270 degrees or mirrored, grouped by
                              geometric consistency
  cs_*  splicing statistics - colour-vs-brightness consistency per block, fine-scale noise level

`extract(img)` returns an ordered dict of floats; `heatmap(img)` returns a 64x64 map in [0,1]
showing WHERE the evidence is (used for explanation and localisation).
"""
from __future__ import annotations

from collections import Counter

import cv2
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

EPS = 1e-6
GROUPS = ("rs", "fq", "nz", "cc", "cm", "cs")

_SRM = np.array([[-1, 2, -1], [2, -4, 2], [-1, 2, -1]], np.float32) / 4.0
_PRED4 = np.array([[0, .25, 0], [.25, 0, .25], [0, .25, 0]], np.float32)


def _dct_matrix(n=8):
    k = np.arange(n)
    D = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n)) * np.sqrt(2 / n)
    D[0] /= np.sqrt(2)
    return D.astype(np.float32)


_D8 = _dct_matrix()
_ZZ = [(0, 1), (1, 0), (2, 0), (1, 1), (0, 2), (0, 3), (1, 2), (2, 1), (3, 0)]  # skip DC


def gray(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float32)
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def _robust_std(x):
    x = np.asarray(x, np.float32).ravel()
    return float(1.4826 * np.median(np.abs(x - np.median(x))) + EPS)


def _kurt(x):
    x = np.asarray(x, np.float64).ravel()
    s = x.std() + EPS
    return float(((x - x.mean()) ** 4).mean() / s ** 4)


def _block_stat(a: np.ndarray, b: int, fn=np.std) -> np.ndarray:
    h, w = a.shape[0] // b, a.shape[1] // b
    v = a[:h * b, :w * b].reshape(h, b, w, b).swapaxes(1, 2).reshape(h, w, b * b)
    return fn(v, axis=-1)


# ------------------------------------------------------------------------ resampling
def resampling_features(g: np.ndarray) -> dict:
    out = {}
    for axis, name in ((1, "h"), (0, "v")):
        d = np.abs(np.diff(g, n=2, axis=axis))
        sig = d.mean(axis=1 - axis)
        sig = (sig - sig.mean()) * np.hanning(len(sig))
        F = np.abs(np.fft.rfft(sig))[2:]
        out[f"rs_peak_{name}"] = float(F.max() / (np.median(F) + EPS))
    pred = cv2.filter2D(g, -1, _PRED4, borderType=cv2.BORDER_REFLECT)
    e = (g - pred)[1:-1, 1:-1]
    s = _robust_std(e)
    p = np.exp(-0.5 * (e / s) ** 2)
    P = np.abs(np.fft.fftshift(np.fft.fft2(p - p.mean())))
    n = P.shape[0]
    yy, xx = np.mgrid[:n, :n] - n // 2
    r = np.hypot(yy, xx)
    P[r < 4] = 0
    out["rs_pmap_peak"] = float(P.max() / (np.median(P[r >= 4]) + EPS))
    out["rs_pmap_peak_r"] = float(r.flat[P.argmax()] / (n / 2))
    out["rs_resid_std"] = float(np.log(s))
    out["rs_resid_kurt"] = _kurt(e)
    return out


# ------------------------------------------------------------------------- frequency
def frequency_features(g: np.ndarray, nbins: int = 8) -> dict:
    n = g.shape[0]
    w = np.outer(np.hanning(n), np.hanning(n)).astype(np.float32)
    P = np.abs(np.fft.fftshift(np.fft.fft2((g - g.mean()) * w))) ** 2
    yy, xx = np.mgrid[:n, :n] - n // 2
    r = np.hypot(yy, xx)
    edges = np.linspace(1, n / 2, nbins + 1)
    prof = np.array([P[(r >= edges[i]) & (r < edges[i + 1])].mean() for i in range(nbins)])
    lp = np.log(prof + EPS)
    out = {f"fq_r{i}": float(lp[i] - lp.mean()) for i in range(nbins)}
    centres = 0.5 * (edges[:-1] + edges[1:])
    out["fq_slope"] = float(np.polyfit(np.log(centres), lp, 1)[0])
    out["fq_hf_ratio"] = float(np.log((P[r > n / 4].sum() + EPS) / (P[(r >= 2) & (r <= n / 4)].sum() + EPS)))
    # JPEG 8x8 grid strength (authentic EuroSAT RGB patches are single-JPEG compressed)
    dh = np.abs(np.diff(g, axis=1)).mean(0)
    dv = np.abs(np.diff(g, axis=0)).mean(1)
    idx = np.arange(len(dh))
    on = (idx % 8) == 7
    out["fq_jpeg_grid"] = float(np.log((dh[on].mean() + dv[on].mean() + EPS) / (dh[~on].mean() + dv[~on].mean() + EPS)))
    return out


# ----------------------------------------------------------------------- noise residual
def _residual(g):
    return cv2.filter2D(g, -1, _SRM, borderType=cv2.BORDER_REFLECT)


def noise_maps(g: np.ndarray):
    """Block-level (8x8) log noise level and its robust z-score."""
    r = _residual(g)
    bs = _block_stat(r, 8)
    lb = np.log(bs + 0.05)
    med = np.median(lb)
    z = (lb - med) / (_robust_std(lb) + 0.05)
    return r, bs, lb, z


def noise_features(g: np.ndarray) -> dict:
    r, bs, lb, z = noise_maps(g)
    z2 = cv2.blur(z.astype(np.float32), (2, 2))[:-1, :-1]  # 16x16 px neighbourhoods
    med = np.median(bs) + EPS
    return {
        "nz_level": float(np.log(med)),
        "nz_std": float(lb.std()),
        "nz_range": float(lb.max() - lb.min()),
        "nz_zmax": float(z.max()),
        "nz_zmin": float(z.min()),
        "nz_frac_out": float((np.abs(z) > 2.5).mean()),
        "nz_frac_smooth": float((bs < 0.35 * med).mean()),
        "nz_z2max": float(z2.max()),
        "nz_z2min": float(z2.min()),
        "nz_kurt": _kurt(r),
    }


def channel_features(img: np.ndarray) -> dict:
    f = img.astype(np.float32)
    rr = [_residual(f[..., c]) for c in range(3)]
    out = {}
    for (a, b), name in (((0, 1), "rg"), ((1, 2), "gb"), ((0, 2), "rb")):
        x, y = rr[a].ravel(), rr[b].ravel()
        out[f"cc_{name}"] = float(np.corrcoef(x, y)[0, 1]) if x.std() > EPS and y.std() > EPS else 1.0
    # local (16x16) correlation between R and G residuals: edits often break it locally
    loc = []
    for i in range(0, 64, 16):
        for j in range(0, 64, 16):
            x, y = rr[0][i:i + 16, j:j + 16].ravel(), rr[1][i:i + 16, j:j + 16].ravel()
            loc.append(np.corrcoef(x, y)[0, 1] if x.std() > EPS and y.std() > EPS else 1.0)
    loc = np.nan_to_num(np.array(loc), nan=1.0)
    out["cc_local_min"] = float(loc.min())
    out["cc_local_std"] = float(loc.std())
    return out


# ------------------------------------------------------------------------- copy-move
def copy_move_match(g: np.ndarray, b: int = 8, flat_std: float = 2.5, qstep: float = 4.0,
                    min_dist: float = 8.0, neighbours: int = 6):
    """Exhaustive block matching on overlapping 8x8 blocks (Fridrich-style, DCT features).
    Flat blocks (water, cloud, bare soil) are ignored to avoid false matches."""
    win = sliding_window_view(g, (b, b))
    nh, nw = win.shape[:2]
    blocks = win.reshape(-1, b, b)
    std = blocks.reshape(len(blocks), -1).std(1)
    keep = np.nonzero(std > flat_std)[0]
    if len(keep) < 10:
        return 0, (0, 0), np.zeros(g.shape, bool), len(keep)
    C = _D8 @ blocks[keep].astype(np.float32) @ _D8.T
    feat = np.stack([C[:, i, j] for i, j in _ZZ], 1)
    Q = np.round(feat / qstep).astype(np.int32)
    order = np.lexsort(Q.T[::-1])
    Qs, ks = Q[order], keep[order]
    ys, xs = ks // nw, ks % nw
    shifts = Counter()
    pairs = {}
    for k in range(1, neighbours + 1):
        same = np.abs(Qs[k:] - Qs[:-k]).max(1) <= 1
        idx = np.nonzero(same)[0]
        if not len(idx):
            continue
        dy = ys[idx + k] - ys[idx]
        dx = xs[idx + k] - xs[idx]
        flip = (dy < 0) | ((dy == 0) & (dx < 0))
        dy, dx = np.where(flip, -dy, dy), np.where(flip, -dx, dx)
        far = np.hypot(dy, dx) >= min_dist
        for i, a, c in zip(idx[far], dy[far], dx[far]):
            key = (int(a), int(c))
            shifts[key] += 1
            pairs.setdefault(key, []).append((ks[i], ks[i + k]))
    if not shifts:
        return 0, (0, 0), np.zeros(g.shape, bool), len(keep)
    vec, cnt = shifts.most_common(1)[0]
    mask = np.zeros(g.shape, bool)
    for a, c in pairs[vec]:
        for q in (a, c):
            y, x = q // nw, q % nw
            mask[y:y + b, x:x + b] = True
    return cnt, vec, mask, len(keep)


# --- rotation/flip-invariant variant (dihedral group D4: 4 rotations x optional transpose)
_D4 = [(k, t) for t in (0, 1) for k in range(4)]
_MR = np.array([[0, -1], [1, 0]])
_MT = np.array([[0, 1], [1, 0]])
_M = [np.linalg.matrix_power(_MR, k) @ (_MT if t else np.eye(2, dtype=int)) for k, t in _D4]
_MINV = [np.round(np.linalg.inv(m)).astype(int) for m in _M]
_MID = {tuple(m.ravel()): i for i, m in enumerate(_M)}
_MSTACK = np.stack(_M).astype(float)
_SIGN_ROWS = ((-1.0) ** np.arange(8))[:, None].astype(np.float32)
# _REL[cj, ci] = index of the symmetry mapping block i's region onto block j's region
_REL = np.array([[_MID[tuple((_MINV[cj] @ _M[ci]).ravel())] for ci in range(8)] for cj in range(8)])


def copy_move_match_d4(g: np.ndarray, b: int = 8, flat_std: float = 2.5, qstep: float = 4.0,
                       min_dist: float = 8.0, neighbours: int = 6):
    """Block matching that also finds copies that were rotated by 90/180/270 degrees or mirrored.
    Each textured block gets a canonical key: the lexicographically smallest quantised DCT vector
    among its 8 dihedral variants. Matching keys reveal a copy under SOME symmetry; pairs are then
    grouped by geometric consistency: the same symmetry M and the same translation
    t = centre_j - M centre_i (exact for copied regions, random for natural look-alike blocks).
    Returns (count of the largest consistent group, its symmetry index, mask, textured blocks)."""
    win = sliding_window_view(g, (b, b))
    nh, nw = win.shape[:2]
    blocks = win.reshape(-1, b, b)
    std = blocks.reshape(len(blocks), -1).std(1)
    keep = np.nonzero(std > flat_std)[0]
    if len(keep) < 10:
        return 0, 0, np.zeros(g.shape, bool), len(keep)
    # rotations/flips of a block only permute and sign-flip its DCT coefficients:
    # transpose -> C.T ; flip rows -> C[i, j] * (-1)^i ; rot90 = flip rows of the transpose
    C0 = _D8 @ blocks[keep].astype(np.float32) @ _D8.T
    Q = np.empty((len(keep), 8, len(_ZZ)), np.int32)
    zi, zj = np.array([i for i, _ in _ZZ]), np.array([j for _, j in _ZZ])
    for v, (k, t) in enumerate(_D4):
        C = C0.transpose(0, 2, 1) if t else C0
        for _ in range(k):
            C = C.transpose(0, 2, 1) * _SIGN_ROWS
        Q[:, v] = np.round(C[:, zi, zj] / qstep)
    cand = np.ones((len(keep), 8), bool)
    for d in range(Q.shape[2]):  # lexicographic minimum over the 8 variants, per block
        vals = np.where(cand, Q[:, :, d], np.iinfo(np.int32).max)
        cand &= vals == vals.min(1, keepdims=True)
    canon = cand.argmax(1)
    key = Q[np.arange(len(keep)), canon]
    order = np.lexsort(key.T[::-1])
    Ks, ks, cs = key[order], keep[order], canon[order]
    A_, C_, CA, CC = [], [], [], []
    for k in range(1, neighbours + 1):
        same = np.nonzero(np.abs(Ks[k:] - Ks[:-k]).max(1) <= 1)[0]
        A_.append(ks[same]); C_.append(ks[same + k]); CA.append(cs[same]); CC.append(cs[same + k])
    a, c, ca, cc = (np.concatenate(v) if v else np.zeros(0, int) for v in (A_, C_, CA, CC))
    swap = a > c
    a, c = np.where(swap, c, a), np.where(swap, a, c)
    ca, cc = np.where(swap, cc, ca), np.where(swap, ca, cc)
    pa = np.stack([a // nw, a % nw], 1) + 3.5
    pc = np.stack([c // nw, c % nw], 1) + 3.5
    far = np.hypot(*(pc - pa).T) >= min_dist
    a, c, ca, cc, pa, pc = a[far], c[far], ca[far], cc[far], pa[far], pc[far]
    if not len(a):
        return 0, 0, np.zeros(g.shape, bool), len(keep)
    r = _REL[cc, ca]
    tvec = np.round(pc - np.einsum("nij,nj->ni", _MSTACK[r], pa)).astype(int)
    gid = r * 1_000_000 + (tvec[:, 0] + 500) * 1000 + (tvec[:, 1] + 500)
    vals, counts = np.unique(gid, return_counts=True)
    best = vals[counts.argmax()]
    cnt = int(counts.max())
    mask = np.zeros(g.shape, bool)
    sel = gid == best
    for q in np.concatenate([a[sel], c[sel]]):
        mask[q // nw:q // nw + b, q % nw:q % nw + b] = True
    return cnt, int(best // 1_000_000), mask, len(keep)


def copy_move_features(g: np.ndarray) -> dict:
    cnt, vec, mask, n = copy_move_match(g)
    cnt4, sym, mask4, _ = copy_move_match_d4(g)
    return {
        "cm_count": float(np.log1p(cnt)),
        "cm_frac": float(cnt / max(n, 1)),
        "cm_area": float(mask.mean()),
        "cm_shift": float(np.hypot(*vec) / 64.0),
        "cm_textured": float(n / 3249.0),
        "cm_d4_count": float(np.log1p(cnt4)),
        "cm_d4_frac": float(cnt4 / max(n, 1)),
        "cm_d4_area": float(mask4.mean()),
        "cm_d4_symmetric": float(sym != 0),
    }


# ------------------------------------------------- colour / fine-scale splicing statistics
def splice_features(img: np.ndarray) -> dict:
    """A spliced region keeps its own colour-vs-brightness relation and its own noise level even
    when its edges are blended (feathering, Poisson blending). Per 8x8 block we predict chroma from
    luminance with one linear fit over the patch; a region that does not follow the patch's
    relation stands out. Noise level is also measured at a finer, overlapping scale (stride 4)."""
    f = img.astype(np.float32)
    Y = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
    chans = {"cb": f[..., 2] - Y, "cr": f[..., 0] - Y, "sat": f.max(-1) - f.min(-1)}
    Yb = _block_stat(Y, 8, np.mean).ravel()
    out = {}
    zs = []
    for name, ch in chans.items():
        cb = _block_stat(ch, 8, np.mean).ravel()
        A = np.stack([Yb, np.ones_like(Yb)], 1)
        coef, *_ = np.linalg.lstsq(A, cb, rcond=None)
        res = cb - A @ coef
        z = np.abs(res - np.median(res)) / (_robust_std(res) + 0.5)
        zs.append(z.reshape(8, 8))
        out[f"cs_{name}_zmax"] = float(z.max())
    zsum = np.maximum.reduce(zs)
    out["cs_z2max"] = float(cv2.blur(zsum.astype(np.float32), (2, 2))[:-1, :-1].max())
    out["cs_frac_out"] = float((zsum > 3).mean())
    # fine-scale noise map: 8x8 windows, stride 4 -> 15x15
    r = _residual(gray(img))
    win = sliding_window_view(r, (8, 8))[::4, ::4]
    lv = np.log(win.reshape(win.shape[0], win.shape[1], -1).std(-1) + 0.05)
    zf = (lv - np.median(lv)) / (_robust_std(lv) + 0.05)
    z3 = cv2.blur(zf.astype(np.float32), (3, 3))[1:-1, 1:-1]
    out["cs_noise_z3max"] = float(z3.max())
    out["cs_noise_z3min"] = float(z3.min())
    return out


# ----------------------------------------------------------------------------- API
def extract(img: np.ndarray) -> dict:
    if img.shape[:2] != (64, 64):
        img = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA)
    g = gray(img)
    f = {}
    f.update(resampling_features(g))
    f.update(frequency_features(g))
    f.update(noise_features(g))
    f.update(channel_features(img))
    f.update(copy_move_features(g))
    f.update(splice_features(img))
    return {k: (0.0 if not np.isfinite(v) else v) for k, v in f.items()}


FEATURE_NAMES = list(extract(np.random.default_rng(0).integers(0, 255, (64, 64, 3), dtype=np.uint8)).keys())


def heatmap(img: np.ndarray) -> np.ndarray:
    """Where is the evidence? max of (noise inconsistency, copy-move matches, over-smooth areas)."""
    if img.shape[:2] != (64, 64):
        img = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA)
    g = gray(img)
    _, bs, _, z = noise_maps(g)
    noise = np.clip((np.abs(z) - 1.5) / 2.5, 0, 1)
    smooth = np.clip(1 - bs / (0.35 * np.median(bs) + EPS), 0, 1)
    block = np.maximum(noise, smooth).astype(np.float32)
    hm = cv2.resize(block, (64, 64), interpolation=cv2.INTER_NEAREST)
    _, _, cm, _ = copy_move_match(g)
    hm = np.maximum(hm, cm.astype(np.float32))
    return cv2.GaussianBlur(hm, (0, 0), 2.0)
