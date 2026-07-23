#!/usr/bin/env bash
# Install (or refresh) a persistent SSH reverse tunnel that publishes the local
# provider gateway (:8443) on a public host (typically the Abakos validator).
#
# TLS stays end-to-end to provider-services. Do NOT put Caddy/nginx in front.
#
# Usage (on the provider VM):
#   TUNNEL_HOST=217.154.169.211 \
#   TUNNEL_USER=root \
#   bash scripts/tunnel-remote.sh
#
# Optional:
#   TUNNEL_KEY=~/.ssh/abakos_tunnel
#   LOCAL_PORT=8443
#   REMOTE_PORT=8443
#   UNIT_NAME=abakos-provider-tunnel
#
# Validator sshd must allow remote binds, e.g. drop-in:
#   /etc/ssh/sshd_config.d/99-abakos-tunnel.conf
#     AllowTcpForwarding yes
#     GatewayPorts clientspecified
# Then: sshd -t && systemctl reload ssh
#
# Also open inbound TCP REMOTE_PORT on the cloud firewall (IONOS panel) for the
# public host. Host iptables alone is not enough if the edge blocks the port.
set -euo pipefail

TUNNEL_HOST="${TUNNEL_HOST:?set TUNNEL_HOST to the public SSH target (validator IP/DNS)}"
TUNNEL_USER="${TUNNEL_USER:-root}"
TUNNEL_KEY="${TUNNEL_KEY:-$HOME/.ssh/abakos_tunnel}"
LOCAL_PORT="${LOCAL_PORT:-8443}"
REMOTE_PORT="${REMOTE_PORT:-8443}"
UNIT_NAME="${UNIT_NAME:-abakos-provider-tunnel}"
UNIT_PATH="/etc/systemd/system/${UNIT_NAME}.service"

echo "== tunnel target: ${TUNNEL_USER}@${TUNNEL_HOST}  remote 0.0.0.0:${REMOTE_PORT} -> 127.0.0.1:${LOCAL_PORT} =="

echo "== [1/4] tunnel key =="
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
if [ ! -f "$TUNNEL_KEY" ]; then
  ssh-keygen -t ed25519 -f "$TUNNEL_KEY" -N "" -C "abakos-provider-tunnel"
fi
chmod 600 "$TUNNEL_KEY"
chmod 644 "${TUNNEL_KEY}.pub"
echo "public key (install on ${TUNNEL_USER}@${TUNNEL_HOST} authorized_keys with comment abakos-provider-tunnel):"
cat "${TUNNEL_KEY}.pub"

echo "== [2/4] test SSH =="
ssh -i "$TUNNEL_KEY" \
  -o StrictHostKeyChecking=accept-new \
  -o BatchMode=yes \
  -o ConnectTimeout=15 \
  "${TUNNEL_USER}@${TUNNEL_HOST}" hostname

echo "== [3/4] systemd unit ${UNIT_PATH} =="
TMP_UNIT="$(mktemp)"
cat > "$TMP_UNIT" <<EOF
[Unit]
Description=Abakos provider reverse tunnel (LAN gateway to ${TUNNEL_HOST}:${REMOTE_PORT})
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(id -un)
Group=$(id -gn)
ExecStart=/usr/bin/ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -i ${TUNNEL_KEY} -R 0.0.0.0:${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT} ${TUNNEL_USER}@${TUNNEL_HOST}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo cp "$TMP_UNIT" "$UNIT_PATH"
rm -f "$TMP_UNIT"
sudo systemctl daemon-reload
sudo systemctl enable --now "${UNIT_NAME}.service"
sleep 2
systemctl --no-pager -l status "${UNIT_NAME}.service" | head -n 20

echo "== [4/4] local checks =="
systemctl is-active "${UNIT_NAME}.service"
echo "On ${TUNNEL_HOST}, expect sshd listening on :${REMOTE_PORT}:"
echo "  ss -lntp | grep ${REMOTE_PORT}"
echo "Then from the internet (after cloud firewall allows ${REMOTE_PORT}):"
echo "  curl -sk --max-time 10 https://${TUNNEL_HOST}:${REMOTE_PORT}/"
echo "Expect HTTP 404 from a live provider gateway."
echo "Done."
