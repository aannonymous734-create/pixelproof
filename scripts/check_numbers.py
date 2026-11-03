"""Guarantee that every number in the report comes from a result file (non-negotiable rule #1).

The report never hard-codes a measured number. It writes a token instead:

    {{m:/models/fused (w=0.4)/test_heldout/detection_rate|pct1}}

`check_numbers.py` resolves every token against the JSON result files and fails if any token is
missing, unresolved or badly formatted. `--render IN.md OUT.md` writes a copy with the tokens
replaced by their formatted values (this is what scripts/render_report.py feeds to pandoc), so the
PDF can only ever contain numbers that exist in results/.

Sources (prefix):   m = results/metrics.json           h = results/heldout_v2_v2model.json
                    h1 = results/heldout_v2_v1model.json  r = results/robustness.json
                     c = results/integrity_campaign.json  lab = results/lab/summary.json
                    dk = results/docker_lab/summary.json  at = results/attack_runs/summary.json
                    dm = results/docker_mitm/summary.json  tr = results/docker_mitm/transparency.json
Formats:  pct1 (xx.x%)  pct0 (xx%)  f1 f2 f3 f4 (decimals)  int  ms1  raw
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
SOURCES = {
    "m": RES / "metrics.json",
    "h": RES / "heldout_v2_v2model.json",
    "h1": RES / "heldout_v2_v1model.json",
    "r": RES / "robustness.json",
    "c": RES / "integrity_campaign.json",
    "lab": RES / "lab" / "summary.json",
    "dk": RES / "docker_lab" / "summary.json",
    "at": RES / "attack_runs" / "summary.json",
    "dm": RES / "docker_mitm" / "summary.json",
    "tr": RES / "docker_mitm" / "transparency.json",
}
TOKEN = re.compile(r"\{\{([a-z0-9]+):([^|}]+)\|([a-z0-9]+)\}\}")


def load(src):
    p = SOURCES[src]
    if not p.exists():
        return None
    return json.loads(p.read_text())


def resolve(data, path):
    cur = data
    for part in path.split("/"):
        if part == "":
            continue
        if isinstance(cur, list):
            cur = cur[int(part)]
        else:
            cur = cur[part]
    return cur


def fmt(v, f):
    if f == "pct1":
        return f"{100 * float(v):.1f}%"
    if f == "pct0":
        return f"{100 * float(v):.0f}%"
    if f.startswith("f") and f[1:].isdigit():
        return f"{float(v):.{int(f[1:])}f}"
    if f == "ms1":
        return f"{float(v):.1f} ms"
    if f == "int":
        return str(int(v))
    if f == "raw":
        return str(v)
    raise ValueError(f"unknown format {f}")


def process(text, strict=True):
    cache, errors, out, n = {}, [], [], 0
    for m in TOKEN.finditer(text):
        src, path, f = m.group(1), m.group(2).strip(), m.group(3)
        n += 1
        if src not in SOURCES:
            errors.append((m.group(0), f"unknown source '{src}'"))
            continue
        if src not in cache:
            cache[src] = load(src)
        if cache[src] is None:
            errors.append((m.group(0), f"result file missing: {SOURCES[src].relative_to(ROOT)}"))
            continue
        try:
            val = fmt(resolve(cache[src], path), f)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            errors.append((m.group(0), f"cannot resolve: {type(e).__name__} {e}"))
            continue
        out.append((m.span(), val))
    rendered = text
    for (a, b), val in reversed(out):
        rendered = rendered[:a] + val + rendered[b:]
    return rendered, n, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report", nargs="?", default=str(ROOT / "docs" / "REPORT.md"))
    ap.add_argument("--render", nargs="?", const="-", help="write the resolved report to this path")
    a = ap.parse_args()
    text = Path(a.report).read_text()
    rendered, n, errors = process(text)
    # malformed = brace tokens that do not match the strict src:path|fmt syntax at all
    leftover = [t for t in re.findall(r"\{\{[^}]*\}\}", text) if not TOKEN.fullmatch(t)]
    print(f"{n} numeric tokens checked against results/")
    if errors:
        print(f"\n{len(errors)} UNRESOLVED tokens:")
        for tok, why in errors[:50]:
            print(f"  {tok}  ->  {why}")
    if leftover:
        print(f"\n{len(leftover)} malformed tokens (wrong syntax): {leftover[:10]}")
    if a.render:
        if a.render == "-":
            sys.stdout.write(rendered)
        else:
            Path(a.render).write_text(rendered)
            print(f"wrote resolved report -> {a.render}")
    if errors or leftover:
        sys.exit(1)
    print("OK: zero mismatches, every number resolves to a result file.")


if __name__ == "__main__":
    main()
