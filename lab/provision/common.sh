#!/usr/bin/env bash
# Shared provisioning: an unprivileged service user, a private virtualenv, pinned dependencies.
# Runs on every VM. No secrets are baked into any image.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends python3 python3-venv python3-pip tcpdump curl ca-certificates

# Unprivileged user that runs the lab services (never root).
id pxp >/dev/null 2>&1 || useradd -m -s /bin/bash pxp

# Private virtualenv with the exact pinned versions from the repo (CPU-only). PyTorch is NOT installed, so the
# detector runs in its features-only mode (its own calibrated threshold); the CNN is optional.
cp /tmp/requirements.txt /home/pxp/requirements.txt
chown pxp:pxp /home/pxp/requirements.txt
sudo -u pxp bash -eu <<'EOF'
python3 -m venv ~/venv
~/venv/bin/pip install --upgrade pip wheel >/dev/null
~/venv/bin/pip install -r ~/requirements.txt >/dev/null
EOF

# A writable working folder (the shared /opt/pixelproof is read-only).
install -d -o pxp -g pxp /home/pxp/runtime
echo "common provisioning done on $(hostname)"
