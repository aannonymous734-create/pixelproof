"""Draw the architecture figure used in the report -> docs/figures/architecture.png"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

INK, MUTED, EDGE = "#1b2633", "#5b6b7c", "#8193a6"
FILL = {"trust": "#e3f1ec", "content": "#e6eef8", "attack": "#fbe9e7", "out": "#f4f1e6", "plain": "#f5f7f9"}


def box(ax, x, y, w, h, title, lines, kind="plain"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc=FILL[kind], ec=EDGE, lw=1.1))
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="top", fontsize=10.5, fontweight="bold", color=INK)
    for i, t in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.68 - 0.34 * i, t, ha="center", va="top", fontsize=8.6, color=MUTED)


def arrow(ax, a, b, label=None, color=EDGE, style="-|>", ls="-", off=(0, 0.12)):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, color=color, lw=1.3, linestyle=ls))
    if label:
        ax.text((a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1], label, ha="center", fontsize=8, color=MUTED)


def main():
    fig, ax = plt.subplots(figsize=(13, 6.4))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6.6)
    ax.axis("off")
    ax.text(0.1, 6.4, "PixelProof: integrity is proven, content is assessed, and the two answers stay separate",
            fontsize=12.5, fontweight="bold", color=INK, va="top")

    box(ax, 0.1, 3.4, 2.4, 2.3, "Source (emulated S-2)", ["EuroSAT patch", "SHA-256 pixel digest", "claim: id, date, source",
                                                          "Ed25519 signature"], "trust")
    box(ax, 3.2, 3.4, 2.4, 2.3, "Untrusted channel", ["attacker VM / container", "edit, re-date, replay,", "strip, re-sign,",
                                                      "md5 downgrade"], "attack")
    box(ax, 6.3, 3.4, 2.8, 2.3, "1. Integrity verifier", ["pinned sha256 + ed25519", "trusted public-key registry",
                                                          "signed processing chain", "replay & date checks"], "trust")
    n_features = len(json.loads((Path(__file__).resolve().parents[1] / "models" / "detector.json").read_text())["features"])
    box(ax, 6.3, 0.4, 2.8, 2.5, "2. Content analysis", [f"{n_features} forensic features -> GBM", "SRM-front CNN (74k params)",
                                                         "fusion, threshold for <=5%", "false alarms + heatmap"], "content")
    box(ax, 10.2, 1.5, 2.75, 3.4, "3. Two-axis verdict", ["VERIFIED", "SIGNED_BUT_SUSPICIOUS",
                                                        "ALTERED_AFTER_CAPTURE", "UNVERIFIED_NO_TRACES", "SUSPICIOUS",
                                                        "release or quarantine", "hash-chained audit log"], "out")
    box(ax, 0.1, 0.4, 5.5, 2.4, "Analyst / jury input", ["patches without provenance (held-out test)",
                                                         "-> CLI `detect` (CSV) or dashboard upload",
                                                         "-> integrity = NO_PROVENANCE,",
                                                         "content analysis decides"], "plain")

    arrow(ax, (2.55, 4.55), (3.15, 4.55))
    ax.text(2.85, 5.95, "image + signed manifest", ha="center", fontsize=8.5, color=MUTED)
    arrow(ax, (5.65, 4.55), (6.25, 4.55))
    arrow(ax, (7.7, 3.38), (7.7, 2.95), "pixels", off=(0.38, -0.05))
    arrow(ax, (5.65, 1.6), (6.25, 1.6))
    arrow(ax, (9.15, 4.55), (10.15, 4.0))
    ax.text(9.65, 4.75, "integrity\nstatus", ha="center", fontsize=8, color=MUTED)
    arrow(ax, (9.15, 1.6), (10.15, 2.1))
    ax.text(9.65, 1.0, "type, score,\nevidence", ha="center", fontsize=8, color=MUTED)
    Path("docs/figures").mkdir(parents=True, exist_ok=True)
    fig.savefig("docs/figures/architecture.png", dpi=160, metadata={"Software": None}, bbox_inches="tight")


if __name__ == "__main__":
    main()
