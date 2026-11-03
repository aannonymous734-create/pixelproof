# PixelProof: Trust the Pixel (TSYP14, Track 3)

**Was this image altered or falsely attributed?** PixelProof answers the two halves of that question separately, as the
track requires ("distinguish post-capture integrity from semantic truth"):

| Answer | Question | How | Nature |
|---|---|---|---|
| **Integrity** | Are these exactly the pixels, date and source a trusted source signed? | SHA-256 pixel digest · Ed25519-signed claim · signed processing chain · pinned algorithms · replay checks | **proof** |
| **Content** | Does the patch carry traces of resampling, splicing, copy-move or generation/inpainting? | 48 explainable forensic features → gradient boosting, fused with a small SRM-front CNN; threshold calibrated for a 5% false-alarm budget on authentic EuroSAT | **evidence** (never "authentic", only "no traces found") |

> **A signature proves who signed and that nothing changed afterwards. It does not prove the picture is true.** A compromised
> source can sign a fake; only the content detector can notice, and it misses some. The attack lab measures this (scenario F1).

Everything is software, runs on a CPU laptop, and uses the official reference data (EuroSAT, Sentinel-2).

![architecture](docs/figures/architecture.png)

## Start here

| If you are... | Read |
|---|---|
| **a team member** learning the project | [`docs/TEAM_GUIDE.md`](docs/TEAM_GUIDE.md) (beginner level, every command tested) |
| wanting to **run each part** (frontend, backend, satellite, attacker, CNN, tests) | [`docs/HOW_TO_RUN.md`](docs/HOW_TO_RUN.md) |
| doing the **VM / lab** part | [`vm/README.md`](vm/README.md) (step by step) |
| **the jury** | [`docs/RUN_GUIDE.md`](docs/RUN_GUIDE.md), [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md), the report `PixelProof_Phase1_Report.pdf` |
| preparing the **demo** | [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md), [`docs/JURY_QA.md`](docs/JURY_QA.md) |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate         # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-cnn.txt --index-url https://download.pytorch.org/whl/cpu   # optional CNN (keep the path short on Windows)
python -m pytest -q                                        # automated tests
python scripts/quick_demo.py                               # ground + attacker + satellite; dashboard at http://127.0.0.1:8000
python -m simulation.run_attack --all --n 20               # every attack scenario, with evidence
python -m pixelproof.cli detect --input FOLDER_OF_PATCHES --output predictions.csv      # the jury's held-out patches
```

## What was run, and what was not

| | Status |
|---|---|
| Automated tests (Python, dashboard unit, dashboard end-to-end) | **run**, see [`docs/FINAL_VALIDATION.md`](docs/FINAL_VALIDATION.md) |
| Attack scenarios A to F (`simulation.run_attack`) | **run**; evidence in `results/attack_runs/` |
| Docker lab, explicit relay (`docker-compose.yml`) | **run**; `results/docker_lab/` |
| **Docker lab, transparent man-in-the-middle** (`docker-compose.mitm.yml`) | **run and verified**; `results/docker_mitm/` (packet capture included) |
| Linux network-namespace lab (`lab/netns_lab.py`) | run in an earlier session; not re-run on the Windows laptop |
| **VirtualBox / Vagrant lab** (`lab/`) | scripts provided and syntax-checked; **never booted by us** |
| Full retraining (`make reproduce`) | not re-run in this pass; the saved model and `results/` come from the earlier runs |

Every measured number lives in `results/` and is inserted into the report by a script that fails on any mismatch
(`python scripts/check_numbers.py docs/REPORT.md`). Known weak spots are reported, not hidden: [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).

## The six deliverables

| # | Deliverable | Where |
|---|---|---|
| 1 | Threat model and segment analysis | [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md), [`docs/SECURITY_ANALYSIS.md`](docs/SECURITY_ANALYSIS.md), report §1 |
| 2 | Platform / architecture / trust anchor | `pixelproof/provenance.py`, `ledger.py`, `service.py`, `api.py`, report §2 |
| 3 | Signal / image processing | `pixelproof/features.py`, report §3 |
| 4 | AI or statistical detection | `pixelproof/detector.py`, `cnn.py`, `scripts/train.py`, report §4 |
| 5 | Adversarial validation and response | `pixelproof/lab.py`, `integrity_attacks.py`, `simulation/`, [`docs/ATTACK_SCENARIOS.md`](docs/ATTACK_SCENARIOS.md), the labs, report §5 |
| 6 | Documentation using the official reference datasets | [`docs/DATASET_CARD.md`](docs/DATASET_CARD.md), [`docs/RUN_GUIDE.md`](docs/RUN_GUIDE.md), `scripts/download_eurosat.py` |

## Repository layout

```
pixelproof/     BACKEND: crypto trust layer, detector, API, attack-scenario engine (lab.py), audit log, CLI
frontend/       dashboard source (React + TypeScript + Tailwind + shadcn-style UI + Three.js + Motion); built into pixelproof/static/app
simulation/     satellite_node.py · attacker.py · score_demo.py · run_attack.py
lab/, vm/       VirtualBox lab (Vagrantfile + provisioning) and its beginner runbook
docker-compose.yml, docker-compose.mitm.yml, Dockerfile     the Docker labs
samples/        30 unmodified official EuroSAT patches for the labs and tests (no dataset download needed)
scripts/        quick_demo · check_numbers · render_report · anonymity_check · make_delivery · train · evaluate · ...
models/         detector.joblib (+ model card with SHA-256) · pixelnet.pt
results/        measured results as JSON, figures, and the lab evidence (attack_runs/, docker_lab/, docker_mitm/, lab/)
docs/           report, team guide, threat and security analysis, attack scenarios, testing, reproducibility, audit, ...
tests/          automated tests
```

The folder names in the competition brief map as: **backend** = `pixelproof/`, **frontend** = `frontend/`, **simulation** =
`simulation/`, **vm** = `lab/` + `vm/`, **report** = `PixelProof_Phase1_Report.pdf` (source `docs/REPORT.md`). The code keeps this layout so
that imports, the Dockerfile and the tests keep working.

Licence: MIT. Data: EuroSAT (MIT) with Copernicus Sentinel data terms.
