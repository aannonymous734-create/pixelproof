"""Ground-station HTTP API + dashboard.

Run:  uvicorn pixelproof.api:app --host 0.0.0.0 --port 8000
      then open http://localhost:8000

Endpoints
  POST /api/v1/ingest    live downlink (JSON {image_png_b64, manifest|null}); registers the product
  POST /api/v1/analyse   analyst upload (multipart: image file + optional manifest .json); read-only
  GET  /api/v1/ledger    last entries of the hash-chained audit log + chain validity (with a display severity)
  GET  /api/v1/registry  trusted PUBLIC keys
  GET  /api/v1/stats     overview counters computed from the audit log
  GET  /api/v1/station   trusted identities (public-key fingerprints), last downlink, trust policy, detector
  GET  /api/v1/results   the measured result files (read-only)
  GET  /api/v1/health
  GET  /api/v1/lab/scenarios, GET /api/v1/lab/runs, POST /api/v1/lab/run
                         attack lab on synthetic traffic; the POST works only with PIXELPROOF_LAB_MODE=1
"""
from __future__ import annotations

import base64
import binascii
from pathlib import Path

import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import __version__, lab
from .inputs import InputError, load_any
from .provenance import b64d, sha256_hex
from .service import GroundStation, event_severity, load_manifest, summarize

MAX_BYTES = 2 * 1024 * 1024
STATIC = Path(__file__).with_name("static")

# Per-client rate limit on the analysis endpoints: a fixed number of requests per rolling window.
# In-process and dependency-free (enough for the lab and a single ground node); put a reverse proxy
# in front for production. Configure with PIXELPROOF_RATE_PER_MIN (0 disables).
RATE_PER_MIN = int(os.environ.get("PIXELPROOF_RATE_PER_MIN", "120"))
_hits: dict[str, deque] = {}


def _rate_limit(request: Request):
    if RATE_PER_MIN <= 0:
        return
    now = time.monotonic()
    ip = request.client.host if request.client else "?"
    dq = _hits.setdefault(ip, deque())
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= RATE_PER_MIN:
        raise HTTPException(429, f"rate limit {RATE_PER_MIN}/min exceeded; retry shortly")
    dq.append(now)


app = FastAPI(title="PixelProof ground station", version=__version__)
_gs: GroundStation | None = None


def gs() -> GroundStation:
    global _gs
    if _gs is None:
        _gs = GroundStation()
    return _gs


def _decode(data: bytes):
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "image larger than 2 MB")
    try:
        return load_any(data)[0]
    except InputError as e:
        raise HTTPException(422, f"file is not a usable image: {e}")


class Downlink(BaseModel):
    image_png_b64: str
    manifest: dict | None = None


@app.get("/api/v1/health")
def health():
    g = gs()
    return {"status": "ok", "version": __version__, "model": g.detector.info.get("version"),
            "model_mode": "features+cnn" if g.detector.fused else "features",
            "trusted_keys": len(g.registry.keys)}


@app.post("/api/v1/ingest")
def ingest(msg: Downlink, request: Request):
    _rate_limit(request)
    try:
        raw = base64.b64decode(msg.image_png_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "image_png_b64 is not valid base64")
    return gs().process(_decode(raw), msg.manifest, live=True, source="downlink")


@app.post("/api/v1/analyse")
async def analyse(request: Request, image: UploadFile = File(...), manifest: UploadFile | None = File(None)):
    _rate_limit(request)
    img = _decode(await image.read(MAX_BYTES + 1))
    man = None
    if manifest is not None:
        try:
            man = load_manifest(await manifest.read(256 * 1024))
        except ValueError:
            raise HTTPException(422, "manifest is not a JSON object")
    return gs().process(img, man, live=False, source="analyst")


@app.get("/api/v1/ledger")
def ledger(limit: int = 50):
    g = gs()
    ok, bad = g.ledger.verify()
    recent = g.ledger.entries()[-max(1, min(limit, 500)):][::-1]
    return {"chain_valid": ok, "first_bad_entry": bad,
            "entries": [{**e, "severity": event_severity(e)} for e in recent]}


@app.get("/api/v1/registry")
def registry():
    return gs().registry.keys


@app.get("/api/v1/stats")
def stats():
    """Overview counters, computed from the audit log only."""
    g = gs()
    ok, _ = g.ledger.verify()
    return {**summarize(g.ledger.entries()), "audit_chain_valid": ok}


@app.get("/api/v1/station")
def station():
    """Who this ground station trusts and what it last received. PUBLIC information only: the registry holds
    public keys, and no private key, file path or secret is ever returned."""
    g = gs()
    g.reload_registry()
    identities = [{"key_id": kid, "role": k["role"], "owner": k["owner"], "revoked": k["revoked"],
                   "fingerprint_sha256": sha256_hex(b64d(k["public_key"])), "public_key": k["public_key"]}
                  for kid, k in g.registry.keys.items()]
    entries = g.ledger.entries()
    downlinks = [e for e in entries if e.get("channel") == "downlink"]
    last = downlinks[-1] if downlinks else None
    ok, bad = g.ledger.verify()
    return {
        "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "identities": identities,
        "downlinks_received": len(downlinks),
        "last_downlink": ({"time": last["time"], "product_id": last["product_id"], "verdict": last["verdict"],
                           "integrity": last["integrity"], "action": last["action"]} if last else None),
        "audit_chain_valid": ok,
        "first_bad_entry": bad,
        "replay_memory": {"products": len(g.verifier.seen), "sources": len(g.verifier.last_seq)},
        "trust_policy": {"hash": "sha256", "signature": "ed25519", "pinned": True,
                         "max_future_minutes": int(g.verifier.max_future.total_seconds() // 60),
                         "replay_protection": "enforced, rebuilt from the audit log after a restart"},
        "detector": {"version": g.detector.info.get("version"), "mode": "features+cnn" if g.detector.fused else "features",
                     "model_sha256": g.model_sha256, "model_card_match": g.model_card_match},
        "lab_mode": lab_enabled(),
    }


# ---------------------------------------------------------------------------------- attack lab (opt-in)
# The attack lab signs, attacks and verifies SYNTHETIC traffic inside this process (see pixelproof/lab.py).
# It is OFF unless the operator starts the server with PIXELPROOF_LAB_MODE=1, so a production ground station
# (or the ground VM) never exposes it. It uses its own temporary keys, registry and audit log: it can never
# change what this station trusts or write to its real audit log.
def lab_enabled() -> bool:
    return os.environ.get("PIXELPROOF_LAB_MODE") == "1"


_lab_lock = threading.Lock()
_lab_history: deque = deque(maxlen=20)


class LabRun(BaseModel):
    scenario: str
    n: int = 1


@app.get("/api/v1/lab/scenarios")
def lab_scenarios():
    return {"enabled": lab_enabled(), "max_trials": lab.MAX_TRIALS, "scenarios": lab.list_scenarios()}


@app.post("/api/v1/lab/run")
def lab_run(req: LabRun, request: Request):
    _rate_limit(request)
    if not lab_enabled():
        raise HTTPException(403, "The attack lab is disabled on this server. Start it with PIXELPROOF_LAB_MODE=1.")
    if not _lab_lock.acquire(blocking=False):
        raise HTTPException(429, "Another lab run is in progress; try again in a moment.")
    try:
        result = lab.run_scenario(req.scenario, n=req.n)
    except lab.LabError as e:
        raise HTTPException(422, str(e))
    finally:
        _lab_lock.release()
    _lab_history.appendleft({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             **{k: result[k] for k in ("scenario", "id", "title", "expected", "n", "matches_expected")}})
    return result


@app.get("/api/v1/lab/runs")
def lab_runs():
    return list(_lab_history)


RESULTS = Path(__file__).resolve().parents[1] / "results"
_RESULT_FILES = {
    "metrics": "metrics.json",
    "heldout_v2": "heldout_v2_v2model.json",
    "heldout_v2_v1": "heldout_v2_v1model.json",
    "robustness": "robustness.json",
    "campaign": "integrity_campaign.json",
}


@app.get("/api/v1/results")
def results():
    """Serve the measured result files so the dashboard shows only real, reproduced numbers."""
    import json
    out = {}
    for key, name in _RESULT_FILES.items():
        p = RESULTS / name
        out[key] = json.loads(p.read_text()) if p.exists() else None
    return out


# Built React dashboard (pixelproof/static/app); falls back to the classic single-file dashboard.
APP_DIR = STATIC / "app"
if APP_DIR.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/app", StaticFiles(directory=str(APP_DIR), html=True), name="app")


@app.get("/")
def index():
    if (APP_DIR / "index.html").exists():
        return FileResponse(APP_DIR / "index.html")
    return FileResponse(STATIC / "index.html")


@app.get("/classic")
def classic():
    return FileResponse(STATIC / "index.html")
