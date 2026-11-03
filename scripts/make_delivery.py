"""Build the Phase 1 delivery zip: the whole repo minus heavy or generated artefacts.

  python scripts/make_delivery.py [--out PixelProof_Phase1_Submission.zip]

Excluded: the dataset, the 25 MB feature cache, node_modules and frontend build caches, virtualenvs, editor and
assistant settings (they can hold the author's name), runtime/ (demo private keys), __pycache__, private keys, the
bulky lab pcaps (but NOT results/docker_mitm/*.pcap, which is the evidence) and the v1 snapshot. Kept: all source,
the trained model, the built React dashboard (so the jury needs only Python), the results JSON/figures,
every doc and the VM provisioning files. Prints the file list and total size.
"""
from __future__ import annotations

import argparse
import fnmatch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# results/lab IS kept as evidence (summary.json, logs, ledger) but its pcaps and private keys are not.
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", ".claude", "__pycache__", ".pytest_cache", "data",
    "docs/team_only",  # internal study and speaking guides: not for the jury
    "frontend/node_modules", "frontend/dist", "frontend/.vite",
    "frontend/playwright-report", "frontend/test-results",
    "results/quick", "results/lab/satkeys", "lab/.vagrant", ".mypy_cache",
    "docs/latex/build",  # pdflatex logs and aux files contain absolute paths of the build machine
}
EXCLUDE_GLOBS = ["*.pem", "*.pyc", "results/features.csv.gz", "*.pcap", "runtime/*",
                 "results/iteration*/**", "*.key", ".DS_Store", "docs/REPORT.resolved.md",
                 "results/lab/registry.json", "docs/build/REPORT.html", "frontend/test-results/**"]


def excluded(rel: str) -> bool:
    if rel.startswith("results/docker_mitm/") and rel.endswith(".pcap"):
        return False  # the satellite's own packet capture is the evidence of the transparent man-in-the-middle
    parts = rel.split("/")
    for d in EXCLUDE_DIRS:
        dp = d.split("/")
        if parts[: len(dp)] == dp:
            return True
    return any(fnmatch.fnmatch(rel, g) for g in EXCLUDE_GLOBS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "PixelProof_Phase1_Submission.zip"))
    a = ap.parse_args()
    out = Path(a.out)
    out.unlink(missing_ok=True)
    n, total = 0, 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if rel == out.name or excluded(rel):
                continue
            z.write(p, rel)
            n += 1
            total += p.stat().st_size
    size_mb = out.stat().st_size / 1e6
    print(f"{n} files, {total / 1e6:.1f} MB uncompressed -> {out.name} ({size_mb:.1f} MB zipped)")
    # a quick top-level sanity listing
    import collections
    tops = collections.Counter()
    with zipfile.ZipFile(out) as z:
        for name in z.namelist():
            tops[name.split("/")[0]] += 1
    for k, v in sorted(tops.items()):
        print(f"  {k}/ : {v} files")


if __name__ == "__main__":
    main()
