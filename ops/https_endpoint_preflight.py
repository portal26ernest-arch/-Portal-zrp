#!/usr/bin/env python3
"""Read-only production HTTPS preflight for PORTAL."""
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import socket
import ssl
from urllib.parse import urlparse

REQUIRED_HEADERS = {
    "strict-transport-security": "max-age=",
    "x-content-type-options": "nosniff",
    "x-frame-options": "",
    "referrer-policy": "",
}


def validate_url(raw: str):
    p = urlparse(raw)
    if p.scheme.lower() != "https" or not p.hostname:
        raise ValueError("production endpoint must be absolute HTTPS")
    if p.username or p.password or p.query or p.fragment:
        raise ValueError("endpoint must not contain credentials, query or fragment")
    if p.port not in (None, 443):
        raise ValueError("production endpoint must use standard HTTPS port 443")
    return p


def cert_check(host: str, timeout: float, min_days: int):
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=timeout) as raw:
        with ctx.wrap_socket(raw, server_hostname=host) as tls:
            cert = tls.getpeercert()
            version = tls.version()
    not_after = cert.get("notAfter")
    if not not_after:
        raise ValueError("TLS certificate expiry is unavailable")
    expiry = dt.datetime.fromtimestamp(
        ssl.cert_time_to_seconds(not_after), tz=dt.timezone.utc
    )
    days = (expiry - dt.datetime.now(dt.timezone.utc)).total_seconds() / 86400
    return {
        "tls_version": version,
        "certificate_expires_utc": expiry.isoformat(),
        "certificate_days_remaining": round(days, 2),
        "certificate_valid_long_enough": days >= min_days,
    }


def https_ping(parsed, timeout: float):
    conn = http.client.HTTPSConnection(
        parsed.hostname, 443, timeout=timeout, context=ssl.create_default_context()
    )
    base = parsed.path.rstrip("/")
    path = (base + "/api/ping") if base else "/api/ping"
    conn.request("GET", path, headers={"User-Agent": "PORTAL-preflight/1"})
    response = conn.getresponse()
    body = response.read(1024 * 1024)
    headers = {k.lower(): v for k, v in response.getheaders()}
    conn.close()
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        payload = None
    return response.status, headers, payload


def http_redirect(host: str, timeout: float):
    conn = http.client.HTTPConnection(host, 80, timeout=timeout)
    conn.request("GET", "/", headers={"User-Agent": "PORTAL-preflight/1"})
    response = conn.getresponse()
    response.read(65536)
    location = response.getheader("Location") or ""
    status = response.status
    conn.close()
    p = urlparse(location)
    safe = (
        status in (301, 302, 307, 308)
        and p.scheme.lower() == "https"
        and p.hostname == host
        and not p.username
        and not p.password
    )
    return {"status": status, "location": location, "safe_https_redirect": safe}


def api_port_closed(host: str, port: int, timeout: float):
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex((host, port))
        return result != 0
    finally:
        sock.close()


def evaluate(raw_url: str, timeout=5.0, min_cert_days=14, api_port=None):
    p = validate_url(raw_url)
    result = {
        "endpoint": raw_url.rstrip("/"),
        "host": p.hostname,
        "read_only": True,
        "checks": {},
        "failures": [],
    }
    tls = cert_check(p.hostname, timeout, min_cert_days)
    result["checks"]["tls"] = tls
    if not tls["certificate_valid_long_enough"]:
        result["failures"].append("certificate_expiry")
    status, headers, payload = https_ping(p, timeout)
    ping_ok = status == 200 and isinstance(payload, dict) and payload.get("ok") is True
    result["checks"]["api_ping"] = {"status": status, "ok": ping_ok}
    if not ping_ok:
        result["failures"].append("api_ping")

    header_result = {}
    for name, expected in REQUIRED_HEADERS.items():
        value = headers.get(name, "")
        ok = bool(value) and (expected.lower() in value.lower() if expected else True)
        header_result[name] = {"value": value, "ok": ok}
        if not ok:
            result["failures"].append("header:" + name)
    result["checks"]["security_headers"] = header_result

    redirect = http_redirect(p.hostname, timeout)
    result["checks"]["http_redirect"] = redirect
    if not redirect["safe_https_redirect"]:
        result["failures"].append("http_to_https_redirect")

    if api_port:
        closed = api_port_closed(p.hostname, api_port, timeout)
        result["checks"]["public_api_port"] = {"port": api_port, "closed": closed}
        if not closed:
            result["failures"].append("api_port_public")

    result["go"] = not result["failures"]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--min-cert-days", type=int, default=14)
    ap.add_argument("--expect-api-port-closed", type=int)
    ap.add_argument("--output")
    args = ap.parse_args()
    if args.timeout <= 0 or args.min_cert_days < 1:
        raise SystemExit("invalid timeout/certificate threshold")
    try:
        result = evaluate(
            args.url,
            timeout=args.timeout,
            min_cert_days=args.min_cert_days,
            api_port=args.expect_api_port_closed,
        )
    except Exception as exc:
        result = {
            "endpoint": args.url,
            "read_only": True,
            "go": False,
            "failures": ["preflight_error"],
            "error": type(exc).__name__ + ": " + str(exc),
        }
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        from pathlib import Path
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["go"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
