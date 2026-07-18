#!/usr/bin/env bash
set -uo pipefail
BIN=/home/marlon/abakos-build/abakosd
H=/home/marlon/abktest
"$BIN" start --home "$H" --minimum-gas-prices 0uaba > /tmp/node.log 2>&1 &
NPID=$!
sleep 9
echo "=== evm params ==="
"$BIN" query evm params --home "$H" --output json 2>/dev/null \
  | python3 -c "import sys,json;p=json.load(sys.stdin).get('params',{});print('evm_denom =',p.get('evm_denom'));print('extended  =',p.get('extended_denom_options'))" 2>&1 \
  || "$BIN" query vm params --home "$H" 2>&1 | head -6
echo "=== bank total supply ==="
"$BIN" query bank total-supply --home "$H" --output json 2>/dev/null \
  | python3 -c "import sys,json;[print(c['denom'],c['amount']) for c in json.load(sys.stdin).get('supply',[])]" 2>&1 \
  || "$BIN" query bank total --home "$H" 2>&1 | head -8
echo "=== block time (heights 3s apart) ==="
H1=$("$BIN" status --home "$H" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['sync_info']['latest_block_height'])" 2>/dev/null)
sleep 3
H2=$("$BIN" status --home "$H" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['sync_info']['latest_block_height'])" 2>/dev/null)
echo "height $H1 -> $H2 in 3s"
kill $NPID 2>/dev/null || true; wait $NPID 2>/dev/null || true
echo VERIFY_DONE
