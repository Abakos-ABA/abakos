#!/usr/bin/env bash
echo "=== eth_gasPrice ==="
GP=$(curl -s -m 12 -X POST -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":1,"method":"eth_gasPrice","params":[]}' https://evm-rpc.abakos.ai)
echo "$GP"
python3 - "$GP" <<'PY'
import sys, json
try:
    hx = json.loads(sys.argv[1])["result"]; wei = int(hx, 16)
    print("gasPrice wei :", wei)
    print("gasPrice gwei:", wei/1e9)
    print("gasPrice ABA :", wei/1e18)
    for g in (21000, 150000, 2000000):
        print(f"  cost of {g} gas: {g*wei/1e18:.6f} ABA")
except Exception as e:
    print("parse err", e)
PY
echo "=== feemarket base_fee (rest) ==="
curl -s -m 12 https://rest.abakos.ai/cosmos/evm/feemarket/v1/base_fee; echo
echo "=== feemarket params (rest) ==="
curl -s -m 12 https://rest.abakos.ai/cosmos/evm/feemarket/v1/params; echo
echo "VERIFY_GAS_DONE"
