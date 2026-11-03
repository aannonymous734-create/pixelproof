#!/usr/bin/env bash
# Attacker (Kali). It is a compromised ROUTER between the satellite subnet (10.56.1.0/24) and the ground subnet
# (10.56.2.0/24). Kali already ships the standard tools (tcpdump, iptables, ...); this script installs nothing
# offensive of our own, it only drops four small helper scripts. Everything runs ONLY inside the isolated lab.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get install -y --no-install-recommends iptables tcpdump || true

# Forward packets between the two subnets (also persisted; the Vagrantfile re-applies it on every boot).
echo "net.ipv4.ip_forward=1" >/etc/sysctl.d/99-pxp-forward.conf
sysctl -w net.ipv4.ip_forward=1

# (1) The tampering relay (simulation/attacker.py). Mode: passthrough | random | one attack name.
cat >/home/pxp/relay.sh <<'RUN'
#!/usr/bin/env bash
# Usage: relay.sh [mode] [rate]     e.g.  relay.sh random 0.7     or     relay.sh date_replace 1.0
[ "$(id -un)" = pxp ] || exec sudo -u pxp "$0" "$@"
set -eu
export PYTHONPATH=/opt/pixelproof
cd /opt/pixelproof
exec /home/pxp/venv/bin/python simulation/attacker.py \
    --listen 10.56.2.1:8081 --ground http://10.56.2.30:8000 \
    --mode "${1:-random}" --rate "${2:-0.7}" --log /home/pxp/runtime/attacker_log.jsonl
RUN

# (2) Transparent redirection. The satellite still sends to 10.56.2.30:8000; because this machine is its router,
#     an iptables DNAT silently sends that traffic to our relay instead. Run as the normal (vagrant) user: it uses sudo.
cat >/home/pxp/transparent_redirect.sh <<'RUN'
#!/usr/bin/env bash
set -eu
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A PREROUTING -p tcp -d 10.56.2.30 --dport 8000 -j DNAT --to-destination 10.56.2.1:8081
echo "Ground-bound port 8000 traffic is now redirected to the relay on 10.56.2.1:8081."
echo "Undo with:  /home/pxp/stop_redirect.sh"
RUN

cat >/home/pxp/stop_redirect.sh <<'RUN'
#!/usr/bin/env bash
set -eu
sudo iptables -t nat -F
echo "Redirect removed."
RUN

# (3) Evidence: capture the lab traffic on the satellite-side interface (found by its address).
cat >/home/pxp/capture.sh <<'RUN'
#!/usr/bin/env bash
# Usage: capture.sh [seconds]    writes /home/pxp/runtime/attack.pcap (run as the normal user; it uses sudo)
set -eu
IFACE=$(ip -o -4 addr show | awk '$4 ~ /^10\.56\.1\.1\// {print $2}')
echo "capturing on ${IFACE} for ${1:-120} s ..."
sudo timeout "${1:-120}" tcpdump -i "$IFACE" -w /home/pxp/runtime/attack.pcap tcp port 8000 or tcp port 8081 || true
sudo chown pxp:pxp /home/pxp/runtime/attack.pcap
echo "saved /home/pxp/runtime/attack.pcap"
RUN

chmod +x /home/pxp/relay.sh /home/pxp/transparent_redirect.sh /home/pxp/stop_redirect.sh /home/pxp/capture.sh
chown pxp:pxp /home/pxp/relay.sh /home/pxp/transparent_redirect.sh /home/pxp/stop_redirect.sh /home/pxp/capture.sh
echo "attacker ready. Helpers: relay.sh, transparent_redirect.sh, stop_redirect.sh, capture.sh (see vm/README.md)"
