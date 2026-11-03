"""Write a pcap of traffic on one lab interface, as forensic evidence.

Run inside a namespace by the lab orchestrator:
  nsenter --net=/var/run/netns/pxl-satellite python3 lab/_sniff.py s0 600 evidence/satellite.pcap

Passive capture of the lab's OWN generated traffic on its OWN interface, so the report can show the
satellite only ever addressed the ground station (it never knew about the attacker). The pcap is written
both on normal timeout and when the orchestrator stops the sniffer (SIGTERM/SIGINT), so evidence is never
lost.
"""
import signal
import sys
import time

from scapy.all import AsyncSniffer, wrpcap

iface, seconds, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
# promisc + no BPF filter (some veth setups drop filtered capture); we filter to IP on read.
sniffer = AsyncSniffer(iface=iface, store=True, promisc=True)


def flush(*_):
    try:
        pkts = sniffer.stop()
    except Exception:
        pkts = []
    wrpcap(out, pkts or [])
    print(f"{len(pkts or [])} packets -> {out}", flush=True)
    sys.exit(0)


signal.signal(signal.SIGTERM, flush)
signal.signal(signal.SIGINT, flush)
sniffer.start()
time.sleep(seconds)
flush()
