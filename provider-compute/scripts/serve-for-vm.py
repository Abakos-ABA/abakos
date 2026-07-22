#!/usr/bin/env python3
"""Serve abakos repo to the Ubuntu VM over VMware NAT (192.168.227.1:8765)."""
import http.server
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # abakos/
ARTIFACTS = ROOT / "provider-compute" / "artifacts"
PORT = int(os.environ.get("ABAKOS_VM_PORT", "8765"))
HOST = os.environ.get("ABAKOS_VM_HOST", "192.168.227.1")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        # Scripts edited on Windows may have CRLF; Linux bash needs LF.
        if self.path.endswith(".sh"):
            self.send_header("Content-Type", "text/x-shellscript; charset=utf-8")
        super().end_headers()

    def copyfile(self, source, outputfile):
        if self.path.endswith(".sh"):
            data = source.read().replace(b"\r\n", b"\n")
            outputfile.write(data)
            return
        super().copyfile(source, outputfile)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    abakosd = ARTIFACTS / "abakosd"
    tmp = Path(os.environ.get("TEMP", "/tmp")) / "abakosd"
    if not abakosd.exists() and tmp.exists() and tmp.stat().st_size > 1_000_000:
        print(f"Linking {tmp} -> {abakosd}")
        try:
            os.link(tmp, abakosd)
        except OSError:
            import shutil
            shutil.copy2(tmp, abakosd)

    # Bind VMware NAT interface so the guest can reach us.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((HOST, PORT))
    except OSError:
        print(f"Cannot bind {HOST}:{PORT} — try another host or stop the old server.", file=sys.stderr)
        sock.bind(("0.0.0.0", PORT))
        host_show = f"0.0.0.0:{PORT}"
    else:
        host_show = f"{HOST}:{PORT}"
    sock.listen(128)

    print(f"Serving {ROOT}")
    print(f"VM paste command:")
    print(f"  curl -fsSL http://{HOST}:{PORT}/provider-compute/scripts/vm-paste-install.sh | bash")
    httpd = http.server.HTTPServer((HOST if HOST != "0.0.0.0" else "", PORT), Handler)
    httpd.socket = sock
    httpd.serve_forever()


if __name__ == "__main__":
    main()
