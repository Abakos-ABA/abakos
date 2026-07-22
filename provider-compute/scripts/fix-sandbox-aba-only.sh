#!/usr/bin/env bash
# Run on the sandbox validator (217.154.169.211) as root AFTER upgrading abakosd
# to the ABA-only build. Switches deployment + market params to uaba.
set -euo pipefail

HOME="${ABA_HOME:-/root/.abakos}"
CHAIN_ID="${ABA_CHAIN_ID:-abakos-sandbox-1}"
NODE="${ABA_NODE:-tcp://127.0.0.1:26657}"
TX="--chain-id $CHAIN_ID --node $NODE --keyring-backend test --home $HOME --gas auto --gas-adjustment 1.4 --gas-prices 0uaba -y -o json"
GOV_AUTH="abakos10d07y265gmmuvt4z0w9aw880jnsr700jaunrrs"
PROP="/tmp/aba-only-proposal.json"

cat >"$PROP" <<EOF
{
  "messages": [
    {
      "@type": "/akash.deployment.v1beta4.MsgUpdateParams",
      "authority": "$GOV_AUTH",
      "params": {
        "min_deposits": [{"denom": "uaba", "amount": "500000"}]
      }
    },
    {
      "@type": "/akash.market.v1beta5.MsgUpdateParams",
      "authority": "$GOV_AUTH",
      "params": {
        "bid_min_deposit": {"denom": "uaba", "amount": "500000"},
        "bid_min_deposits": [{"denom": "uaba", "amount": "500000"}],
        "order_max_bids": 20,
        "min_reclamation_window": "3600s",
        "max_reclamation_window": "2592000s"
      }
    }
  ],
  "metadata": "ipfs://CID",
  "deposit": "50000000uaba",
  "title": "Sandbox: ABA-only compute market",
  "summary": "Use native uaba for deployment escrow and provider bid deposits (no ACT/BME)",
  "expedited": true
}
EOF

echo "== submit expedited gov proposal (ABA-only params) =="
abakosd tx gov submit-proposal "$PROP" --from treasury $TX | tee /tmp/aba-only-prop.json
PROP_ID="$(python3 -c "import json; print(json.load(open('/tmp/aba-only-prop.json')).get('proposal_id',''))" 2>/dev/null || true)"
if [ -z "$PROP_ID" ] || [ "$PROP_ID" = "" ]; then
  PROP_ID="$(abakosd query gov proposals --node "$NODE" -o json | python3 -c "import sys,json; ps=json.load(sys.stdin)['proposals']; print(ps[-1]['id'] if ps else '')")"
fi
echo "proposal_id=$PROP_ID"

echo "== vote yes =="
abakosd tx gov vote "$PROP_ID" yes --from treasury $TX
sleep 8

echo "== current params =="
abakosd query deployment params --node "$NODE" -o json | jq '.params.min_deposits'
abakosd query market params --node "$NODE" -o json | jq '.params | {bid_min_deposit, bid_min_deposits}'
