#!/usr/bin/env bash
# Step 3: create the provider key, fund it, publish a server cert, and register the
# provider on-chain. Then it prints the command to run the daemon.
#
# Requires: abakosd (chain binary) + provider-services on PATH, and steps 00/10 done.
set -euo pipefail

CHAIN_ID="abakos-sandbox-1"
NODE="https://rpc.abakos.ai:443"
KRING="test"
KEY="provider"
DOMAIN="${DOMAIN:-provider.abakos.local}"
HOST_URI="${HOST_URI:-https://127.0.0.1:8443}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TX="--chain-id $CHAIN_ID --node $NODE --keyring-backend $KRING --gas auto --gas-adjustment 1.4 --gas-prices 0uaba -y -o json"

echo "== [1/5] provider key ($KEY) =="
if ! abakosd keys show "$KEY" -a --keyring-backend "$KRING" >/dev/null 2>&1; then
  abakosd keys add "$KEY" --keyring-backend "$KRING"
fi
ADDR="$(abakosd keys show "$KEY" -a --keyring-backend "$KRING")"
echo "provider address: $ADDR"
[[ "$ADDR" == abakos1* ]] || { echo "!! address is not abakos1... - fix the bech32 prefix in step 2"; exit 1; }

echo "== [2/5] fund from faucet =="
curl -sS -X POST https://explorer.abakos.ai/faucet -H 'content-type: application/json' \
  -d "{\"address\":\"$ADDR\"}" || true
echo; sleep 6
abakosd query bank balances "$ADDR" --node "$NODE" -o json | jq '.balances' || true

echo "== [3/5] write provider.local.yaml (daemon) + provider-register.local.yaml (on-chain tx) =="
sed "s/PROVIDER_ADDRESS/$ADDR/; s|provider.abakos.local|$DOMAIN|" "$HERE/provider.yaml" > "$HERE/provider.local.yaml"
sed "s|https://HOST_IP:8443|$HOST_URI|" "$HERE/provider-register.yaml" > "$HERE/provider-register.local.yaml"
cat "$HERE/provider.local.yaml"
echo "--- register tx config (host field) ---"
cat "$HERE/provider-register.local.yaml"

echo "== [4/5] server certificate (x/cert) =="
abakosd tx cert generate server "$DOMAIN" --from "$KEY" $TX 2>/dev/null || \
  provider-services tx cert generate server "$DOMAIN" --from "$KEY" $TX 2>/dev/null || \
  echo "   (cert generate: check the exact subcommand for your provider-services version)"
abakosd tx cert publish server --from "$KEY" $TX 2>/dev/null || \
  provider-services tx cert publish server --from "$KEY" $TX 2>/dev/null || \
  echo "   (cert publish: check subcommand)"

echo "== [5/5] register provider on-chain (MsgCreateProvider) =="
# abakosd reads `host:` from provider-register.local.yaml (NOT host_uri / provider.yaml).
abakosd tx provider create "$HERE/provider-register.local.yaml" --from "$KEY" $TX
sleep 6
abakosd query provider get "$ADDR" --node "$NODE" -o json | jq '.' || true

cat <<EOF

== provider registered (verify above). Run the daemon: ==
  export AKASH_KEYRING_BACKEND=$KRING
  provider-services run \\
    --chain-id $CHAIN_ID \\
    --node $NODE \\
    --from $KEY \\
    --keyring-backend $KRING \\
    --gas-prices 0uaba --gas auto --gas-adjustment 1.4 \\
    --cluster-k8s \\
    --kubeconfig \$HOME/.kube/config \\
    --deployment-ingress-domain $DOMAIN \\
    --bid-price-strategy shellScript \\
    --bid-price-script-path $HERE/pricing.sh \\
    --bid-deposit 5000000uaba

(Consider a systemd unit for this. Then run scripts/30-test-deploy.sh from a tenant key.)
EOF
