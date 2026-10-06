"""Short-lived authenticated credentials for the PORTAL Messenger relay.

The app never embeds a relay password. A signed ticket is issued by the authenticated
PORTAL API and validated by the relay with a shared deployment-only secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

REALM = "PORTAL Messenger Relay"
DEFAULT_TTL_SECONDS = 12 * 60 * 60
USERNAME_RE = re.compile(r"^v1\.(\d+)\.(\d+)\.(\d+)\.([A-Za-z0-9_-]{8,64})$")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def normalize_proxy_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("PORTAL_MESSENGER_RELAY_URL is not configured")
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Messenger relay must use a dedicated HTTPS proxy URL")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Messenger relay URL must contain only scheme, host and optional port")
    port = parsed.port or 443
    if not 1 <= port <= 65535:
        raise ValueError("Messenger relay port is invalid")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
        raise ValueError("Messenger relay must use an owned remote HTTPS host")
    return f"https://{host}" + ("" if port == 443 else f":{port}")


def relay_status(env=os.environ):
    url = env.get("PORTAL_MESSENGER_RELAY_URL", "").strip()
    secret = env.get("PORTAL_MESSENGER_RELAY_SECRET", "")
    if not url or len(secret) < 32:
        return {"enabled": False}
    try:
        normalized = normalize_proxy_url(url)
    except ValueError:
        return {"enabled": False}
    return {"enabled": True, "proxy_url": normalized, "realm": REALM}


def issue_ticket(user_id: int, company_id: int, env=os.environ, now: int | None = None):
    status = relay_status(env)
    if not status["enabled"]:
        return status
    if type(user_id) is not int or user_id <= 0 or type(company_id) is not int or company_id <= 0:
        raise ValueError("Relay ticket requires numeric user and company identifiers")
    ttl = int(env.get("PORTAL_MESSENGER_RELAY_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))
    ttl = max(300, min(ttl, 24 * 60 * 60))
    issued = int(time.time() if now is None else now)
    expires = issued + ttl
    nonce = secrets.token_urlsafe(12)
    username = f"v1.{user_id}.{company_id}.{expires}.{nonce}"
    password = _b64url(hmac.new(env["PORTAL_MESSENGER_RELAY_SECRET"].encode("utf-8"), username.encode("utf-8"), hashlib.sha256).digest())
    return {
        **status,
        "username": username,
        "password": password,
        "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def validate_ticket(username: str, password: str, secret: str, now: int | None = None):
    if not isinstance(username, str) or not isinstance(password, str) or len(secret) < 32:
        return None
    match = USERNAME_RE.fullmatch(username)
    if not match:
        return None
    user_id, company_id, expires, _nonce = match.groups()
    expires = int(expires)
    current = int(time.time() if now is None else now)
    if expires < current or expires > current + 24 * 60 * 60 + 300:
        return None
    expected = _b64url(hmac.new(secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, password):
        return None
    return {"user_id": int(user_id), "company_id": int(company_id), "expires": expires}
