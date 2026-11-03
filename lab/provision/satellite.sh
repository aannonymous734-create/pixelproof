#!/usr/bin/env bash
# Satellite: creates its OWN signing keys (the private keys never leave this VM) and downlinks signed patches.
# The satellite only ever addresses the GROUND station (10.56.2.30). It is not configured to use the attacker.
set -euo pipefail

install -d -o pxp -g pxp -m 700 /home/pxp/keys
install -d -o pxp -g pxp /home/pxp/runtime/public

# -- 1. Create the keys and publish ONLY the public registry, for a short time, so the ground operator can fetch it.
cat >/home/pxp/publish_registry.sh <<'RUN'
#!/usr/bin/env bash
# Creates the satellite keys (once), prints the public-key fingerprints, and serves the PUBLIC registry on
# 10.56.1.10:9000 for 5 minutes. Run as the user pxp (this script re-runs itself as pxp if needed).
[ "$(id -un)" = pxp ] || exec sudo -u pxp "$0" "$@"
set -eu
export PYTHONPATH=/opt/pixelproof
/home/pxp/venv/bin/python -m pixelproof.cli keys-init --keys /home/pxp/keys --registry /home/pxp/runtime/registry.json
cp /home/pxp/runtime/registry.json /home/pxp/runtime/public/registry.json
echo
echo "Fingerprints of the satellite's PUBLIC keys (write the first 16 characters down):"
/home/pxp/venv/bin/python -m pixelproof.cli fingerprints --registry /home/pxp/runtime/registry.json
echo
echo "Serving ONLY the public registry on http://10.56.1.10:9000/registry.json for 5 minutes (Ctrl+C to stop)."
exec timeout 300 python3 -m http.server 9000 --bind 10.56.1.10 --directory /home/pxp/runtime/public
RUN

# -- 2. Downlink N signed patches to the ground station.
cat >/home/pxp/downlink.sh <<'RUN'
#!/usr/bin/env bash
# Usage: downlink.sh [N]     (default 40 patches, one per second)
[ "$(id -un)" = pxp ] || exec sudo -u pxp "$0" "$@"
set -eu
export PYTHONPATH=/opt/pixelproof
cd /opt/pixelproof
/home/pxp/venv/bin/python simulation/satellite_node.py \
    --target http://10.56.2.30:8000 \
    --keys /home/pxp/keys \
    --registry /home/pxp/runtime/registry.json \
    --patches /opt/pixelproof/samples/authentic \
    --n "${1:-40}" --interval 1.0
RUN

chmod +x /home/pxp/publish_registry.sh /home/pxp/downlink.sh
chown pxp:pxp /home/pxp/publish_registry.sh /home/pxp/downlink.sh
echo "satellite ready. Next: /home/pxp/publish_registry.sh  (see vm/README.md STEP 4)"
