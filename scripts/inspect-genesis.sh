#!/usr/bin/env bash
set -e
export PATH="$HOME/sdk/go/bin:$HOME/go/bin:$PATH"
B="$HOME/go/bin/abakosd"
rm -rf /tmp/g1
"$B" genesis init x --chain-id abakos-sandbox-1 --home /tmp/g1 >/dev/null 2>&1
echo "=== *denom* fields (single) ==="
grep -oE '"[a-z_]*denom[a-z_]*": *"[a-z]*"' /tmp/g1/config/genesis.json | sort | uniq -c
echo "=== coin denom occurrences ==="
grep -oE '"denom": *"[a-z]+"' /tmp/g1/config/genesis.json | sort | uniq -c
echo "=== take rates / deposits context ==="
grep -oE '"(denom_take_rates|default_take_rate|deposits|min_deposit|bid_min_deposits|deployment_min_deposits)":[^]}]{0,160}' /tmp/g1/config/genesis.json | head -30
