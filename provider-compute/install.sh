#!/usr/bin/env bash
# Abakos Compute Provider - one-command HEADLESS installer (no desktop/UI needed).
#
# Run on a dedicated Ubuntu 22.04/24.04 host or VM (NOT the chain-node/website box).
# It installs k3s + Akash operators, builds provider-services for abakos, registers the
# provider on-chain, and installs a systemd service so the provider runs on boot.
#
#   curl -fsSL https://raw.githubusercontent.com/Abakos-ABA/abakos/main/provider-compute/install.sh | sudo bash
#   (or) sudo bash provider-compute/install.sh
#
# Env:
#   DOMAIN=provider.example.com   tenant-reachable gateway hostname (default provider.abakos.local)
#   ALLOW_ON_NODE=1               override the safety guard (NOT recommended)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== Abakos Compute Provider - headless install =="

# ---- safety guard: never turn the live chain-node / website box into a k8s host ----
if [ "${ALLOW_ON_NODE:-0}" != "1" ]; then
  is_node=0
  systemctl is-active --quiet abakosd 2>/dev/null && is_node=1
  caddy_443=0
  ss -ltn 2>/dev/null | grep -qE ':443 ' && caddy_443=1
  if [ "$is_node" = "1" ] || [ "$caddy_443" = "1" ]; then
    echo "!! This host looks like the chain-node / website server (abakosd active and/or :443 in use)."
    echo "!! Installing k3s here can disrupt the validator and the website (ingress vs Caddy on 80/443)."
    echo "!! Run this on a separate Ubuntu VM/box instead. To override anyway: ALLOW_ON_NODE=1"
    exit 1
  fi
fi

# ---- abakosd must be present (same-arch Linux binary; copy from the node if needed) ----
if ! command -v abakosd >/dev/null 2>&1; then
  echo "!! abakosd not found on PATH."
  echo "   Copy it from the node:  scp root@217.154.169.211:/usr/local/bin/abakosd /usr/local/bin/ && chmod +x /usr/local/bin/abakosd"
  echo "   (or build it from ../chain). Then re-run."
  exit 1
fi

echo "== [1/4] k3s + operators =="; bash "$HERE/scripts/00-install-k3s.sh"
echo "== [2/4] build provider-services (abakos) =="; bash "$HERE/scripts/10-build-provider.sh"
echo "== [3/4] register provider on-chain =="; bash "$HERE/scripts/20-register-provider.sh"

echo "== [4/4] install systemd service =="
DOMAIN="${DOMAIN:-provider.abakos.local}"
PS_BIN="$(command -v provider-services)"
sed -e "s|__PS_BIN__|$PS_BIN|g" -e "s|__DOMAIN__|$DOMAIN|g" -e "s|__HERE__|$HERE|g" -e "s|__USER__|${SUDO_USER:-$USER}|g" \
  "$HERE/systemd/provider-services.service" > /etc/systemd/system/abakos-provider.service
systemctl daemon-reload
systemctl enable abakos-provider
systemctl restart abakos-provider
sleep 3
systemctl status abakos-provider --no-pager | head -12 || true

cat <<EOF

== Provider is installed and running as a service (abakos-provider). ==
Logs:    journalctl -u abakos-provider -f
Test:    bash $HERE/scripts/30-test-deploy.sh   (from a tenant key)
EOF
