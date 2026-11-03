"""Run attack scenarios against the real ground-station pipeline, on this machine, in memory.

  python -m simulation.run_attack --list                       # what can be run
  python -m simulation.run_attack --scenario image_tampering   # one scenario, with the full story
  python -m simulation.run_attack --all --n 20 --out results/attack_runs   # everything, saved as evidence

Nothing leaves this process: it signs synthetic traffic made from the bundled sample patches, attacks it, and
feeds it to the real ground-station code. The three-machine versions of the same attacks are in docs/VM_LAB.md.
Exit code 0 means every INTEGRITY scenario produced exactly the expected status; the content scenarios
(visual manipulation) report a measured detection rate instead, because a detector is never perfect.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pixelproof import lab  # noqa: E402


def show(r: dict, story: bool) -> None:
    kind = r["kind"]
    print(f"\n[{r['id']}] {r['title']}   (scenario: {r['scenario']})")
    print(f"  attacker does : {r['attacker_action']}")
    print(f"  why it fails  : {r['why_it_fails']}")
    if kind == "content":
        print(f"  expected      : the content detector flags the manipulation (not guaranteed)")
        print(f"  RESULT        : flagged {r['matches_expected']}/{r['n']}   "
              f"| false alarms on the {r['control']['n']} untouched originals: {r['control']['false_alarms']}")
    else:
        got = Counter(t["integrity_status"] for t in r["trials"])
        verdicts = Counter(t["verdict"] for t in r["trials"])
        ok = "PASS" if r["matches_expected"] == r["n"] else "FAIL"
        print(f"  expected      : integrity = {r['expected']}")
        print(f"  RESULT        : {ok}  integrity = {dict(got)}  verdict = {dict(verdicts)}  "
              f"({r['matches_expected']}/{r['n']} as expected)")
        print(f"  control       : {r['control']['verified']}/{r['n']} untouched products were VERIFIED")
    print(f"  audit log     : {r['audit_log']['entries']} entries, hash chain valid = {r['audit_log']['chain_valid']}")
    if story:
        t = r["trials"][0]
        print(f"  evidence      : signed digest {t.get('signed_digest')}  |  received digest {t.get('received_digest')}")
        for reason in t["reasons"]:
            print(f"                  ground says: {reason}")
        print("  timeline of trial 1:")
        for e in t["timeline"]:
            extra = {k: v for k, v in e.items() if k not in ("t_ms", "actor", "event")}
            print(f"    {e['t_ms']:8.1f} ms  {e['actor']:9s} {e['event']}  {extra if extra else ''}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list the scenarios and exit")
    ap.add_argument("--scenario", choices=list(lab.SCENARIOS), help="run one scenario")
    ap.add_argument("--all", action="store_true", help="run every scenario")
    ap.add_argument("--n", type=int, default=None, help="trials per scenario (default 1, or 20 with --all)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--samples", default=None, help="folder of patches (default: samples/authentic)")
    ap.add_argument("--out", default=None, help="folder to write the evidence JSON files into")
    a = ap.parse_args(argv)

    if a.list:
        for s in lab.list_scenarios():
            print(f"{s['id']:3s} {s['name']:28s} expected: {s['expected']:16s} {s['title']}")
        return 0
    if not a.scenario and not a.all:
        ap.error("choose --scenario NAME, --all or --list")

    names = list(lab.SCENARIOS) if a.all else [a.scenario]
    n = a.n if a.n is not None else (20 if a.all else 1)
    results = []
    try:
        for name in names:
            r = lab.run_scenario(name, n=n, seed=a.seed, samples_dir=a.samples)
            results.append(r)
            show(r, story=not a.all)
    except lab.LabError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    integrity = [r for r in results if r["kind"] != "content" and r["kind"] != "compromised_source"]
    all_ok = all(r["matches_expected"] == r["n"] for r in integrity)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for r in results:
            (out / f"{r['scenario']}.json").write_text(json.dumps(r, indent=2))
        if a.all:
            summary = {
                "n_per_scenario": n, "seed": a.seed, "environment": results[0]["environment"],
                "all_integrity_scenarios_as_expected": all_ok,
                "scenarios": {r["scenario"]: {
                    "id": r["id"], "title": r["title"], "kind": r["kind"], "expected": r["expected"], "n": r["n"],
                    "matches_expected": r["matches_expected"], "rate": r["rate"], "control": r["control"],
                    "content_flagged": sum(t["content"]["flagged"] for t in r["trials"]),
                    "audit_chain_valid": r["audit_log"]["chain_valid"]} for r in results},
            }
            (out / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"\nevidence written to {out}/")
    if a.all:
        print(f"\nAll integrity scenarios produced exactly the expected status: {all_ok}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
