#!/usr/bin/env bash
# Tenant E2E — same flow as mainnet (uaba escrow, SDL v2.1, mTLS manifest).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/config/network.sh"

bash "$HERE/scripts/render-hello-cpu.sh" "$HERE/examples/hello-cpu.yaml"
SDL="$HERE/examples/hello-cpu.yaml"
TKEY="${TKEY:-tenant}"
TX="--chain-id $ABA_CHAIN_ID --node $ABA_RPC --keyring-backend $ABA_KEYRING_BACKEND --gas auto --gas-adjustment 1.4 --gas-prices $ABA_GAS_PRICES -y -o json"
Q="--node $ABA_RPC -o json"

PROVIDER_URL="${ABA_PROVIDER_URL:-}"
if [ -z "$PROVIDER_URL" ]; then
  echo "!! set ABA_PROVIDER_URL or HOST_URI (public gateway https://IP:8443)"
  exit 1
fi

echo "== network $ABA_NETWORK | provider-url $PROVIDER_URL =="

echo "== tenant key ($TKEY) =="
abakosd keys show "$TKEY" -a --keyring-backend "$ABA_KEYRING_BACKEND" >/dev/null 2>&1 || \
  abakosd keys add "$TKEY" --keyring-backend "$ABA_KEYRING_BACKEND"
TADDR="$(abakosd keys show "$TKEY" -a --keyring-backend "$ABA_KEYRING_BACKEND")"

if [ -n "$ABA_FAUCET" ] && [ "$ABA_NETWORK" = "sandbox" ]; then
  curl -sS -X POST "$ABA_FAUCET" -H 'content-type: application/json' -d "{\"address\":\"$TADDR\"}" || true
  echo; sleep 6
fi

UABA="$(abakosd query bank spendable-balances "$TADDR" --node "$ABA_RPC" -o json | jq -r '[.balances[]|select(.denom=="uaba")|.amount]|first // "0"')"
[ "${UABA:-0}" != "0" ] || { echo "!! no spendable uaba"; exit 1; }
echo "tenant uaba: $UABA"

abakosd tx cert generate client --from "$TKEY" $TX 2>/dev/null || true
abakosd tx cert publish client --from "$TKEY" $TX 2>/dev/null || true
sleep 6

echo "== [1/5] create deployment ($ABA_DEPLOY_DEPOSIT) =="
abakosd tx deployment create "$SDL" --deposit "$ABA_DEPLOY_DEPOSIT" --from "$TKEY" $TX | jq '.txhash'
sleep 6
DSEQ="$(abakosd query deployment list --owner "$TADDR" $Q | jq -r '.deployments[-1].deployment.id.dseq')"
echo "dseq=$DSEQ hostname=$ABA_EXAMPLE_SERVICE_HOST"

echo "== [2/5] wait for bids =="
for i in $(seq 1 20); do
  n="$(abakosd query market bid list --owner "$TADDR" --dseq "$DSEQ" $Q | jq '.bids|length')"
  echo "  bids: $n"; [ "$n" -gt 0 ] && break; sleep 6
done
BIDS_JSON="$(abakosd query market bid list --owner "$TADDR" --dseq "$DSEQ" $Q)"
# Bid id lives at .bid.id on current builds, .bid.bid_id on older ones — accept both.
BIDID="$(echo "$BIDS_JSON" | jq -c '.bids[0].bid.id // .bids[0].bid.bid_id')"
PROVIDER="$(echo "$BIDID" | jq -r '.provider')"
GSEQ="$(echo "$BIDID" | jq -r '.gseq')"
OSEQ="$(echo "$BIDID" | jq -r '.oseq')"

echo "== [3/5] create lease =="
abakosd tx market lease create --dseq "$DSEQ" --gseq "$GSEQ" --oseq "$OSEQ" --provider "$PROVIDER" --from "$TKEY" $TX | jq '.txhash'
sleep 6

echo "== [4/5] send manifest =="
provider-services send-manifest "$SDL" --dseq "$DSEQ" --provider "$PROVIDER" --from "$TKEY" \
  --keyring-backend "$ABA_KEYRING_BACKEND" --node "$ABA_RPC" \
  --provider-url "$PROVIDER_URL" || echo "   (check gateway TLS and firewall :$ABA_PROVIDER_GATEWAY_PORT)"

echo "== [5/5] lease status =="
provider-services lease-status --dseq "$DSEQ" --provider "$PROVIDER" --from "$TKEY" \
  --keyring-backend "$ABA_KEYRING_BACKEND" --node "$ABA_RPC" \
  --provider-url "$PROVIDER_URL" || true

echo "SUCCESS: lease URI should be https://${ABA_EXAMPLE_SERVICE_HOST}/"
