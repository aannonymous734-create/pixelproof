"""Ground-station service logic shared by the API and the CLI: verify + analyse + decide + log."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
from pathlib import Path

import numpy as np
from PIL import Image

from .detector import Detector
from .ledger import Ledger
from .provenance import Registry, Verifier, pixel_digest
from .verdict import combine


def heatmap_png_b64(img: np.ndarray, hm: np.ndarray) -> str:
    """Overlay of the evidence heatmap on the patch, upscaled x4 for display."""
    base = img.astype(np.float32)
    red = np.zeros_like(base)
    red[..., 0] = 255
    red[..., 1] = 60
    a = (np.clip(hm, 0, 1) * 0.65)[..., None]
    over = (base * (1 - a) + red * a).astype(np.uint8)
    h, w = over.shape[:2]
    k = max(1, min(4, 1024 // max(h, w)))  # x4 for 64x64 patches, never larger than 1024 px
    big = Image.fromarray(over).resize((w * k, h * k), Image.NEAREST)
    buf = io.BytesIO()
    big.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class GroundStation:
    def __init__(self, model_path=None, registry_path=None, ledger_path=None):
        root = Path(__file__).resolve().parents[1]
        self.model_path = Path(model_path or os.environ.get("PIXELPROOF_MODEL", root / "models" / "detector.joblib"))
        reg_path = Path(registry_path or os.environ.get("PIXELPROOF_REGISTRY", root / "runtime" / "registry.json"))
        self.detector = Detector.load(self.model_path)
        # The model is a pickle file (it can run code when loaded): record its real hash and compare it with the
        # hash written in the model card at training time, so a swapped model file is visible on the dashboard.
        self.model_sha256 = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        try:
            card = json.loads(self.model_path.with_suffix(".json").read_text())
            self.model_card_match: bool | None = card.get("sha256") == self.model_sha256
        except (OSError, ValueError):
            self.model_card_match = None  # no model card next to the file
        self.registry = Registry.load(reg_path) if reg_path.exists() else Registry()
        self.registry_path = reg_path
        self.verifier = Verifier(self.registry)
        self.ledger = Ledger(ledger_path or os.environ.get("PIXELPROOF_LEDGER", root / "runtime" / "ledger.jsonl"))
        self._lock = threading.Lock()
        self._restore_replay_state()

    def _restore_replay_state(self):
        """Replay protection must survive a restart. The verifier keeps "already received" and "last sequence
        number" in memory, so we rebuild them from the audit log: every accepted live downlink was recorded with
        its capture time, claimed digest, key id and sequence number."""
        for e in self.ledger.entries():
            if e.get("channel") == "downlink" and e.get("integrity") == "VERIFIED" and e.get("claim_digest"):
                self.verifier.seen[e["product_id"]] = (e["capture_time"], e["claim_digest"])
                if e.get("key_id") is not None and e.get("seq") is not None:
                    self.verifier.last_seq[e["key_id"]] = max(self.verifier.last_seq.get(e["key_id"], 0), int(e["seq"]))

    def reload_registry(self):
        if self.registry_path.exists():
            self.registry.keys = Registry.load(self.registry_path).keys

    def process(self, img: np.ndarray, manifest: dict | None, live: bool, source: str = "upload") -> dict:
        with self._lock:
            if live:
                self.reload_registry()
            integrity = self.verifier.verify(img, manifest, record=live)
        content = self.detector.analyse(img)
        result = combine(integrity, content)
        result["product_id"] = (manifest or {}).get("product_id") if isinstance(manifest, dict) else None
        result["capture_time"] = (manifest or {}).get("capture_time") if isinstance(manifest, dict) else None
        result["pixel_digest"] = pixel_digest(img)
        result["heatmap_png_b64"] = heatmap_png_b64(img, content["heatmap"])
        event = {"channel": source, "product_id": result["product_id"],
                 "pixel_digest": result["pixel_digest"], "verdict": result["verdict"],
                 "action": result["action"], "integrity": integrity.status,
                 "content_type": content["type"], "score": content["manipulation_score"]}
        if live and integrity.ok and integrity.claim:  # what a restarted ground station needs to refuse a replay
            event.update({"capture_time": integrity.claim["capture_time"],
                          "claim_digest": integrity.claim["pixel_digest"],
                          "key_id": integrity.claim["key_id"], "seq": integrity.claim["seq"]})
        entry = self.ledger.append(event)
        result["ledger_hash"] = entry["hash"]
        return result


SIGNATURE_PROBLEMS = {"BAD_SIGNATURE", "UNKNOWN_KEY", "REVOKED_KEY", "WEAK_ALGORITHM", "CHAIN_BROKEN", "MALFORMED"}


def event_severity(entry: dict) -> str:
    """Display severity of an audit-log entry (computed, never stored): critical / warning / info."""
    verdict = entry.get("verdict")
    if verdict == "ALTERED_AFTER_CAPTURE":
        return "critical"
    if verdict in ("SUSPICIOUS", "SIGNED_BUT_SUSPICIOUS"):
        return "warning"
    return "info"


def summarize(entries: list[dict]) -> dict:
    """Counters for the dashboard overview, computed ONLY from the audit log (nothing is typed by hand)."""
    from collections import Counter
    verdicts = Counter(e.get("verdict") for e in entries)
    integrity = Counter(e.get("integrity") for e in entries)
    actions = Counter(e.get("action") for e in entries)
    return {
        "total": len(entries),
        "verified": verdicts["VERIFIED"],  # valid provenance and no content alarm (never called "authentic")
        "unverified_no_traces": verdicts["UNVERIFIED_NO_TRACES"],
        "suspicious": verdicts["SUSPICIOUS"] + verdicts["SIGNED_BUT_SUSPICIOUS"],
        "rejected": verdicts["ALTERED_AFTER_CAPTURE"],
        "invalid_signatures": sum(integrity[k] for k in SIGNATURE_PROBLEMS),
        "replays": integrity["REPLAY"],
        "manipulation_alerts": sum(1 for e in entries if e.get("content_type") not in (None, "authentic")),
        "released": actions["RELEASE"],
        "quarantined": actions["QUARANTINE"],
        "by_verdict": dict(verdicts),
        "by_integrity": dict(integrity),
        "by_channel": dict(Counter(e.get("channel") for e in entries)),
    }


def load_manifest(text_or_bytes) -> dict | None:
    if not text_or_bytes:
        return None
    data = json.loads(text_or_bytes)
    if data is not None and not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data
