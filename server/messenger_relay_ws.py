"""Cloudflare-compatible WebSocket tunnel for PORTAL Telegram Relay.

This service is intended to bind only to loopback and sit behind an owned
Cloudflare Named Tunnel. It authenticates short-lived PORTAL relay tickets,
permits only Telegram destinations on TCP/443, and forwards raw provider TLS
bytes without terminating provider TLS.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
from contextlib import suppress

from messenger_relay import _allowed_host, _connect_socks5, _target
from messenger_relay_auth import validate_ticket

PATH = "/connect"
MAX_HEADER = 16 * 1024
MAX_FRAME = max(4096, min(int(os.environ.get("PORTAL_MESSENGER_RELAY_WS_MAX_FRAME", str(128 * 1024))), 1024 * 1024))
READ_TIMEOUT = 45
IDLE_TIMEOUT = max(30, min(int(os.environ.get("PORTAL_MESSENGER_RELAY_WS_IDLE_SECONDS", "300")), 600))
CONNECT_TIMEOUT = 15
MAX_CONNECTIONS = max(1, min(int(os.environ.get("PORTAL_MESSENGER_RELAY_WS_MAX_CONNECTIONS", "100")), 500))
SEMAPHORE = asyncio.Semaphore(MAX_CONNECTIONS)


def _http_response(status: str, body: str = "") -> bytes:
    payload = body.encode("utf-8")
    return (
        f"HTTP/1.1 {status}\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        "X-Content-Type-Options: nosniff\r\n"
        f"Content-Length: {len(payload)}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
    ).encode("ascii") + payload


async def _send_http(writer: asyncio.StreamWriter, status: str, body: str = ""):
    writer.write(_http_response(status, body))
    await asyncio.wait_for(writer.drain(), timeout=READ_TIMEOUT)
    if writer.can_write_eof():
        with suppress(Exception):
            writer.write_eof()
            await asyncio.wait_for(writer.drain(), timeout=READ_TIMEOUT)
    # Give loopback clients a scheduling turn to consume the final HTTP bytes
    # before the common connection-finalizer closes the socket (important on Windows).
    await asyncio.sleep(0.02)


async def _read_http_head(reader: asyncio.StreamReader):
    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=READ_TIMEOUT)
    if len(raw) > MAX_HEADER:
        raise ValueError("header too large")
    lines = raw[:-4].decode("iso-8859-1").split("\r\n")
    if not lines or len(lines[0]) > 2048:
        raise ValueError("invalid request")
    parts = lines[0].split()
    if len(parts) != 3:
        raise ValueError("invalid request line")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            raise ValueError("invalid header")
        name, value = line.split(":", 1)
        key = name.strip().lower()
        if not key or len(key) > 128 or len(value) > 4096:
            raise ValueError("invalid header")
        if key in headers:
            raise ValueError("duplicate header")
        headers[key] = value.strip()
    return parts, headers


def _basic_credentials(headers: dict[str, str]):
    value = headers.get("authorization", "")
    if not value.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(value[6:].strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeError):
        return None
    if ":" not in decoded:
        return None
    username, password = decoded.split(":", 1)
    if len(username) > 256 or len(password) > 256:
        return None
    return username, password


def _validate_upgrade(headers: dict[str, str]) -> str:
    if headers.get("upgrade", "").lower() != "websocket":
        raise ValueError("missing websocket upgrade")
    if "upgrade" not in {part.strip().lower() for part in headers.get("connection", "").split(",")}:
        raise ValueError("missing connection upgrade")
    if headers.get("sec-websocket-version") != "13":
        raise ValueError("unsupported websocket version")
    key = headers.get("sec-websocket-key", "")
    try:
        decoded = base64.b64decode(key, validate=True)
    except ValueError as exc:
        raise ValueError("invalid websocket key") from exc
    if len(decoded) != 16:
        raise ValueError("invalid websocket key")
    return key


def _accept_value(key: str) -> str:
    digest = hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


async def _send_frame(writer: asyncio.StreamWriter, opcode: int, payload: bytes = b""):
    if len(payload) > MAX_FRAME:
        raise ValueError("frame too large")
    first = 0x80 | (opcode & 0x0F)
    length = len(payload)
    if length < 126:
        header = bytes((first, length))
    elif length <= 0xFFFF:
        header = bytes((first, 126)) + length.to_bytes(2, "big")
    else:
        header = bytes((first, 127)) + length.to_bytes(8, "big")
    writer.write(header + payload)
    await asyncio.wait_for(writer.drain(), timeout=READ_TIMEOUT)


async def _read_frame(reader: asyncio.StreamReader):
    head = await asyncio.wait_for(reader.readexactly(2), timeout=IDLE_TIMEOUT)
    first, second = head
    if first & 0x70 or not first & 0x80:
        raise ValueError("fragmented or reserved websocket frame")
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    if not masked:
        raise ValueError("client websocket frame must be masked")
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(await asyncio.wait_for(reader.readexactly(2), timeout=READ_TIMEOUT), "big")
    elif length == 127:
        length = int.from_bytes(await asyncio.wait_for(reader.readexactly(8), timeout=READ_TIMEOUT), "big")
    if length > MAX_FRAME:
        raise ValueError("frame too large")
    mask = await asyncio.wait_for(reader.readexactly(4), timeout=READ_TIMEOUT)
    payload = bytearray(await asyncio.wait_for(reader.readexactly(length), timeout=IDLE_TIMEOUT))
    for index in range(length):
        payload[index] ^= mask[index % 4]
    return opcode, bytes(payload)


async def _ws_to_upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, client_writer: asyncio.StreamWriter):
    while True:
        opcode, payload = await _read_frame(reader)
        if opcode == 0x2:
            if payload:
                writer.write(payload)
                await asyncio.wait_for(writer.drain(), timeout=READ_TIMEOUT)
        elif opcode == 0x8:
            with suppress(Exception):
                await _send_frame(client_writer, 0x8, payload[:125])
            break
        elif opcode == 0x9:
            await _send_frame(client_writer, 0xA, payload[:125])
        elif opcode == 0xA:
            continue
        else:
            with suppress(Exception):
                await _send_frame(client_writer, 0x8, b"\x03\xeb")
            raise ValueError("only binary websocket frames are allowed")


async def _upstream_to_ws(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        chunk = await asyncio.wait_for(reader.read(64 * 1024), timeout=IDLE_TIMEOUT)
        if not chunk:
            break
        await _send_frame(writer, 0x2, chunk)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    remote = peer[0] if isinstance(peer, tuple) and peer else "unknown"
    upgraded = False
    upstream_writer = None
    try:
        async with SEMAPHORE:
            request, headers = await _read_http_head(reader)
            method, path, version = request
            if method != "GET" or version != "HTTP/1.1":
                await _send_http(writer, "405 Method Not Allowed")
                return
            if path == "/healthz":
                await _send_http(writer, "200 OK", "ok")
                return
            if path != PATH:
                await _send_http(writer, "404 Not Found")
                return
            key = _validate_upgrade(headers)
            creds = _basic_credentials(headers)
            secret = os.environ.get("PORTAL_MESSENGER_RELAY_SECRET", "")
            identity = validate_ticket(*(creds or ("", "")), secret)
            if not identity:
                await _send_http(writer, "401 Unauthorized")
                return
            target = headers.get("x-portal-target", "")
            host, port = _target(target)
            if port != 443 or not _allowed_host(host):
                await _send_http(writer, "403 Forbidden")
                return
            upstream_reader, upstream_writer = await asyncio.wait_for(
                _connect_socks5(host, port),
                timeout=CONNECT_TIMEOUT,
            )
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {_accept_value(key)}\r\n"
                "Cache-Control: no-store\r\n\r\n"
            ).encode("ascii")
            writer.write(response)
            await writer.drain()
            upgraded = True
            print(json.dumps({
                "event": "relay_ws_connect",
                "remote": remote,
                "company_id": identity["company_id"],
                "user_id": identity["user_id"],
                "target": host,
            }, separators=(",", ":")), flush=True)
            tasks = {
                asyncio.create_task(_ws_to_upstream(reader, upstream_writer, writer)),
                asyncio.create_task(_upstream_to_ws(upstream_reader, writer)),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                with suppress(asyncio.CancelledError, ConnectionError, asyncio.IncompleteReadError):
                    task.result()
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError, ValueError):
        if not upgraded:
            with suppress(Exception):
                await _send_http(writer, "400 Bad Request")
    except Exception as exc:
        print(json.dumps({
            "event": "relay_ws_error",
            "remote": remote,
            "error": type(exc).__name__,
        }, separators=(",", ":")), file=sys.stderr, flush=True)
        if not upgraded:
            with suppress(Exception):
                await _send_http(writer, "502 Bad Gateway")
    finally:
        if upstream_writer is not None:
            with suppress(Exception):
                upstream_writer.close()
                await upstream_writer.wait_closed()
        with suppress(Exception):
            writer.close()
            await writer.wait_closed()


async def serve(host: str, port: int):
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("WebSocket relay must bind to loopback only")
    if len(os.environ.get("PORTAL_MESSENGER_RELAY_SECRET", "")) < 32:
        raise SystemExit("PORTAL_MESSENGER_RELAY_SECRET must contain at least 32 characters")
    server = await asyncio.start_server(handle, host, port, limit=MAX_HEADER)
    sockets = ", ".join(str(sock.getsockname()) for sock in (server.sockets or []))
    print(json.dumps({
        "event": "relay_ws_started",
        "listen": sockets,
        "path": PATH,
        "max_connections": MAX_CONNECTIONS,
        "upstream": "configured" if os.environ.get("PORTAL_MESSENGER_RELAY_UPSTREAM_SOCKS5") else "direct",
    }, separators=(",", ":")), flush=True)
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("PORTAL_MESSENGER_RELAY_WS_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORTAL_MESSENGER_RELAY_WS_PORT", "9444")))
    args = parser.parse_args()
    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
