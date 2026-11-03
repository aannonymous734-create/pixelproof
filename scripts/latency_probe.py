"""Measure single-patch latency and peak memory of the full analysis in a fresh process.
Prints one JSON line. Used by scripts/evaluate.py."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def peak_rss_mb() -> float:
    """Peak resident memory of this process in MB (Linux/macOS: getrusage; Windows: peak working set)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
        return c.PeakWorkingSetSize / 2**20
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # kilobytes on Linux


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/detector.joblib")
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()
    try:
        import torch
        torch.set_num_threads(1)
    except ImportError:
        pass
    from pixelproof.data import list_samples
    from pixelproof.detector import Detector
    from pixelproof.imageio import load_rgb

    t = time.perf_counter()
    det = Detector.load(args.model)
    load_s = time.perf_counter() - t
    samples = list_samples(args.data_dir)
    imgs = [load_rgb(samples[i].path) for i in np.linspace(0, len(samples) - 1, args.n).astype(int)]
    det.analyse(imgs[0])  # warm-up
    ms, ms_nohm = [], []
    for im in imgs:
        t = time.perf_counter()
        det.analyse(im, with_heatmap=True)
        ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        det.analyse(im, with_heatmap=False)
        ms_nohm.append((time.perf_counter() - t) * 1000)
    rss_mb = peak_rss_mb()
    print(json.dumps({"model_used": "features+cnn" if det.fused else "features",
                      "analyse_ms_p50_with_heatmap": float(np.median(ms)),
                      "analyse_ms_p95_with_heatmap": float(np.percentile(ms, 95)),
                      "analyse_ms_p50": float(np.median(ms_nohm)),
                      "throughput_patches_per_s_1core": float(1000 / np.median(ms_nohm)),
                      "model_load_s": load_s, "peak_rss_mb": rss_mb}))


if __name__ == "__main__":
    main()
