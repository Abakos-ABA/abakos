#!/usr/bin/env bash
# Build the Abakos Provider DESKTOP app for Linux -> one-click installers:
#   src-tauri/target/release/bundle/appimage/*.AppImage   (portable, "one-click")
#   src-tauri/target/release/bundle/deb/*.deb             (apt install)
#
# Run on Ubuntu 22.04/24.04 (the VM, or any Linux build host / CI). NOT on the
# single-validator VPS (heavy build). Tauri config already has "targets":"all".
set -euo pipefail
cd "$(dirname "$0")/.."   # desktop/

echo "== system deps (Tauri v2 on Linux) =="
sudo apt-get update
sudo apt-get install -y \
  build-essential curl wget file jq \
  libwebkit2gtk-4.1-dev librsvg2-dev libssl-dev \
  libgtk-3-dev libayatana-appindicator3-dev

echo "== rust =="
if ! command -v cargo >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
fi
# shellcheck disable=SC1090
source "$HOME/.cargo/env" 2>/dev/null || true

echo "== node =="
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

echo "== install js deps =="
npm ci || npm install

# tauri.conf.json sets createUpdaterArtifacts:true + a pubkey, so `tauri build`
# HARD-FAILS (exit 1, after the installers are already written) without a signing
# key. If the key is present we build signed (updater artifacts + latest.json);
# otherwise we disable updater artifacts so an unsigned installer build exits 0.
echo "== build =="
if [ -f .tauri/updater.key ]; then
  export TAURI_SIGNING_PRIVATE_KEY="$(cat .tauri/updater.key)"
  export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="${TAURI_SIGNING_PRIVATE_KEY_PASSWORD:-}"
  echo "== signing enabled: updater artifacts + latest.json will be produced =="
  npm run tauri:build
else
  echo "== no .tauri/updater.key: building UNSIGNED installers (no auto-update artifacts) =="
  npm run tauri:build -- --config '{"bundle":{"createUpdaterArtifacts":false}}'
fi

echo
echo "== done. Installers: =="
ls -1 src-tauri/target/release/bundle/appimage/*.AppImage 2>/dev/null || true
ls -1 src-tauri/target/release/bundle/deb/*.deb 2>/dev/null || true
echo "AppImage = portable one-click; .deb = sudo apt install ./<file>.deb"
