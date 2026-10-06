#!/usr/bin/env python3
"""Public/runtime smoke for PORTAL Telegram WSS Relay.

Public-only mode requires no credentials and proves the Cloudflare/NAMED-tunnel
boundary reaches the loopback WSS service: /healthz must return 200 and an
unauthenticated WebSocket upgrade must be denied with 401.

Full mode reads the protected deployment env locally, mints a short-lived relay
ticket without printing credentials, verifies a non-Telegram target is denied,
and verifies an authenticated Telegram WebSocket upgrade returns 101.
"""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
import secrets
import socket
import ssl
import sys
from urllib.parse import urlsplit


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _exchange(host: str, port: int, request: bytes) -> bytes:
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=15) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            tls.settimeout(20)
            tls.sendall(request)
            response = b""
            while b"\r\n\r\n" not in response and len(response) < 16 * 1024:
                chunk = tls.recv(2048)
                if not chunk:
                    break
                response += chunk
    return response


def _status(response: bytes) -> int:
    first = response.split(b"\r\n", 1)[0].decode("ascii", "replace")
    parts = first.split()
    if len(parts) < 2 or not parts[1].isdigit():
        raise RuntimeError(f"invalid WSS HTTP response: {first[:120]}")
    return int(parts[1])


def health_status(url: str) -> int:
    parsed = urlsplit(url)
    if parsed.scheme != "wss" or not parsed.hostname:
        raise RuntimeError("invalid configured WSS URL")
    port = parsed.port or 443
    request = (
        "GET /healthz HTTP/1.1\r\n"
        f"Host: {parsed.hostname}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("ascii")
    return _status(_exchange(parsed.hostname, port, request))


def response_status(url: str, target: str, authorization: str | None) -> int:
    parsed = urlsplit(url)
    if parsed.scheme != "wss" or not parsed.hostname or parsed.path != "/connect":
        raise RuntimeError("invalid configured WSS URL")
    port = parsed.port or 443
    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    lines = [
        "GET /connect HTTP/1.1",
        f"Host: {parsed.hostname}",
        "Upgrade: websocket",
        "Connection: Upgrade",
        "Sec-WebSocket-Version: 13",
        f"Sec-WebSocket-Key: {key}",
        f"X-Portal-Target: {target}",
    ]
    if authorization:
        lines.append(f"Authorization: Basic {authorization}")
    request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")
    return _status(_exchange(parsed.hostname, port, request))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="/etc/portal-production/messenger-relay.env")
    parser.add_argument("--url", default="")
    parser.add_argument("--target", default="web.telegram.org:443")
    parser.add_argument("--public-only", action="store_true")
    args = parser.parse_args()

    env: dict[str, str] = {}
    if Path(args.env).exists():
        env = load_env(Path(args.env))
    wss_url = args.url or env.get("PORTAL_MESSENGER_RELAY_WSS_URL", "") or "wss://relay.vart-portal.ru/connect"

    health = health_status(wss_url)
    if health != 200:
        print(f"FAIL WSS health returned {health}, expected 200", file=sys.stderr)
        return 2
    unauthenticated = response_status(wss_url, args.target, None)
    if unauthenticated != 401:
        print(f"FAIL unauthenticated WSS returned {unauthenticated}, expected 401", file=sys.stderr)
        return 3

    if args.public_only:
        print(f"PASS health=200 unauthenticated=401 url={wss_url}")
        return 0

    secret = env.get("PORTAL_MESSENGER_RELAY_SECRET", "")
    if len(secret) < 32 or env.get("PORTAL_MESSENGER_RELAY_WSS_URL", "") != wss_url:
        print("FAIL WSS relay deployment config is incomplete", file=sys.stderr)
        return 4
    os.environ.update(env)

    server_dir = Path(__file__).resolve().parents[1] / "server"
    sys.path.insert(0, str(server_dir))
    from messenger_relay_auth import issue_ticket

    ticket = issue_ticket(1, 1)
    if not ticket.get("enabled") or ticket.get("wss_url") != wss_url:
        print("FAIL ticket did not expose the configured WSS transport", file=sys.stderr)
        return 5
    token = base64.b64encode(
        f"{ticket['username']}:{ticket['password']}".encode("utf-8")
    ).decode("ascii")

    forbidden = response_status(wss_url, "web.max.ru:443", token)
    if forbidden != 403:
        print(f"FAIL non-Telegram WSS target returned {forbidden}, expected 403", file=sys.stderr)
        return 6

    accepted = response_status(wss_url, args.target, token)
    if accepted != 101:
        print(f"FAIL authenticated Telegram WSS returned {accepted}, expected 101", file=sys.stderr)
        return 7

    print(f"PASS health=200 unauthenticated=401 non_telegram=403 telegram=101 target={args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
