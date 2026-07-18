#!/usr/bin/env python3
"""Abakos waitlist micro-service (stdlib only).

Listens on 127.0.0.1:<PORT> behind Caddy (reverse_proxy /api/* -> here).
POST /api/waitlist  {"email": "...", "segment": "...", "ref": "..."}  -> CSV.
  segment: buyer | developer | chat | provider | partner | investor | general
  segment is an internal tag only (which page someone signed up from) --
  there is exactly one list. It is never shown to the visitor.
GET  /api/health    -> {"ok": true}

On a new (non-duplicate) signup this also emails:
  1. A short confirmation to the subscriber, from info@abakos.ai.
  2. A notification to info@abakos.ai, so a human sees new entries without
     needing to SSH in and read the CSV.
Both are sent via the local Postfix relay (127.0.0.1:25) that already
accepts mail from localhost -- no SMTP credentials needed, no dependency
beyond the standard library. Email failures never fail the signup itself.

Design goals: zero dependencies, loopback-only, safe (size limit, email
validation, per-IP rate limit, CSV-quoted writes, in-memory dedupe).
"""
from __future__ import annotations

import csv
import json
import os
import re
import smtplib
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("WAITLIST_PORT", "13011"))
DATA_FILE = os.environ.get(
    "WAITLIST_FILE", "/opt/sites/abakos.ai/data/waitlist.csv"
)
CSV_HEADER = ["ts", "email", "segment", "ref", "ip"]
FROM_ADDR = os.environ.get("WAITLIST_FROM", "info@abakos.ai")
NOTIFY_ADDR = os.environ.get("WAITLIST_NOTIFY", "info@abakos.ai")
SMTP_HOST = os.environ.get("WAITLIST_SMTP_HOST", "127.0.0.1")
SMTP_PORT = int(os.environ.get("WAITLIST_SMTP_PORT", "25"))
MAX_BODY = 4096
EMAIL_RE = re.compile(r"^[^@\s]{1,128}@[^@\s]{1,128}\.[^@\s]{2,24}$")
VALID_SEGMENTS = (
    "buyer",
    "developer",
    "chat",
    "provider",
    "partner",
    "investor",
    "general",
)

_lock = threading.Lock()
_seen: set[str] = set()
_rate: dict[str, list[float]] = {}
RATE_MAX = 8          # max requests
RATE_WINDOW = 300.0   # per 5 minutes per IP


def _load_seen() -> None:
    try:
        with open(DATA_FILE, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        print(f"[waitlist] no existing file yet at {DATA_FILE}")
        return
    for row in rows[1:] if rows and rows[0] == CSV_HEADER else rows:
        if len(row) >= 2 and row[1].strip():
            _seen.add(row[1].strip().lower())
    print(f"[waitlist] loaded {len(_seen)} existing entries from {DATA_FILE}")


def _rate_ok(ip: str) -> bool:
    now = time.time()
    with _lock:
        hits = [t for t in _rate.get(ip, []) if now - t < RATE_WINDOW]
        if len(hits) >= RATE_MAX:
            _rate[ip] = hits
            return False
        hits.append(now)
        _rate[ip] = hits
        return True


def _save(email: str, segment: str, ref: str, ip: str) -> None:
    with _lock:
        needs_header = not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0
        with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if needs_header:
                w.writerow(CSV_HEADER)
            w.writerow([
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                email, segment[:32], ref[:200], ip,
            ])
        _seen.add(email.lower())


def _send_mail(to_addr: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Abakos <{FROM_ADDR}>"
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.send_message(msg)
    except Exception as exc:  # pragma: no cover -- best-effort, never fail signup
        print(f"[waitlist] mail to {to_addr} failed: {exc}")


def _notify_new_signup(email: str, segment: str, ref: str, ip: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _send() -> None:
        _send_mail(
            NOTIFY_ADDR,
            f"Abakos list: new signup ({segment})",
            (
                f"New signup on the Abakos list.\n\n"
                f"Email:    {email}\n"
                f"Segment:  {segment}\n"
                f"Page:     {ref or '(unknown)'}\n"
                f"IP:       {ip}\n"
                f"Time:     {ts} UTC\n\n"
                f"Full list: {DATA_FILE} (on the VPS)\n"
            ),
        )
        _send_mail(
            email,
            "You're on the Abakos list",
            (
                "Thanks for signing up.\n\n"
                "There is one Abakos list, covering everything: testnet "
                "delivery, the Console, the developer API and Chat. "
                "Wherever you joined from, this is the only list you're on "
                "-- you will not get separate emails for each product.\n\n"
                "We send delivery updates when something real ships, not "
                "price hype. See the current status any time at "
                "https://status.abakos.ai/\n\n"
                "Didn't sign up, or want out? Just reply to this email and "
                "we'll remove you -- no automated unsubscribe flow yet, but "
                "a real human reads this inbox.\n\n"
                "-- Abakos (info@abakos.ai)\n"
            ),
        )

    threading.Thread(target=_send, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "abakos-waitlist/1.1"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self) -> str:
        return (self.headers.get("X-Real-IP")
                or self.headers.get("X-Forwarded-For", "").split(",")[0].strip()
                or self.client_address[0])

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/") in ("/api/health", "/health"):
            self._json(200, {"ok": True})
        else:
            self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") not in ("/api/waitlist", "/waitlist"):
            self._json(404, {"ok": False, "error": "not_found"})
            return
        ip = self._client_ip()
        if not _rate_ok(ip):
            self._json(429, {"ok": False, "error": "rate_limited"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._json(400, {"ok": False, "error": "bad_request"})
            return
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            email = str(data.get("email", "")).strip()
            segment = str(data.get("segment", "general")).strip().lower() or "general"
            ref = str(data.get("ref", "")).strip()
            if segment not in VALID_SEGMENTS:
                segment = "general"
        except Exception:
            self._json(400, {"ok": False, "error": "invalid_json"})
            return
        if not EMAIL_RE.match(email):
            self._json(400, {"ok": False, "error": "invalid_email"})
            return
        if email.lower() in _seen:
            self._json(200, {"ok": True, "duplicate": True})
            return
        try:
            _save(email, segment, ref, ip)
        except Exception as exc:  # pragma: no cover
            print(f"[waitlist] save error: {exc}")
            self._json(500, {"ok": False, "error": "server_error"})
            return
        _notify_new_signup(email, segment, ref, ip)
        self._json(200, {"ok": True})

    def log_message(self, fmt, *args):  # quieter logs
        print("[waitlist] " + (fmt % args))


def main() -> None:
    _load_seen()
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[waitlist] listening on 127.0.0.1:{PORT}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
