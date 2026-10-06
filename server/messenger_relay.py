#!/usr/bin/env python3
"""Authenticated Telegram-only destination-restricted HTTPS CONNECT proxy for PORTAL Messenger.

This is intentionally not a general VPN or open proxy. It accepts only authenticated
CONNECT tunnels to Telegram-owned hostnames on TCP/443 and logs no message bodies.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import ipaddress
import json
import os
import socket
import ssl
import sys
from urllib.parse import urlsplit
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from messenger_relay_auth import REALM, validate_ticket

MAX_HEADER = 32 * 1024
ALLOWED_SUFFIXES = ("telegram.org", "t.me")
MAX_CONNECTIONS = max(8, min(int(os.environ.get("PORTAL_MESSENGER_RELAY_MAX_CONNECTIONS", "256")), 4096))
SEMAPHORE = asyncio.Semaphore(MAX_CONNECTIONS)
UPSTREAM_SOCKS5_ENV = "PORTAL_MESSENGER_RELAY_UPSTREAM_SOCKS5"


def _parse_upstream_socks5(value: str | None):
    """Return (host, port) for an explicitly loopback-only SOCKS5 URL."""
    if value is None or value == "":
        return None
    try:
        if "?" in value or "#" in value:
            raise ValueError
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "socks5" or parsed.username is not None or parsed.password is not None:
            raise ValueError
        if parsed.path or parsed.query or parsed.fragment or not parsed.hostname:
            raise ValueError
        host = parsed.hostname.lower()
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError
        # urlsplit validates malformed bracket and port syntax when accessing port.
        port = parsed.port
        if port is None or not 1 <= port <= 65535:
            raise ValueError
        return host, port
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"{UPSTREAM_SOCKS5_ENV} must be a loopback socks5 URL") from exc


def _configured_upstream():
    return _parse_upstream_socks5(os.environ.get(UPSTREAM_SOCKS5_ENV))


def _allowed_host(host: str) -> bool:
    host = host.rstrip(".").lower()
    if not host or len(host) > 253:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_SUFFIXES)


def _public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _basic_credentials(headers: dict[str, str]):
    value = headers.get("proxy-authorization", "")
    if not value.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(value.split(None, 1)[1], validate=True).decode("utf-8")
        username, password = raw.split(":", 1)
        return username, password
    except Exception:
        return None


async def _read_head(reader: asyncio.StreamReader):
    data = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
    if len(data) > MAX_HEADER:
        raise ValueError("request header too large")
    lines = data.decode("iso-8859-1").split("\r\n")
    request = lines[0].split(" ")
    if len(request) != 3:
        raise ValueError("invalid request line")
    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("invalid header")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return request, headers


def _target(value: str):
    if value.startswith("["):
        end = value.find("]")
        if end < 0 or end + 2 > len(value) or value[end + 1] != ":":
            raise ValueError("invalid CONNECT target")
        return value[1:end], int(value[end + 2:])
    host, sep, port = value.rpartition(":")
    if not sep or not host:
        raise ValueError("invalid CONNECT target")
    return host, int(port)


async def _connect_public(host: str, port: int):
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    seen = set()
    last = None
    for family, socktype, proto, _canon, sockaddr in infos:
        ip = sockaddr[0]
        if ip in seen or not _public_ip(ip):
            continue
        seen.add(ip)
        try:
            return await asyncio.wait_for(asyncio.open_connection(ip, port, family=family), timeout=10)
        except Exception as exc:
            last = exc
    raise OSError("no public reachable address") from last


async def _read_exactly(reader: asyncio.StreamReader, count: int) -> bytes:
    return await asyncio.wait_for(reader.readexactly(count), timeout=10)


async def _socks_drain(writer: asyncio.StreamWriter):
    await asyncio.wait_for(writer.drain(), timeout=10)


async def _connect_socks5(host: str, port: int, upstream=None):
    upstream = upstream if upstream is not None else _configured_upstream()
    if upstream is None:
        return await _connect_public(host, port)
    proxy_host, proxy_port = upstream
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(proxy_host, proxy_port), timeout=10)
    except (OSError, TimeoutError) as exc:
        raise OSError("SOCKS5 upstream unavailable") from exc
    try:
        writer.write(b"\x05\x01\x00")
        await _socks_drain(writer)
        if await _read_exactly(reader, 2) != b"\x05\x00":
            raise OSError("SOCKS5 no-auth negotiation rejected")
        try:
            encoded_host = host.encode("idna")
        except UnicodeError as exc:
            raise ValueError("invalid SOCKS5 target hostname") from exc
        if not encoded_host or len(encoded_host) > 253:
            raise ValueError("invalid SOCKS5 target hostname")
        if not 1 <= port <= 65535:
            raise ValueError("invalid SOCKS5 target port")
        writer.write(b"\x05\x01\x00\x03" + bytes((len(encoded_host),)) + encoded_host + port.to_bytes(2, "big"))
        await _socks_drain(writer)
        head = await _read_exactly(reader, 4)
        version, reply, reserved, atyp = head
        if version != 5 or reply != 0 or reserved != 0 or atyp not in (1, 3, 4):
            raise OSError("SOCKS5 CONNECT rejected")
        address_length = {1: 4, 4: 16}.get(atyp)
        if atyp == 3:
            address_length = (await _read_exactly(reader, 1))[0]
            if address_length == 0:
                raise OSError("invalid SOCKS5 bind address")
        await _read_exactly(reader, address_length + 2)
        return reader, writer
    except (asyncio.IncompleteReadError, TimeoutError) as exc:
        writer.transport.abort()
        raise OSError("SOCKS5 upstream protocol failure") from exc
    except BaseException:
        writer.transport.abort()
        raise


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            chunk = await reader.read(64 * 1024)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _reply(writer, status: str, extra: str = ""):
    writer.write((f"HTTP/1.1 {status}\r\nConnection: close\r\n{extra}\r\n").encode("ascii"))
    await writer.drain()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    remote = peer[0] if isinstance(peer, tuple) and peer else "unknown"
    try:
        async with SEMAPHORE:
            request, headers = await _read_head(reader)
            method, target, _version = request
            creds = _basic_credentials(headers)
            secret = os.environ.get("PORTAL_MESSENGER_RELAY_SECRET", "")
            identity = validate_ticket(*(creds or ("", "")), secret)
            if not identity:
                await _reply(writer, "407 Proxy Authentication Required", f'Proxy-Authenticate: Basic realm="{REALM}"\r\n')
                return
            if method.upper() != "CONNECT":
                await _reply(writer, "405 Method Not Allowed")
                return
            host, port = _target(target)
            if port != 443 or not _allowed_host(host):
                await _reply(writer, "403 Forbidden")
                return
            upstream_reader, upstream_writer = await _connect_socks5(host, port)
            writer.write(b"HTTP/1.1 200 Connection Established\r\nProxy-Agent: PORTAL-Relay\r\n\r\n")
            await writer.drain()
            print(json.dumps({"event":"relay_connect","remote":remote,"company_id":identity["company_id"],"user_id":identity["user_id"],"target":host}, separators=(",", ":")), flush=True)
            await asyncio.gather(_pipe(reader, upstream_writer), _pipe(upstream_reader, writer))
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError, ValueError):
        try:
            await _reply(writer, "400 Bad Request")
        except Exception:
            pass
    except Exception as exc:
        print(json.dumps({"event":"relay_error","remote":remote,"error":type(exc).__name__}, separators=(",", ":")), file=sys.stderr, flush=True)
        try:
            await _reply(writer, "502 Bad Gateway")
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


def build_ssl_context(cert: str, key: str):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert, keyfile=key)
    return context


async def serve(host: str, port: int, cert: str, key: str):
    if len(os.environ.get("PORTAL_MESSENGER_RELAY_SECRET", "")) < 32:
        raise SystemExit("PORTAL_MESSENGER_RELAY_SECRET must contain at least 32 characters")
    upstream = _configured_upstream()
    mode = "socks5-loopback" if upstream is not None else "direct"
    server = await asyncio.start_server(handle, host, port, ssl=build_ssl_context(cert, key), limit=MAX_HEADER)
    sockets = ", ".join(str(sock.getsockname()) for sock in (server.sockets or []))
    print(json.dumps({"event":"relay_started","listen":sockets,"allowed_suffixes":ALLOWED_SUFFIXES,"upstream_mode":mode}), flush=True)
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("PORTAL_MESSENGER_RELAY_BIND", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORTAL_MESSENGER_RELAY_PORT", "9443")))
    parser.add_argument("--cert", default=os.environ.get("PORTAL_MESSENGER_RELAY_CERT", ""))
    parser.add_argument("--key", default=os.environ.get("PORTAL_MESSENGER_RELAY_KEY", ""))
    args = parser.parse_args()
    if not args.cert or not args.key:
        raise SystemExit("TLS certificate and key are required")
    asyncio.run(serve(args.host, args.port, args.cert, args.key))


if __name__ == "__main__":
    main()
