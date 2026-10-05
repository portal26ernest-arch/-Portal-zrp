"""Strict static serving for the shared browser/Desktop client."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import gzip
import hashlib
import json
import mimetypes
import os

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "android_src" / "app" / "src" / "main" / "assets"
RELEASE_PROPERTIES = ROOT / "android_src" / "release.properties"
FIXED = {"index.html", "privacy.html", "support.html", "ui.css", "core.js", "app.js", "screens.js", "production.js", "preview.js", "invoices.js", "documents_excel.js", "build_meta.js", "web_adapter.js", "desktop_mascots.js", "brand-mark.svg", "stickers/catalog.json"}
COMPRESSIBLE = frozenset({".html", ".js", ".css", ".svg", ".json"})


def _release_properties():
    values = {}
    for raw in RELEASE_PROPERTIES.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _build_meta_script():
    values = _release_properties()
    try:
        version_code = int(values.get("versionCode", "0"))
    except ValueError:
        version_code = 0
    metadata = {
        "applicationId": "ru.portal.web",
        "versionName": values.get("versionName", ""),
        "versionCode": version_code,
        "buildNumber": os.environ.get("PORTAL_BUILD_NUMBER") or values.get("buildNumber", ""),
        "buildDate": os.environ.get("PORTAL_BUILD_DATE") or values.get("buildDate", ""),
        "channel": values.get("channel", "release"),
        "updatesConfigured": False,
        "platform": "Web",
    }
    payload = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    return ("window.__PORTAL_BUILD_METADATA__=window.__PORTAL_BUILD_METADATA__||" + payload + ";\n").encode("utf-8")


def _security_headers(handler):
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def serve(handler):
    parsed = urlsplit(handler.path)
    raw = parsed.path
    if parsed.query or parsed.fragment:
        return handler.send_error(404)
    try:
        decoded = unquote(raw, errors="strict")
    except (UnicodeError, ValueError):
        return handler.send_error(404)
    if "%" in decoded or "\\" in raw or "\\" in decoded or ".." in decoded or "//" in raw:
        return handler.send_error(404)
    if decoded in ("/web", "/web/"):
        name = "index.html"
    elif decoded.startswith("/web/"):
        name = decoded[5:]
    else:
        return handler.send_error(404)
    allowed = name in FIXED or (name.startswith("stickers/") and name.endswith(".svg") and name.count("/") == 1)
    target = (ASSETS / name).resolve()
    if not allowed or name.startswith(".") or ASSETS not in target.parents or not target.is_file():
        return handler.send_error(404)

    request_accept_encoding = str(handler.headers.get("Accept-Encoding", ""))
    request_etag = str(handler.headers.get("If-None-Match", ""))
    data = _build_meta_script() if name == "build_meta.js" else target.read_bytes()
    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
    cache_control = "no-cache, max-age=0, must-revalidate" if name in {"index.html", "build_meta.js"} else "private, max-age=3600, must-revalidate"

    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if target.suffix == ".js":
        mime = "text/javascript"
    if target.suffix in (".html", ".js", ".css"):
        mime += "; charset=utf-8"

    if request_etag == etag:
        handler.send_response(304)
        handler.send_header("ETag", etag)
        handler.send_header("Cache-Control", cache_control)
        handler.send_header("Vary", "Accept-Encoding")
        _security_headers(handler)
        handler.end_headers()
        return

    encoded = data
    use_gzip = len(data) >= 1024 and target.suffix in COMPRESSIBLE and "gzip" in request_accept_encoding.lower()
    if use_gzip:
        encoded = gzip.compress(data, compresslevel=6)

    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", cache_control)
    handler.send_header("ETag", etag)
    handler.send_header("Vary", "Accept-Encoding")
    if use_gzip:
        handler.send_header("Content-Encoding", "gzip")
    _security_headers(handler)
    handler.end_headers()
    handler.wfile.write(encoded)
