#!/usr/bin/env python3
"""Authenticated live smoke for PORTAL Messenger HTTPS CONNECT relay.

Reads deployment env locally, never prints relay credentials, and verifies:
1) unauthenticated CONNECT is rejected;
2) a freshly issued short-lived Telegram ticket can CONNECT to an allowed target.
"""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
import socket
import ssl
import sys


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def connect_status(address: str, port: int, server_name: str, target: str, authorization: str | None) -> int:
    context = ssl.create_default_context()
    with socket.create_connection((address, port), timeout=20) as raw:
        with context.wrap_socket(raw, server_hostname=server_name) as tls:
            lines = [
                f"CONNECT {target}:443 HTTP/1.1",
                f"Host: {target}:443",
                "Proxy-Connection: close",
            ]
            if authorization:
                lines.append(f"Proxy-Authorization: Basic {authorization}")
            tls.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
            response = b""
            while b"\r\n" not in response and len(response) < 4096:
                chunk = tls.recv(1024)
                if not chunk:
                    break
                response += chunk
    first = response.split(b"\r\n", 1)[0].decode("ascii", "replace")
    parts = first.split()
    if len(parts) < 2 or not parts[1].isdigit():
        raise RuntimeError(f"invalid proxy response: {first[:120]}")
    return int(parts[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="/etc/portal-production/messenger-relay.env")
    parser.add_argument("--proxy-address", default="127.0.0.1")
    parser.add_argument("--proxy-host", default="api.vart-portal.ru")
    parser.add_argument("--proxy-port", type=int, default=9443)
    parser.add_argument("--target", default="web.telegram.org")
    args = parser.parse_args()

    env = load_env(Path(args.env))
    secret = env.get("PORTAL_MESSENGER_RELAY_SECRET", "")
    if len(secret) < 32:
        print("FAIL relay secret is not configured", file=sys.stderr)
        return 2
    os.environ.update(env)

    server_dir = Path(__file__).resolve().parents[1] / "server"
    sys.path.insert(0, str(server_dir))
    from messenger_relay_auth import issue_ticket

    rejected = connect_status(args.proxy_address, args.proxy_port, args.proxy_host, args.target, None)
    if rejected != 407:
        print(f"FAIL unauthenticated CONNECT returned {rejected}, expected 407", file=sys.stderr)
        return 3

    ticket = issue_ticket(1, 1)
    token = base64.b64encode(f"{ticket['username']}:{ticket['password']}".encode("utf-8")).decode("ascii")
    accepted = connect_status(args.proxy_address, args.proxy_port, args.proxy_host, args.target, token)
    if accepted != 200:
        print(f"FAIL authenticated CONNECT returned {accepted}, expected 200", file=sys.stderr)
        return 4

    print(f"PASS unauthenticated=407 authenticated=200 target={args.target}:443")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
