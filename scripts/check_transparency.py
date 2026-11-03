"""Prove, from the satellite's OWN packet capture, that the man-in-the-middle was transparent.

  python scripts/check_transparency.py [--capture results/docker_mitm/satellite_capture.txt]
                                       [--satellite 172.28.1.10] [--ground 172.28.2.30]
                                       [--attacker 172.28.1.1,172.28.2.1] [--out results/docker_mitm/transparency.json]

The satellite was configured with one address only (the ground station). If the attacker is truly transparent,
then in every IP header the satellite sent or received, the other end is the ground station's address: the
satellite never addressed the attacker, and replies even appear to come from the ground station (the attacker's
redirect rewrites them back). `docker-compose.mitm.yml` writes the capture with tcpdump inside the satellite container.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

LINE = re.compile(r"\bIP (\d+\.\d+\.\d+\.\d+)\.(\d+) > (\d+\.\d+\.\d+\.\d+)\.(\d+)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", default="results/docker_mitm/satellite_capture.txt")
    ap.add_argument("--satellite", default="172.28.1.10")
    ap.add_argument("--ground", default="172.28.2.30")
    ap.add_argument("--attacker", default="172.28.1.1,172.28.2.1")
    ap.add_argument("--out", default="results/docker_mitm/transparency.json")
    a = ap.parse_args()
    path = Path(a.capture)
    if not path.exists():
        print(f"{path} not found. Run: docker compose -f docker-compose.mitm.yml up --build "
              f"--abort-on-container-exit --exit-code-from satellite", file=sys.stderr)
        return 2
    attackers = set(a.attacker.split(","))
    peers: Counter = Counter()
    packets = 0
    for line in path.read_text(errors="ignore").splitlines():
        m = LINE.search(line)
        if not m:
            continue
        src, dst = m.group(1), m.group(3)
        if a.satellite not in (src, dst):
            continue
        packets += 1
        peers[dst if src == a.satellite else src] += 1
    seen_attacker = sorted(attackers & set(peers))
    result = {
        "satellite_ip": a.satellite,
        "satellite_configured_target": f"http://{a.ground}:8000 (the ground station only; the attacker is never named)",
        "ip_packets_captured_on_the_satellite": packets,
        "peers_in_ip_headers": dict(peers),
        "attacker_address_in_any_ip_header": bool(seen_attacker),
        "transparent": packets > 0 and set(peers) == {a.ground},
        "note": "Replies appear to come from the ground station address although the attacker's relay answered: "
                "the redirect rewrites the source back. The satellite cannot tell.",
    }
    Path(a.out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if result["transparent"] else 1


if __name__ == "__main__":
    sys.exit(main())
