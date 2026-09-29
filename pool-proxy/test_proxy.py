#!/usr/bin/env python3
"""Regression tests for share attribution in the stratum proxy (stdlib only).

Runs the real handlers against an in-process fake upstream pool on 127.0.0.1 -- no
network, no real pool, no real miners:

    python pool-proxy/test_proxy.py

Covers the 2026-09-29 report "forged payout weight from miner-controlled job_id":
a miner reused the RPC id of its (accepted) mining.authorize for a mining.submit
carrying a forged job_id "deadbeef_777777777777"; the proxy credited the authorize
ack as that share and took the weight from the forged job_id suffix.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="aba-proxy-test-")
os.environ["ABA_SHARES_DB"] = os.path.join(_TMP, "shares.json")
os.environ.setdefault("ABA_KRYPTEX_USER", "testalias")
os.environ["ABA_WORKER_SEP"] = "."
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proxy  # noqa: E402

HONEST = "abakos1honestminer000000000000000000000000"
ATTACKER = "abakos1attackerminer0000000000000000000000"
JOB_DIFF = 65536


class FakePearlPool:
    """Minimal Pearl (unMineable pearlpow) upstream: authorize -> true + one
    mining.notify with an object-params job; submit -> true only for issued jobs."""

    def __init__(self):
        self.server = None
        self.port = None
        self.received = []

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def _handle(self, reader, writer):
        issued = set()
        seq = 0
        while True:
            line = await reader.readline()
            if not line:
                break
            msg = json.loads(line)
            self.received.append(msg)
            method = msg.get("method")
            if method == "mining.authorize":
                writer.write((json.dumps({"id": msg["id"], "error": None, "result": True}) + "\n").encode())
                jid = "%08x_%d" % (seq, JOB_DIFF)
                seq += 1
                issued.add(jid)
                writer.write((json.dumps({"id": None, "method": "mining.notify",
                                          "params": {"job_id": jid, "header": "00" * 76,
                                                     "target": "00" * 32, "height": 1,
                                                     "cert_version": 3}}) + "\n").encode())
            elif method == "mining.submit":
                p = msg.get("params") or {}
                jid = p.get("job_id") if isinstance(p, dict) else p[1]
                nonce = p.get("nonce") if isinstance(p, dict) else p[2]
                if jid in issued and nonce != "bad":
                    reply = {"id": msg["id"], "error": None, "result": True}
                else:
                    reply = {"id": msg["id"], "error": {"code": 21, "message": "Job not found"}, "result": None}
                writer.write((json.dumps(reply) + "\n").encode())
            elif msg.get("id") is not None:
                await asyncio.sleep(0.05)  # slow ack: lets a same-id submit get in first
                writer.write((json.dumps({"id": msg["id"], "error": None, "result": True}) + "\n").encode())
            await writer.drain()
        writer.close()

    def close(self):
        self.server.close()


class FakeCryptonotePool:
    """Minimal cryptonote (xmrig) upstream: login -> status OK + job; submit -> OK
    only for issued jobs."""

    def __init__(self):
        self.server = None
        self.port = None

    async def start(self):
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def _handle(self, reader, writer):
        issued = {"cpujob1"}
        while True:
            line = await reader.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("method") == "login":
                reply = {"id": msg["id"], "jsonrpc": "2.0", "error": None,
                         "result": {"id": "sess", "status": "OK",
                                    "job": {"job_id": "cpujob1", "blob": "00", "target": "b88d0600"}}}
            elif msg.get("method") == "submit":
                ok = msg["params"].get("job_id") in issued
                reply = {"id": msg["id"], "jsonrpc": "2.0",
                         "error": None if ok else {"code": -1, "message": "Invalid job id"},
                         "result": {"status": "OK"} if ok else None}
            else:
                reply = {"id": msg["id"], "jsonrpc": "2.0", "error": None, "result": {"status": "KEEPALIVED"}}
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
        writer.close()

    def close(self):
        self.server.close()


class Miner:
    def __init__(self, reader, writer):
        self.r, self.w = reader, writer

    async def send(self, obj):
        self.w.write((json.dumps(obj) + "\n").encode())
        await self.w.drain()

    async def recv_until(self, pred, timeout=3.0):
        """Read lines until pred(msg) is true; returns all messages read."""
        seen = []
        async def _loop():
            while True:
                line = await self.r.readline()
                if not line:
                    return
                m = json.loads(line)
                seen.append(m)
                if pred(m):
                    return
        await asyncio.wait_for(_loop(), timeout)
        return seen

    async def recv_id(self, rid):
        return (await self.recv_until(lambda m: m.get("id") == rid))[-1]

    def close(self):
        self.w.close()


def _reset_state():
    with proxy._lock:
        proxy._state["totals"] = {}
        proxy._state["events"] = []


def _gpu_weight(addr):
    return (proxy._state["totals"].get(addr) or {}).get("gpu_weighted", 0)


def _cpu_weight(addr):
    return (proxy._state["totals"].get(addr) or {}).get("cpu_weighted", 0)


class GpuShareAttribution(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _reset_state()
        self.pool = FakePearlPool()
        await self.pool.start()
        proxy.GPU_UP_HOST, proxy.GPU_UP_PORT = "127.0.0.1", self.pool.port
        self.listener = await asyncio.start_server(proxy.handle_gpu_miner, "127.0.0.1", 0, limit=proxy.STREAM_LIMIT)
        self.port = self.listener.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.listener.close()
        self.pool.close()
        await asyncio.sleep(0.05)

    async def connect(self, addr, auth_id):
        m = Miner(*await asyncio.open_connection("127.0.0.1", self.port))
        await m.send({"id": auth_id, "method": "mining.authorize",
                      "params": {"wallet": addr, "worker": "rig", "pass": "x"}})
        msgs = await m.recv_until(lambda x: x.get("method") == "mining.notify")
        ack = [x for x in msgs if x.get("id") == auth_id]
        self.assertTrue(ack and ack[0]["result"] is True, msgs)
        job = [x for x in msgs if x.get("method") == "mining.notify"][0]["params"]["job_id"]
        return m, job

    async def test_honest_share_credited_with_upstream_difficulty(self):
        m, job = await self.connect(HONEST, 1)
        await m.send({"id": 7, "method": "mining.submit", "params": {"job_id": job, "nonce": "01"}})
        reply = await m.recv_id(7)
        self.assertIs(reply["result"], True)
        await asyncio.sleep(0.05)
        self.assertEqual(_gpu_weight(HONEST), JOB_DIFF)
        m.close()

    async def test_reported_poc_authorize_id_reuse_forged_job(self):
        """Exact PoC from the report: authorize id 903, submit id 903 with a forged job."""
        honest, job = await self.connect(HONEST, 1)
        await honest.send({"id": 2, "method": "mining.submit", "params": {"job_id": job, "nonce": "01"}})
        await honest.recv_id(2)

        m = Miner(*await asyncio.open_connection("127.0.0.1", self.port))
        auth = {"id": 903, "method": "mining.authorize",
                "params": {"wallet": ATTACKER, "worker": "rig", "pass": "x"}}
        forged = {"id": 903, "method": "mining.submit",
                  "params": {"job_id": "deadbeef_777777777777", "nonce": "00"}}
        # Pipelined: the submit is in flight before the authorize ack comes back.
        m.w.write((json.dumps(auth) + "\n" + json.dumps(forged) + "\n").encode())
        await m.w.drain()
        replies = await m.recv_until(lambda x: x.get("id") == 903 and x.get("result") is not True)
        await asyncio.sleep(0.1)
        self.assertEqual(_gpu_weight(ATTACKER), 0, replies)
        self.assertEqual(_gpu_weight(HONEST), JOB_DIFF)
        honest.close()
        m.close()

    async def test_forged_job_id_rejected_and_never_credited(self):
        m, _job = await self.connect(ATTACKER, 1)
        await m.send({"id": 5, "method": "mining.submit",
                      "params": {"job_id": "deadbeef_777777777777", "nonce": "00"}})
        reply = await m.recv_id(5)
        self.assertIsNot(reply.get("result"), True)
        self.assertTrue(reply.get("error"))
        await asyncio.sleep(0.05)
        self.assertEqual(_gpu_weight(ATTACKER), 0)
        # never relayed upstream either
        self.assertFalse(any((x.get("params") or {}).get("job_id") == "deadbeef_777777777777"
                             for x in self.pool.received if isinstance(x.get("params"), dict)))
        m.close()

    async def test_rpc_id_collision_with_other_request_cannot_credit(self):
        """A submit sharing its id with a later non-submit request (e.g. a second
        authorize or any rpc the pool answers true) must not be credited by that ack."""
        m, job = await self.connect(ATTACKER, 1)
        # the pool never issued this job -> the pool rejects the share
        forged = {"id": 44, "method": "mining.submit",
                  "params": {"job_id": "00000000_999999999", "nonce": "00"}}
        extra = {"id": 44, "method": "mining.extranonce.subscribe", "params": []}
        # extranonce first: its (slow) true-ack returns after the submit is registered
        m.w.write((json.dumps(extra) + "\n" + json.dumps(forged) + "\n").encode())
        await m.w.drain()
        await m.recv_until(lambda x: x.get("id") == 44 and x.get("result") is True)
        await asyncio.sleep(0.1)
        self.assertEqual(_gpu_weight(ATTACKER), 0)
        m.close()

    async def test_pool_rejected_share_on_real_job_not_credited_by_id_collision(self):
        """ID binding on its own: real issued job, pool rejects the share (bad nonce),
        a same-id request acked true must not turn that into a credit."""
        m, job = await self.connect(ATTACKER, 1)
        extra = {"id": 55, "method": "mining.extranonce.subscribe", "params": []}
        bad = {"id": 55, "method": "mining.submit", "params": {"job_id": job, "nonce": "bad"}}
        m.w.write((json.dumps(extra) + "\n" + json.dumps(bad) + "\n").encode())
        await m.w.drain()
        replies = await m.recv_until(lambda x: x.get("id") == 55 and x.get("result") is True)
        replies += await m.recv_until(lambda x: x.get("id") == 55 and x.get("error"))
        await asyncio.sleep(0.05)
        self.assertEqual(_gpu_weight(ATTACKER), 0, replies)
        m.close()

    async def test_repeated_forged_submits_do_not_accumulate(self):
        m, job = await self.connect(ATTACKER, 1)
        for i in range(20):
            await m.send({"id": 100 + i, "method": "mining.submit",
                          "params": {"job_id": "%08x_999999999999" % i, "nonce": "00"}})
            await m.recv_id(100 + i)
        await asyncio.sleep(0.05)
        self.assertEqual(_gpu_weight(ATTACKER), 0)
        m.close()

    async def test_miner_sees_its_own_rpc_ids(self):
        m, job = await self.connect(HONEST, "auth-1")
        await m.send({"id": "s-1", "method": "mining.submit", "params": {"job_id": job, "nonce": "01"}})
        reply = await m.recv_id("s-1")
        self.assertIs(reply["result"], True)
        m.close()

    async def test_array_params_submit(self):
        m, job = await self.connect(HONEST, 1)
        await m.send({"id": 9, "method": "mining.submit", "params": ["rig", job, "01"]})
        self.assertIs((await m.recv_id(9))["result"], True)
        await asyncio.sleep(0.05)
        self.assertEqual(_gpu_weight(HONEST), JOB_DIFF)
        m.close()


class CpuShareAttribution(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _reset_state()
        self.pool = FakeCryptonotePool()
        await self.pool.start()
        proxy.UP_HOST, proxy.UP_PORT = "127.0.0.1", self.pool.port
        self.listener = await asyncio.start_server(proxy.handle_miner, "127.0.0.1", 0, limit=proxy.STREAM_LIMIT)
        self.port = self.listener.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.listener.close()
        self.pool.close()
        await asyncio.sleep(0.05)

    async def test_login_id_reuse_cannot_credit_rejected_submit(self):
        m = Miner(*await asyncio.open_connection("127.0.0.1", self.port))
        login = {"id": 1, "jsonrpc": "2.0", "method": "login",
                 "params": {"login": ATTACKER, "pass": "x", "agent": "t"}}
        forged = {"id": 1, "jsonrpc": "2.0", "method": "submit",
                  "params": {"id": "sess", "job_id": "nope", "nonce": "00", "result": "00"}}
        # pipelined: the submit is queued before the login ack (status OK) returns
        m.w.write((json.dumps(login) + "\n" + json.dumps(forged) + "\n").encode())
        await m.w.drain()
        await m.recv_until(lambda x: x.get("id") == 1 and x.get("error"))
        await asyncio.sleep(0.1)
        self.assertEqual(_cpu_weight(ATTACKER), 0)
        m.close()

    async def test_honest_cpu_share_credited(self):
        m = Miner(*await asyncio.open_connection("127.0.0.1", self.port))
        await m.send({"id": 1, "jsonrpc": "2.0", "method": "login",
                      "params": {"login": HONEST, "pass": "x", "agent": "t"}})
        login_reply = await m.recv_id(1)
        self.assertEqual(login_reply["result"]["status"], "OK")
        await m.send({"id": 2, "jsonrpc": "2.0", "method": "submit",
                      "params": {"id": "sess", "job_id": "cpujob1", "nonce": "00", "result": "00"}})
        self.assertEqual((await m.recv_id(2))["result"]["status"], "OK")
        await asyncio.sleep(0.05)
        self.assertEqual(_cpu_weight(HONEST), proxy.diff_from_target("b88d0600"))
        m.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
