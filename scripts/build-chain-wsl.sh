#!/usr/bin/env bash
# Build abakosd (Abakos chain, fork of akash/node) inside WSL.
# Source lives on the Windows side; copy to WSL-native fs for a fast build.
set -euo pipefail

export PATH="$HOME/sdk/go/bin:$HOME/go/bin:$PATH"
export GOTOOLCHAIN=auto

SRC=/mnt/c/Users/Marlon/abakos
DST="$HOME/abakos"

echo "[1/4] sync source -> $DST (chain + chain-sdk as siblings for the go.mod replace)"
mkdir -p "$DST"
rm -rf "$DST/chain" "$DST/chain-sdk"
cp -r "$SRC/chain" "$DST/chain"
cp -r "$SRC/chain-sdk" "$DST/chain-sdk"

cd "$DST/chain"
echo "[2/4] toolchain: $(go version)"
echo "[3/4] building abakosd (first build downloads many modules, be patient) ..."
mkdir -p "$HOME/go/bin"
CGO_ENABLED=1 go build -mod=mod -o "$HOME/go/bin/abakosd" ./cmd/akash

echo "[4/4] BUILD_OK"
"$HOME/go/bin/abakosd" version 2>&1 | head -5 || true
ls -la "$HOME/go/bin/abakosd"
