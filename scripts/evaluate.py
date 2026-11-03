"""Compute every number and figure used in the report (all from saved predictions; nothing typed by hand).

Usage: python scripts/evaluate.py [--data-dir data/eurosat] [--loc-n 600]
Inputs : results/features.csv.gz, results/predictions.csv.gz, models/detector.json,
         results/integrity_campaign.json (optional)
Outputs: results/metrics.json, results/RESULTS.md, results/figures/*.png
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, roc_auc_score  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof import LABELS  # noqa: E402
from pixelproof.calibration import adaptive, fit_thresholds  # noqa: E402
from pixelproof.detector import decide, threshold_for, train_gbm  # noqa: E402
from pixelproof.features import FEATURE_NAMES, GROUPS  # noqa: E402

TEST_SETS = ["test_dev", "test_heldout", "test_dev_laundered", "test_heldout_laundered"]
SET_TITLE = {"test_dev": "Seen variants", "test_heldout": "HELD-OUT variants",
             "test_dev_laundered": "Seen + laundering", "test_heldout_laundered": "Held-out + laundering"}


def boot_ci(fn, n, B=300, seed=0):
    rng = np.random.default_rng(seed)
    vals = [fn(rng.integers(0, n, n)) for _ in range(B)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def metrics_for(P, y, thr, fam=None, ci=True):
    s = 1 - P[:, 0]
    pred = decide(P, thr)
    auth, man = y == 0, y != 0
    m = {
        "n": int(len(y)),
        "auc_roc": float(roc_auc_score(man, s)),
        "auc_pr": float(average_precision_score(man, s)),
        "false_alarm_rate": float((pred[auth] != 0).mean()),
        "detection_rate": float((pred[man] != 0).mean()),
        "binary_f1": float(f1_score(man, pred != 0)),
        "macro_f1_4class": float(f1_score(y, pred, average="macro")),
        "type_accuracy_on_detected": float((pred[man & (pred != 0)] == y[man & (pred != 0)]).mean())
        if (man & (pred != 0)).any() else 0.0,
        "confusion": confusion_matrix(y, pred, labels=[0, 1, 2, 3]).tolist(),
    }
    if ci:
        m["detection_rate_ci95"] = boot_ci(lambda i: float((pred[i][man[i]] != 0).mean()), len(y))
        m["false_alarm_rate_ci95"] = boot_ci(lambda i: float((pred[i][auth[i]] != 0).mean()), len(y))
    if fam is not None:
        m["detection_by_family"] = {f: float((pred[fam == f] != 0).mean()) for f in sorted(set(fam[man]))}
    return m


def pct(x):
    return f"{100 * x:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--results", default="results")
    ap.add_argument("--models", default="models")
    ap.add_argument("--loc-n", type=int, default=600)
    ap.add_argument("--skip-ablation", action="store_true")
    args = ap.parse_args()
    R = Path(args.results)
    figs = R / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    feats = pd.read_csv(R / "features.csv.gz")
    pred = pd.read_csv(R / "predictions.csv.gz")
    card = json.loads((Path(args.models) / "detector.json").read_text())
    target = card["target_fpr"]
    y_all = pred["label"].to_numpy()
    va = (pred["set"] == "val").to_numpy()

    g_all = pred["p_gate"].to_numpy() if "p_gate" in pred else np.zeros(len(pred))
    clean = (pred["launder"] == "none").to_numpy()
    reenc = ~clean

    def vec(c, p):  # per-patch threshold (pixelproof.calibration.adaptive)
        return adaptive(g_all, c, p) if p is not None else np.full(len(pred), c)

    models = {"features (GBM)": ("p_gbm", (card["threshold_gbm"], card.get("threshold_proc_gbm")))}
    if "p_cnn_0" in pred:
        s_cnn = 1 - pred["p_cnn_0"].to_numpy()
        cal_c, cal_p = va & (y_all == 0) & clean, va & (y_all == 0) & reenc
        models["pixel CNN"] = ("p_cnn", fit_thresholds(s_cnn[cal_c], g_all[cal_c], s_cnn[cal_p], g_all[cal_p], target)
                               if "p_gate" in pred else (threshold_for(s_cnn[cal_c], target), None))
        models[f"fused (w={card['w_gbm']:.1f})"] = ("p_fused", (card["threshold_fused"], card.get("threshold_proc_fused")))
    main_model = list(models)[-1]
    THR = {name: vec(*cp) for name, (_, cp) in models.items()}

    M = {"target_fpr": target, "models": {}, "card": {k: card[k] for k in ("sha256", "w_gbm", "threshold_gbm",
         "threshold_fused", "threshold_proc_gbm", "threshold_proc_fused") if k in card}}
    if "p_gate" in pred:
        vs = (pred["set"] == "val").to_numpy()
        M["gate_val_accuracy"] = float(((g_all[vs] >= 0.5) == reenc[vs]).mean())
    for name, (pre, cp) in models.items():
        M["models"][name] = {"threshold_clean": cp[0], "threshold_reencoded": cp[1]}
        for s_ in TEST_SETS:
            m = (pred["set"] == s_).to_numpy()
            d = pred[m]
            P = d[[f"{pre}_{i}" for i in range(4)]].to_numpy()
            M["models"][name][s_] = metrics_for(P, d["label"].to_numpy(), THR[name][m], d["family"].to_numpy(),
                                                ci=(name == main_model))

    # false alarms by land-cover class (main model, clean + laundered authentic test patches)
    pre = models[main_model][0]
    lc = {}
    for s_ in ("test_dev", "test_heldout", "test_heldout_laundered"):
        m = ((pred["set"] == s_) & (pred["label"] == 0)).to_numpy()
        d = pred[m]
        p = decide(d[[f"{pre}_{i}" for i in range(4)]].to_numpy(), THR[main_model][m])
        lc[s_] = d.assign(fa=(p != 0)).groupby("landcover")["fa"].mean().round(4).to_dict()
    M["false_alarm_by_landcover"] = lc
    # detection by held-out method (main model)
    m = ((pred["set"] == "test_heldout") & (pred["label"] > 0)).to_numpy()
    d = pred[m].copy()
    p = decide(d[[f"{pre}_{i}" for i in range(4)]].to_numpy(), THR[main_model][m])
    d["hit"] = p != 0
    d["method"] = d["meta"].map(lambda s: (lambda m: m.get("method") or m.get("interp") or m.get("shape"))(json.loads(s)))
    M["heldout_by_method"] = d.groupby(["family", "method"])["hit"].agg(["mean", "size"]).round(4).reset_index() \
        .to_dict(orient="records")

    # ablation (feature model): drop one feature group / no laundering augmentation
    if not args.skip_ablation:
        X = feats[FEATURE_NAMES].to_numpy(np.float64)
        y = feats["label"].to_numpy()
        tr, va_f = (feats["set"] == "train").to_numpy(), (feats["set"] == "val").to_numpy()
        abl = {}
        configs = [("all features", FEATURE_NAMES, tr)] + \
                  [(f"without {g}_*", [f for f in FEATURE_NAMES if not f.startswith(g + "_")], tr) for g in GROUPS] + \
                  [("no laundering augmentation", FEATURE_NAMES, tr & (feats["launder"] == "none").to_numpy())]
        for name, cols, rows in configs:
            idx = [FEATURE_NAMES.index(c) for c in cols]
            g = train_gbm(X[rows][:, idx], y[rows])
            cal = va_f & (y == 0) & (feats["launder"] == "none").to_numpy()
            th = threshold_for(1 - g.predict_proba(X[cal][:, idx])[:, 0], target)
            abl[name] = {}
            for s in ("test_dev", "test_heldout", "test_heldout_laundered"):
                m = (feats["set"] == s).to_numpy()
                P = g.predict_proba(X[m][:, idx])
                pr = decide(P, th)
                abl[name][s] = {"auc_roc": float(roc_auc_score(y[m] != 0, 1 - P[:, 0])),
                                "detection_rate": float((pr[y[m] != 0] != 0).mean()),
                                "false_alarm_rate": float((pr[y[m] == 0] != 0).mean())}
            print("ablation", name, {s: round(v["auc_roc"], 3) for s, v in abl[name].items()}, flush=True)
        M["ablation_feature_model"] = abl

    # localisation quality of the evidence heatmap (local manipulations, seen variants)
    if args.loc_n:
        from pixelproof.data import list_samples, split_samples
        from pixelproof.dataset import jobs_for_split, render
        from pixelproof.features import heatmap
        jobs = [j for j in jobs_for_split("test_dev", split_samples(list_samples(args.data_dir))["test_dev"])
                if j["family"] in ("splice", "copy_move", "inpaint") and j["set"] == "test_dev"][:args.loc_n]
        loc = {}
        for j in jobs:
            img, mask, _ = render(j)
            h = heatmap(img) > 0.5
            inter, union = (h & mask).sum(), (h | mask).sum()
            loc.setdefault(j["family"], []).append(inter / union if union else 0.0)
        M["localisation_iou_mean"] = {k: float(np.mean(v)) for k, v in loc.items()}

    # efficiency
    eff = {"feature_ms_p50": float(feats["feat_ms"].median()), "feature_ms_p95": float(feats["feat_ms"].quantile(0.95))}
    probe = subprocess.run([sys.executable, str(Path(__file__).with_name("latency_probe.py")),
                            "--model", str(Path(args.models) / "detector.joblib"), "--data-dir", args.data_dir],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        eff.update(json.loads(probe.stdout.strip().splitlines()[-1]))
    else:
        print(probe.stderr[-2000:])
    eff["model_sizes_kb"] = {p.name: round(p.stat().st_size / 1024, 1) for p in Path(args.models).glob("*")
                             if p.suffix in (".joblib", ".pt")}
    M["efficiency"] = eff
    camp = R / "integrity_campaign.json"
    if camp.exists():
        M["integrity_campaign"] = json.loads(camp.read_text())
    (R / "metrics.json").write_text(json.dumps(M, indent=2))

    # ------------------------------------------------------------------ figures
    mm = M["models"][main_model]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, s in zip(axes, ("test_dev", "test_heldout")):
        C = np.array(mm[s]["confusion"])
        Cn = C / C.sum(1, keepdims=True)
        ax.imshow(Cn, cmap="Blues", vmin=0, vmax=1)
        for i in range(4):
            for j in range(4):
                ax.text(j, i, f"{Cn[i, j]:.2f}", ha="center", va="center", color="white" if Cn[i, j] > .6 else "black")
        short = ["authentic", "resamp/splice", "copy-move", "gen/inpaint"]
        ax.set_xticks(range(4), short, rotation=25)
        ax.set_yticks(range(4), short)
        ax.set_xlabel("predicted")
        ax.set_ylabel("true")
        ax.set_title(SET_TITLE[s])
    fig.suptitle(f"Confusion matrices, {main_model}, thresholds for {target:.0%} false alarms on validation authentics")
    fig.tight_layout()
    fig.savefig(figs / "confusion.png", dpi=150, metadata={"Software": None})
    plt.close(fig)

    fams = ["resample", "splice", "copy_move", "inpaint"]
    fig, ax = plt.subplots(figsize=(9, 4))
    width = 0.2
    for k, s in enumerate(TEST_SETS):
        vals = [mm[s]["detection_by_family"].get(f, np.nan) for f in fams]
        ax.bar(np.arange(4) + (k - 1.5) * width, vals, width, label=SET_TITLE[s])
    ax.set_xticks(range(4), ["resampling", "splicing", "copy-move", "generated/inpainted"])
    ax.set_ylim(0, 1)
    ax.set_ylabel("detection rate")
    ax.axhline(0, color="k", lw=.5)
    ax.legend(fontsize=8, ncol=2)
    ax.set_title("Detection rate by manipulation family and test condition")
    fig.tight_layout()
    fig.savefig(figs / "detection_by_family.png", dpi=150, metadata={"Software": None})
    plt.close(fig)

    ex = sorted((R / "examples").glob("test_dev__*__*.png"))
    ex = [p for p in ex if not p.name.endswith("__mask.png")]
    chosen = []
    for f in ("authentic", "resample", "splice", "copy_move", "inpaint"):
        chosen += [p for p in ex if f"__{f}__" in p.name][:1]
    if chosen:
        from pixelproof.features import heatmap
        from pixelproof.imageio import load_rgb
        fig, axes = plt.subplots(3, len(chosen), figsize=(2.2 * len(chosen), 6.6))
        for k, p in enumerate(chosen):
            img = load_rgb(p)
            mask = load_rgb(p.with_name(p.stem + "__mask.png"))[..., 0] > 0
            axes[0, k].imshow(img)
            axes[0, k].set_title(p.name.split("__")[1], fontsize=9)
            axes[1, k].imshow(mask, cmap="gray", vmin=0, vmax=1)
            axes[2, k].imshow(img)
            axes[2, k].imshow(heatmap(img), cmap="inferno", alpha=.55, vmin=0, vmax=1)
            for a in axes[:, k]:
                a.axis("off")
        axes[0, 0].text(-8, 32, "patch", rotation=90, va="center")
        axes[1, 0].text(-8, 32, "true mask", rotation=90, va="center")
        axes[2, 0].text(-8, 32, "evidence", rotation=90, va="center")
        fig.tight_layout()
        fig.savefig(figs / "examples.png", dpi=150, metadata={"Software": None})
        plt.close(fig)

    # ------------------------------------------------------------------ RESULTS.md
    L = [f"# Measured results\n\nGenerated by `scripts/evaluate.py` on {time.strftime('%Y-%m-%d')}. "
         f"Alarm thresholds: {target:.0%} false alarms on clean validation authentic patches and {target:.0%} on "
         f"re-encoded ones, interpolated per patch by the re-encoding gate (validation accuracy "
         f"{M.get('gate_val_accuracy', float('nan')):.1%}). "
         f"Model file sha256: `{card.get('sha256', '?')[:16]}...`\n",
         "## 1. Detection (manipulated vs authentic)\n",
         "| Model | Test set | AUC-ROC | AUC-PR | Detection rate | False-alarm rate | Binary F1 | 4-class macro-F1 |",
         "|---|---|---|---|---|---|---|---|"]
    for name in models:
        for s in TEST_SETS:
            m = M["models"][name][s]
            L.append(f"| {name} | {SET_TITLE[s]} | {m['auc_roc']:.3f} | {m['auc_pr']:.3f} | {pct(m['detection_rate'])} | "
                     f"{pct(m['false_alarm_rate'])} | {m['binary_f1']:.3f} | {m['macro_f1_4class']:.3f} |")
    L += ["", f"95% bootstrap intervals ({main_model}):", ""]
    for s in TEST_SETS:
        m = mm[s]
        L.append(f"- {SET_TITLE[s]}: detection {pct(m['detection_rate'])} "
                 f"[{pct(m['detection_rate_ci95'][0])}, {pct(m['detection_rate_ci95'][1])}], false alarms "
                 f"{pct(m['false_alarm_rate'])} [{pct(m['false_alarm_rate_ci95'][0])}, {pct(m['false_alarm_rate_ci95'][1])}]")
    L += ["", f"## 2. Detection rate by manipulation family ({main_model})\n",
          "| Family | " + " | ".join(SET_TITLE[s] for s in TEST_SETS) + " |", "|---" * 5 + "|"]
    for f in fams:
        L.append(f"| {f} | " + " | ".join(pct(mm[s]['detection_by_family'].get(f, float('nan'))) for s in TEST_SETS) + " |")
    L += ["", "Held-out detection by method:", "", "| Family | Method / shape | Detection | n |", "|---|---|---|---|"]
    for r in M["heldout_by_method"]:
        L.append(f"| {r['family']} | {r['method']} | {pct(r['mean'])} | {r['size']} |")
    L += ["", f"## 3. False alarms by land-cover class ({main_model}, authentic patches)\n",
          "| Land cover | Seen-variant test | Held-out test | Held-out + laundering |", "|---|---|---|---|"]
    for c in sorted(lc["test_dev"]):
        L.append(f"| {c} | {pct(lc['test_dev'][c])} | {pct(lc['test_heldout'][c])} | {pct(lc['test_heldout_laundered'][c])} |")
    if "ablation_feature_model" in M:
        L += ["", "## 4. Ablation of the feature model (AUC-ROC)\n",
              "| Configuration | Seen | Held-out | Held-out + laundering |", "|---|---|---|---|"]
        for k, v in M["ablation_feature_model"].items():
            L.append(f"| {k} | {v['test_dev']['auc_roc']:.3f} | {v['test_heldout']['auc_roc']:.3f} | "
                     f"{v['test_heldout_laundered']['auc_roc']:.3f} |")
    if "localisation_iou_mean" in M:
        L += ["", "## 5. Localisation (evidence heatmap > 0.5 vs true mask, seen variants)\n",
              "| Family | Mean IoU |", "|---|---|"]
        for k, v in M["localisation_iou_mean"].items():
            L.append(f"| {k} | {v:.3f} |")
    L += ["", "## 6. Efficiency (single CPU core unless stated)\n", "| Measure | Value |", "|---|---|"]
    for k, v in eff.items():
        L.append(f"| {k} | {v if not isinstance(v, float) else round(v, 3)} |")
    if "integrity_campaign" in M:
        c = M["integrity_campaign"]
        L += ["", f"## 7. Trust layer: attack campaign ({c['n_products']} signed EuroSAT products per attack)\n",
              "| Attack | What it does | Expected status | Caught as expected |", "|---|---|---|---|"]
        for r in c["attacks"]:
            L.append(f"| {r['attack']} | {r['description']} | {r['expected']} | {pct(r['caught_as_expected'])} |")
        o = c["overhead"]
        L += ["", f"Security overhead: sign {o['sign_ms_p50']:.2f} ms (p50), verify {o['verify_ms_p50']:.2f} ms (p50), "
                  f"manifest {o['manifest_bytes_mean']:.0f} bytes ({o['overhead_percent_of_png']:.1f}% of a 64x64 PNG).", ""]
        if c.get("two_axis_verdicts"):
            L += ["Two-axis verdicts (integrity x content):", ""]
            for k, v in c["two_axis_verdicts"].items():
                L.append(f"- {k}: {v}")
    rob = R / "robustness.json"
    if rob.exists():
        rb = json.loads(rob.read_text())
        L += ["", f"## 8. Robustness sweep ({rb['model']}, {rb['n_sources']} authentic + {rb['n_sources']} manipulated "
                  "seen-variant patches, one operation applied to every patch)\n",
              "| Operation | Seen in training | False-alarm rate | Detection rate |", "|---|---|---|---|"]
        for r in rb["rows"]:
            L.append(f"| {r['condition']} | {'yes' if r['seen_in_training'] else 'NO'} | {pct(r['false_alarm_rate'])} | "
                     f"{pct(r['detection_rate'])} |")
        M["robustness"] = rb
        (R / "metrics.json").write_text(json.dumps(M, indent=2))
    (R / "RESULTS.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
