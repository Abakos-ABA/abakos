#!/usr/bin/env bash
# One-time forwarder setup on the validator. Idempotent.
set -euo pipefail
umask 077
D=/opt/abakos-forwarder
mkdir -p "$D"
cp /root/bridge-relayer/forwarder.mjs /root/bridge-relayer/package.json "$D/"
cd "$D"
npm install --no-fund --no-audit --loglevel=error
if [ ! -s hot.key ]; then
  node -e "const{Wallet}=require('ethers');const w=Wallet.createRandom();require('fs').writeFileSync('hot.key',w.privateKey);console.log('hot wallet created')"
  chmod 600 hot.key
fi
node -e "const{Wallet}=require('ethers');const fs=require('fs');console.log('HOT ADDRESS:',new Wallet(fs.readFileSync('hot.key','utf8').trim()).address)"
cp /root/bridge-relayer/abakos-forwarder.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now abakos-forwarder
sleep 3
systemctl is-active abakos-forwarder
