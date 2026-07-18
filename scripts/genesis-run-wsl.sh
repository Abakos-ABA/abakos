#!/usr/bin/env bash
# Create the abakos-sandbox-1 genesis (10B ABA, uaba) and run a single-node
# validator in WSL to prove blocks advance. Uses the test keyring (sandbox only).
set -euo pipefail
export PATH="$HOME/sdk/go/bin:$HOME/go/bin:/snap/bin:$PATH"

BIN="$HOME/go/bin/abakosd"
HOME_DIR="$HOME/abakos-sandbox"
CHAIN_ID="abakos-sandbox-1"
KR=(--keyring-backend test --home "$HOME_DIR")
G="$HOME_DIR/config/genesis.json"

echo "[1] fresh init ($CHAIN_ID)"
rm -rf "$HOME_DIR"
"$BIN" genesis init abakos-sandbox --chain-id "$CHAIN_ID" --home "$HOME_DIR" >/dev/null 2>&1

echo "[2] normalize economic denoms -> uaba (jq, sort-safe; leaves inert multi-denom lists)"
jq '.app_state.staking.params.bond_denom="uaba"
  | .app_state.mint.params.mint_denom="uaba"
  | (.app_state.gov.params.min_deposit[]?.denom)="uaba"
  | (.app_state.gov.params.expedited_min_deposit[]?.denom)="uaba"' "$G" > "$G.tmp" && mv "$G.tmp" "$G"
echo "  bond_denom=$(jq -r .app_state.staking.params.bond_denom "$G") mint_denom=$(jq -r .app_state.mint.params.mint_denom "$G")"

echo "[3] create keys (test keyring): liquidity treasury ecosystem reserve team community"
for k in liquidity treasury ecosystem reserve team community; do
  "$BIN" keys add "$k" "${KR[@]}" >/dev/null 2>&1
done

echo "[4] genesis accounts (10,000,000,000 ABA total = 1e16 uaba)"
add() { "$BIN" genesis add-account "$("$BIN" keys show "$1" -a "${KR[@]}")" "${2}uaba" --home "$HOME_DIR"; }
add liquidity 3200000000000000
add treasury  1800000000000000
add ecosystem 1500000000000000
add reserve   1500000000000000
add team      1200000000000000
add community  800000000000000

echo "[5] gentx: treasury runs the genesis validator, self-delegate 100,000,000 ABA"
"$BIN" genesis gentx treasury 100000000000000uaba --chain-id "$CHAIN_ID" --min-self-delegation=1 --fees 5000uaba --gas-prices 0uaba "${KR[@]}" >/dev/null 2>&1
"$BIN" genesis collect --home "$HOME_DIR" >/dev/null 2>&1
"$BIN" genesis validate --home "$HOME_DIR" >/dev/null 2>&1 && echo "  genesis valid"

echo "[6] tune app.toml/config.toml"
sed -i 's|^minimum-gas-prices = .*|minimum-gas-prices = "0.0025uaba"|' "$HOME_DIR/config/app.toml"
sed -i 's|^timeout_commit = .*|timeout_commit = "2s"|' "$HOME_DIR/config/config.toml"

echo "[7] start node (background), sample block height twice"
nohup "$BIN" start --home "$HOME_DIR" >"$HOME_DIR/node.log" 2>&1 &
NODEPID=$!
echo "  node pid=$NODEPID"
height() { "$BIN" status --home "$HOME_DIR" 2>&1 | tr ',' '\n' | grep -o '"latest_block_height":"[0-9]*"' | head -1; }
sleep 18; H1="$(height || true)"
sleep 8;  H2="$(height || true)"
echo "  height sample 1: ${H1:-<none>}"
echo "  height sample 2: ${H2:-<none>}"
echo "---- node.log tail ----"; tail -n 12 "$HOME_DIR/node.log" || true
echo "---- addresses ----"
echo "  treasury acc: $("$BIN" keys show treasury -a "${KR[@]}")"
echo "  treasury val: $("$BIN" keys show treasury --bech val -a "${KR[@]}")"
echo "[8] stop node"
kill "$NODEPID" 2>/dev/null || true
wait "$NODEPID" 2>/dev/null || true
echo "DONE"
