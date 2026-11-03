import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from tests.test_trust import textured

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "models" / "detector.joblib").exists(), reason="train the model first")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from pixelproof.provenance import demo_setup
    _, reg, src, proc = demo_setup(tmp_path / "keys")
    reg.save(tmp_path / "registry.json")
    monkeypatch.setenv("PIXELPROOF_REGISTRY", str(tmp_path / "registry.json"))
    monkeypatch.setenv("PIXELPROOF_LEDGER", str(tmp_path / "ledger.jsonl"))
    from fastapi.testclient import TestClient
    import pixelproof.api as api
    api._gs = None
    return TestClient(api.app), src


def png(img):
    b = io.BytesIO()
    Image.fromarray(img).save(b, format="PNG")
    return b.getvalue()


def test_downlink_genuine_then_replay(client):
    c, src = client
    img = textured(1)
    m = src.capture(img, "P1", "2026-09-01T10:00:00+00:00")
    body = {"image_png_b64": base64.b64encode(png(img)).decode(), "manifest": m}
    r1 = c.post("/api/v1/ingest", json=body).json()
    assert r1["integrity"]["status"] == "VERIFIED"
    r2 = c.post("/api/v1/ingest", json=body).json()
    assert r2["integrity"]["status"] == "REPLAY" and r2["action"] == "QUARANTINE"
    led = c.get("/api/v1/ledger").json()
    assert led["chain_valid"] and len(led["entries"]) == 2


def test_analyst_upload_with_altered_date(client):
    c, src = client
    img = textured(2)
    m = src.capture(img, "P2", "2026-09-01T10:00:00+00:00")
    m["capture_time"] = "2025-09-01T10:00:00+00:00"
    r = c.post("/api/v1/analyse", files={"image": ("p.png", png(img), "image/png"),
                                         "manifest": ("m.json", json.dumps(m), "application/json")}).json()
    assert r["integrity"]["status"] == "BAD_SIGNATURE" and r["verdict"] == "ALTERED_AFTER_CAPTURE"


def test_rejects_non_images(client):
    c, _ = client
    r = c.post("/api/v1/analyse", files={"image": ("x.png", b"not an image", "image/png")})
    assert r.status_code == 422


def test_rate_limit(client, monkeypatch):
    import pixelproof.api as api
    c, src = client
    monkeypatch.setattr(api, "RATE_PER_MIN", 5)
    api._hits.clear()
    img = textured(3)
    m = src.capture(img, "RL", "2026-09-01T10:00:00+00:00")
    body = {"image_png_b64": base64.b64encode(png(img)).decode(), "manifest": m}
    codes = [c.post("/api/v1/ingest", json=body).status_code for _ in range(7)]
    assert codes.count(429) >= 1 and codes[0] == 200  # first allowed, later ones throttled
