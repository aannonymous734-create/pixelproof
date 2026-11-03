"""The obvious command `python scripts/train.py` must never silently replace the shipped model."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "detector.joblib"
pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="no shipped model")


def test_default_training_command_refuses_to_overwrite_the_shipped_model():
    before = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "train.py")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0
    assert "refusing to overwrite" in r.stderr and "--overwrite" in r.stderr
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == before  # untouched


def test_default_epochs_match_the_shipped_model():
    """The model card and train_log of the shipped model say 8 epochs; the script default must agree."""
    text = (ROOT / "scripts" / "train.py").read_text()
    assert '"--epochs", type=int, default=8' in text
