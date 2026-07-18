#!/usr/bin/env bash
# Compile-gate: does cosmos/evm v0.4.1 (SDK v0.53 line) build against our akash SDK fork?
# Throwaway copy; does NOT touch the real chain/. Prints tidy + build results.
set -uo pipefail
export PATH="$HOME/sdk/go/bin:$HOME/go/bin:/usr/local/go/bin:$PATH"
export GOTOOLCHAIN=auto

SRC=/mnt/c/Users/Marlon/abakos
DST="$HOME/abakos-evmprobe"

echo "[1/5] sync throwaway copy -> $DST"
rm -rf "$DST"; mkdir -p "$DST"
cp -r "$SRC/chain" "$DST/chain"
cp -r "$SRC/chain-sdk" "$DST/chain-sdk"
cd "$DST/chain"

echo "[2/5] add cosmos/evm require + geth-fork/gin replaces"
cat >> go.mod <<'EOF'

require github.com/cosmos/evm v0.5.1

replace github.com/ethereum/go-ethereum => github.com/cosmos/go-ethereum v1.16.2-cosmos-1
replace github.com/gin-gonic/gin => github.com/gin-gonic/gin v1.9.1
EOF

echo "[3/5] probe imports (evm keepers + ante)"
mkdir -p evmprobe
cat > evmprobe/probe.go <<'EOF'
package evmprobe

import (
	_ "github.com/cosmos/evm/ante"
	_ "github.com/cosmos/evm/x/erc20/keeper"
	_ "github.com/cosmos/evm/x/feemarket/keeper"
	_ "github.com/cosmos/evm/x/vm/keeper"
)
EOF

echo "[4/5] go mod tidy (downloads cosmos/evm + geth fork; be patient) ..."
go mod tidy 2>tidy.err; TRC=$?
tail -35 tidy.err
echo "=== TIDY_RC=$TRC ==="

echo "[5/5] go build ./evmprobe/ ..."
go build ./evmprobe/ 2>build.err; BRC=$?
tail -60 build.err
echo "=== EVMPROBE_BUILD_RC=$BRC ==="
