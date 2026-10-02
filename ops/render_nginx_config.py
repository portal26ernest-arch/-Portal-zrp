#!/usr/bin/env python3
"""Safely render the PORTAL nginx template from hostname and loopback port."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "deploy/nginx/portal.conf.template"
HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)


def validate_host(host: str) -> str:
    if not isinstance(host, str) or host != host.strip():
        raise ValueError("hostname is required without surrounding whitespace")
    if "://" in host or "@" in host or "/" in host or ":" in host:
        raise ValueError("hostname must not contain scheme, credentials, path or port")
    if not HOST_RE.fullmatch(host):
        raise ValueError("hostname must be a valid FQDN")
    return host.lower()


def validate_port(port: int) -> int:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("loopback port must be an integer from 1024 to 65535")
    return port


def render(host: str, port: int, template: Path = TEMPLATE) -> str:
    host = validate_host(host)
    port = validate_port(port)
    text = template.read_text(encoding="utf-8")
    if text.count("__PORTAL_HOST__") < 1:
        raise ValueError("hostname placeholder is missing from nginx template")
    if text.count("__PORTAL_LOOPBACK_PORT__") < 1:
        raise ValueError("loopback port placeholder is missing from nginx template")
    rendered = (
        text.replace("__PORTAL_HOST__", host)
        .replace("__PORTAL_LOOPBACK_PORT__", str(port))
    )
    if "__PORTAL_" in rendered:
        raise ValueError("unresolved PORTAL placeholder remains")
    expected = f"proxy_pass http://127.0.0.1:{port};"
    if expected not in rendered:
        raise ValueError("rendered proxy is not loopback-only")
    if "proxy_pass http://0.0.0.0:" in rendered:
        raise ValueError("unsafe public bind found in rendered nginx config")
    return rendered


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--output", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    output = Path(args.output).expanduser().resolve()
    if output.exists() and not args.force:
        raise SystemExit("output exists; use --force only after reviewing the target")
    rendered = render(args.host, args.port)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

    result = {
        "output": str(output),
        "host": validate_host(args.host),
        "loopback_port": validate_port(args.port),
        "sha256": sha256_text(rendered),
        "contains_secrets": False,
        "production_mutation": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
