"""Print the measured v1 -> v2 before/after numbers for CHANGELOG.md (so none are hand-typed).

v1 = results/v1_baseline/ (frozen snapshot before the P1 changes).
v2 = results/ (current). Held-out v2 before/after = results/heldout_v2_v1model.json vs _v2model.json.

  python scripts/changelog_numbers.py
"""
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1] / "results"


def g(path, *keys):
    d = json.load(open(path))
    for k in keys:
        d = d[k]
    return d


def pct(x):
    return f"{100 * x:.1f}%"


def line(label, a, b, f=pct):
    arrow = "→"
    print(f"| {label} | {f(a)} | {f(b)} |")


print("### Seen variants (test_dev), fused")
for m in ["detection_rate", "false_alarm_rate", "auc_roc"]:
    v1 = g(R / "v1_baseline/metrics.json", "models", "fused (w=0.4)", "test_dev", m)
    v2 = g(R / "metrics.json", "models", "fused (w=0.4)", "test_dev", m)
    line(m, v1, v2, (lambda x: f"{x:.3f}") if m == "auc_roc" else pct)

print("\n### Held-out v1 (test_heldout), fused, by family")
for fam in ["resample", "splice", "copy_move", "inpaint"]:
    v1 = g(R / "v1_baseline/metrics.json", "models", "fused (w=0.4)", "test_heldout", "detection_by_family", fam)
    v2 = g(R / "metrics.json", "models", "fused (w=0.4)", "test_heldout", "detection_by_family", fam)
    line(fam, v1, v2)

print("\n### FROZEN held-out v2, fused (v1 model vs v2 model)")
for m in ["detection_rate", "false_alarm_rate", "auc_roc"]:
    v1 = g(R / "heldout_v2_v1model.json", "models", "fused", m)
    v2 = g(R / "heldout_v2_v2model.json", "models", "fused", m)
    line(m, v1, v2, (lambda x: f"{x:.3f}") if m == "auc_roc" else pct)
for fam in ["resample", "splice", "copy_move", "inpaint"]:
    v1 = g(R / "heldout_v2_v1model.json", "models", "fused", "detection_by_family", fam)
    v2 = g(R / "heldout_v2_v2model.json", "models", "fused", "detection_by_family", fam)
    line(fam, v1, v2)
