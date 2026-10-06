#!/usr/bin/env python3
"""External no-secret smoke for the public PORTAL Telegram Relay boundary."""
from __future__ import annotations
import socket
import ssl

HOST = "relay.vart-portal.ru"
PORT = 9443
TARGET = "web.telegram.org"

# Diagnostic: standard HTTPS reachability of the direct DNS hostname. Certificate
# validation is intentionally disabled here because nginx does not serve this relay
# hostname; this probe only distinguishes provider filtering of 9443 from all TCP/TLS.
diag = ssl._create_unverified_context()
try:
    with socket.create_connection((HOST, 443), timeout=8) as raw:
        with diag.wrap_socket(raw, server_hostname=HOST) as tls:
            print(f"DIAG standard443_tls={tls.version()}")
except Exception as exc:
    print(f"DIAG standard443_failed={type(exc).__name__}")

context = ssl.create_default_context()
with socket.create_connection((HOST, PORT), timeout=12) as raw:
    raw.settimeout(12)
    with context.wrap_socket(raw, server_hostname=HOST) as tls:
        cert = tls.getpeercert()
        sans = {value for kind, value in cert.get("subjectAltName", ()) if kind == "DNS"}
        if HOST not in sans:
            raise SystemExit(f"FAIL certificate SAN does not contain {HOST}")
        request = (
            f"CONNECT {TARGET}:443 HTTP/1.1\r\n"
            f"Host: {TARGET}:443\r\n"
            "Proxy-Connection: close\r\n\r\n"
        ).encode("ascii")
        tls.sendall(request)
        first = tls.recv(1024).split(b"\r\n", 1)[0].decode("ascii", "replace")
parts = first.split()
if len(parts) < 2 or parts[1] != "407":
    raise SystemExit(f"FAIL expected unauthenticated 407, got {first[:120]}")
print(f"PASS tls={HOST}:{PORT} unauthenticated=407 target={TARGET}:443")
