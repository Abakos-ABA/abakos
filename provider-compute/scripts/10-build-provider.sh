#!/usr/bin/env bash
# Step 2: build `provider-services` for the abakos chain.
#
# Upstream seals bech32 prefix + denom in pkg.akt.dev/go/sdkutil at compile time.
# We vendor deps, patch sdkutil in vendor/, then build with -mod=vendor.
#
# Requires: Go 1.22+, git.
set -euo pipefail

SRC="${SRC:-$HOME/akash-provider-src}"
REPO="https://github.com/akash-network/provider"
TAG="${TAG:-v0.14.2}"

echo "== clone $REPO -> $SRC ($TAG) =="
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --branch "$TAG" "$REPO" "$SRC"
fi
cd "$SRC"
git fetch --tags --quiet 2>/dev/null || true
git checkout "$TAG" 2>/dev/null || true
git reset --hard HEAD
git clean -fd

# --- Abakos EVM-account patch: let the provider read cosmos/evm (ethsecp256k1) accounts ---
# The abakos chain issues EVM-wallet accounts whose pubkey type is
# /cosmos.evm.crypto.v1.ethsecp256k1.PubKey (github.com/cosmos/evm). Vanilla provider-services
# registers only Akash ModuleBasics interfaces, so InterfaceRegistry.UnpackAny() fails for EVERY
# EVM-wallet tenant (cmd/provider-services/cmd/certs.go) -> account-querier / cert validation
# breaks for all Desktop-wallet users. We register the evm crypto codec exactly like the chain
# does (chain/app/evm.go: evmcryptocodec.RegisterInterfaces(registry)). Compile-verified against
# the akash cosmos-sdk fork; no go-ethereum replace needed for the narrow crypto/codec import.
ROOT="cmd/provider-services/cmd/root.go"
if ! grep -q 'evm/crypto/codec' "$ROOT"; then
  sed -i 's#\t"github.com/akash-network/provider/version"#\t"github.com/akash-network/provider/version"\n\tevmcryptocodec "github.com/cosmos/evm/crypto/codec"#' "$ROOT"
  sed -i 's#\tapp.ModuleBasics().RegisterInterfaces(encodingConfig.InterfaceRegistry)#\tapp.ModuleBasics().RegisterInterfaces(encodingConfig.InterfaceRegistry)\n\tevmcryptocodec.RegisterInterfaces(encodingConfig.InterfaceRegistry)#' "$ROOT"
fi
grep -q 'evmcryptocodec.RegisterInterfaces' "$ROOT" || { echo "!! evm-codec patch failed in $ROOT"; exit 1; }
echo "== patched $ROOT: registered cosmos/evm ethsecp256k1 pubkey codec =="
# Add the cosmos/evm module (chain pins v0.5.1) so `go mod vendor` below includes it:
GOFLAGS=-mod=mod go get github.com/cosmos/evm@v0.5.1

echo "== vendor + patch bech32/denom in vendor/pkg.akt.dev/go/sdkutil =="
export GOTOOLCHAIN=auto
go mod vendor
SDKUTIL="vendor/pkg.akt.dev/go/sdkutil/init.go"
sed -i \
  -e 's/Bech32PrefixAccAddr = "akash"/Bech32PrefixAccAddr = "abakos"/g' \
  -e 's/Bech32PrefixAccPub  = "akashpub"/Bech32PrefixAccPub  = "abakospub"/g' \
  -e 's/Bech32PrefixValAddr = "akashvaloper"/Bech32PrefixValAddr = "abakosvaloper"/g' \
  -e 's/Bech32PrefixValPub  = "akashvaloperpub"/Bech32PrefixValPub  = "abakosvaloperpub"/g' \
  -e 's/Bech32PrefixConsAddr = "akashvalcons"/Bech32PrefixConsAddr = "abakosvalcons"/g' \
  -e 's/Bech32PrefixConsPub  = "akashvalconspub"/Bech32PrefixConsPub  = "abakosvalconspub"/g' \
  -e 's/DenomUakt = "uakt"/DenomUakt = "uaba"/g' \
  -e 's/DenomAkt  = "akt"/DenomAkt  = "aba"/g' \
  -e 's/DenomMakt = "makt"/DenomMakt = "maba"/g' \
  "$SDKUTIL"

# ABA-only sandbox: escrow funds are uaba (DenomUakt), not uact.
BC="balance_checker.go"
if grep -q 'funds.Denom == sdkutil.DenomUact' "$BC" && ! grep -q 'DenomUakt' "$BC"; then
  sed -i 's/funds.Denom == sdkutil.DenomUact/funds.Denom == sdkutil.DenomUakt || funds.Denom == sdkutil.DenomUact/g' "$BC"
fi

# --- Abakos sponsor-model patch: let the bid engine offer grant-sponsored deposits ---
# Vanilla v0.14.2 hard-codes the bid deposit source to the operator's own balance
# (bidengine/order.go: `Sources: deposit.Sources{deposit.SourceBalance}`), so a
# DepositAuthorization grant from the main wallet is never consulted. We make each bid
# try the grant FIRST and fall back to balance -- matching the chain/CLI default
# (`--deposit-sources grant,balance`). The chain then pulls the 5-ABA deposit from the
# GRANTER (main wallet), decrements its spend-limit, and RE-CREDITS the limit when the
# bid/lease closes (revolving), so the "max ABA for hosting" cap is a live simultaneous
# cap. Refs: chain/x/escrow/keeper/keeper.go:226-326 (pull from granter) & 1053-1076
# (re-credit on close).
# Safe rollout: with NO grant present the engine falls back to SourceBalance => behaviour
# is byte-for-byte identical to today until the operator's main wallet creates a grant.
ORDER="bidengine/order.go"
if grep -q 'deposit.Sources{deposit.SourceBalance}' "$ORDER" && ! grep -q 'SourceGrant' "$ORDER"; then
  sed -i 's/deposit\.Sources{deposit\.SourceBalance}/deposit.Sources{deposit.SourceGrant, deposit.SourceBalance}/' "$ORDER"
fi
grep -q 'deposit.Sources{deposit.SourceGrant, deposit.SourceBalance}' "$ORDER" \
  || { echo "!! bid-deposit-source patch failed to apply in $ORDER"; exit 1; }
echo "== patched $ORDER: bid deposit sources = grant,balance =="

LDFLAGS="-X github.com/akash-network/provider/version.Name=provider-services \
  -X github.com/akash-network/provider/version.AppName=provider-services \
  -X github.com/akash-network/provider/version.Version=$TAG"
go build -mod=vendor -tags osusergo,netgo -ldflags "$LDFLAGS" -o "$(go env GOPATH)/bin/provider-services" ./cmd/provider-services

PS_BIN="$(command -v provider-services || echo "$HOME/go/bin/provider-services")"
echo "provider-services installed to: $PS_BIN"
"$PS_BIN" version || true

echo "Sanity: address prefix must be abakos1..."
ADDR="$("$PS_BIN" keys show provider -a --keyring-backend test 2>/dev/null || true)"
if [ -n "$ADDR" ]; then
  echo "provider key: $ADDR"
  [[ "$ADDR" == abakos1* ]] || { echo "!! prefix still wrong"; exit 1; }
fi
echo "Next: scripts/20-register-provider.sh"
