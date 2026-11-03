#!/usr/bin/env bash
# Ground station: verifier + detector + dashboard + audit log as a systemd service.
# It receives only the PUBLIC key registry. The attack lab (PIXELPROOF_LAB_MODE) is deliberately NOT enabled:
# on this machine attacks come from the attacker VM, never from the dashboard.
set -euo pipefail

# The model ships with the repository (models/detector.joblib).
if [ ! -f /opt/pixelproof/models/detector.joblib ]; then
  echo "WARNING: /opt/pixelproof/models/detector.joblib is missing from the shared folder." >&2
fi

cat >/etc/systemd/system/pixelproof-ground.service <<'UNIT'
[Unit]
Description=PixelProof ground station
After=network-online.target

[Service]
User=pxp
WorkingDirectory=/opt/pixelproof
Environment=PYTHONPATH=/opt/pixelproof
Environment=PIXELPROOF_MODEL=/opt/pixelproof/models/detector.joblib
Environment=PIXELPROOF_REGISTRY=/home/pxp/runtime/registry.json
Environment=PIXELPROOF_LEDGER=/home/pxp/runtime/ledger.jsonl
# 0.0.0.0 so that BOTH the lab network and the host's forwarded port (127.0.0.1:8000, via the NAT adapter) reach it.
# Nothing is exposed to the internet: the lab networks are internal and NAT is outbound-only.
ExecStart=/home/pxp/venv/bin/uvicorn pixelproof.api:app --host 0.0.0.0 --port 8000
Restart=on-failure
# Hardening. ProtectHome=read-only (not "true"): the service's own virtualenv lives under /home/pxp, and with
# ProtectHome=true the executable would be invisible and the service would not start.
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths=/home/pxp/runtime

[Install]
WantedBy=multi-user.target
UNIT

# Fetch the satellite's PUBLIC registry (the operator then compares fingerprints by eye: out-of-band trust).
cat >/home/pxp/fetch_registry.sh <<'RUN'
#!/usr/bin/env bash
# Fetches the public registry from the satellite and prints its fingerprints. COMPARE them with the ones printed
# on the satellite VM before you trust it: a key that is not confirmed out of band could be an attacker's.
[ "$(id -un)" = pxp ] || exec sudo -u pxp "$0" "$@"
set -eu
export PYTHONPATH=/opt/pixelproof
curl -fsS http://10.56.1.10:9000/registry.json -o /home/pxp/runtime/registry.json.new
/home/pxp/venv/bin/python -m pixelproof.cli fingerprints --registry /home/pxp/runtime/registry.json.new
echo
read -r -p "Do these fingerprints match the ones on the satellite VM? Type yes to trust them: " ok
if [ "$ok" = yes ]; then
  mv /home/pxp/runtime/registry.json.new /home/pxp/runtime/registry.json
  echo "Registry installed. The ground station now trusts these keys."
else
  rm -f /home/pxp/runtime/registry.json.new
  echo "Not installed."
  exit 1
fi
RUN
chmod +x /home/pxp/fetch_registry.sh
chown pxp:pxp /home/pxp/fetch_registry.sh

systemctl daemon-reload
systemctl enable --now pixelproof-ground.service
echo "ground station is running on port 8000 (it trusts no key until you run /home/pxp/fetch_registry.sh)"
