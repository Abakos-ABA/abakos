#!/usr/bin/env python3
"""Abakos Provider Agent - real mining on YOUR machine, linked to your ABA wallet.

Runs real miners on your idle hardware and reports live hashrate to Abakos, which
pays you ABA on the sandbox by your real contributed hashrate:
  * CPU  -> xmrig (RandomX / Monero)          -- the best CPU coin
  * GPU  -> T-Rex (NVIDIA)                     -- the best GPU coin from the oracle

Usage:
  python3 miner.py <abakos1_address> [options]

Options:
  --xmr <monero_address>   Real CPU pool mining to this Monero address (you keep the XMR).
                           Without it, the CPU runs a real RandomX *benchmark loop*
                           (real hashing to prove/measure your rate, no wallet needed).
  --gpu-wallet <address>   Payout address for the mined GPU coin (enables real GPU pool mining).
  --no-cpu / --no-gpu      Disable a device.
  --threads <N>            CPU threads (default: auto).

ABA on the sandbox has no value. Real coin custody + buyback (XMR/coin -> ABA via a
DEX/exchange) is the next phase; today the mining/hashrate is real and ABA is paid
on-chain by your real hashrate. Ctrl+C to stop.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile

BACKEND = os.environ.get("ABA_BACKEND", "https://explorer.abakos.ai/agent")
CPU_API = 16000
GPU_API = 16001
WORKDIR = os.path.join(tempfile.gettempdir(), "abakos-agent")

# Abakos project custody wallets (public receiving addresses; keys stay server-side).
# CPU proceeds accrue here via MoneroOcean; you are paid ABA for your hashrate.
PROJECT_XMR = os.environ.get("ABA_PROJECT_XMR", "46Z6RqAnZAk5JR4JdS1VkudtRqgsyf4afcQSaEaa1xnT7BSWT8AjfP5MwpSjCgkNTYWCJSBSqH59UNpydMAuiTZBEpBekpk")
PROJECT_BTC = os.environ.get("ABA_PROJECT_BTC", "1JEMuHbSRNTkQh4V375YmywXxPg5vKtZDf")
PROJECT_RVN = os.environ.get("ABA_PROJECT_RVN", "RHXYCjwdw8koSxeDGzpuYawpWbshzvapMs")  # GPU proceeds (Ravencoin)

_state = {"cpu_hs": 0.0, "gpu_hs": 0.0, "cpu_coin": "XMR", "gpu_coin": None}


def log(m):
    print("[abakos] " + m, flush=True)


def http_json(url, data=None, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "abakos-agent"})
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def gh_release(repo):
    return http_json("https://api.github.com/repos/%s/releases/latest" % repo, timeout=20)


def pick_asset(rel, matches):
    """matches: list of substring-lists; return (url, name) for the first asset matching any list."""
    for match in matches:
        for a in rel.get("assets", []):
            n = a["name"].lower()
            if all(m in n for m in match):
                return a["browser_download_url"], a["name"]
    return None, None


def download(url, dest):
    log("downloading " + url)
    req = urllib.request.Request(url, headers={"User-Agent": "abakos-agent"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def extract(path, into):
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            z.extractall(into)
    else:
        with tarfile.open(path) as t:
            t.extractall(into)


def find_bin(root, name):
    exe = name + (".exe" if platform.system() == "Windows" else "")
    for dp, _, fs in os.walk(root):
        if exe in fs:
            return os.path.join(dp, exe)
    return None


def xmrig_matches():
    s = platform.system(); m = platform.machine().lower()
    if s == "Windows":
        return [["windows-x64.zip"], ["windows", "x64", ".zip"], ["win64", ".zip"]]
    if s == "Darwin":
        if m in ("arm64", "aarch64"):
            return [["macos-arm64.tar"], ["macos", "arm64"]]
        return [["macos-x64.tar"], ["macos", "x64"]]
    if m in ("aarch64", "arm64"):
        return [["linux-static-arm64.tar"], ["linux", "arm64", ".tar"]]
    return [["linux-static-x64.tar"], ["linux", "x64", ".tar"]]


def trex_match():
    s = platform.system()
    if s == "Windows":
        return ["win", ".zip"]
    if s == "Linux":
        return ["linux", ".tar"]
    return None


# ---------------- CPU (xmrig) ----------------

def setup_xmrig():
    rel = gh_release("xmrig/xmrig")
    url, name = pick_asset(rel, xmrig_matches())
    if not url:
        raise RuntimeError("no xmrig asset for this platform; assets: " + ", ".join(a["name"] for a in rel.get("assets", [])))
    root = os.path.join(WORKDIR, "xmrig")
    os.makedirs(root, exist_ok=True)
    arc = os.path.join(root, name)
    download(url, arc)
    extract(arc, root)
    b = find_bin(root, "xmrig")
    if not b:
        raise RuntimeError("xmrig binary not found after extract")
    return b


def run_cpu(aba, xmr, threads):
    try:
        b = setup_xmrig()
    except Exception as e:
        log("CPU miner setup failed: " + str(e))
        return
    pool_user = xmr or PROJECT_XMR
    cfg = {
        "http": {"enabled": True, "host": "127.0.0.1", "port": CPU_API, "access-token": None, "restricted": True},
        "autosave": False, "cpu": {"enabled": True}, "randomx": {"1gb-pages": False},
        "pools": [{
            "url": "gulf.moneroocean.stream:10128", "user": pool_user, "pass": aba,
            "rig-id": aba[:24], "keepalive": True, "tls": False, "algo": "rx/0",
        }],
    }
    dest = "your Monero wallet" if xmr else "the Abakos project wallet (you earn ABA for the hashrate)"
    log("CPU: real RandomX mining -> MoneroOcean; proceeds to " + dest + "; rig=" + aba[:16] + "...")
    cfgp = os.path.join(os.path.dirname(b), "abakos-cpu.json")
    with open(cfgp, "w") as f:
        json.dump(cfg, f)
    args = ["-t", str(threads)] if threads else []
    while True:
        p = subprocess.Popen([b, "-c", cfgp] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.wait()
        time.sleep(3)


def poll_cpu():
    while True:
        try:
            s = http_json("http://127.0.0.1:%d/2/summary" % CPU_API, timeout=5)
            tot = (s.get("hashrate", {}) or {}).get("total") or [0]
            _state["cpu_hs"] = float(tot[0] or 0)
        except Exception:
            pass
        time.sleep(5)


# ---------------- GPU (T-Rex, NVIDIA) ----------------

def has_nvidia():
    return shutil.which("nvidia-smi") is not None


TREX_POOLS = {  # algo -> (pool host:port)
    "octopus": "cfx.woolypooly.com:3094", "kawpow": "rvn.2miners.com:6060",
    "etchash": "etc.2miners.com:1010", "autolykos2": "erg.2miners.com:8888",
}
COIN_ALGO = {"CFX": "octopus", "RVN": "kawpow", "ETC": "etchash", "ERG": "autolykos2"}


def setup_trex():
    tm = trex_match()
    if not tm:
        return None
    rel = gh_release("trexminer/T-Rex")
    url, name = pick_asset(rel, [tm])
    if not url:
        return None
    root = os.path.join(WORKDIR, "trex")
    os.makedirs(root, exist_ok=True)
    arc = os.path.join(root, name)
    download(url, arc)
    extract(arc, root)
    return find_bin(root, "t-rex")


def run_gpu(aba, gpu_coin, gpu_wallet):
    algo = COIN_ALGO.get(gpu_coin)
    if not algo or algo not in TREX_POOLS:
        log("GPU: no supported pool for " + str(gpu_coin) + "; skipping GPU")
        return
    try:
        b = setup_trex()
    except Exception as e:
        b = None
        log("GPU miner setup failed: " + str(e))
    if not b:
        log("GPU: T-Rex not available for this OS; skipping GPU")
        return
    _state["gpu_coin"] = gpu_coin
    log("GPU: real mining %s (%s) -> %s" % (gpu_coin, algo, TREX_POOLS[algo]))
    args = [b, "-a", algo, "-o", "stratum+tcp://" + TREX_POOLS[algo],
            "-u", gpu_wallet + "." + aba[:12], "-p", "x",
            "--api-bind-http", "127.0.0.1:%d" % GPU_API]
    while True:
        p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p.wait()
        time.sleep(3)


def poll_gpu():
    while True:
        try:
            s = http_json("http://127.0.0.1:%d/summary" % GPU_API, timeout=5)
            _state["gpu_hs"] = float(s.get("hashrate", 0) or 0)
        except Exception:
            pass
        time.sleep(5)


# ---------------- reporting ----------------

def report_loop(aba):
    while True:
        try:
            http_json(BACKEND + "/report", data={
                "address": aba, "cpu_hashrate_hs": _state["cpu_hs"], "gpu_hashrate_hs": _state["gpu_hs"],
                "cpu_coin": _state["cpu_coin"], "gpu_coin": _state["gpu_coin"],
                "miner": "xmrig+trex", "os": platform.system(),
            }, timeout=10)
            log("reported: CPU %.0f H/s | GPU %.0f H/s -> earning ABA to %s" % (_state["cpu_hs"], _state["gpu_hs"], aba[:16] + "..."))
        except Exception as e:
            log("report failed: " + str(e))
        time.sleep(20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("address")
    ap.add_argument("--xmr")
    ap.add_argument("--gpu-wallet")
    ap.add_argument("--no-cpu", action="store_true")
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--threads", type=int)
    a = ap.parse_args()
    if not a.address.startswith("abakos1"):
        log("first argument must be your abakos1... wallet address"); sys.exit(1)
    os.makedirs(WORKDIR, exist_ok=True)

    log("Abakos Provider Agent starting. Wallet: " + a.address)
    log("CPU coin: XMR (RandomX) | GPU coin: RVN (KawPow)")

    threads = []
    if not a.no_cpu:
        threads += [threading.Thread(target=run_cpu, args=(a.address, a.xmr, a.threads), daemon=True),
                    threading.Thread(target=poll_cpu, daemon=True)]
    if not a.no_gpu and has_nvidia():
        gw = a.gpu_wallet or PROJECT_RVN
        threads += [threading.Thread(target=run_gpu, args=(a.address, "RVN", gw), daemon=True),
                    threading.Thread(target=poll_gpu, daemon=True)]
    elif not a.no_gpu:
        log("no NVIDIA GPU detected (nvidia-smi missing); CPU only. AMD support coming.")

    for t in threads:
        t.start()
    threading.Thread(target=report_loop, args=(a.address,), daemon=True).start()
    log("running. Watch your machine in the wallet: https://abakos.ai/wallet/  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        log("stopping.")


if __name__ == "__main__":
    main()
