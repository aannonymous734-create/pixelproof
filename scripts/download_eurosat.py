"""Download the official EuroSAT RGB release and verify it (class counts must match the paper).

Official source: Helber et al., EuroSAT, Zenodo record 7711810 (file EuroSAT_RGB.zip, ~90 MB),
also linked from https://github.com/phelber/EuroSAT .  Licence: MIT; Copernicus Sentinel data terms apply.

  python scripts/download_eurosat.py --out data/eurosat

If the download is blocked on your network, download EuroSAT_RGB.zip in a browser, then:
  python scripts/download_eurosat.py --zip path/to/EuroSAT_RGB.zip --out data/eurosat
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof.data import OFFICIAL_COUNTS, find_root, list_samples  # noqa: E402

URL = "https://zenodo.org/records/7711810/files/EuroSAT_RGB.zip?download=1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/eurosat")
    ap.add_argument("--zip", help="use an already downloaded EuroSAT_RGB.zip")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    z = Path(a.zip) if a.zip else out / "EuroSAT_RGB.zip"
    if not z.exists():
        print(f"downloading {URL}")
        urllib.request.urlretrieve(URL, z)
    with zipfile.ZipFile(z) as zf:
        for m in zf.namelist():  # refuse path traversal in archive members
            if m.startswith("/") or ".." in Path(m).parts:
                sys.exit(f"unsafe path in archive: {m}")
        zf.extractall(out)
    samples = list_samples(out, verify=True)  # raises if counts differ from the official release
    h = hashlib.sha256()
    for s in samples:
        h.update(s.sid.encode())
        h.update(hashlib.sha256(s.path.read_bytes()).digest())
    card = {"root": str(find_root(out)), "n_patches": len(samples), "class_counts": OFFICIAL_COUNTS,
            "content_sha256": h.hexdigest()}
    (out / "MANIFEST.json").write_text(json.dumps(card, indent=2))
    print(json.dumps(card, indent=2))


if __name__ == "__main__":
    main()
