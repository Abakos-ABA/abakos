#!/usr/bin/env bash
set -uo pipefail
BIN=/home/marlon/abakos-build/abakosd
H=/home/marlon/abktest
rm -rf "$H"
echo "[init]"
"$BIN" genesis init testnode --chain-id abakos-localtest-1 --home "$H" 2>&1 | tail -2 || true
G="$H/config/genesis.json"
python3 - "$G" <<'PY'
import json,sys
g=json.load(open(sys.argv[1]))
a=g["app_state"]
print("MODULES:", sorted(a.keys()))
for k in ("vm","evm","feemarket","precisebank","erc20"):
    if k in a:
        print("== %s ==" % k)
        print(json.dumps(a[k], indent=1)[:1800])
print("== bank.denom_metadata ==", json.dumps(a["bank"].get("denom_metadata"), indent=1))
print("== staking.bond_denom ==", a["staking"]["params"]["bond_denom"])
print("== mint.mint_denom ==", a.get("mint",{}).get("params",{}).get("mint_denom"))
print("== gov deposit ==", json.dumps(a.get("gov",{}).get("params",{}).get("min_deposit")))
PY
echo INSPECT_DONE
