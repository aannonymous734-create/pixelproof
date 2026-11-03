"""Attack-scenario engine: run one named attack against the REAL ground-station pipeline and keep the evidence.

Everything runs inside one process, on this machine, on synthetic traffic made from the bundled
EuroSAT sample patches (`samples/`). Nothing touches the network and nothing outside this process is
attacked. It is the same code that the VM / Docker lab exercises with three separate machines.

Roles, kept apart exactly as in the lab:
  * SATELLITE  holds the private keys (a temporary folder that is deleted afterwards) and signs.
  * ATTACKER   sees only the intercepted (image, manifest) message and its OWN untrusted key.
  * GROUND     is the real `GroundStation`: it receives only the PUBLIC registry, verifies, runs the
               content detector, decides and writes the hash-chained audit log.

Every scenario reports: what the attacker did, what a correct system must answer (`expected`), what the
ground station really answered, and the evidence (digests, reasons, audit-log hashes, a timeline).
`matches_expected` is computed, never typed in: a scenario only "passes" when the ground station's real
answer equals the expected one.

Used by `python -m simulation.run_attack` and by the dashboard's Attack-lab page (POST /api/v1/lab/run,
only when PIXELPROOF_LAB_MODE=1).
"""
from __future__ import annotations

import copy
import json
import os
import platform
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from . import manipulations as M
from .imageio import load_rgb
from .integrity_attacks import ATTACKS, _ATTACKER_KEY
from .provenance import CLAIM_FIELDS, b64e, canonical, demo_setup, pixel_digest
from .service import GroundStation

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES = ROOT / "samples" / "authentic"
MAX_TRIALS = 50


class LabError(RuntimeError):
    """A scenario cannot run (unknown name, no sample images, ...). The message is safe to show to a user."""


# ---------------------------------------------------------------------------- attacks specific to the lab
def forge_image_and_manifest(img, m, rng, **_):
    """Attack C: edit the image AND rebuild the manifest to match, signing with the attacker's own key
    while still claiming to be the satellite. The digest now matches, but the signature cannot."""
    out = M.inpaint(img, rng, "heldout")[0]
    forged = copy.deepcopy(m)
    forged["pixel_digest"] = pixel_digest(out)
    forged["processing"] = []
    claim = {k: forged[k] for k in CLAIM_FIELDS}
    forged["signature"] = b64e(_ATTACKER_KEY.sign(canonical(claim)))
    return out, forged


# Visual attacks edit the pixels and then drop the manifest: the attacker cannot forge a valid one.
_EDITORS = {
    "copy_move": lambda img, other, rng: M.copy_move(img, rng, "heldout")[0],
    "splice": lambda img, other, rng: M.splice(img, other, rng, "heldout")[0],
    "inpaint": lambda img, other, rng: M.inpaint(img, rng, "heldout")[0],
    "resample": lambda img, other, rng: M.resample(img, rng, "heldout")[0],
}

# name -> definition. `kind` selects the trial procedure below; `expected` is what a correct system answers.
SCENARIOS: dict[str, dict] = {
    "image_tampering": {
        "id": "A1", "kind": "integrity", "attack": ATTACKS["pixel_inpaint"][0], "expected": "PIXELS_ALTERED",
        "title": "Image tampering after signing",
        "attacker_action": "Intercepts a signed message, erases a region of the image and fills it in, and forwards "
                           "it with the original manifest.",
        "why_it_fails": "The manifest holds the SHA-256 digest of the original pixels, so the new pixels no longer match.",
    },
    "invisible_tampering": {
        "id": "A2", "kind": "integrity", "attack": ATTACKS["lsb_embed"][0], "expected": "PIXELS_ALTERED",
        "title": "Invisible tampering (hidden bits)",
        "attacker_action": "Flips the least-significant bit of 512 pixels: invisible to the eye and to content detectors.",
        "why_it_fails": "Any single changed pixel value changes the SHA-256 digest, visible or not.",
    },
    "manifest_tampering": {
        "id": "B1", "kind": "integrity", "attack": ATTACKS["date_replace"][0], "expected": "BAD_SIGNATURE",
        "title": "Manifest tampering (capture date changed)",
        "attacker_action": "Changes the capture date inside the manifest and keeps the original signature.",
        "why_it_fails": "The Ed25519 signature covers the whole claim, so changing any field invalidates it.",
    },
    "identity_forgery": {
        "id": "B2", "kind": "integrity", "attack": ATTACKS["date_replace_resign"][0], "expected": "UNKNOWN_KEY",
        "title": "Satellite identity forgery",
        "attacker_action": "Changes the date, claims to be the satellite and signs with its own key.",
        "why_it_fails": "The ground station trusts only the public keys in its own registry, never a key sent with the message.",
    },
    "image_manifest_replacement": {
        "id": "C1", "kind": "integrity", "attack": forge_image_and_manifest, "expected": "BAD_SIGNATURE",
        "title": "Image and manifest replacement",
        "attacker_action": "Edits the image, builds a new manifest with the matching digest, and signs it with the "
                           "attacker's own key while claiming the satellite's identity.",
        "why_it_fails": "A matching digest is easy to compute, but a valid signature needs the satellite's private key, "
                        "which exists only on the satellite.",
    },
    "algorithm_downgrade": {
        "id": "C2", "kind": "integrity", "attack": ATTACKS["algorithm_downgrade"][0], "expected": "WEAK_ALGORITHM",
        "title": "Algorithm substitution (md5)",
        "attacker_action": "Edits the pixels and claims the weak hash md5, recomputed over the edited pixels.",
        "why_it_fails": "The verifier pins sha256 + ed25519 and rejects any other algorithm before comparing anything.",
    },
    "replay": {
        "id": "D1", "kind": "replay", "attack": ATTACKS["replay"][0], "expected": "REPLAY",
        "title": "Replay of a genuine message",
        "attacker_action": "Re-sends a genuine, validly signed message that was already delivered.",
        "why_it_fails": "The ground station remembers received products and each source's last sequence number, "
                        "and this memory survives a restart (it is rebuilt from the audit log).",
    },
    "visual_copy_move": {
        "id": "E1", "kind": "content", "editor": "copy_move", "expected": "CONTENT_FLAGGED",
        "title": "Copy-move manipulation (no provenance)",
        "attacker_action": "Duplicates a region inside the image and removes the manifest.",
        "why_it_fails": "It may not: with no signature to check, only the statistical detector can notice. The result is "
                        "a measured detection, never a guarantee.",
    },
    "visual_splice": {
        "id": "E2", "kind": "content", "editor": "splice", "expected": "CONTENT_FLAGGED",
        "title": "Splicing (no provenance)",
        "attacker_action": "Pastes a region from a different image and removes the manifest.",
        "why_it_fails": "Splicing is our weakest family on unseen methods (see the report): expect misses.",
    },
    "visual_inpaint": {
        "id": "E3", "kind": "content", "editor": "inpaint", "expected": "CONTENT_FLAGGED",
        "title": "Inpainting / generated fill (no provenance)",
        "attacker_action": "Erases a region and fills it with synthesised texture, then removes the manifest.",
        "why_it_fails": "It may not: the detector looks for missing sensor noise in the filled region.",
    },
    "visual_resample": {
        "id": "E4", "kind": "content", "editor": "resample", "expected": "CONTENT_FLAGGED",
        "title": "Resampling (no provenance)",
        "attacker_action": "Rescales or rotates the patch, which leaves periodic interpolation traces, and removes the manifest.",
        "why_it_fails": "Resampling leaves strong periodic traces; this is the detector's best family.",
    },
    "compromised_source": {
        "id": "F1", "kind": "compromised_source", "expected": "VERIFIED",
        "title": "Manipulated BEFORE signing (compromised payload)",
        "attacker_action": "Edits the image before it reaches the signer, so the satellite signs the fake itself.",
        "why_it_fails": "It is NOT stopped by the signature: a valid signature proves who signed and that nothing changed "
                        "afterwards, not that the picture is true. Only the content detector can raise a flag.",
    },
}


def list_scenarios() -> list[dict]:
    keys = ("id", "kind", "title", "attacker_action", "why_it_fails", "expected")
    return [{"name": n, **{k: s[k] for k in keys}} for n, s in SCENARIOS.items()]


# ----------------------------------------------------------------------------------------------- helpers
def _load_samples(samples_dir) -> list[Path]:
    d = Path(samples_dir)
    files = sorted(p for p in d.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff"))
    if not files:
        raise LabError(f"no sample images found in {d}. The repository ships them in samples/authentic/.")
    return files


def _short(d: str | None) -> str | None:
    return None if d is None else f"{d[:16]}…"


def _content_view(result: dict) -> dict:
    c = result.get("content") or {}
    return {"flagged": bool(c.get("manipulated")), "type": c.get("type"), "score": c.get("manipulation_score"),
            "threshold": c.get("threshold"), "evidence": c.get("evidence", [])[:3]}


class _Run:
    """Holds the three roles of one run and the timeline of what happened."""

    def __init__(self, tmp: Path, model_path):
        # SATELLITE side: the only place a private key exists (a temp folder, deleted when the run ends)
        _, reg, self.src, self.proc = demo_setup(tmp / "satellite_keys")
        # GROUND side: receives the PUBLIC registry only
        reg.save(tmp / "registry.json")
        self.ground = GroundStation(model_path=model_path, registry_path=tmp / "registry.json",
                                    ledger_path=tmp / "ledger.jsonl")
        self.t0 = time.perf_counter()
        self.clock0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
        self.n_signed = 0
        self.timeline: list[dict] = []

    def log(self, actor: str, event: str, **detail):
        self.timeline.append({"t_ms": round((time.perf_counter() - self.t0) * 1000, 1), "actor": actor,
                              "event": event, **detail})

    def sign(self, img, product_id):
        when = (self.clock0 + timedelta(minutes=self.n_signed)).isoformat(timespec="seconds")
        self.n_signed += 1
        m = self.src.capture(img, product_id, when)
        m = self.proc.record(m, "eurosat_patch_export", {"format": "uint8 RGB 64x64"}, img)
        self.log("satellite", "signed product", product_id=product_id, pixel_digest=_short(m["pixel_digest"]),
                 seq=m["seq"])
        return m

    def deliver(self, img, manifest, source):
        r = self.ground.process(img, manifest, live=True, source=source)
        self.log("ground", "verdict", integrity=r["integrity"]["status"], verdict=r["verdict"], action=r["action"],
                 ledger_hash=_short(r.get("ledger_hash")))
        return r


# ------------------------------------------------------------------------------------------------ the run
def run_scenario(name: str, *, n: int = 1, seed: int = 7, samples_dir=None, model_path=None) -> dict:
    """Run `n` independent trials of one scenario and return the full, JSON-serialisable evidence."""
    if name not in SCENARIOS:
        raise LabError(f"unknown scenario {name!r}; choose one of: {', '.join(SCENARIOS)}")
    sc = SCENARIOS[name]
    samples = _load_samples(samples_dir or DEFAULT_SAMPLES)
    n = max(1, min(int(n), MAX_TRIALS))
    started = time.perf_counter()
    rng_pick = np.random.default_rng(seed)
    order = [samples[i] for i in rng_pick.permutation(len(samples))]
    trials, control_ok, control_false_alarms = [], 0, 0

    with tempfile.TemporaryDirectory(prefix="pxp_lab_") as tmp:
        run = _Run(Path(tmp), model_path)
        for i in range(n):
            path, other_path = order[i % len(order)], order[(i + 1) % len(order)]
            img, other = load_rgb(path), load_rgb(other_path)
            rng = np.random.default_rng(seed * 1000 + i)
            run.timeline.clear()
            pid = f"LAB-{sc['id']}-{i + 1:03d}"
            trial = {"trial": i + 1, "sample": path.name}

            if sc["kind"] == "content":
                # the attacker edits and drops the manifest; the control is the untouched authentic image
                ctl = run.deliver(img, None, f"lab:{name}:control")
                control_false_alarms += bool(ctl["content"]["manipulated"])
                a_img = _EDITORS[sc["editor"]](img, other, rng)
                run.log("attacker", f"edited image ({sc['editor']}) and removed the manifest")
                r = run.deliver(a_img, None, f"lab:{name}")
                trial["matches_expected"] = bool(r["content"]["manipulated"])
                trial["received_digest"] = _short(pixel_digest(a_img))
            elif sc["kind"] == "compromised_source":
                m_ctl = run.sign(other, pid + "-ctl")
                ctl = run.deliver(other, m_ctl, f"lab:{name}:control")
                control_ok += ctl["integrity"]["status"] == "VERIFIED"
                fake = M.inpaint(img, rng, "heldout")[0]
                run.log("attacker", "edited the image BEFORE signing (compromised payload)")
                m = run.sign(fake, pid)
                r = run.deliver(fake, m, f"lab:{name}")
                trial["matches_expected"] = r["integrity"]["status"] == "VERIFIED"
                trial["signed_digest"], trial["received_digest"] = _short(m["pixel_digest"]), _short(pixel_digest(fake))
            else:  # "integrity" and "replay"
                m_ctl = run.sign(other, pid + "-ctl")
                ctl = run.deliver(other, m_ctl, f"lab:{name}:control")
                control_ok += ctl["integrity"]["status"] == "VERIFIED"
                m = run.sign(img, pid)
                if sc["kind"] == "replay":
                    first = run.deliver(img, m, f"lab:{name}:first-delivery")
                    trial["first_delivery"] = first["integrity"]["status"]
                    run.log("attacker", "recorded the delivered message and sends it again")
                    a_img, a_m = sc["attack"](img, m, rng)
                else:
                    a_img, a_m = sc["attack"](img, m, rng, other=other)
                    run.log("attacker", "intercepted the message and modified it", action=sc["title"])
                r = run.deliver(a_img, a_m, f"lab:{name}")
                trial["matches_expected"] = r["integrity"]["status"] == sc["expected"]
                trial["signed_digest"], trial["received_digest"] = _short(m["pixel_digest"]), _short(pixel_digest(a_img))

            trial.update({
                "product_id": pid,
                "integrity_status": r["integrity"]["status"],
                "verdict": r["verdict"],
                "action": r["action"],
                "content": _content_view(r),
                "reasons": [x for x in r["reasons"] if not x.startswith("content:")][:3],
                "ledger_hash": r.get("ledger_hash"),
                "timeline": copy.deepcopy(run.timeline),
            })
            if sc["kind"] != "content":
                trial["control_status"] = ctl["integrity"]["status"]
            trials.append(trial)

        ledger_ok, first_bad = run.ground.ledger.verify()
        ledger_entries = len(run.ground.ledger.entries())
        model_mode = "features+cnn" if run.ground.detector.fused else "features"

    matches = sum(t["matches_expected"] for t in trials)
    result = {
        "scenario": name, "id": sc["id"], "kind": sc["kind"], "title": sc["title"],
        "attacker_action": sc["attacker_action"], "why_it_fails": sc["why_it_fails"], "expected": sc["expected"],
        "n": n, "matches_expected": matches, "rate": matches / n,
        "control": ({"n": n, "false_alarms": control_false_alarms} if sc["kind"] == "content"
                    else {"n": n, "verified": control_ok}),
        "audit_log": {"entries": ledger_entries, "chain_valid": ledger_ok, "first_bad_entry": first_bad},
        "trials": trials,
        "environment": {"python": platform.python_version(), "platform": platform.system(),
                        "cpu_threads": os.cpu_count(), "model_mode": model_mode, "seed": seed,
                        "samples": "samples/authentic (official EuroSAT RGB patches, unmodified)"},
        "duration_s": round(time.perf_counter() - started, 2),
    }
    return json.loads(json.dumps(result, default=str))
