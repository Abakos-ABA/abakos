#!/usr/bin/env python3
"""Abakos sandbox faucet: sends sandbox ABA to a requested abakos1 address.

POST /  {"address": "abakos1..."}  -> runs `abakosd tx bank send` from the
faucet key. Per-address cooldown, CORS enabled, requests serialized so the
account sequence stays consistent. Sandbox only; ABA has no value.
"""
import json
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8090
HOME = "/root/.abakos"
CHAIN_ID = "abakos-sandbox-1"
NODE = "tcp://127.0.0.1:26657"
FAUCET_KEY = "community"          # genesis bucket used as faucet source
AMOUNT = "250000000uaba"          # 250 ABA per claim
COOLDOWN = 6 * 3600
STATE = "/opt/abakos-faucet/claims.json"
ADDR_RE = re.compile(r"^abakos1[0-9a-z]{38,}$")
_lock = threading.Lock()


def _load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    with open(STATE, "w") as f:
        json.dump(d, f)


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        self._json(200, {"service": "abakos-faucet", "amount": AMOUNT, "chain_id": CHAIN_ID})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        addr = str(body.get("address", "")).strip()
        if not ADDR_RE.match(addr):
            return self._json(400, {"error": "invalid abakos1 address"})
        with _lock:
            claims = _load()
            now = time.time()
            last = claims.get(addr, 0)
            if now - last < COOLDOWN:
                return self._json(429, {"error": "cooldown", "retry_after_s": int(COOLDOWN - (now - last))})
            proc = subprocess.run(
                ["abakosd", "tx", "bank", "send", FAUCET_KEY, addr, AMOUNT,
                 "--keyring-backend", "test", "--home", HOME, "--chain-id", CHAIN_ID,
                 "--node", NODE, "--gas", "250000", "--fees", "0uaba",
                 "--broadcast-mode", "sync", "-y", "--output", "json"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return self._json(500, {"error": "send failed", "detail": proc.stderr[-300:]})
            claims[addr] = now
            _save(claims)
            try:
                txhash = json.loads(proc.stdout).get("txhash")
            except Exception:
                txhash = None
            return self._json(200, {"ok": True, "amount": AMOUNT, "txhash": txhash})

    def log_message(self, *a):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
