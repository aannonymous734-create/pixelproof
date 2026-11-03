"""EuroSAT (Sentinel-2) RGB loader and leakage-free splitting.

Official reference data: EuroSAT, Helber et al. 27,000 labelled 64x64 Sentinel-2 patches,
10 land-cover classes. The RGB release stores each patch as a JPEG file:
    <root>/<ClassName>/<ClassName>_<n>.jpg
(the Zenodo release uses root "EuroSAT_RGB", the older DFKI release uses "2750").

Splits are made per SOURCE PATCH using a stable hash of its file name, so a patch and every
manipulated version made from it always land in the same split (no leakage).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

OFFICIAL_COUNTS = {
    "AnnualCrop": 3000, "Forest": 3000, "HerbaceousVegetation": 3000, "Highway": 2500,
    "Industrial": 2500, "Pasture": 2000, "PermanentCrop": 2500, "Residential": 3000,
    "River": 2500, "SeaLake": 3000,
}


@dataclass(frozen=True)
class Sample:
    path: Path
    landcover: str
    sid: str  # stable id, e.g. "Forest_123"


def find_root(data_dir: str | Path) -> Path:
    """Locate the folder that directly contains the 10 class folders."""
    data_dir = Path(data_dir)
    for cand in [data_dir, *sorted(p for p in data_dir.rglob("*") if p.is_dir())]:
        if (cand / "AnnualCrop").is_dir() and (cand / "SeaLake").is_dir():
            return cand
    raise FileNotFoundError(
        f"EuroSAT RGB not found under {data_dir}. Run: python scripts/download_eurosat.py")


def list_samples(data_dir: str | Path, verify: bool = True) -> list[Sample]:
    root = find_root(data_dir)
    out: list[Sample] = []
    counts = {}
    for cls in sorted(OFFICIAL_COUNTS):
        files = sorted((root / cls).glob("*.jpg"))
        counts[cls] = len(files)
        out += [Sample(f, cls, f.stem) for f in files]
    if verify and counts != OFFICIAL_COUNTS:
        raise ValueError(f"EuroSAT class counts differ from the official release: {counts}")
    return out


def split_of(sid: str, fractions=(("train", 0.60), ("val", 0.15), ("test_dev", 0.125), ("test_heldout", 0.125))) -> str:
    h = int.from_bytes(hashlib.sha256(sid.encode()).digest()[:8], "big") / 2**64
    acc = 0.0
    for name, f in fractions:
        acc += f
        if h < acc:
            return name
    return fractions[-1][0]


def split_samples(samples: list[Sample]) -> dict[str, list[Sample]]:
    out: dict[str, list[Sample]] = {}
    for s in samples:
        out.setdefault(split_of(s.sid), []).append(s)
    return out
