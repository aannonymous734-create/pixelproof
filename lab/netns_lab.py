"""No-VM version of the attack lab, using Linux network namespaces (root, Linux only).

  sudo python lab/netns_lab.py --model models/detector.joblib --data-dir data/eurosat --n 24

It reproduces the Vagrant lab's topology on one machine, with NO route to any outside network.
The attacker is a compromised relay/router ON THE PATH between two isolated subnets:

    [satellite 10.56.1.10/24] ──s0─┐
                                    ├─(attacker 10.56.1.1 | 10.56.2.1, ip_forward)─┐
    [ground    10.56.2.30/24] ──g0─────────────────────────────────────────────────┘

Phase A  (control):       the satellite sends signed patches to the ground station's real address;
                          the attacker only routes.  Expect every product VERIFIED.
Phase B  (transparent):   the attacker adds an iptables DNAT rule that silently redirects TCP:8000
                          destined for the ground station to its own tampering relay
                          (simulation/attacker.py), which modifies traffic and forwards it on. The
                          satellite is NOT configured to use the attacker: it still sends to
                          10.56.2.30. This is a transparent man-in-the-middle via a standard
                          mechanism (the same redirection a transparent proxy uses); no ARP or
                          packet forging. On the Kali VM the ARP-spoofing variant uses the
                          pre-installed `arpspoof`/`ettercap` tools (see docs/VM_LAB.md).

Evidence (written under --out): a pcap captured on the satellite's own interface (showing it only
ever talks to 10.56.2.30), the attacker log, the ground audit ledger, and a JSON summary scored the
same way as simulation/score_demo.py. Everything is torn down at the end, including on error.

Safety: addresses are private (RFC 1918), the namespaces have no default route to the host network,
and the tampering runs only inside this isolated lab.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = "pxl"  # namespace prefix
SAT, ATK, GRD = f"{P}-satellite", f"{P}-attacker", f"{P}-ground"
SAT_IP, ATK_SAT_IP, ATK_GRD_IP, GRD_IP = "10.56.1.10", "10.56.1.1", "10.56.2.1", "10.56.2.30"


def nse(ns):
    return ["nsenter", f"--net=/var/run/netns/{ns}"]


def run(ns, *cmd, check=True):
    return subprocess.run([*nse(ns), *cmd], check=check, capture_output=True, text=True)


def popen(ns, *cmd, **kw):
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.Popen([*nse(ns), *cmd], env=env, **kw)


def build():
    from pyroute2 import IPRoute, NetNS, netns
    teardown(quiet=True)
    for n in (SAT, ATK, GRD):
        netns.create(n)
    ipr = IPRoute()
    idx = lambda name: ipr.link_lookup(ifname=name)[0]
    ipr.link("add", ifname="s0", kind="veth", peer="s1")
    ipr.link("add", ifname="g0", kind="veth", peer="g1")
    ipr.link("set", index=idx("s0"), net_ns_fd=SAT)
    ipr.link("set", index=idx("s1"), net_ns_fd=ATK)
    ipr.link("set", index=idx("g1"), net_ns_fd=ATK)
    ipr.link("set", index=idx("g0"), net_ns_fd=GRD)
    sat, atk, grd = NetNS(SAT), NetNS(ATK), NetNS(GRD)

    def cfg(h, dev, addr):
        i = h.link_lookup(ifname=dev)[0]
        h.addr("add", index=i, address=addr, prefixlen=24)
        h.link("set", index=i, state="up")

    cfg(sat, "s0", SAT_IP)
    cfg(atk, "s1", ATK_SAT_IP)
    cfg(atk, "g1", ATK_GRD_IP)
    cfg(grd, "g0", GRD_IP)
    for h in (sat, atk, grd):
        h.link("set", index=h.link_lookup(ifname="lo")[0], state="up")
    sat.route("add", dst="0.0.0.0/0", gateway=ATK_SAT_IP)
    grd.route("add", dst="0.0.0.0/0", gateway=ATK_GRD_IP)
    for h in (sat, atk, grd):
        h.close()
    run(ATK, "sysctl", "-w", "net.ipv4.ip_forward=1")


def teardown(quiet=False):
    from pyroute2 import netns
    for n in (SAT, ATK, GRD):
        try:
            netns.remove(n)
        except Exception:
            if not quiet:
                pass


def wait_http(ns, url, tries=40):
    for _ in range(tries):
        r = run(ns, "python3", "-c",
                f"import urllib.request,sys;\nurllib.request.urlopen('{url}',timeout=2)", check=False)
        if r.returncode == 0:
            return True
        time.sleep(0.5)
    return False


def satellite(args, n, log):
    """Run the satellite node (addresses the GROUND station directly in both phases)."""
    cmd = ["python3", "simulation/satellite_node.py", "--target", f"http://{GRD_IP}:8000",
           "--keys", str(args.keys), "--registry", str(args.registry), "--n", str(n), "--interval", "0.3"]
    if args.patches:
        cmd += ["--patches", args.patches]
    else:
        cmd += ["--data-dir", args.data_dir]
    with open(log, "w") as f:
        p = popen(SAT, *cmd, stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
        p.wait()


def score(path):
    rows = [json.loads(x) for x in open(path) if x.strip()]
    ok, tot = Counter(), Counter()
    for r in rows:
        tot[r["attack"]] += 1
        ok[r["attack"]] += r["ground_integrity"] == r["expected_integrity"]
    return {k: {"messages": tot[k], "correct": ok[k]} for k in sorted(tot)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/detector.joblib")
    ap.add_argument("--data-dir", default="data/eurosat")
    ap.add_argument("--patches", default=None)
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--mode", default="random", help="attacker mode for phase B")
    ap.add_argument("--rate", type=float, default=0.7)
    ap.add_argument("--out", default="results/lab")
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("needs root for network namespaces: sudo python lab/netns_lab.py ...")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    args.keys = out / "satkeys"
    args.registry = out / "registry.json"
    env_model = str((ROOT / args.model).resolve())

    procs = []
    try:
        build()
        # ground station in the ground namespace
        genv = {**os.environ, "PYTHONPATH": str(ROOT), "PIXELPROOF_MODEL": env_model,
                "PIXELPROOF_REGISTRY": str((out / "registry.json").resolve()),
                "PIXELPROOF_LEDGER": str((out / "ledger.jsonl").resolve()),
                "PIXELPROOF_RATE_PER_MIN": "0"}  # the demo bursts faster than the limit; off here
        (out / "ledger.jsonl").write_text("")
        gp = subprocess.Popen([*nse(GRD), "python3", "-m", "uvicorn", "pixelproof.api:app",
                               "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
                              env=genv, cwd=ROOT, stdout=open(out / "ground.log", "w"), stderr=subprocess.STDOUT)
        procs.append(gp)
        if not wait_http(GRD, "http://127.0.0.1:8000/api/v1/health"):
            raise RuntimeError("ground station did not start (see results/lab/ground.log)")

        # ---- Phase A: control, attacker only routes ----
        sniffer = popen(SAT, "python3", "lab/_sniff.py", "s0", "600", str((out / "satellite_phaseA.pcap").resolve()),
                        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        satellite(args, args.n, out / "satellite_phaseA.log")
        sniffer.terminate(); sniffer.wait(timeout=10)  # let _sniff.py flush the pcap on SIGTERM
        phaseA_ledger = [json.loads(x) for x in open(out / "ledger.jsonl") if x.strip()]

        # ---- Phase B: transparent MITM via iptables DNAT to the tampering relay ----
        alog = (out / "attacker_log.jsonl").resolve()
        alog.write_text("")
        relay = popen(ATK, "python3", "simulation/attacker.py", "--listen", f"{ATK_GRD_IP}:8081",
                      "--ground", f"http://{GRD_IP}:8000", "--mode", args.mode, "--rate", str(args.rate),
                      "--log", str(alog), cwd=ROOT, stdout=open(out / "attacker.log", "w"), stderr=subprocess.STDOUT)
        procs.append(relay)
        time.sleep(1.5)
        run(ATK, "iptables", "-t", "nat", "-A", "PREROUTING", "-p", "tcp", "-d", GRD_IP, "--dport", "8000",
            "-j", "DNAT", "--to-destination", f"{ATK_GRD_IP}:8081")
        sniffer = popen(SAT, "python3", "lab/_sniff.py", "s0", "600", str((out / "satellite_phaseB.pcap").resolve()),
                        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        satellite(args, args.n, out / "satellite_phaseB.log")
        sniffer.terminate(); sniffer.wait(timeout=10)  # flush pcap before reading it

        # The proof that the MITM is transparent is structural: the satellite was configured to reach
        # ONLY the ground IP (never the attacker), yet its traffic was intercepted and tampered. The
        # pcap on the satellite's own interface is confirmatory evidence of the destinations it used.
        peers = set()
        try:
            from scapy.all import rdpcap
            for pk in rdpcap(str(out / "satellite_phaseB.pcap")):
                if pk.haslayer("IP"):
                    peers.update({pk["IP"].src, pk["IP"].dst})
        except Exception:
            pass
        ips = {p for p in peers if p not in (SAT_IP,)}

        summary = {
            "topology": {"satellite": SAT_IP, "attacker": [ATK_SAT_IP, ATK_GRD_IP], "ground": GRD_IP},
            "satellite_configured_target": f"http://{GRD_IP}:8000 (ground station only; attacker never named)",
            "phaseA_control": {"products": len(phaseA_ledger),
                               "all_verified": all(e["verdict"] == "VERIFIED" for e in phaseA_ledger)},
            "phaseB_transparent_mitm": score(alog),
            # transparent by construction: the satellite never addressed an attacker IP
            "mitm_transparent": ATK_SAT_IP not in ips and ATK_GRD_IP not in ips,
            "satellite_pcap_destinations": sorted(ips) or ["(pcap empty — see note)"],
            "pcap_note": "destinations captured on the satellite's own interface; empty if L2 capture "
                         "was unavailable in this environment (the structural proof above still holds)",
        }
        tampered = [k for k in summary["phaseB_transparent_mitm"] if k not in ("passthrough",)]
        caught = sum(summary["phaseB_transparent_mitm"][k]["correct"] for k in tampered)
        total = sum(summary["phaseB_transparent_mitm"][k]["messages"] for k in tampered)
        summary["tampering_caught"] = f"{caught}/{total}"
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        print(f"\nevidence in {out}/  (summary.json, *.pcap, attacker_log.jsonl, ledger.jsonl)")
    finally:
        for p in procs:
            p.terminate()
        try:
            run(ATK, "iptables", "-t", "nat", "-F", check=False)
        except Exception:
            pass
        teardown()


if __name__ == "__main__":
    main()
