#!/usr/bin/env bash
# One-time Ubuntu VM prep: SSH, build deps, abakosd from the live node.
# Run INSIDE the Ubuntu VM (terminal), once, as a user with sudo:
#   curl -fsSL https://raw.githubusercontent.com/Abakos-ABA/abakos/main/provider-compute/scripts/vm-bootstrap.sh | bash
# Or from the VMware shared folder:
#   bash /mnt/hgfs/abakos/provider-compute/scripts/vm-bootstrap.sh
set -euo pipefail

echo "== Abakos VM bootstrap =="

if [ "$(id -u)" -eq 0 ]; then
  echo "Run as your normal user (marlon), not root."
  exit 1
fi

echo "== [1/4] packages =="
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  openssh-server git curl jq make build-essential ca-certificates gnupg

echo "== [2/4] SSH server =="
sudo systemctl enable --now ssh 2>/dev/null || sudo systemctl enable --now sshd
sudo ufw allow OpenSSH 2>/dev/null || true
IP="$(hostname -I | awk '{print $1}')"
echo "SSH should be up on $IP (from host: ssh marlon@$IP)"

echo "== [3/4] Go (if missing) =="
if ! command -v go >/dev/null 2>&1; then
  GO_VER="1.23.4"
  curl -fsSL "https://go.dev/dl/go${GO_VER}.linux-amd64.tar.gz" | sudo tar -C /usr/local -xz
  grep -q '/usr/local/go/bin' ~/.bashrc || echo 'export PATH=/usr/local/go/bin:$HOME/go/bin:$PATH' >> ~/.bashrc
  export PATH=/usr/local/go/bin:$HOME/go/bin:$PATH
fi
go version

echo "== [4/4] abakosd from node =="
if ! command -v abakosd >/dev/null 2>&1; then
  echo "Copying abakosd from root@217.160.46.61 (you may be prompted for the node password or use your SSH key)..."
  scp -o StrictHostKeyChecking=accept-new root@217.154.169.211:/usr/local/bin/abakosd /tmp/abakosd
  sudo install -m 0755 /tmp/abakosd /usr/local/bin/abakosd
  rm -f /tmp/abakosd
fi
abakosd version 2>/dev/null || abakosd --help | head -3

cat <<EOF

== VM ready. From Windows host (PowerShell): ==
  ssh marlon@$IP

Then on the VM:
  git clone https://github.com/Abakos-ABA/abakos.git ~/abakos
  cd ~/abakos/provider-compute
  sudo DOMAIN=provider.abakos.local bash install.sh

Or step-by-step: scripts/00 -> 10 -> 20 -> 30-test-deploy.sh
EOF
