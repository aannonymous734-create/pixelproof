"""simulation/score_demo.py: the machine-readable summary and the audit-log chain check."""
import json
import subprocess
import sys
from pathlib import Path

from pixelproof.ledger import Ledger

ROOT = Path(__file__).resolve().parents[1]

ROWS = [
    {"attack": "passthrough", "expected_integrity": "VERIFIED", "ground_integrity": "VERIFIED", "ground_verdict": "VERIFIED"},
    {"attack": "replay", "expected_integrity": "REPLAY", "ground_integrity": "REPLAY", "ground_verdict": "ALTERED_AFTER_CAPTURE"},
    {"attack": "pixel_inpaint", "expected_integrity": "PIXELS_ALTERED", "ground_integrity": "VERIFIED",  # missed
     "ground_verdict": "VERIFIED"},
    # the attacker edits the image and deletes the manifest: the integrity axis can only say NO_PROVENANCE
    {"attack": "strip_manifest", "expected_integrity": "NO_PROVENANCE", "ground_integrity": "NO_PROVENANCE",
     "ground_verdict": "UNVERIFIED_NO_TRACES"},
]


def score(tmp_path, tamper_ledger=False):
    log = tmp_path / "attacker_log.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in ROWS))
    ledger = tmp_path / "ledger.jsonl"
    led = Ledger(ledger)
    led.append({"verdict": "VERIFIED"})
    led.append({"verdict": "SUSPICIOUS"})
    if tamper_ledger:  # rewrite history: the second decision becomes VERIFIED
        ledger.write_text(ledger.read_text().replace("SUSPICIOUS", "VERIFIED"))
    out = tmp_path / "summary.json"
    subprocess.run([sys.executable, str(ROOT / "simulation" / "score_demo.py"), "--log", str(log),
                    "--ledger", str(ledger), "--json", str(out)], check=True, capture_output=True)
    return json.loads(out.read_text())


def test_cryptographic_attacks_and_genuine_messages_are_counted_separately(tmp_path):
    s = score(tmp_path)
    assert s["messages"] == 4
    assert s["crypto_attack_messages"] == 2 and s["crypto_attack_stopped"] == 1  # the inpaint was missed
    assert s["passthrough_messages"] == 1 and s["passthrough_correct"] == 1
    assert s["all_correct"] is False
    assert s["by_attack"]["pixel_inpaint"] == {"messages": 1, "correct": 0}


def test_a_stripped_manifest_is_never_counted_as_caught(tmp_path):
    """Without a manifest only the content detector can notice; the summary reports the outcome, not a catch."""
    s = score(tmp_path)
    assert s["provenance_stripped_messages"] == 1
    assert s["provenance_stripped_verdicts"] == {"UNVERIFIED_NO_TRACES": 1}
    assert s["crypto_attack_messages"] == 2  # strip_manifest is not among them


def test_untouched_ledger_chain_is_valid(tmp_path):
    s = score(tmp_path)
    assert s["ledger_entries"] == 2 and s["ledger_chain_valid"] is True


def test_edited_ledger_is_reported_broken(tmp_path):
    assert score(tmp_path, tamper_ledger=True)["ledger_chain_valid"] is False
