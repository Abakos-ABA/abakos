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
