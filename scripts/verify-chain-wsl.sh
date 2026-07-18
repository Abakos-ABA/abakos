#!/usr/bin/env bash
# Verify the built abakosd: runs, shows version, and produces abakos1 addresses.
set -uo pipefail
export PATH="$HOME/sdk/go/bin:$HOME/go/bin:$PATH"

echo "=== abakosd version ==="
abakosd version --long 2>&1 | head -25 || echo "version cmd rc=$?"

echo "=== keys add val (expect an abakos1... address) ==="
rm -rf /tmp/abxtest
abakosd keys add val --keyring-backend test --home /tmp/abxtest --output json 2>&1 | head -25 || echo "keys add rc=$?"

echo "=== address only ==="
abakosd keys show val -a --keyring-backend test --home /tmp/abxtest 2>&1 || true

echo "=== default bond denom check (genesis init dry) ==="
rm -rf /tmp/abxinit
abakosd genesis init sandbox-check --chain-id abakos-sandbox-1 --home /tmp/abxinit >/dev/null 2>&1 || abakosd init sandbox-check --chain-id abakos-sandbox-1 --home /tmp/abxinit >/dev/null 2>&1 || echo "init rc=$?"
if [ -f /tmp/abxinit/config/genesis.json ]; then
  echo "bond_denom: $(grep -o '\"bond_denom\": \"[^\"]*\"' /tmp/abxinit/config/genesis.json | head -1)"
  echo "mint_denom: $(grep -o '\"mint_denom\": \"[^\"]*\"' /tmp/abxinit/config/genesis.json | head -1)"
fi
