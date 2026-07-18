#!/usr/bin/env bash
# Local smoke test: bring up a single-validator Abakos node WITH EVM and confirm
# it produces blocks (i.e. EVM InitGenesis + coin-config sealing succeeded).
set -uo pipefail
BIN=/home/marlon/abakos-build/abakosd
H=/home/marlon/abktest
CHAIN=abakos-localtest-1
KR="--keyring-backend test --home $H"
rm -rf "$H"
G="$H/config/genesis.json"

echo "[1] genesis init"
"$BIN" genesis init testnode --chain-id "$CHAIN" --home "$H" >/dev/null 2>&1 || true
[ -f "$G" ] || { echo "INIT_FAIL (no genesis)"; exit 1; }

echo "[2] patch genesis"
python3 - "$G" <<'PY'
import json,sys
p=sys.argv[1]; g=json.load(open(p)); a=g["app_state"]
a["staking"]["params"]["bond_denom"]="uaba"
m=a["mint"]; m["params"]["mint_denom"]="uaba"
for k in ("inflation_min","inflation_max","inflation_rate_change"): m["params"][k]="0.000000000000000000"
m["minter"]["inflation"]="0.000000000000000000"; m["minter"]["annual_provisions"]="0.000000000000000000"
for k in ("min_deposit","expedited_min_deposit"):
    for c in (a["gov"]["params"].get(k) or []): c["denom"]="uaba"
if "crisis" in a: a["crisis"]["constant_fee"]["denom"]="uaba"
# EVM: 6-decimal uaba base + 18-decimal extended aaba
a["evm"]["params"]["evm_denom"]="uaba"
a["evm"]["params"]["extended_denom_options"]={"extended_denom":"aaba"}
# faster blocks: raise consensus block gas limit
cp=g.setdefault("consensus",{}).setdefault("params",{}); cp.setdefault("block",{})["max_gas"]="100000000"
json.dump(g,open(p,"w"),indent=1); print("  patched")
PY

echo "[3] key + genesis account + gentx + collect"
"$BIN" keys add val $KR >/dev/null 2>&1
ADDR=$("$BIN" keys show val -a $KR)
echo "  val=$ADDR"
"$BIN" genesis add-account "$ADDR" 1000000000000uaba --home "$H" >/dev/null 2>&1 || "$BIN" genesis add-account "$ADDR" 1000000000000uaba --home "$H"
# self-delegate 500k ABA; min-self-delegation must be >= 0.01% of total supply
# (supply here is 1e12 uaba => floor 1e8 uaba = 100 ABA). Fee in uaba, not uakt.
"$BIN" genesis gentx val 500000000000uaba --min-self-delegation=100000000 --fees 5000uaba --gas-prices 0uaba --chain-id "$CHAIN" $KR >/tmp/gentx.log 2>&1 || { echo "  GENTX_FAIL"; tail -15 /tmp/gentx.log; }
"$BIN" genesis collect --home "$H" >/dev/null 2>&1 || "$BIN" genesis collect --home "$H"
echo -n "  validate: "; "$BIN" genesis validate --home "$H" 2>&1 | tail -1

echo "[4] config: 1s blocks + min-gas-price 0uaba"
sed -i 's/^timeout_commit = .*/timeout_commit = "1s"/' "$H/config/config.toml"
sed -i 's#^minimum-gas-prices = .*#minimum-gas-prices = "0uaba"#' "$H/config/app.toml"

echo "[5] start node (bg, ~28s)"
"$BIN" start --home "$H" --minimum-gas-prices 0uaba > /tmp/node.log 2>&1 &
NPID=$!
sleep 28
echo "--- node.log tail ---"
tail -20 /tmp/node.log
echo -n "--- height: "
"$BIN" status --home "$H" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); si=d.get('sync_info',d.get('SyncInfo',{})); print(si.get('latest_block_height'))" 2>/dev/null || echo "status failed"
echo "--- eth JSON-RPC (127.0.0.1:8545) ---"
python3 - <<'PY'
import urllib.request, json
def call(m, p=None):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p or []}).encode()
    req=urllib.request.Request("http://127.0.0.1:8545", data=body, headers={"Content-Type":"application/json"})
    try:
        r=json.load(urllib.request.urlopen(req, timeout=6)); return r.get("result", r.get("error"))
    except Exception as e:
        return "ERR: %s" % e
cid=call("eth_chainId")
print("eth_chainId   =", cid, "(expect 0x2609 = 9737? actual 9721=0x25f9)" if cid else "")
print("net_version   =", call("net_version"))
print("eth_blockNumber =", call("eth_blockNumber"))
print("eth_gasPrice  =", call("eth_gasPrice"))
PY
kill $NPID 2>/dev/null || true; wait $NPID 2>/dev/null || true
echo "LOCALRUN_DONE"
