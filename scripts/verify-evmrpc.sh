#!/usr/bin/env bash
# Verify the public eth JSON-RPC endpoint (TLS via Caddy) once DNS is live.
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -m 12 -o /tmp/er.txt -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
    --data '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' https://evm-rpc.abakos.ai 2>/dev/null)
  echo "attempt $i: http=$code body=$(cat /tmp/er.txt 2>/dev/null)"
  [ "$code" = "200" ] && break
  sleep 8
done
echo "--- eth_blockNumber ---"
curl -s -m 12 -X POST -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}' https://evm-rpc.abakos.ai 2>/dev/null; echo
echo "VERIFY_EVMRPC_DONE"
