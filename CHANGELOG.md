# Changelog — Phase 1 hardening (before → after, measured)

All numbers below are produced by `scripts/changelog_numbers.py` from the frozen v1 snapshot
(`results/v1_baseline/`) and the current results (`results/`). The **frozen held-out v2** set was
SHA-256-locked *before* any change on this list and is the honest measure of generalisation (its hash is
in `results/heldout_v2_manifest.json`). "v1 model" and "v2 model" are the models before and after these
changes, both scored on that same frozen set.

## Second pass (2 November, evening): attack scenarios, labs, new dashboard pages, learning material

The detector and the shipped model are **still unchanged** (SHA-256 `927f0930…`). All numbers below are from test runs or result files.

| Change | Before | After |
|---|---|---|
| Attack demonstrations | the 11 attacks existed only inside the 200-product campaign and the relay | `python -m simulation.run_attack`: 12 scenarios (A to F) with expected vs actual result, evidence, timeline and a control; `pixelproof/lab.py`; evidence in `results/attack_runs/` |
| **Replay protection** | enforced, but held only in memory: **a replay after a restart was accepted** | rebuilt from the audit log on start; a test fails if the fix is removed |
| `score_demo.py` / report | counted an edit with the manifest deleted as "caught" | cryptographic attacks and provenance-stripped messages are counted separately; the report states how many such edits the detector missed |
| Dashboard | Overview, Analyse, Provenance, Live link, Results, Jury guide | + **Attack lab** (real attacks, off unless `PIXELPROOF_LAB_MODE=1`), **Station** (public-key fingerprints, model-hash check), **Audit log** (filter by severity), **About**, live counters from the audit log, toast notifications |
| API | health, ingest, analyse, ledger, registry, results | + `/stats`, `/station`, severity in `/ledger`, `/lab/scenarios`, `/lab/runs`, `/lab/run` |
| Transparent man-in-the-middle | claimed for VirtualBox only; the design could not work (flat network) | **`docker-compose.mitm.yml`: run and verified**; the satellite's own capture shows it never addressed the attacker (`results/docker_mitm/`) |
| VirtualBox lab | flat network; `ProtectHome=true` (service would not start); `scp` into another user's folder; 2 GB dataset path; whole repo shared (host keys visible); "no NAT" claim | routed topology mirroring the lab that was run; fixed service and key hand-off with a fingerprint comparison; only needed folders shared read-only; honest NAT note. **Still not booted by us.** |
| Windows | JSON saved by PowerShell/Notepad (UTF-8 BOM) crashed the CLI | accepted; tested |
| One-command demo | none | `python scripts/quick_demo.py` |
| Samples | none (labs needed the 2 GB dataset) | `samples/authentic/`: 30 unmodified official patches |
| Documents | report, run guide, Q&A | + team learning guide, VM runbook, attack scenarios, security analysis, testing, reproducibility, known limitations, audit, requirements, plan, demo script, validation and anonymity records |
| Retraining safety | `python scripts/train.py` defaulted to **10 epochs** and wrote straight over the shipped model (the Makefile and the shipped model used 8) | default 8 epochs; **refuses** to overwrite the shipped model unless `--overwrite`; tested |
| Frontend development | `npm run dev` loaded the page but every API call failed (no CORS, no proxy) | Vite proxy for `/api` (`PXP_API` to change the target); verified |
| CNN testing | none | `scripts/compare_models.py` (features vs CNN vs fused, plus the measured table); `docs/HOW_TO_RUN.md` |
| Tests | 54 Python, 16 unit (was 12), 3 end-to-end | **81 Python, 16 unit, 5 end-to-end** |

**Incident.** A retraining (10 epochs) overwrote the model files at 14:30. The original files were restored and verified, and the retrained model was
archived untouched; see `docs/FINAL_VALIDATION.md` §6 and `docs/TEAM_LEADER_STATUS.md`.

## Final verification pass (2 November, before the feature freeze)

**The detector and its model are unchanged** (`models/detector.json`, SHA-256 `927f0930…`): every detection
figure in this file and in the report is the same as before. This pass verified, corrected and packaged.

| Change | Before | After |
|---|---|---|
| `docker compose up` | never built; first real run failed (`PermissionError` writing `/home/app/keys`: the named volumes were root-owned and the satellite runs unprivileged) | Dockerfile creates the mount points owned by the unprivileged user and installs the pinned torch; run scored by `simulation/score_demo.py`: 40 downlinks, 20/20 tampered caught, 20/20 genuine unharmed, audit-log chain valid (`results/docker_lab/summary.json`) |
| Report claim "inconclusive (globally processed)" | stated in the report, the Q&A and the not-done list, **but no such output exists in the code** | corrected everywhere: smoothed authentic patches are flagged and quarantined; listed as not done and as Phase 2 |
| "37 forensic features" | in the architecture figure and two code comments | 48, the figure now reads the count from the model card |
| Delivery zip | could include `.claude/` (it can hold the author's name) | excluded in `make_delivery.py`, `.gitignore`, `.dockerignore` |
| Windows | `make` unavailable, torch warning shown as a red error in PowerShell | documented plain commands; read-only buffers copied in `cnn.py`; `render_report.py` finds pandoc and Edge/Chrome by itself |
| Dashboard | sidebar layout, plain cards | new design system (see below) |
| Tests | 51 Python, 8 unit, 1 e2e | 54 Python (+ `test_score_demo.py`), 12 unit (+ `results.test.ts`), 3 e2e (Edge, against the live backend) |

**Dashboard redesign.** Dark Geist theme (fonts bundled, no CDN), spotlight cards, animated verdict border and
glow that follow the verdict colour, animated score bars and counters (Motion, reduced-motion safe), a floating
glass navigation bar, a new Overview page with a Three.js dotted globe of the satellite → attacker → ground
link and the headline figures read live from `/api/v1/results`. Every other page inherits the new primitives.

**Report.** Added a rubric map and a "check our claims in five minutes" box, and replaced the lab paragraph by a
table of what was *run* (Docker, network namespaces) versus what is only *provided* (VirtualBox/Vagrant, not
booted by us). New limitations: the frozen v2 set has now been used to measure our changes, and the Vagrant lab
was not booted. All 102 numeric tokens still resolve to result files.

## Headline: frozen held-out v2 (fused), v1 model → v2 model

| Metric | v1 model | v2 model |
|---|---|---|
| detection rate | 32.0% | **42.9%** |
| false-alarm rate | 4.2% | 4.3% |
| AUC-ROC | 0.755 | **0.855** |
| copy-move | 9.8% | **41.7%** |
| resample | 59.6% | **67.5%** |
| splice | 14.2% | **17.4%** |
| inpaint | 50.9% | 45.1% |

Generalisation to unseen manipulations improved by **+10.9 points of detection and +0.10 AUC at an
essentially unchanged false-alarm rate**, driven mostly by copy-move (+31.9 points). Inpainting dropped
5.8 points — reported, not hidden (see "Regressions" below).

## Changes

### 1. D4 (rotation/flip) invariant copy-move matching
`pixelproof/features.py`: block-DCT keys are canonicalised over the 8 dihedral transforms (the 8 variants
are derived algebraically from one transform, then the lexicographically smallest is the signature), and
matches are grouped by a common symmetry + translation instead of a single shift vector. Four new features
(`cm_d4_*`). **Effect (frozen v2 copy-move): 9.8% → 41.7%.** Speed kept at ~21 ms/patch by vectorising the
match loop.

### 2. Colour-statistics inconsistency features for splicing
`pixelproof/features.py`: local z-scores of chroma (Cb, Cr) and saturation, outlier-region share and local
noise-level inconsistency (`cs_*`), plus feathered-edge splice augmentation in training. **Effect (frozen
v2 splice): 14.2% → 17.4%** (still the hardest family; see Limitations).

Feature count: 37 → **48**.

### 3. Frozen held-out v2 set (leakage-proof evaluation)
New `pixelproof/heldout_v2.py` (never imported by training code) and `scripts/heldout_v2.py freeze/evaluate`:
Poisson/seamless-clone splices with donors from a different land-cover class, mirrored copy-move,
exemplar-fill inpainting with injected noise, perspective/biquadratic resampling. Frozen and hashed before
any detector change; the v1 baseline on it is recorded.

### 4. Jury input robustness (no resizing)
New `pixelproof/inputs.py`: non-64×64 images are **tiled** into 64×64 (never resized — resizing itself
creates resampling traces) with a max-of-n threshold correction from stored clean-score quantiles;
EuroSAT-MS 13-band GeoTIFF (B4/B3/B2), 16-bit, grayscale/RGBA and corrupted files are handled. Wired into
`Detector.analyse`, the CLI `detect`/`analyse` and the API. 13 new tests.

### 5. VM attack lab + transparent MITM
`lab/` (Vagrantfile + provisioning for 3 isolated VMs; `netns_lab.py` no-VM runner using iptables
redirection), `docs/VM_LAB.md`. Demonstrates a transparent man-in-the-middle the satellite is unaware of;
the ground station still catches every tampering attempt.

### 6. Ground-station hardening
`pixelproof/api.py`: per-client rate limiting (`PIXELPROOF_RATE_PER_MIN`, default 120/min), served React
dashboard, results endpoint. TLS documented for production.

### 7. React dashboard
`frontend/` (React + TS + Tailwind + shadcn-style UI + Three.js + Motion), built into
`pixelproof/static/app`, served by FastAPI; classic dashboard kept at `/classic`.

### 8. Reproducibility & trust
`scripts/check_numbers.py` (every report number must resolve to a result file; zero mismatches),
report rewritten to the mandated structure, pinned dependency versions (torch included).

### 9. Bug fix
`scripts/robustness_sweep.py`: a `NameError` (`budget` undefined) in the compute path crashed the sweep;
fixed to use the detector's target false-alarm rate.

## Regressions (reported honestly)

| Metric | v1 | v2 | Note |
|---|---|---|---|
| Seen variants (test_dev) detection | 92.8% | 90.3% | small cost of trading seen-fit for generalisation; false alarms also fell (3.9% → 3.6%) |
| Seen AUC | 0.978 | 0.972 | — |
| Frozen v2 inpaint | 50.9% | 45.1% | the new copy-move/splice emphasis slightly reduced inpaint recall; net v2 detection still up +10.9 pts |

Held-out v1 by family moved resample 90.8% → 96.6%, copy-move 22.7% → 25.3%, splice 16.6% → 18.1%,
inpaint 67.3% → 63.8%.
