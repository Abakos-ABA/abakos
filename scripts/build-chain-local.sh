#!/usr/bin/env bash
# Local iterative build of abakosd (with EVM) in WSL. Syncs chain + chain-sdk to
# a native ext4 dir (fast go cache) and builds cmd/akash.
set -uo pipefail
export PATH=/home/marlon/sdk/go/bin:/home/marlon/go/bin:/usr/local/go/bin:/usr/bin:/bin
export GOTOOLCHAIN=auto
export CGO_ENABLED=1

SRC=/mnt/c/Users/Marlon/abakos
DST=/home/marlon/abakos-build
mkdir -p "$DST"

echo "[sync] chain + chain-sdk + cosmos-sdk -> $DST"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude 'data' --exclude '.git' "$SRC/chain/" "$DST/chain/"
  rsync -a --delete --exclude '.git' "$SRC/chain-sdk/" "$DST/chain-sdk/"
  rsync -a --delete --exclude '.git' "$SRC/cosmos-sdk/" "$DST/cosmos-sdk/"
else
  rm -rf "$DST/chain" "$DST/chain-sdk" "$DST/cosmos-sdk"
  cp -r "$SRC/chain" "$DST/chain"
  cp -r "$SRC/chain-sdk" "$DST/chain-sdk"
  cp -r "$SRC/cosmos-sdk" "$DST/cosmos-sdk"
fi

cd "$DST/chain"
echo "[build] go build ./cmd/akash (first EVM build is slow) ..."
go build -mod=mod -o "$DST/abakosd" ./cmd/akash 2>/tmp/build.local.err; RC=$?
echo "---- build errors (tail) ----"
tail -80 /tmp/build.local.err
echo "=== LOCAL_BUILD_RC=$RC ==="
if [ "$RC" = "0" ]; then ls -la "$DST/abakosd"; fi
