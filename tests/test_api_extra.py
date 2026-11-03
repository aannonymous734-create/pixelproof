"""Dashboard endpoints: stats, station identity, audit severity, and the opt-in attack lab."""
import base64
import json

import pytest

from pixelproof.service import event_severity, summarize
from tests.test_api import client, png  # noqa: F401  (client is a pytest fixture)
from tests.test_trust import textured


def _ingest(c, src, pid, seed, tamper=False):
    img = textured(seed)
    m = src.capture(img, pid, "2026-09-01T10:00:00+00:00")
    if tamper:
        m["capture_time"] = "2025-01-01T00:00:00+00:00"  # break the signature
    return c.post("/api/v1/ingest", json={"image_png_b64": base64.b64encode(png(img)).decode(), "manifest": m}).json()


def test_stats_are_computed_from_the_audit_log(client):
    c, src = client
    assert c.get("/api/v1/stats").json()["total"] == 0  # an empty station reports zeros, not invented numbers
    _ingest(c, src, "S1", 10)
    _ingest(c, src, "S2", 11, tamper=True)
    s = c.get("/api/v1/stats").json()
    assert s["total"] == 2 and s["verified"] + s["suspicious"] == 1
    assert s["rejected"] == 1 and s["invalid_signatures"] == 1 and s["audit_chain_valid"] is True
    assert s["quarantined"] >= 1


def test_summarize_counts_each_category():
    entries = [
        {"verdict": "VERIFIED", "integrity": "VERIFIED", "action": "RELEASE", "content_type": "authentic"},
        {"verdict": "ALTERED_AFTER_CAPTURE", "integrity": "UNKNOWN_KEY", "action": "QUARANTINE", "content_type": "authentic"},
        {"verdict": "SUSPICIOUS", "integrity": "NO_PROVENANCE", "action": "QUARANTINE", "content_type": "copy_move"},
        {"verdict": "ALTERED_AFTER_CAPTURE", "integrity": "REPLAY", "action": "QUARANTINE", "content_type": "authentic"},
    ]
    s = summarize(entries)
    assert (s["total"], s["verified"], s["suspicious"], s["rejected"]) == (4, 1, 1, 2)
    assert (s["invalid_signatures"], s["replays"], s["manipulation_alerts"]) == (1, 1, 1)


def test_severity_levels():
    assert event_severity({"verdict": "ALTERED_AFTER_CAPTURE"}) == "critical"
    assert event_severity({"verdict": "SIGNED_BUT_SUSPICIOUS"}) == "warning"
    assert event_severity({"verdict": "VERIFIED"}) == "info"


def test_ledger_entries_carry_a_severity(client):
    c, src = client
    _ingest(c, src, "SEV1", 12, tamper=True)
    assert c.get("/api/v1/ledger").json()["entries"][0]["severity"] == "critical"


def test_station_exposes_public_fingerprints_and_never_secrets(client):
    c, src = client
    _ingest(c, src, "ST1", 13)
    body = c.get("/api/v1/station")
    st = body.json()
    ids = {i["key_id"]: i for i in st["identities"]}
    assert {"sat-01", "proc-01"} <= set(ids) and len(ids["sat-01"]["fingerprint_sha256"]) == 64
    assert st["downlinks_received"] == 1 and st["last_downlink"]["product_id"] == "ST1"
    assert st["trust_policy"]["hash"] == "sha256" and st["trust_policy"]["signature"] == "ed25519"
    assert len(st["detector"]["model_sha256"]) == 64 and st["detector"]["model_card_match"] is True
    text = body.text
    assert "PRIVATE" not in text and "BEGIN" not in text and ".pem" not in text and "\\" not in text


def test_lab_is_disabled_by_default(client, monkeypatch):
    c, _ = client
    monkeypatch.delenv("PIXELPROOF_LAB_MODE", raising=False)
    listing = c.get("/api/v1/lab/scenarios").json()
    assert listing["enabled"] is False and len(listing["scenarios"]) >= 10
    r = c.post("/api/v1/lab/run", json={"scenario": "image_tampering"})
    assert r.status_code == 403 and "PIXELPROOF_LAB_MODE" in r.json()["detail"]


def test_lab_runs_when_enabled_and_does_not_touch_the_real_audit_log(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("PIXELPROOF_LAB_MODE", "1")
    r = c.post("/api/v1/lab/run", json={"scenario": "manifest_tampering", "n": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["matches_expected"] == 2 and body["trials"][0]["integrity_status"] == "BAD_SIGNATURE"
    assert "PRIVATE" not in r.text and "BEGIN" not in r.text
    assert c.get("/api/v1/stats").json()["total"] == 0  # the real station's log is untouched
    assert c.get("/api/v1/lab/runs").json()[0]["scenario"] == "manifest_tampering"


def test_lab_rejects_unknown_scenarios_and_caps_trials(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("PIXELPROOF_LAB_MODE", "1")
    assert c.post("/api/v1/lab/run", json={"scenario": "../../etc/passwd"}).status_code == 422
    r = c.post("/api/v1/lab/run", json={"scenario": "replay", "n": 10_000}).json()
    assert r["n"] == 50  # capped


def test_internal_errors_do_not_leak_a_stack_trace(client, monkeypatch):
    import pixelproof.api as api
    from fastapi.testclient import TestClient
    c, src = client

    def boom(*a, **k):
        raise RuntimeError("secret internal detail /home/user/app.py")
    monkeypatch.setattr(api.gs(), "process", boom)
    quiet = TestClient(api.app, raise_server_exceptions=False)
    img = textured(14)
    r = quiet.post("/api/v1/ingest", json={"image_png_b64": base64.b64encode(png(img)).decode(),
                                           "manifest": src.capture(img, "X", "2026-09-01T10:00:00+00:00")})
    assert r.status_code == 500
    assert "secret internal detail" not in r.text and "Traceback" not in r.text
