#!/usr/bin/env bash
# Step 3: provider key, cert, on-chain registration (mainnet-parity flow).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"

KEY="${PROVIDER_KEY:-provider}"
DOMAIN="$ABA_PROVIDER_DOMAIN"
HOST_URI="${HOST_URI:-$ABA_PROVIDER_URL}"
[ -n "$HOST_URI" ] || { echo "!! set HOST_URI or ensure PUBLIC_IP is reachable"; exit 1; }

TX="--chain-id $ABA_CHAIN_ID --node $ABA_RPC --keyring-backend $ABA_KEYRING_BACKEND --gas auto --gas-adjustment 1.4 --gas-prices $ABA_GAS_PRICES -y -o json"

echo "== network: $ABA_NETWORK chain=$ABA_CHAIN_ID domain=$DOMAIN =="
echo "== gateway: $HOST_URI =="

echo "== [1/5] provider key ($KEY) =="
if ! abakosd keys show "$KEY" -a --keyring-backend "$ABA_KEYRING_BACKEND" >/dev/null 2>&1; then
  abakosd keys add "$KEY" --keyring-backend "$ABA_KEYRING_BACKEND"
fi
ADDR="$(abakosd keys show "$KEY" -a --keyring-backend "$ABA_KEYRING_BACKEND")"
echo "provider address: $ADDR"
[[ "$ADDR" == abakos1* ]] || { echo "!! address is not abakos1..."; exit 1; }

# Bid deposits are escrowed from the provider's own wallet — no faucet funding,
# identical flow on sandbox and mainnet.
BID_UAB="${ABA_BID_DEPOSIT%uaba}"
NEED_UAB="$((BID_UAB + 1000000))"   # bid deposit + 1 ABA fee/tx buffer
FUND_TIMEOUT="${FUND_TIMEOUT:-900}"

spendable_uaba() {
  abakosd query bank spendable-balances "$ADDR" --node "$ABA_RPC" -o json 2>/dev/null \
    | jq -r '[.balances[]? | select(.denom=="uaba") | .amount] | first // "0"'
}

echo "== [2/5] wallet funding (provider pays its own bid deposits) =="
BAL="$(spendable_uaba)"
if [ "$BAL" -lt "$NEED_UAB" ]; then
  cat <<EOF
Provider wallet needs at least ${NEED_UAB}uaba (bid deposit $ABA_BID_DEPOSIT + buffer).
Current spendable balance: ${BAL}uaba

  Send ABA to: $ADDR
  (e.g. from the Abakos Desktop Wallet, Send tab)

Waiting up to ${FUND_TIMEOUT}s for funds...
EOF
  waited=0
  while [ "$BAL" -lt "$NEED_UAB" ]; do
    if [ "$waited" -ge "$FUND_TIMEOUT" ]; then
      echo "!! timed out after ${FUND_TIMEOUT}s — fund $ADDR and re-run this script" >&2
      exit 1
    fi
    sleep 5; waited=$((waited + 5))
    BAL="$(spendable_uaba)"
  done
  echo "funded: ${BAL}uaba"
fi
abakosd query bank spendable-balances "$ADDR" --node "$ABA_RPC" -o json | jq '.balances' || true

echo "== [3/5] provider config files =="
sed -e "s|PROVIDER_ADDRESS|$ADDR|g" \
    -e "s|ABA_RPC_PLACEHOLDER|$ABA_RPC|g" \
    -e "s|ABA_CHAIN_ID_PLACEHOLDER|$ABA_CHAIN_ID|g" \
    -e "s|ABA_KEYRING_PLACEHOLDER|$ABA_KEYRING_BACKEND|g" \
    -e "s|ABA_PROVIDER_DOMAIN_PLACEHOLDER|$DOMAIN|g" \
    -e "s|ABA_HOST_URI_PLACEHOLDER|$HOST_URI|g" \
  "$HERE/provider.yaml" > "$HERE/provider.local.yaml"
sed "s|https://HOST_IP:8443|$HOST_URI|" "$HERE/provider-register.yaml" > "$HERE/provider-register.local.yaml"

echo "== [4/5] server certificate =="
abakosd tx cert generate server "$DOMAIN" --from "$KEY" $TX 2>/dev/null || true
abakosd tx cert publish server --from "$KEY" $TX 2>/dev/null || true
sleep 6

echo "== [5/5] register provider on-chain =="
abakosd tx provider create "$HERE/provider-register.local.yaml" --from "$KEY" $TX
sleep 6
abakosd query provider get "$ADDR" --node "$ABA_RPC" -o json | jq '.' || true

cat <<EOF

Registered on $ABA_CHAIN_ID. Daemon flags (also in systemd):
  --deployment-ingress-domain $DOMAIN
  --bid-deposit $ABA_BID_DEPOSIT
  --provider gateway for tenants: $HOST_URI

Next: bash scripts/30-test-deploy.sh
EOF
