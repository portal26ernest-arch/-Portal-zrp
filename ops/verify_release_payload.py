#!/usr/bin/env python3
"""Fail-closed check for PORTAL release payload completeness and optional HTTP smoke."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REQUIRED_FILES = (
    "server/portal_app_server.py",
    "server/web_static.py",
    "android_src/app/src/main/assets/index.html",
    "android_src/app/src/main/assets/ui.css",
    "android_src/app/src/main/assets/core.js",
    "android_src/app/src/main/assets/app.js",
    "android_src/app/src/main/assets/screens.js",
    "android_src/app/src/main/assets/messenger_notifications.js",
    "android_src/app/src/main/assets/production.js",
    "android_src/app/src/main/assets/preview.js",
    "android_src/app/src/main/assets/invoices.js",
    "android_src/app/src/main/assets/documents_excel.js",
    "android_src/app/src/main/assets/web_adapter.js",
    "android_src/app/src/main/assets/brand-mark.svg",
    "android_src/app/src/main/assets/stickers/catalog.json",
)
SMOKE_PATHS = ("/api/ping", "/api/ready", "/web/", "/web/app.js", "/web/production.js")

def verify_payload(root: Path):
    missing, empty = [], []
    for rel in REQUIRED_FILES:
        p = root / rel
        if not p.is_file():
            missing.append(rel)
        elif p.stat().st_size == 0:
            empty.append(rel)
    return missing, empty

def smoke(base_url: str, timeout: float = 10.0):
    failures = []
    base = base_url.rstrip("/")
    for path in SMOKE_PATHS:
        try:
            req = Request(base + path, headers={"User-Agent": "PORTAL-release-integrity/1"})
            with urlopen(req, timeout=timeout) as response:
                body = response.read(1024 * 1024)
                if response.status != 200 or not body:
                    failures.append(f"{path}:status={response.status}:bytes={len(body)}")
                    continue
                if path == "/api/ping":
                    data = json.loads(body.decode("utf-8"))
                    if data.get("ok") is not True:
                        failures.append("/api/ping:ok!=true")
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{path}:{type(exc).__name__}:{exc}")
    return failures

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Extracted release root")
    ap.add_argument("--base-url", help="Optional deployed origin, e.g. https://portal.example")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    missing, empty = verify_payload(root)
    smoke_failures = smoke(args.base_url, args.timeout) if args.base_url else []
    result = {
        "go": not missing and not empty and not smoke_failures,
        "root": str(root),
        "missing": missing,
        "empty": empty,
        "smoke_failures": smoke_failures,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["go"] else 3

if __name__ == "__main__":
    raise SystemExit(main())
