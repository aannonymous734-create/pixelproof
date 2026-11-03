"""Render the LaTeX report docs/latex/main.tex -> docs/latex/PixelProof_Phase1_Report.pdf.

The LaTeX sources use the same result-file tokens as docs/REPORT.md (non-negotiable rule #1: no measured number
is typed by hand):

    {{m:/models/fused (w=0.4)/test_heldout/detection_rate|pct1}}

This script copies every .tex file under docs/latex/ into docs/latex/build/, replacing each token by its formatted
value (the % sign is escaped for LaTeX), and refuses to build when any token is missing or malformed. It then runs
pdflatex until the cross-references settle.

  python scripts/render_latex.py            # resolve + compile
  python scripts/render_latex.py --check    # resolve only (no LaTeX needed)

Needs a LaTeX distribution with pdflatex (MiKTeX or TeX Live). Sources use the prefixes of scripts/check_numbers.py
plus  v3 = results/heldout_v3_manifest.json.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_numbers as cn  # noqa: E402

TEX = ROOT / "docs" / "latex"
BUILD = TEX / "build"
OUT = TEX / "PixelProof_Phase1_Report.pdf"
cn.SOURCES = dict(cn.SOURCES, v3=cn.RES / "heldout_v3_manifest.json")

# any "{{src:" that is not a well-formed token is a typo we want to hear about
OPEN = re.compile(r"\{\{[a-z0-9]+:")


def latex_escape(value: str) -> str:
    return value.replace("%", r"\%").replace(" ms", "~ms").replace("_", r"\_")


def resolve(text: str, name: str):
    cache, errors, spans = {}, [], []
    for m in cn.TOKEN.finditer(text):
        src, path, f = m.group(1), m.group(2).strip(), m.group(3)
        if src not in cn.SOURCES:
            errors.append((name, m.group(0), f"unknown source '{src}'"))
            continue
        if src not in cache:
            cache[src] = cn.load(src)
        if cache[src] is None:
            errors.append((name, m.group(0), f"result file missing: {cn.SOURCES[src].relative_to(ROOT)}"))
            continue
        try:
            spans.append((m.span(), latex_escape(cn.fmt(cn.resolve(cache[src], path), f))))
        except (KeyError, IndexError, ValueError, TypeError) as e:
            errors.append((name, m.group(0), f"cannot resolve: {type(e).__name__} {e}"))
    good = {s for s, _ in spans}
    for m in OPEN.finditer(text):
        if not any(a <= m.start() < b for (a, b), _ in spans) and not any(
                e[1].startswith(text[m.start():m.start() + 6]) for e in errors):
            tok = cn.TOKEN.match(text, m.start())
            if tok is None:
                errors.append((name, text[m.start():m.start() + 60], "malformed token"))
    out = text
    for (a, b), val in reversed(spans):
        out = out[:a] + val + out[b:]
    return out, len(spans), errors


def run_pdflatex() -> bool:
    cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
           "--enable-installer", "main.tex"]
    for i in range(3):
        r = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True, errors="replace")
        log = (BUILD / "main.log").read_text(errors="replace") if (BUILD / "main.log").exists() else ""
        if r.returncode != 0:
            print(r.stdout[-3000:])
            err = [l for l in log.splitlines() if l.startswith("!") or ":error:" in l or ".tex:" in l and "rror" in l]
            print("pdflatex FAILED on pass", i + 1)
            for l in (err or log.splitlines()[-30:])[:30]:
                print("  ", l)
            return False
        if "Rerun to get" not in log and "Label(s) may have changed" not in log and i >= 1:
            break
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="resolve tokens only, do not run LaTeX")
    a = ap.parse_args()

    BUILD.mkdir(exist_ok=True)
    total, errors = 0, []
    for src in sorted(TEX.rglob("*.tex")):
        if BUILD in src.parents:
            continue
        rel = src.relative_to(TEX)
        text, n, errs = resolve(src.read_text(encoding="utf-8"), str(rel))
        total += n
        errors += errs
        dst = BUILD / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
    print(f"{total} numeric tokens resolved against results/")
    if errors:
        print(f"\n{len(errors)} PROBLEMS:")
        for name, tok, why in errors[:60]:
            print(f"  {name}: {tok}  ->  {why}")
        sys.exit("not building: fix the tokens above")
    if a.check:
        print("OK: every number resolves to a result file.")
        return
    if shutil.which("pdflatex") is None:
        sys.exit("pdflatex not found: install MiKTeX or TeX Live")
    if not run_pdflatex():
        sys.exit(1)
    shutil.copyfile(BUILD / "main.pdf", OUT)
    log = (BUILD / "main.log").read_text(errors="replace")
    pages = re.search(r"Output written on .*\((\d+) page", log)
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  pages: {pages.group(1) if pages else '?'}, overfull boxes: {len(re.findall(r'Overfull .hbox', log))}, "
          f"undefined references: {len(re.findall(r'undefined', log))}")


if __name__ == "__main__":
    main()
