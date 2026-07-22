#!/usr/bin/env bash
# Run on the sandbox validator (217.154.169.211) as root.
# Adds the genesis `host` key as an authorized oracle feeder so BME can mint uact.
set -euo pipefail

HOME="${ABA_HOME:-/root/.abakos}"
CHAIN_ID="${ABA_CHAIN_ID:-abakos-sandbox-1}"
NODE="${ABA_NODE:-tcp://127.0.0.1:26657}"
TX="--chain-id $CHAIN_ID --node $NODE --keyring-backend test --home $HOME --gas auto --gas-adjustment 1.4 --gas-prices 0uaba -y -o json"

HOST_ADDR="$(abakosd keys show host -a --keyring-backend test --home "$HOME")"
GOV_AUTH="abakos10d07y265gmmuvt4z0w9aw880jnsr700jaunrrs"
PROP="/tmp/oracle-sources-proposal.json"

cat >"$PROP" <<EOF
{
  "messages": [{
    "@type": "/akash.oracle.v2.MsgUpdateParams",
    "authority": "$GOV_AUTH",
    "params": {
      "sources": ["$HOST_ADDR"],
      "min_price_sources": 1,
      "max_price_staleness_period": "30s",
      "twap_window": "5s",
      "max_price_deviation_bps": "150",
      "feed_contracts_params": [],
      "price_retention": "86400s",
      "prune_epoch": "hour",
      "max_prune_per_epoch": "1000",
      "max_future_time_drift": "10s"
    }
  }],
  "metadata": "ipfs://CID",
  "deposit": "50000000uaba",
  "title": "Sandbox: authorize host oracle feeder",
  "summary": "Enable aba/usd price feed from host key for BME uact minting",
  "expedited": true
}
EOF

echo "== submit expedited gov proposal =="
abakosd tx gov submit-proposal "$PROP" --from treasury $TX | tee /tmp/oracle-prop.json
PROP_ID="$(python3 -c "import json; print(json.load(open('/tmp/oracle-prop.json')).get('proposal_id',''))" 2>/dev/null || true)"
if [ -z "$PROP_ID" ] || [ "$PROP_ID" = "" ]; then
  PROP_ID="$(abakosd query gov proposals --node "$NODE" -o json | python3 -c "import sys,json; ps=json.load(sys.stdin)['proposals']; print(ps[-1]['id'] if ps else '')")"
fi
echo "proposal_id=$PROP_ID"

echo "== vote yes (treasury has 100% stake) =="
abakosd tx gov vote "$PROP_ID" yes --from treasury $TX

cat <<EOF

Proposal $PROP_ID submitted (expedited voting period ~24h).
After it passes, run:
  TS=\$(date -u +%Y-%m-%dT%H:%M:%SZ)
  abakosd tx oracle feed aba usd 1.0 \$TS --from host $TX
  abakosd tx bme mint-act 50000000uaba --from treasury $TX
  abakosd tx bank send treasury TENANT_ADDR 100000000uact --from treasury $TX

Then re-run scripts/30-test-deploy.sh on the provider VM.
EOF
