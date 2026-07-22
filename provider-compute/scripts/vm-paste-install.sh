#!/usr/bin/env bash
# Paste this ONE line in the Ubuntu VM terminal (Ctrl+Alt+T):
#   curl -fsSL http://192.168.227.1:8765/provider-compute/scripts/vm-paste-install.sh | bash
#
# Host must run:  python provider-compute/scripts/serve-for-vm.py
set -euo pipefail
HOST="${ABAKOS_HOST:-192.168.227.1}"
PORT="${ABAKOS_PORT:-8765}"
BASE="http://${HOST}:${PORT}/provider-compute"

echo "== Abakos VM one-shot install (from $BASE) =="

echo "== [1/5] packages + SSH =="
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  openssh-server open-vm-tools open-vm-tools-desktop \
  git curl jq make build-essential ca-certificates gnupg
sudo systemctl enable --now ssh 2>/dev/null || sudo systemctl enable --now sshd
IP="$(hostname -I | awk '{print $1}')"
echo "SSH enabled on $IP"

echo "== [2/5] Go =="
if ! command -v go >/dev/null 2>&1; then
  GO_VER="1.23.4"
  curl -fsSL "https://go.dev/dl/go${GO_VER}.linux-amd64.tar.gz" | sudo tar -C /usr/local -xz
  export PATH=/usr/local/go/bin:$HOME/go/bin:$PATH
  grep -q '/usr/local/go/bin' ~/.bashrc || echo 'export PATH=/usr/local/go/bin:$HOME/go/bin:$PATH' >> ~/.bashrc
fi
go version

echo "== [3/5] abakosd from host file server =="
if ! command -v abakosd >/dev/null 2>&1; then
  curl -fsSL "${BASE}/artifacts/abakosd" -o /tmp/abakosd
  sudo install -m 0755 /tmp/abakosd /usr/local/bin/abakosd
  rm -f /tmp/abakosd
fi
abakosd version 2>/dev/null | head -1 || true

echo "== [4/5] sync provider-compute =="
mkdir -p "$HOME/abakos"
if [ -d /mnt/hgfs/abakos/provider-compute ]; then
  echo "Using VMware shared folder"
  ln -sfn /mnt/hgfs/abakos "$HOME/abakos" 2>/dev/null || cp -a /mnt/hgfs/abakos "$HOME/abakos"
else
  rm -rf "$HOME/abakos/provider-compute"
  mkdir -p "$HOME/abakos"
  curl -fsSL "${BASE}/install.sh" -o "$HOME/abakos/provider-compute/install.sh"
  for f in scripts/00-install-k3s.sh scripts/10-build-provider.sh scripts/20-register-provider.sh scripts/30-test-deploy.sh provider.yaml pricing.sh examples/hello-cpu.yaml systemd/provider-services.service; do
    mkdir -p "$(dirname "$HOME/abakos/provider-compute/$f")"
    curl -fsSL "${BASE}/${f}" -o "$HOME/abakos/provider-compute/${f}"
  done
  chmod +x "$HOME/abakos/provider-compute"/install.sh "$HOME/abakos/provider-compute"/scripts/*.sh "$HOME/abakos/provider-compute"/pricing.sh 2>/dev/null || true
fi

echo "== [5/5] headless provider install =="
cd "$HOME/abakos/provider-compute"
export SKIP_PREFIX_PROMPT=1
sudo DOMAIN=provider.abakos.local bash install.sh

echo
echo "== Done. From Windows: ssh marlon@$IP =="
echo "Test: bash $HOME/abakos/provider-compute/scripts/30-test-deploy.sh"
