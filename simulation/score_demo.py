"""Score a simulation run: did the ground station answer correctly for every message the attacker handled?
  python simulation/score_demo.py --log runtime/attacker_log.jsonl
  python simulation/score_demo.py --log attacker_log.jsonl --ledger ledger.jsonl --json summary.json

--ledger  also verifies the ground station's hash-chained audit log (is the chain intact?)
--json    writes a machine-readable summary; scripts/check_numbers.py reads it for the report

Two kinds of attack are scored separately, on purpose:
  * CRYPTOGRAPHIC attacks (changed pixels, date, key, algorithm; replay): the signature layer must produce the
    expected integrity status. This is a hard guarantee.
  * PROVENANCE-STRIPPED messages (the attacker edits the image AND deletes the manifest): the integrity axis can
    only say NO_PROVENANCE. Whether the edit is noticed depends on the content detector, so it is reported as an
    outcome (see "ground verdict"), never as "caught".
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STRIPPED = "strip_manifest"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="runtime/attacker_log.jsonl")
    ap.add_argument("--ledger", help="ground-station audit log (jsonl) to verify")
    ap.add_argument("--json", help="write a summary here")
    a = ap.parse_args()
    rows = [json.loads(x) for x in open(a.log) if x.strip()]
    ok = Counter()
    tot = Counter()
    for r in rows:
        tot[r["attack"]] += 1
        ok[r["attack"]] += r["ground_integrity"] == r["expected_integrity"]
    print(f"{'attack':22s} {'messages':>8s} {'integrity status as expected':>30s}")
    for k in sorted(tot):
        print(f"{k:22s} {tot[k]:8d} {ok[k]:>23d} ({100 * ok[k] / tot[k]:.0f}%)")

    crypto = [k for k in tot if k not in ("passthrough", STRIPPED)]
    stripped_verdicts = Counter(r["ground_verdict"] for r in rows if r["attack"] == STRIPPED)
    summary = {
        "messages": len(rows),
        "passthrough_messages": tot.get("passthrough", 0),
        "passthrough_correct": ok.get("passthrough", 0),
        "crypto_attack_messages": sum(tot[k] for k in crypto),
        "crypto_attack_stopped": sum(ok[k] for k in crypto),
        "provenance_stripped_messages": tot.get(STRIPPED, 0),
        "provenance_stripped_verdicts": dict(stripped_verdicts),
        "all_correct": sum(ok.values()) == len(rows),
        "by_attack": {k: {"messages": tot[k], "correct": ok[k]} for k in sorted(tot)},
    }
    if a.ledger:
        from pixelproof.ledger import Ledger
        led = Ledger(a.ledger)
        valid, first_bad = led.verify()
        summary["ledger_entries"] = len(led.entries())
        summary["ledger_chain_valid"] = valid
        print(f"\nground audit log: {summary['ledger_entries']} entries, hash chain {'intact' if valid else f'BROKEN at {first_bad}'}")
    print(f"\ncryptographic attacks stopped with the expected status: {summary['crypto_attack_stopped']}/"
          f"{summary['crypto_attack_messages']}; genuine messages passed unharmed: "
          f"{summary['passthrough_correct']}/{summary['passthrough_messages']}")
    if summary["provenance_stripped_messages"]:
        print(f"provenance-stripped messages: {summary['provenance_stripped_messages']} "
              f"(outcome decided by the content detector, ground verdicts: {dict(stripped_verdicts)})")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(summary, indent=2))
        print(f"summary -> {a.json}")


if __name__ == "__main__":
    main()
