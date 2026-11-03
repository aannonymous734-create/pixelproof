"""The attack-scenario engine and the persistent replay protection. Uses the bundled sample patches."""
import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from tests.test_trust import textured

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "models" / "detector.joblib").exists(), reason="train the model first")

from pixelproof import lab  # noqa: E402

INTEGRITY = [n for n, s in lab.SCENARIOS.items() if s["kind"] in ("integrity", "replay")]


@pytest.mark.parametrize("name", INTEGRITY)
def test_every_integrity_attack_is_caught_with_the_expected_status(name):
    r = lab.run_scenario(name, n=3)
    assert r["matches_expected"] == r["n"] == 3, [t["integrity_status"] for t in r["trials"]]
    assert r["control"]["verified"] == 3  # an untouched product is VERIFIED
    assert r["audit_log"]["chain_valid"]
    assert all(t["action"] == "QUARANTINE" for t in r["trials"])


def test_replay_first_delivery_is_accepted_then_the_resend_is_rejected():
    t = lab.run_scenario("replay", n=1)["trials"][0]
    assert t["first_delivery"] == "VERIFIED" and t["integrity_status"] == "REPLAY"


def test_signature_does_not_prove_the_picture_is_true():
    """Attack F: a fake signed before it reaches the signer passes the integrity axis."""
    r = lab.run_scenario("compromised_source", n=3)
    assert r["matches_expected"] == 3  # integrity VERIFIED for every signed fake
    assert {t["integrity_status"] for t in r["trials"]} == {"VERIFIED"}
    # the verdict is VERIFIED only if the detector missed it; otherwise the two axes disagree
    assert {t["verdict"] for t in r["trials"]} <= {"VERIFIED", "SIGNED_BUT_SUSPICIOUS"}


def test_visual_scenarios_report_a_measured_rate_not_a_guarantee():
    r = lab.run_scenario("visual_resample", n=4)
    assert 0 <= r["matches_expected"] <= r["n"]
    assert {t["integrity_status"] for t in r["trials"]} == {"NO_PROVENANCE"}
    assert "false_alarms" in r["control"]


def test_unknown_scenario_and_missing_samples_are_clean_errors(tmp_path):
    with pytest.raises(lab.LabError):
        lab.run_scenario("not_a_scenario")
    with pytest.raises(lab.LabError):
        lab.run_scenario("replay", samples_dir=tmp_path)


def test_result_never_contains_key_material():
    text = json.dumps(lab.run_scenario("manifest_tampering", n=1))
    assert "PRIVATE KEY" not in text and "BEGIN" not in text


# ---------------------------------------------------------------- replay protection survives a restart
def _png(img):
    b = io.BytesIO()
    Image.fromarray(img).save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


def test_replay_is_still_rejected_after_the_ground_station_restarts(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    import pixelproof.api as api
    from pixelproof.provenance import demo_setup
    _, reg, src, _proc = demo_setup(tmp_path / "keys")
    reg.save(tmp_path / "registry.json")
    monkeypatch.setenv("PIXELPROOF_REGISTRY", str(tmp_path / "registry.json"))
    monkeypatch.setenv("PIXELPROOF_LEDGER", str(tmp_path / "ledger.jsonl"))
    img = textured(5)
    body = {"image_png_b64": _png(img), "manifest": src.capture(img, "RESTART-1", "2026-09-01T10:00:00+00:00")}

    api._gs = None
    c = TestClient(api.app)
    assert c.post("/api/v1/ingest", json=body).json()["integrity"]["status"] == "VERIFIED"

    api._gs = None  # the process restarts: all in-memory state is gone
    c = TestClient(api.app)
    again = c.post("/api/v1/ingest", json=body).json()
    assert again["integrity"]["status"] == "REPLAY" and again["action"] == "QUARANTINE"
