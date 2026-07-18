#!/usr/bin/env python3
"""Abakos Provider Agent (sandbox MVP).

Demonstrates the Abakos differentiator end-to-end against the live sandbox chain:

  1. Rent-first scheduler  - serve Console rentals/jobs first; only *idle* GPU/CPU
     capacity is used for mining (sandbox has no rentals yet -> fully idle).
  2. Profitability oracle   - pick the most profitable coin using *live* market
     prices (CoinGecko) x illustrative per-GPU yields.
  3. Idle mining            - accrue mining proceeds (USD) for the idle fleet
     (simulated: a real miner earns nothing meaningful on a VPS and would only
     obscure the on-chain flow, which is the part that matters here).
  4. Buyback -> ABA         - convert proceeds to ABA at the live Uniswap-v2
     WABA/USDC spot (eth_call token balances); falls back to ABA_PRICE_USD if RPC is down.
  5. Split 88 / 4 / 4 / 4   - 88% host, 4% stakers (community/reward pool), 4%
     treasury, 4% burn (sent to an unspendable burn address). REAL on-chain
     transfers, visible in the explorer.
  6. Payout by shares       - each provider is paid in ABA proportional to the
     VERIFIED accepted shares the stratum proxy counted for its ABA address
     (/shares); self-reported hashrate is only a display/fallback. Shares cannot
     be faked, so the payout basis is trustless.

Everything on-chain is real; only the mining hashing itself is simulated. ABA on
this network has no value. Serves JSON at :8091/stats for the dashboard.

Sandbox buyback still pays from the genesis `liquidity` account (no private key
for an EVM swap wallet on the agent yet); the *price* is the live DEX quote
from the same Uniswap-v2 pool used by abakos.ai/dex. Staker share funds the
community pool. Mainnet would execute a real USDC->ABA swap and route staker
share via a protocol module.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- config ---------------------------------------------------------------
HOME = os.environ.get("ABA_HOME", "/root/.abakos")
CHAIN_ID = os.environ.get("ABA_CHAIN_ID", "abakos-sandbox-1")
NODE = os.environ.get("ABA_NODE", "tcp://127.0.0.1:26657")
BIN = os.environ.get("ABA_BIN", "abakosd")
SOURCE_KEY = os.environ.get("ABA_SOURCE_KEY", "liquidity")   # buyback market source
HOST_KEY = os.environ.get("ABA_HOST_KEY", "host")            # simulated compute host
TREASURY_KEY = os.environ.get("ABA_TREASURY_KEY", "treasury")
PORT = int(os.environ.get("ABA_AGENT_PORT", "8091"))
STATE_PATH = os.environ.get("ABA_AGENT_STATE", "/opt/abakos-agent/state.json")

ABA_PRICE_USD = float(os.environ.get("ABA_PRICE_USD", "0.25"))  # fallback if DEX RPC down
EVM_RPC = os.environ.get("ABA_EVM_RPC", "http://127.0.0.1:8545")
# Same Uniswap-v2 WABA/USDC pool as site/src/dex.body.html
WABA = os.environ.get("ABA_WABA", "0x6F1212300a629A28cB87FDDa66a29B29A62af887")
USDC = os.environ.get("ABA_USDC", "0x17Ecb8BcaDbe756c1bB0DDb3a6dbd169741C05F9")
PAIR = os.environ.get("ABA_PAIR", "0x6C50f8b591f91Be81f7dC36B878427256850BA43")
ROUTER = os.environ.get("ABA_ROUTER", "0x3E321D05BC2De36152Db588bCbec252Bac87902b")
# keccak256("balanceOf(address)")[:4]
_SEL_BALANCE_OF = "0x70a08231"
DEX_PRICE_TTL = int(os.environ.get("ABA_DEX_PRICE_TTL", "30"))
NUM_GPUS = int(os.environ.get("ABA_NUM_GPUS", "12"))
NUM_CPUS = int(os.environ.get("ABA_NUM_CPUS", "6"))
EPOCH_SECONDS = int(os.environ.get("ABA_EPOCH_SECONDS", "60"))
FLUSH_EVERY = int(os.environ.get("ABA_FLUSH_EVERY", "5"))    # flush staker/treasury every N epochs
SIM_FLEET = os.environ.get("ABA_SIM_FLEET", "0") == "1"      # simulated demo fleet (off; real providers mine now)
ORACLE_TTL = int(os.environ.get("ABA_ORACLE_TTL", "300"))
_dex_price_cache = {"ts": 0.0, "price": ABA_PRICE_USD, "source": "fallback"}

# Payout attribution. "shares" (default) pays each provider by the VERIFIED accepted
# shares the stratum proxy counted for its ABA address -- self-reported hashrate can
# be faked, accepted shares cannot. "hashrate" falls back to the POST /report values.
PROXY_HTTP = os.environ.get("ABA_PROXY_HTTP", "http://127.0.0.1:8092").rstrip("/")
PAY_SOURCE = os.environ.get("ABA_PAY_SOURCE", "shares")     # "shares" | "hashrate"
PROXY_TTL = int(os.environ.get("ABA_PROXY_TTL", "20"))
_shares_cache = {"ts": 0.0, "data": None}

SPLIT = {"host": 0.88, "stakers": 0.04, "treasury": 0.04, "burn": 0.04}
BURN_EVM = os.environ.get("ABA_BURN_EVM", "0x000000000000000000000000000000000000dEaD")  # de-facto burn (no key)
FEE = "0uaba"
GAS = "220000"

# Profit-switching by REVENUE per hashrate -- the same principle auto-miners use
# (NiceHash, multipools like Zergpool/Zpool/Prohashing, Hive OS / minerstat):
# revenue/day = (my_hashrate / network_hashrate) x blocks/day x block_reward x price,
# using difficulty from WhatToMine (GPU) and p2pool.observer (Monero/CPU) and USD
# price from CoinGecko. Electricity is intentionally NOT factored in: it is
# host-specific and idle hardware is already running.
GPU_PROFILE = {  # WhatToMine algorithm name -> hashrate H/s (one representative GPU)
    "KawPow": 24e6, "Ethash": 62e6, "Etchash": 62e6, "Autolykos": 200e6, "Octopus": 78e6,
}
GPU_TAGS = ["RVN", "ETC", "ERG", "CFX", "ETHW"]
CPU_HS = 12000.0  # RandomX (Monero) on a representative CPU
CG_IDS = {"RVN": "ravencoin", "ETC": "ethereum-classic", "ERG": "ergo",
          "CFX": "conflux-token", "ETHW": "ethereum-pow-iou", "XMR": "monero"}
FALLBACK_PRICE = {"RVN": 0.0038, "ETC": 7.0, "ERG": 0.22, "CFX": 0.046, "ETHW": 1.1, "XMR": 330.0}
_oracle_cache = {"ts": 0, "data": None}

_lock = threading.Lock()
_state = {
    "running": True,
    "started_at": datetime.now(timezone.utc).isoformat(),
    "epoch": 0,
    "epoch_seconds": EPOCH_SECONDS,
    "num_gpus": NUM_GPUS,
    "aba_price_usd": ABA_PRICE_USD,
    "aba_price_source": "fallback",
    "dex": {"pair": PAIR, "waba": WABA, "usdc": USDC, "router": ROUTER, "rpc": EVM_RPC},
    "buyback": {"enabled": False, "wallet": None, "mode": "cosmos-transfer"},
    "split": {"host_pct": 88, "stakers_pct": 4, "treasury_pct": 4, "burn_pct": 4},
    "rent_first": {"active_rentals": 0, "idle_fraction": 1.0},
    "payout_basis": {"source": "shares", "proxy": PROXY_HTTP, "window_total_shares": 0.0, "providers_paid": 0},
    "oracle": {},
    "totals": {"mined_usd": 0.0, "aba_bought": 0.0, "host_aba": 0.0, "stakers_aba": 0.0, "treasury_aba": 0.0, "burn_aba": 0.0},
    "pending": {"stakers_uaba": 0, "treasury_uaba": 0, "burn_uaba": 0},
    "addresses": {},
    "host": {"address": None, "balance_aba": None},
    "recent_payouts": [],
    "note": "Sandbox. ABA has no value. Mining is simulated; on-chain payouts are real. ABA price from live DEX.",
}


_providers = {}  # abakos1 address -> live real-miner report + cumulative ABA earned


def _now():
    return datetime.now(timezone.utc).isoformat()


def sh(args, timeout=45):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def key_addr(name):
    p = sh([BIN, "keys", "show", name, "-a", "--keyring-backend", "test", "--home", HOME])
    return p.stdout.strip() if p.returncode == 0 else None


def balance_uaba(addr):
    p = sh([BIN, "query", "bank", "balances", addr, "--node", NODE, "--output", "json"])
    if p.returncode != 0:
        return None
    try:
        bals = json.loads(p.stdout).get("balances", [])
        for b in bals:
            if b.get("denom") == "uaba":
                return int(b.get("amount", "0"))
        return 0
    except Exception:
        return None


def broadcast_and_wait(args, wait=40):
    """Broadcast (sync) then poll until committed so the account sequence advances."""
    p = sh(args)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "tx failed").strip()[:300])
    try:
        out = json.loads(p.stdout)
    except Exception:
        raise RuntimeError("bad tx output: " + (p.stdout or "")[:200])
    if out.get("code", 0) not in (0, "0"):
        raise RuntimeError("checktx code %s: %s" % (out.get("code"), str(out.get("raw_log"))[:200]))
    txhash = out.get("txhash")
    deadline = time.time() + wait
    while time.time() < deadline:
        q = sh([BIN, "query", "tx", txhash, "--node", NODE, "--output", "json"])
        if q.returncode == 0:
            try:
                r = json.loads(q.stdout)
                return {"txhash": txhash, "height": r.get("height"), "code": r.get("code", 0)}
            except Exception:
                pass
        time.sleep(1.5)
    return {"txhash": txhash, "height": None, "code": None}


def send(from_key, to_addr, uaba):
    return broadcast_and_wait([
        BIN, "tx", "bank", "send", from_key, to_addr, "%duaba" % uaba,
        "--keyring-backend", "test", "--home", HOME, "--chain-id", CHAIN_ID,
        "--node", NODE, "--gas", GAS, "--fees", FEE, "-y",
        "--broadcast-mode", "sync", "--output", "json",
    ])


def fund_community_pool(from_key, uaba):
    return broadcast_and_wait([
        BIN, "tx", "distribution", "fund-community-pool", "%duaba" % uaba,
        "--from", from_key, "--keyring-backend", "test", "--home", HOME,
        "--chain-id", CHAIN_ID, "--node", NODE, "--gas", GAS, "--fees", FEE, "-y",
        "--broadcast-mode", "sync", "--output", "json",
    ])


def _rpc(method: str, params: list, timeout: int = 15):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        EVM_RPC, data=body,
        headers={"Content-Type": "application/json", "User-Agent": "abakos-agent"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    if resp.get("error"):
        raise RuntimeError(str(resp["error"])[:200])
    return resp.get("result")


def _eth_call(to_addr: str, data: str) -> str:
    result = _rpc("eth_call", [{"to": to_addr, "data": data}, "latest"], timeout=8)
    if not result or result == "0x":
        raise RuntimeError("empty eth_call result")
    return result


def _balance_of_data(holder: str) -> str:
    addr = holder.lower().removeprefix("0x").zfill(64)
    return _SEL_BALANCE_OF + addr


# --- EVM buyback signer (real USDC->ABA swap on the DEX) -------------------
# secp256k1 signing lives in the agent venv (eth-account/eth-abi). If those
# libraries or the buyback key are missing, BUYBACK stays disabled and payouts
# fall back to the cosmos bank send from the liquidity account.
BUYBACK_KEYFILE = os.environ.get("ABA_BUYBACK_KEYFILE", "/opt/abakos-agent/buyback.key")
MIN_SWAP_USDC = int(os.environ.get("ABA_MIN_SWAP_USDC", "1000"))     # 0.001 USDC (6-dec) floor per swap
SWAP_SLIPPAGE = float(os.environ.get("ABA_SWAP_SLIPPAGE", "0.02"))
SWAP_GAS = int(os.environ.get("ABA_SWAP_GAS", "300000"))
EVM_CHAIN_ID = int(os.environ.get("ABA_EVM_CHAIN_ID", "9721"))
_SEL_APPROVE = "0x095ea7b3"          # approve(address,uint256)
_SEL_ALLOWANCE = "0xdd62ed3e"        # allowance(address,address)
_SEL_SWAP_T4ETH = "0x18cbafe5"       # swapExactTokensForETH(uint256,uint256,address[],address,uint256)
_SEL_GET_AMOUNTS_OUT = "0xd06ca61f"  # getAmountsOut(uint256,address[])
_B32CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_buyback = {"loaded": False, "acct": None, "address": None, "error": None}


def _load_buyback():
    if _buyback["loaded"]:
        return _buyback["acct"]
    _buyback["loaded"] = True
    try:
        from eth_account import Account  # noqa: PLC0415
        with open(BUYBACK_KEYFILE) as f:
            key = f.read().strip()
        acct = Account.from_key(key)
        _buyback["acct"] = acct
        _buyback["address"] = acct.address
    except Exception as e:
        _buyback["error"] = str(e)[:200]
    return _buyback["acct"]


def buyback_enabled() -> bool:
    return _load_buyback() is not None


def bech32_to_evm(addr: str) -> str:
    """abakos1... -> 0x<20-byte account>. Same 20 account bytes in both worlds."""
    pos = addr.rfind("1")
    if pos < 0:
        raise ValueError("not a bech32 address: " + addr)
    dec = [_B32CHARSET.index(c) for c in addr[pos + 1:]]
    dec = dec[:-6]  # strip 6-char checksum
    acc = bits = 0
    out = bytearray()
    for v in dec:
        acc = (acc << 5) | v
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    if len(out) != 20:
        raise ValueError("bad address length %d for %s" % (len(out), addr))
    return "0x" + out.hex()


def _bech32_polymod(values):
    gen = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def evm_to_bech32(hex_addr: str, hrp: str = "abakos") -> str:
    """0x<20-byte> -> abakos1... (same account bytes). Used for the burn address."""
    raw = bytes.fromhex(hex_addr.lower().removeprefix("0x").zfill(40))
    acc = bits = 0
    data = []
    for b in raw:
        acc = (acc << 8) | b
        bits += 8
        while bits >= 5:
            bits -= 5
            data.append((acc >> bits) & 31)
    if bits:
        data.append((acc << (5 - bits)) & 31)
    hrp_exp = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    polymod = _bech32_polymod(hrp_exp + data + [0, 0, 0, 0, 0, 0]) ^ 1
    chk = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_B32CHARSET[d] for d in data + chk)


def _addr32(addr: str) -> str:
    return addr.lower().removeprefix("0x").zfill(64)


def _wait_receipt(txh: str, timeout: int = 60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rc = _rpc("eth_getTransactionReceipt", [txh], timeout=8)
        if rc:
            return rc
        time.sleep(1.5)
    return None


def _send_evm_tx(to_addr: str, data: str, gas: int, value: int = 0):
    acct = _load_buyback()
    if acct is None:
        raise RuntimeError("buyback key not loaded: " + str(_buyback["error"]))
    nonce = int(_rpc("eth_getTransactionCount", [acct.address, "pending"]), 16)
    gp = int(_rpc("eth_gasPrice", []), 16)
    if gp > 0:
        gp = int(gp * 1.25)  # small buffer only if the chain sets a non-zero base fee (zero-fee network -> 0)
    tx = {
        "to": to_addr, "value": value, "gas": gas, "gasPrice": gp,
        "nonce": nonce, "chainId": EVM_CHAIN_ID, "data": data,
    }
    signed = acct.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    txh = _rpc("eth_sendRawTransaction", ["0x" + raw.hex()])
    rc = _wait_receipt(txh)
    if rc is not None and int(rc.get("status", "0x1"), 16) == 0:
        raise RuntimeError("evm tx reverted: " + txh)
    return txh, rc


def buyback_swap(usdc_in: int, to_evm: str):
    """Market-buy native ABA with `usdc_in` (6-dec) USDC on the DEX, delivered to `to_evm`.

    Returns (txhash, aba_out_wei). Approves the router once (max allowance)."""
    from eth_abi import encode as abi_encode, decode as abi_decode  # noqa: PLC0415
    acct = _load_buyback()
    if acct is None:
        raise RuntimeError("buyback disabled")
    allowance = int(_eth_call(USDC, _SEL_ALLOWANCE + _addr32(acct.address) + _addr32(ROUTER)), 16)
    if allowance < usdc_in:
        data = _SEL_APPROVE + abi_encode(["address", "uint256"], [ROUTER, (1 << 256) - 1]).hex()
        _send_evm_tx(USDC, data, gas=80000)
    path = [USDC, WABA]
    ao = _eth_call(ROUTER, _SEL_GET_AMOUNTS_OUT + abi_encode(["uint256", "address[]"], [usdc_in, path]).hex())
    amounts = abi_decode(["uint256[]"], bytes.fromhex(ao[2:]))[0]
    expected = int(amounts[-1])
    min_out = int(expected * (1.0 - SWAP_SLIPPAGE))
    deadline = int(time.time()) + 300
    data = _SEL_SWAP_T4ETH + abi_encode(
        ["uint256", "uint256", "address[]", "address", "uint256"],
        [usdc_in, min_out, path, to_evm, deadline],
    ).hex()
    txh, _ = _send_evm_tx(ROUTER, data, gas=SWAP_GAS)
    return txh, expected


def fetch_dex_aba_price() -> tuple[float, str]:
    """Spot USDC per ABA from Uniswap-v2 pair token balances."""
    now = time.time()
    if now - _dex_price_cache["ts"] < DEX_PRICE_TTL and _dex_price_cache["price"] > 0:
        return _dex_price_cache["price"], _dex_price_cache["source"]
    try:
        ra_hex = _eth_call(WABA, _balance_of_data(PAIR))
        ru_hex = _eth_call(USDC, _balance_of_data(PAIR))
        reserve_aba_wei = int(ra_hex, 16)
        reserve_usdc = int(ru_hex, 16)
        if reserve_aba_wei <= 0 or reserve_usdc <= 0:
            raise RuntimeError("empty DEX reserves")
        # WABA is 18-dec; USDC is 6-dec → USD/ABA = usdc/1e6 / (aba/1e18)
        price = (reserve_usdc / 1e6) / (reserve_aba_wei / 1e18)
        if price <= 0:
            raise RuntimeError("non-positive DEX price")
        _dex_price_cache.update(ts=now, price=price, source="uniswap-v2")
        return price, "uniswap-v2"
    except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, OSError):
        _dex_price_cache.update(ts=now, price=ABA_PRICE_USD, source="fallback")
        return ABA_PRICE_USD, "fallback"


def fetch_prices():
    ids = ",".join(sorted(set(CG_IDS.values())))
    url = "https://api.coingecko.com/api/v3/simple/price?ids=%s&vs_currencies=usd" % ids
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "abakos-agent"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.load(r)
        out = {}
        for tag, cg in CG_IDS.items():
            v = data.get(cg, {}).get("usd")
            out[tag] = float(v) if v else FALLBACK_PRICE.get(tag, 0.0)
        return out, "coingecko"
    except Exception:
        return dict(FALLBACK_PRICE), "fallback"


def fetch_wtm():
    """WhatToMine coins.json -> {tag: coin} with network hashrate, block time and reward."""
    req = urllib.request.Request("https://whattomine.com/coins.json",
                                 headers={"User-Agent": "Mozilla/5.0 abakos-agent"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    by_tag = {}
    for name, c in (data.get("coins") or {}).items():
        tag = c.get("tag")
        if tag and tag not in by_tag:
            c["_name"] = name
            by_tag[tag] = c
    return by_tag


def fetch_xmr():
    """Monero (RandomX/CPU) network stats from p2pool.observer."""
    try:
        req = urllib.request.Request("https://p2pool.observer/api/network/stats",
                                     headers={"User-Agent": "abakos-agent"})
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.load(r)
        return {"nethash": float(d["difficulty"]) / 120.0, "block_time": 120.0,
                "block_reward": float(d.get("reward", 600000000000)) / 1e12, "src": "p2pool.observer"}
    except Exception:
        return {"nethash": 5.8e9, "block_time": 120.0, "block_reward": 0.6, "src": "fallback"}


def coin_revenue(hs, nethash, block_time, block_reward, price_usd):
    """revenue/day = (my_hashrate / network_hashrate) * blocks/day * block_reward * price."""
    try:
        nethash = float(nethash); block_time = float(block_time); block_reward = float(block_reward)
        if nethash <= 0 or block_time <= 0:
            return None
        coins_day = (hs / nethash) * (86400.0 / block_time) * block_reward
        return coins_day * float(price_usd)
    except Exception:
        return None


def run_oracle():
    now = time.time()
    if _oracle_cache["data"] and now - _oracle_cache["ts"] < ORACLE_TTL:
        return _oracle_cache["data"]
    prices, psrc = fetch_prices()
    try:
        wtm, wsrc = fetch_wtm(), "whattomine"
    except Exception:
        wtm, wsrc = {}, "unavailable"
    cands = []
    for tag in GPU_TAGS:
        c = wtm.get(tag)
        if not c or c.get("algorithm") not in GPU_PROFILE:
            continue
        hs = GPU_PROFILE[c["algorithm"]]
        rev = coin_revenue(hs, c.get("nethash"), c.get("block_time"), c.get("block_reward"), prices.get(tag, 0.0))
        if rev is not None:
            cands.append({"device": "GPU", "coin": c.get("_name", tag), "tag": tag, "algorithm": c["algorithm"],
                          "hashrate_hs": hs, "price_usd": round(prices.get(tag, 0.0), 6),
                          "revenue_usd_day": round(rev, 4)})
    xmr = fetch_xmr()
    rev = coin_revenue(CPU_HS, xmr["nethash"], xmr["block_time"], xmr["block_reward"], prices.get("XMR", 0.0))
    if rev is not None:
        cands.append({"device": "CPU", "coin": "Monero", "tag": "XMR", "algorithm": "RandomX",
                      "hashrate_hs": CPU_HS, "price_usd": round(prices.get("XMR", 0.0), 2),
                      "revenue_usd_day": round(rev, 4)})
    cands.sort(key=lambda x: x["revenue_usd_day"], reverse=True)
    best_gpu = next((c for c in cands if c["device"] == "GPU"), None)
    best_cpu = next((c for c in cands if c["device"] == "CPU"), None)
    fleet_gross = (NUM_GPUS * best_gpu["revenue_usd_day"] if best_gpu else 0.0) + \
                  (NUM_CPUS * best_cpu["revenue_usd_day"] if best_cpu else 0.0)
    top = cands[0] if cands else None
    data = {
        "num_gpus": NUM_GPUS, "num_cpus": NUM_CPUS,
        "gpu": best_gpu, "cpu": best_cpu,
        "best_coin": top["coin"] if top else "-", "best_symbol": top["tag"] if top else "-",
        "candidates": cands, "fleet_gross_usd_day": round(fleet_gross, 6),
        "sources": [wsrc, xmr["src"], psrc], "updated": _now(),
    }
    _oracle_cache.update({"ts": now, "data": data})
    return data


def add_payout(kind, uaba, txhash, coin):
    entry = {"time": _now(), "type": kind, "amount_aba": round(uaba / 1e6, 6),
             "txhash": txhash, "coin": coin}
    _state["recent_payouts"].insert(0, entry)
    del _state["recent_payouts"][20:]


def fetch_proxy_shares():
    """Verified accepted shares per ABA address from the stratum proxy (/shares).

    Returns {total, per_address, window_sec, source}. `total`/`per_address` are
    difficulty-weighted (≈ hashes done), so they double as a fair payout basis and
    an on-chain-independent hashrate estimate. Cached briefly; empty on failure."""
    now = time.time()
    if _shares_cache["data"] and now - _shares_cache["ts"] < PROXY_TTL:
        return _shares_cache["data"]
    out = {"total": 0.0, "per_address": {}, "window_sec": 3600, "source": "unavailable"}
    try:
        req = urllib.request.Request(PROXY_HTTP + "/shares", headers={"User-Agent": "abakos-agent"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.load(r)
        win = d.get("window") or {}
        per = {a: float(w) for a, w in (win.get("per_address") or {}).items()
               if str(a).startswith("abakos1") and float(w) > 0}
        out = {"total": float(win.get("total") or 0.0), "per_address": per,
               "window_sec": int(d.get("window_sec") or 3600), "source": "proxy"}
    except Exception as e:
        out["error"] = str(e)[:160]
    _shares_cache.update(ts=now, data=out)
    return out


def pay_provider(addr, pusd, coin, use_buyback, aba_price):
    """Pay ONE provider `pusd` USD for this epoch, split 88 / 4 / 4 / 4.

    Host share is a real USDC->ABA buyback on the DEX (accumulated to the dust
    floor, then swapped straight to the provider); staker/treasury/burn shares
    accrue to `pending` and flush periodically. Mirrors the sim-fleet accounting."""
    if pusd <= 0 or aba_price <= 0:
        return
    ptot = int(round(pusd / aba_price * 1e6))
    ph = int(ptot * SPLIT["host"]); ps = int(ptot * SPLIT["stakers"])
    pb = int(ptot * SPLIT["burn"]); pt = ptot - ph - ps - pb
    if ph <= 0:
        return
    with _lock:
        _providers.setdefault(addr, {"address": addr, "earned_aba": 0.0})
    try:
        if use_buyback:
            with _lock:
                pend = int(_providers.get(addr, {}).get("pending_host_usdc", 0)) + int(pusd * SPLIT["host"] * 1e6)
            if pend >= MIN_SWAP_USDC:
                txh, out_wei = buyback_swap(pend, bech32_to_evm(addr))
                with _lock:
                    if addr in _providers:
                        _providers[addr]["earned_aba"] = round(_providers[addr].get("earned_aba", 0.0) + out_wei / 1e18, 6)
                        _providers[addr]["pending_host_usdc"] = 0
                    _state["totals"]["host_aba"] = round(_state["totals"]["host_aba"] + out_wei / 1e18, 6)
                    add_payout("buyback", int(out_wei / 1e12), txh, coin)
            else:
                with _lock:
                    if addr in _providers:
                        _providers[addr]["pending_host_usdc"] = pend
            with _lock:
                _state["totals"]["mined_usd"] = round(_state["totals"]["mined_usd"] + pusd, 6)
                _state["totals"]["aba_bought"] = round(_state["totals"]["aba_bought"] + ptot / 1e6, 6)
                _state["pending"]["stakers_uaba"] += ps
                _state["pending"]["treasury_uaba"] += pt
                _state["pending"]["burn_uaba"] += pb
        else:
            r = send(SOURCE_KEY, addr, ph)
            with _lock:
                if addr in _providers:
                    _providers[addr]["earned_aba"] = round(_providers[addr].get("earned_aba", 0.0) + ph / 1e6, 6)
                _state["totals"]["mined_usd"] = round(_state["totals"]["mined_usd"] + pusd, 6)
                _state["totals"]["aba_bought"] = round(_state["totals"]["aba_bought"] + ptot / 1e6, 6)
                _state["totals"]["host_aba"] = round(_state["totals"]["host_aba"] + ph / 1e6, 6)
                _state["pending"]["stakers_uaba"] += ps
                _state["pending"]["treasury_uaba"] += pt
                _state["pending"]["burn_uaba"] += pb
                add_payout("provider", ph, r["txhash"], coin)
    except Exception as e:
        with _lock:
            _state["last_error"] = "provider payout: " + str(e)[:200]


def save_state():
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w") as f:
            json.dump(_state, f)
    except Exception:
        pass


def load_state():
    try:
        with open(STATE_PATH) as f:
            saved = json.load(f)
        for k in ("epoch", "recent_payouts", "started_at"):
            if k in saved:
                _state[k] = saved[k]
        # Merge (don't replace) so newly added keys like burn_aba/burn_uaba keep defaults.
        for k in ("totals", "pending"):
            if isinstance(saved.get(k), dict):
                _state[k].update(saved[k])
    except Exception:
        pass


def epoch_loop():
    while True:
        try:
            step()
        except Exception as e:
            with _lock:
                _state["last_error"] = str(e)[:300]
        time.sleep(EPOCH_SECONDS)


def step():
    oracle = run_oracle()
    aba_price, price_src = fetch_dex_aba_price()
    with _lock:
        _state["epoch"] += 1
        _state["oracle"] = oracle
        _state["aba_price_usd"] = round(aba_price, 8)
        _state["aba_price_source"] = price_src
        _state["rent_first"] = {"active_rentals": 0, "idle_fraction": 1.0}
        epoch = _state["epoch"]
        coin = oracle.get("best_symbol") or "-"

    use_buyback = buyback_enabled()

    # Optional simulated demo fleet -- OFF by default now that real providers mine.
    if SIM_FLEET:
        usd = oracle["fleet_gross_usd_day"] * (EPOCH_SECONDS / 86400.0)
        aba = usd / aba_price
        total_uaba = int(round(aba * 1e6))
        hu = int(total_uaba * SPLIT["host"]); su = int(total_uaba * SPLIT["stakers"]); bu = int(total_uaba * SPLIT["burn"]); tu = total_uaba - hu - su - bu
        with _lock:
            _state["totals"]["mined_usd"] = round(_state["totals"]["mined_usd"] + usd, 6)
            _state["totals"]["aba_bought"] = round(_state["totals"]["aba_bought"] + aba, 6)
            _state["pending"]["stakers_uaba"] += su
            _state["pending"]["treasury_uaba"] += tu
            _state["pending"]["burn_uaba"] += bu
        if hu > 0:
            host_addr = _state["host"]["address"]
            try:
                host_usdc = int(usd * SPLIT["host"] * 1e6)
                if use_buyback and host_usdc >= MIN_SWAP_USDC:
                    txh, out_wei = buyback_swap(host_usdc, bech32_to_evm(host_addr))
                    with _lock:
                        _state["totals"]["host_aba"] = round(_state["totals"]["host_aba"] + out_wei / 1e18, 6)
                        add_payout("buyback", int(out_wei / 1e12), txh, coin)
                else:
                    r = send(SOURCE_KEY, host_addr, hu)
                    with _lock:
                        _state["totals"]["host_aba"] = round(_state["totals"]["host_aba"] + hu / 1e6, 6)
                        add_payout("host", hu, r["txhash"], coin)
            except Exception as e:
                with _lock:
                    _state["last_error"] = "host payout: " + str(e)[:200]

    # Attribute this epoch's mining revenue to providers, then pay each 88/4/4/4.
    # PRIMARY basis: VERIFIED accepted shares from the stratum proxy (cannot be
    # faked). FALLBACK: self-reported live hashrate from POST /report.
    cpu_rate = (oracle["cpu"]["revenue_usd_day"] / oracle["cpu"]["hashrate_hs"]) if oracle.get("cpu") and oracle["cpu"].get("hashrate_hs") else 0.0
    gpu_rate = (oracle["gpu"]["revenue_usd_day"] / oracle["gpu"]["hashrate_hs"]) if oracle.get("gpu") and oracle["gpu"].get("hashrate_hs") else 0.0
    mining_coin = (oracle.get("cpu") or {}).get("tag") or coin

    attribution = {}     # abakos1 address -> USD earned this epoch
    shares = fetch_proxy_shares() if PAY_SOURCE == "shares" else {"total": 0.0, "per_address": {}, "source": "disabled"}
    if shares.get("total", 0) > 0 and cpu_rate > 0:
        # Weighted shares ≈ hashes done, so shares/window ≈ effective fleet hashrate.
        wsec = max(1, int(shares.get("window_sec", 3600)))
        fleet_hs = shares["total"] / wsec
        epoch_usd = fleet_hs * cpu_rate * (EPOCH_SECONDS / 86400.0)
        tot = shares["total"]
        with _lock:
            for a, w in shares["per_address"].items():
                attribution[a] = epoch_usd * (w / tot)
                p = _providers.setdefault(a, {"address": a, "earned_aba": 0.0})
                p["share_hs"] = round(w / wsec, 2)
                p["window_shares"] = round(w, 2)
                p["share_fraction"] = round(w / tot, 6)
                p["last_report"] = time.time()
                p.setdefault("cpu_coin", mining_coin)
        attr_src = "proxy-shares"
    else:
        now = time.time()
        with _lock:
            active = [dict(p) for p in _providers.values() if now - p.get("last_report", 0) < 180]
        for p in active:
            pusd = (p.get("cpu_hs", 0) * cpu_rate + p.get("gpu_hs", 0) * gpu_rate) * (EPOCH_SECONDS / 86400.0)
            if pusd > 0:
                attribution[p["address"]] = pusd
        attr_src = "self-report" if attribution else (shares.get("source") or "none")

    for addr, pusd in attribution.items():
        pay_provider(addr, pusd, mining_coin, use_buyback, aba_price)

    with _lock:
        _state["payout_basis"] = {
            "source": attr_src, "proxy": PROXY_HTTP,
            "window_total_shares": round(shares.get("total", 0.0), 2),
            "providers_paid": len(attribution),
        }

    # Flush staker + treasury + burn shares periodically (from real providers + optional sim).
    if epoch % FLUSH_EVERY == 0:
        with _lock:
            s = _state["pending"]["stakers_uaba"]; t = _state["pending"]["treasury_uaba"]; b = _state["pending"]["burn_uaba"]
        if s > 0:
            try:
                r = fund_community_pool(SOURCE_KEY, s)
                with _lock:
                    _state["totals"]["stakers_aba"] = round(_state["totals"]["stakers_aba"] + s / 1e6, 6)
                    _state["pending"]["stakers_uaba"] = 0
                    add_payout("stakers", s, r["txhash"], coin)
            except Exception as e:
                with _lock:
                    _state["last_error"] = "stakers flush: " + str(e)[:200]
        if t > 0:
            try:
                r = send(SOURCE_KEY, _state["addresses"].get("treasury"), t)
                with _lock:
                    _state["totals"]["treasury_aba"] = round(_state["totals"]["treasury_aba"] + t / 1e6, 6)
                    _state["pending"]["treasury_uaba"] = 0
                    add_payout("treasury", t, r["txhash"], coin)
            except Exception as e:
                with _lock:
                    _state["last_error"] = "treasury flush: " + str(e)[:200]
        if b > 0:
            try:
                r = send(SOURCE_KEY, _state["addresses"].get("burn"), b)
                with _lock:
                    _state["totals"]["burn_aba"] = round(_state["totals"]["burn_aba"] + b / 1e6, 6)
                    _state["pending"]["burn_uaba"] = 0
                    add_payout("burn", b, r["txhash"], coin)
            except Exception as e:
                with _lock:
                    _state["last_error"] = "burn flush: " + str(e)[:200]

    bal = balance_uaba(_state["host"]["address"])
    with _lock:
        if bal is not None:
            _state["host"]["balance_aba"] = round(bal / 1e6, 6)
        save_state()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in ("", "/stats", "/agent"):
            with _lock:
                resp = dict(_state)
                now = time.time()
                resp["providers"] = [{
                    "address": p["address"], "cpu_hs": p.get("cpu_hs", 0), "gpu_hs": p.get("gpu_hs", 0),
                    "cpu_coin": p.get("cpu_coin"), "gpu_coin": p.get("gpu_coin"), "miner": p.get("miner"),
                    "os": p.get("os"), "earned_aba": p.get("earned_aba", 0.0),
                    "share_hs": p.get("share_hs", 0.0), "window_shares": p.get("window_shares", 0.0),
                    "share_fraction": p.get("share_fraction", 0.0),
                    "last_seen_s": int(now - p.get("last_report", 0)),
                    "active": (now - p.get("last_report", 0)) < 180,
                } for p in _providers.values()]
            self._send(200, resp)
        elif self.path.startswith("/health"):
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path.rstrip("/") != "/report":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        addr = str(body.get("address", "")).strip()
        if not addr.startswith("abakos1"):
            return self._send(400, {"error": "invalid address"})
        with _lock:
            p = _providers.setdefault(addr, {"address": addr, "earned_aba": 0.0})
            p["cpu_hs"] = float(body.get("cpu_hashrate_hs") or 0)
            p["gpu_hs"] = float(body.get("gpu_hashrate_hs") or 0)
            p["cpu_coin"] = body.get("cpu_coin")
            p["gpu_coin"] = body.get("gpu_coin")
            p["miner"] = body.get("miner")
            p["os"] = body.get("os")
            p["last_report"] = time.time()
        self._send(200, {"ok": True})

    def log_message(self, *a):
        return


def main():
    _state["addresses"] = {
        "source": key_addr(SOURCE_KEY),
        "host": key_addr(HOST_KEY),
        "treasury": key_addr(TREASURY_KEY),
        "burn": evm_to_bech32(BURN_EVM),
    }
    _state["host"]["address"] = _state["addresses"]["host"]
    if buyback_enabled():
        _state["buyback"] = {"enabled": True, "wallet": _buyback["address"], "mode": "dex-swap"}
    else:
        _state["buyback"] = {"enabled": False, "wallet": None, "mode": "cosmos-transfer",
                             "error": _buyback.get("error")}
    load_state()
    threading.Thread(target=epoch_loop, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
