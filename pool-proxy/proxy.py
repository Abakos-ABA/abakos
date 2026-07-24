#!/usr/bin/env python3
"""Abakos Stratum Proxy (mine.abakos.ai) - stdlib only, runs on the node VPS.

Sits between Abakos providers and upstream pools (Kryptex). Providers connect
with their ABA address as the login/username. The proxy opens a 1:1 upstream
connection to Kryptex using OUR Kryptex account, so all mined value auto-exchanges
to USDT into our treasury. It counts ACCEPTED shares PER ABA ADDRESS and PER DEVICE
(difficulty-weighted). Those shares are the verified, fake-proof basis for the ABA
payout (provider-agent/agent.py, split 88/4/4/4).

Two stratum listeners, both relayed + verified the same way:
  * CPU: cryptonote / RandomX (Monero)  -> xmr.kryptex.network:7029   (device "cpu")
  * GPU: Pearl / PearlHash (object-params dialect, no subscribe; difficulty is the
         integer suffix of job_id) -> prl.kryptex.network:7048        (device "gpu")

HTTP stats (127.0.0.1): GET /shares, GET /me?address=abakos1..., GET /health

Env:
  ABA_PROXY_PORT       downstream CPU stratum port (default 3333)
  ABA_GPU_PORT         downstream GPU stratum port (default 3356)
  ABA_PROXY_HTTP       http stats port (default 8092, bound to 127.0.0.1)
  ABA_UPSTREAM_HOST    CPU upstream (default xmr.kryptex.network)
  ABA_UPSTREAM_PORT    CPU upstream port (default 7029)
  ABA_GPU_UPSTREAM_HOST  GPU upstream (default prl.kryptex.network)
  ABA_GPU_UPSTREAM_PORT  GPU upstream port (default 7048)
  ABA_KRYPTEX_USER     our Kryptex mining username -> upstream login = USER.<aba>
  ABA_POOL_WALLET      fallback base if no Kryptex user (e.g. an XMR address)
  ABA_UPSTREAM_PASS    upstream password (default "x")
  ABA_SHARES_DB        persist path (default ./shares.json)
  ABA_PPLNS_WINDOW     rolling window seconds for /shares (default 3600)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("ABA_PROXY_PORT", "3333"))
GPU_PORT = int(os.environ.get("ABA_GPU_PORT", "3356"))
HTTP_PORT = int(os.environ.get("ABA_PROXY_HTTP", "8092"))
# asyncio's default StreamReader limit is 64KB; Pearl (PearlHash v2, cert_version 2)
# share submits exceed that, so readline() raises "Separator is not found, and chunk
# exceed the limit" mid-session and the relay drops the connection before any share
# lands. Raise the buffer on every stream (both listeners + both upstream sockets).
STREAM_LIMIT = int(os.environ.get("ABA_STREAM_LIMIT", str(8 * 1024 * 1024)))
UP_HOST = os.environ.get("ABA_UPSTREAM_HOST", "xmr.kryptex.network")
UP_PORT = int(os.environ.get("ABA_UPSTREAM_PORT", "7029"))
GPU_UP_HOST = os.environ.get("ABA_GPU_UPSTREAM_HOST", "prl.kryptex.network")
GPU_UP_PORT = int(os.environ.get("ABA_GPU_UPSTREAM_PORT", "7048"))
KRYPTEX_USER = os.environ.get("ABA_KRYPTEX_USER", "")
POOL_WALLET = os.environ.get("ABA_POOL_WALLET", "")
UP_PASS = os.environ.get("ABA_UPSTREAM_PASS", "x")
WORKER_SEP = os.environ.get("ABA_WORKER_SEP", "/")  # Kryptex uses username/worker
SHARES_DB = os.environ.get("ABA_SHARES_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "shares.json"))
PPLNS_WINDOW = int(os.environ.get("ABA_PPLNS_WINDOW", "3600"))

ABA_RE = re.compile(r"^abakos1[0-9a-z]{6,}$")

_lock = threading.Lock()
_state = {"totals": {}, "events": [], "started": int(time.time()), "conns": 0}
_save_pending = False


def load_state():
    try:
        with open(SHARES_DB) as f:
            s = json.load(f)
        for k in ("totals", "events", "started"):
            if k in s:
                _state[k] = s[k]
    except Exception:
        pass


def save_state():
    try:
        with open(SHARES_DB, "w") as f:
            json.dump({k: _state[k] for k in ("totals", "events", "started")}, f)
    except Exception:
        pass


def prune_events():
    cutoff = time.time() - PPLNS_WINDOW
    if len(_state["events"]) > 50000 or (_state["events"] and _state["events"][0][0] < cutoff - 3600):
        _state["events"] = [e for e in _state["events"] if e[0] >= cutoff]


def record_share(addr, diff, coin, device="cpu"):
    d = diff if diff and diff > 0 else 1
    dev = "gpu" if device == "gpu" else "cpu"
    with _lock:
        t = _state["totals"].get(addr) or {}
        t[dev + "_shares"] = t.get(dev + "_shares", 0) + 1
        t[dev + "_weighted"] = t.get(dev + "_weighted", 0) + d
        t["last"] = int(time.time())
        if coin:
            t[dev + "_coin"] = coin
        _state["totals"][addr] = t
        _state["events"].append([time.time(), addr, d, dev])
        prune_events()
    save_state()


def diff_from_target(target):
    """difficulty from a cryptonote job target (hex, little-endian compact)."""
    if not target or not isinstance(target, str):
        return 1
    hex_s = target[2:] if target.startswith("0x") else target
    try:
        if len(hex_s) <= 8:
            le = bytes.fromhex(hex_s.rjust(8, "0"))[::-1]
            v = int.from_bytes(le, "big")
            return max(1, 0xFFFFFFFF // v) if v > 0 else 1
        b = bytes.fromhex(hex_s)[:8][::-1]
        v = int.from_bytes(b, "big")
        return max(1, (1 << 64) // v) if v > 0 else 1
    except Exception:
        return 1


def window_shares():
    cutoff = time.time() - PPLNS_WINDOW
    dev = {"cpu": {"total": 0, "per_address": {}, "count": {}},
           "gpu": {"total": 0, "per_address": {}, "count": {}}}
    out = {}
    total = 0
    with _lock:
        for e in _state["events"]:
            ts = e[0]
            if ts < cutoff:
                continue
            addr, d = e[1], e[2]
            device = "gpu" if (len(e) > 3 and e[3] == "gpu") else "cpu"
            dv = dev[device]
            dv["per_address"][addr] = dv["per_address"].get(addr, 0) + d
            dv["count"][addr] = dv["count"].get(addr, 0) + 1
            dv["total"] += d
            out[addr] = out.get(addr, 0) + d
            total += d
    return {"total": total, "per_address": out, "cpu": dev["cpu"], "gpu": dev["gpu"]}


async def handle_miner(down_reader, down_writer, first_line=None):
    peer = down_writer.get_extra_info("peername")
    with _lock:
        _state["conns"] += 1
    aba = {"addr": None, "coin": None}
    job_diff = {}          # job_id -> difficulty
    pending = {}           # rpc id -> difficulty (credit on OK)
    up_reader = up_writer = None

    def log(m):
        print("[%s%s] %s" % (peer, (" " + aba["addr"][:12]) if aba["addr"] else "", m), flush=True)

    async def pump_up_to_down():
        try:
            while True:
                line = await up_reader.readline()
                if not line:
                    break
                s = line.decode(errors="ignore").strip()
                if not s:
                    continue
                try:
                    msg = json.loads(s)
                except Exception:
                    down_writer.write(line)
                    await down_writer.drain()
                    continue
                res = msg.get("result")
                if isinstance(res, dict) and isinstance(res.get("job"), dict):
                    j = res["job"]
                    if j.get("job_id"):
                        job_diff[j["job_id"]] = diff_from_target(j.get("target"))
                if msg.get("method") == "job" and isinstance(msg.get("params"), dict):
                    j = msg["params"]
                    if j.get("job_id"):
                        job_diff[j["job_id"]] = diff_from_target(j.get("target"))
                mid = msg.get("id")
                if mid is not None and mid in pending:
                    diff = pending.pop(mid)
                    ok = (not msg.get("error")) and (res == True or (isinstance(res, dict) and res.get("status") == "OK"))
                    if ok and aba["addr"]:
                        record_share(aba["addr"], diff, aba["coin"])
                down_writer.write((json.dumps(msg) + "\n").encode())
                await down_writer.drain()
        except Exception:
            pass

    try:
        first = first_line
        while True:
            if first is not None:
                line, first = first, None
            else:
                line = await down_reader.readline()
            if not line:
                break
            s = line.decode(errors="ignore").strip()
            if not s:
                continue
            try:
                msg = json.loads(s)
            except Exception:
                if up_writer:
                    up_writer.write(line)
                    await up_writer.drain()
                continue

            if msg.get("method") == "login" and up_writer is None:
                login = str((msg.get("params") or {}).get("login") or "").strip()
                base = login.split(".")[0]
                if not ABA_RE.match(base):
                    down_writer.write((json.dumps({"id": msg.get("id"), "jsonrpc": "2.0",
                                                   "error": {"code": -1, "message": "login must be your abakos1 address"},
                                                   "result": None}) + "\n").encode())
                    await down_writer.drain()
                    log("rejected login: " + login[:24])
                    break
                aba["addr"] = base
                algo = (msg.get("params") or {}).get("algo")
                if isinstance(algo, list) and algo:
                    aba["coin"] = algo[0]
                # connect upstream + rewrite login
                try:
                    up_reader, up_writer = await asyncio.open_connection(UP_HOST, UP_PORT, limit=STREAM_LIMIT)
                except Exception as e:
                    log("upstream connect failed: " + str(e)[:120])
                    break
                # short upstream worker tag (pools cap worker length); real per-user
                # attribution is done here in the proxy by the full ABA address.
                worker = re.sub(r"[^a-z0-9]", "", aba["addr"][7:])[:12] or "abk"
                if KRYPTEX_USER:
                    up_login = KRYPTEX_USER + WORKER_SEP + worker
                elif POOL_WALLET:
                    up_login = POOL_WALLET + WORKER_SEP + worker
                else:
                    up_login = login
                params = dict(msg.get("params") or {})
                params["login"] = up_login
                params["pass"] = UP_PASS
                msg["params"] = params
                up_writer.write((json.dumps(msg) + "\n").encode())
                await up_writer.drain()
                log("login ok -> upstream %s:%d as %s" % (UP_HOST, UP_PORT, up_login[:32]))
                asyncio.ensure_future(pump_up_to_down())
                continue

            if msg.get("method") == "submit" and isinstance(msg.get("params"), dict):
                jid = msg["params"].get("job_id")
                mid = msg.get("id")
                if mid is not None:
                    pending[mid] = job_diff.get(jid, 1)
            if up_writer:
                up_writer.write((json.dumps(msg) + "\n").encode())
                await up_writer.drain()
    except Exception:
        pass
    finally:
        try:
            down_writer.close()
        except Exception:
            pass
        try:
            if up_writer:
                up_writer.close()
        except Exception:
            pass


def _pearl_job_diff(job_id):
    """Pearl job_id is '<8hex>_<difficulty>'; the suffix is the share difficulty."""
    try:
        return max(1, int(str(job_id).split("_")[1]))
    except Exception:
        return 1


async def handle_gpu_miner(down_reader, down_writer, first_line=None):
    """Transparent relay for the Pearl (PearlHash / GPU, SRBMiner) stratum dialect,
    verifying accepted shares per ABA address. SRBMiner speaks standard stratum and may
    open with mining.subscribe BEFORE mining.authorize, so we connect upstream on the
    first line and forward every message bidirectionally (dropping nothing -> the
    handshake completes and the connection stays up instead of reconnect-looping). We
    only special-case two methods: mining.authorize (the miner sends its abakos1 address
    as the wallet; we swap in our unMineable "Alias.Worker" login so shares are credited
    to the account) and mining.submit (tag the id to attribute the accepted share).
    Pearl accept == result:true; difficulty is the integer suffix of the job_id. Handles
    both object and array authorize params (SRBMiner uses either depending on version)."""
    peer = down_writer.get_extra_info("peername")
    with _lock:
        _state["conns"] += 1
    aba = {"addr": None}
    pending = {}           # rpc id -> difficulty (credit on accept)

    def log(m):
        print("[gpu %s%s] %s" % (peer, (" " + aba["addr"][:12]) if aba["addr"] else "", m), flush=True)

    # Connect upstream immediately so the opening handshake (subscribe/authorize, in
    # whatever order the miner sends) reaches the pool intact.
    try:
        up_reader, up_writer = await asyncio.open_connection(GPU_UP_HOST, GPU_UP_PORT, limit=STREAM_LIMIT)
    except Exception as e:
        log("gpu upstream connect failed: " + str(e)[:120])
        try:
            down_writer.close()
        except Exception:
            pass
        return

    async def pump_up_to_down():
        try:
            while True:
                line = await up_reader.readline()
                if not line:
                    break
                s = line.decode(errors="ignore").strip()
                if s:
                    try:
                        msg = json.loads(s)
                        mid = msg.get("id")
                        if mid is not None and mid in pending:
                            diff = pending.pop(mid)
                            ok = (msg.get("error") in (None, False)) and (msg.get("result") is True)
                            if ok and aba["addr"]:
                                record_share(aba["addr"], diff, "Pearl", "gpu")
                    except Exception:
                        pass
                down_writer.write(line)
                await down_writer.drain()
        except Exception:
            pass
        finally:
            try:
                down_writer.close()
            except Exception:
                pass

    asyncio.ensure_future(pump_up_to_down())

    def rewrite_authorize(msg):
        """Swap the miner's abakos1 wallet for our unMineable Alias.Worker login.
        Returns the abakos1 base address, or None if the wallet is invalid."""
        p = msg.get("params")
        if isinstance(p, dict):
            wallet = str(p.get("wallet") or "").strip()
        elif isinstance(p, list) and p:
            wallet = str(p[0] or "").strip()
        else:
            wallet = ""
        base = wallet.split(".")[0]  # SRBMiner may glue wallet.worker
        if not ABA_RE.match(base):
            return None
        worker = "gpu" + (re.sub(r"[^a-z0-9]", "", base[7:])[:9] or "abk")
        up_base = KRYPTEX_USER or POOL_WALLET or wallet
        up_login = (up_base + WORKER_SEP + worker) if (KRYPTEX_USER or POOL_WALLET) else wallet
        if isinstance(p, dict):
            p = dict(p)
            p["wallet"] = up_login
            p["worker"] = worker
            p["pass"] = p.get("pass") or UP_PASS
        else:
            p = list(p)
            p[0] = up_login
            if len(p) < 2:
                p.append(UP_PASS)
        msg["params"] = p
        return base

    try:
        first = first_line
        while True:
            if first is not None:
                line, first = first, None
            else:
                line = await down_reader.readline()
            if not line:
                break
            s = line.decode(errors="ignore").strip()
            if not s:
                continue
            try:
                msg = json.loads(s)
            except Exception:
                up_writer.write(line)
                await up_writer.drain()
                continue

            method = msg.get("method")
            if method == "mining.authorize":
                base = rewrite_authorize(msg)
                if base is None:
                    down_writer.write((json.dumps({"id": msg.get("id"),
                                                   "error": {"code": 25, "msg": "wallet must be your abakos1 address"},
                                                   "result": None}) + "\n").encode())
                    await down_writer.drain()
                    log("rejected wallet")
                    break
                aba["addr"] = base
                up_writer.write((json.dumps(msg) + "\n").encode())
                await up_writer.drain()
                wl = msg["params"]["wallet"] if isinstance(msg["params"], dict) else msg["params"][0]
                log("authorize ok -> %s:%d as %s" % (GPU_UP_HOST, GPU_UP_PORT, str(wl)[:24]))
                continue

            if method == "mining.submit" and isinstance(msg.get("params"), dict):
                mid = msg.get("id")
                if mid is not None:
                    pending[mid] = _pearl_job_diff(msg["params"].get("job_id"))
            up_writer.write((json.dumps(msg) + "\n").encode())
            await up_writer.drain()
    except Exception:
        pass
    finally:
        try:
            down_writer.close()
        except Exception:
            pass
        try:
            up_writer.close()
        except Exception:
            pass


class StatsHandler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            self._send(200, {"ok": True})
        elif path == "/shares":
            win = window_shares()
            with _lock:
                totals = dict(_state["totals"])
                started = _state["started"]
            self._send(200, {"upstream": "%s:%d" % (UP_HOST, UP_PORT),
                             "kryptex_user_set": bool(KRYPTEX_USER),
                             "window_sec": PPLNS_WINDOW, "started": started,
                             "window": win, "totals": totals})
        elif path.startswith("/me"):
            from urllib.parse import urlparse, parse_qs
            addr = (parse_qs(urlparse(self.path).query).get("address") or [""])[0]
            win = window_shares()
            with _lock:
                t = _state["totals"].get(addr)
            frac = (win["per_address"].get(addr, 0) / win["total"]) if win["total"] > 0 else 0
            self._send(200, {"address": addr, "totals": t,
                             "window_shares": win["per_address"].get(addr, 0),
                             "window_total": win["total"], "window_fraction": frac})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):
        return


async def handle_conn(down_reader, down_writer):
    """Single-port dispatcher: peek the first line and route by stratum dialect so
    CPU (cryptonote 'login') and GPU (Pearl 'mining.authorize') can share one port
    (avoids opening a second firewall port). The peeked line is handed to the chosen
    handler so nothing is lost."""
    try:
        line = await asyncio.wait_for(down_reader.readline(), timeout=310)
    except Exception:
        line = b""
    if not line:
        try:
            down_writer.close()
        except Exception:
            pass
        return
    method = None
    try:
        method = (json.loads(line.decode(errors="ignore").strip()) or {}).get("method")
    except Exception:
        method = None
    # Pearl/GPU (SRBMiner) speaks standard stratum: it may open with mining.subscribe
    # OR mining.authorize. Cryptonote/CPU (xmrig) opens with "login". Route both Pearl
    # openers to the GPU handler so a subscribe-first miner isn't misrouted to the CPU
    # handler (which drops it -> reconnect loop).
    if method in ("mining.subscribe", "mining.authorize", "mining.hello"):
        await handle_gpu_miner(down_reader, down_writer, first_line=line)
    else:
        await handle_miner(down_reader, down_writer, first_line=line)


def http_thread():
    ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), StatsHandler).serve_forever()


async def main():
    load_state()
    threading.Thread(target=http_thread, daemon=True).start()
    # Main port auto-detects CPU vs GPU. GPU_PORT is also bound directly for miners
    # that prefer a dedicated GPU endpoint (both reach the same verified accounting).
    main_server = await asyncio.start_server(handle_conn, "0.0.0.0", PORT, limit=STREAM_LIMIT)
    gpu_server = await asyncio.start_server(handle_gpu_miner, "0.0.0.0", GPU_PORT, limit=STREAM_LIMIT)
    print("[stratum] listening 0.0.0.0:%d (auto CPU->%s:%d / GPU->%s:%d)"
          % (PORT, UP_HOST, UP_PORT, GPU_UP_HOST, GPU_UP_PORT), flush=True)
    print("[stratum gpu] listening 0.0.0.0:%d -> %s:%d" % (GPU_PORT, GPU_UP_HOST, GPU_UP_PORT), flush=True)
    print("[http] stats on 127.0.0.1:%d (kryptex_user=%s)" % (HTTP_PORT, "set" if KRYPTEX_USER else "unset"), flush=True)
    async with main_server, gpu_server:
        await asyncio.gather(main_server.serve_forever(), gpu_server.serve_forever())


if __name__ == "__main__":
    asyncio.run(main())
