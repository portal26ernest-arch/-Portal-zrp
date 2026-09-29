"""Strict static serving for the shared browser client."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
import mimetypes

ASSETS = Path(__file__).resolve().parents[1] / "android_src" / "app" / "src" / "main" / "assets"
FIXED = {"index.html", "ui.css", "core.js", "app.js", "screens.js", "production.js", "preview.js", "documents_excel.js", "web_adapter.js", "brand-mark.svg", "stickers/catalog.json"}

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
    data = target.read_bytes()
    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if target.suffix == ".js": mime = "text/javascript"
    if target.suffix in (".html", ".js", ".css"): mime += "; charset=utf-8"
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
    handler.end_headers()
    handler.wfile.write(data)
