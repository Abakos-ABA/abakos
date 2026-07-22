#!/usr/bin/env bash
# Step 5: tenant side - deploy the CPU example end-to-end with native ABA (uaba) only.
# Run with a SEPARATE tenant key (not the provider key). Requires the provider daemon
# from step 3 to be running.
set -euo pipefail

CHAIN_ID="abakos-sandbox-1"
NODE="https://rpc.abakos.ai:443"
KRING="test"
TKEY="${TKEY:-tenant}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SDL="$HERE/examples/hello-cpu.yaml"
TX="--chain-id $CHAIN_ID --node $NODE --keyring-backend $KRING --gas auto --gas-adjustment 1.4 --gas-prices 0uaba -y -o json"
Q="--node $NODE -o json"

echo "== tenant key ($TKEY) + faucet =="
abakosd keys show "$TKEY" -a --keyring-backend "$KRING" >/dev/null 2>&1 || abakosd keys add "$TKEY" --keyring-backend "$KRING"
TADDR="$(abakosd keys show "$TKEY" -a --keyring-backend "$KRING")"
curl -sS -X POST https://explorer.abakos.ai/faucet -H 'content-type: application/json' -d "{\"address\":\"$TADDR\"}" || true
echo; sleep 6

UABA="$(abakosd query bank spendable-balances "$TADDR" --node "$NODE" -o json | jq -r '[.balances[]|select(.denom=="uaba")|.amount]|first // "0"')"
if [ "${UABA:-0}" = "0" ]; then
  echo "!! no uaba balance — faucet may be down"
  exit 1
fi
echo "tenant uaba balance: $UABA"

echo "== tenant client certificate (required for deployments) =="
abakosd tx cert generate client --from "$TKEY" $TX 2>/dev/null || true
abakosd tx cert publish client --from "$TKEY" $TX 2>/dev/null || true
sleep 6

echo "== [1/5] create deployment (escrows uaba) =="
abakosd tx deployment create "$SDL" --deposit 5000000uaba --from "$TKEY" $TX | jq '.txhash'
sleep 6
DSEQ="$(abakosd query deployment list --owner "$TADDR" $Q | jq -r '.deployments[-1].deployment.id.dseq')"
echo "dseq=$DSEQ"

echo "== [2/5] wait for provider bids =="
for i in $(seq 1 20); do
  BIDS="$(abakosd query market bid list --owner "$TADDR" --dseq "$DSEQ" $Q | jq '.bids')"
  n="$(echo "$BIDS" | jq 'length')"
  echo "  bids: $n"
  [ "$n" -gt 0 ] && break
  sleep 6
done
PROVIDER="$(echo "$BIDS" | jq -r '.[0].bid.bid_id.provider')"
GSEQ="$(echo "$BIDS" | jq -r '.[0].bid.bid_id.gseq')"
OSEQ="$(echo "$BIDS" | jq -r '.[0].bid.bid_id.oseq')"
echo "chose provider=$PROVIDER gseq=$GSEQ oseq=$OSEQ"

echo "== [3/5] create lease =="
abakosd tx market lease create --dseq "$DSEQ" --gseq "$GSEQ" --oseq "$OSEQ" --provider "$PROVIDER" --from "$TKEY" $TX | jq '.txhash'
sleep 6

echo "== [4/5] send manifest to the provider =="
provider-services send-manifest "$SDL" --dseq "$DSEQ" --provider "$PROVIDER" --from "$TKEY" \
  --keyring-backend "$KRING" --node "$NODE" \
  --provider-url "https://192.168.227.128:8443" || \
  echo "   (send-manifest: check provider gateway at :8443)"

echo "== [5/5] lease status + escrow =="
provider-services lease-status --dseq "$DSEQ" --provider "$PROVIDER" --from "$TKEY" \
  --keyring-backend "$KRING" --node "$NODE" \
  --provider-url "https://192.168.227.128:8443" || true
abakosd query escrow blocks --node "$NODE" -o json 2>/dev/null | jq '.' || true

echo
echo "SUCCESS criteria: lease active, nginx reachable at the lease URI, and the escrow"
echo "account for this deployment draws down uaba to the provider over blocks."
