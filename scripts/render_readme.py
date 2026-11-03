"""Generate README.md from docs/README.template.md.

The template uses the same result-file tokens as the reports, e.g.

    {{m:/models/fused (w=0.4)/test_heldout/detection_rate|pct1}}

so that no measured number in the README is typed by hand (non-negotiable rule #1). This script resolves every
token with scripts/check_numbers.py, fails if any token is unresolved or malformed, and writes README.md with
Unix line endings.

  python scripts/render_readme.py            # write README.md
  python scripts/render_readme.py --check    # only verify that every token resolves
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_numbers as cn  # noqa: E402

TEMPLATE = ROOT / "docs" / "README.template.md"
OUT = ROOT / "README.md"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="resolve tokens only, do not write README.md")
    a = ap.parse_args()

    text = TEMPLATE.read_text(encoding="utf-8")
    rendered, n, errors = cn.process(text)
    leftover = [t for t in cn.re.findall(r"\{\{[^}]*\}\}", text) if not cn.TOKEN.fullmatch(t)]
    print(f"{n} numeric tokens resolved against results/")
    if errors or leftover:
        for tok, why in errors[:50]:
            print(f"  UNRESOLVED {tok}  ->  {why}")
        for tok in leftover[:10]:
            print(f"  MALFORMED  {tok}")
        sys.exit("not writing README.md: fix the tokens above")
    if a.check:
        print("OK: every number resolves to a result file.")
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(rendered)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(rendered.splitlines())} lines)")


if __name__ == "__main__":
    main()
