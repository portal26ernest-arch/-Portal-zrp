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
USERNAME_RE = re.compile(r"^v2\.telegram\.(\d+)\.(\d+)\.(\d+)\.([A-Za-z0-9_-]{8,64})$")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _normalize_owned_remote_url(value: str, *, scheme: str, label: str, allow_path: str = "") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is not configured")
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() != scheme or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{label} must use a dedicated {scheme.upper()} URL")
    expected_paths = ("", "/") if not allow_path else (allow_path,)
    if parsed.path not in expected_paths or parsed.query or parsed.fragment:
        raise ValueError(f"{label} contains an unexpected path/query/fragment")
    port = parsed.port or 443
    if not 1 <= port <= 65535:
        raise ValueError(f"{label} port is invalid")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
        raise ValueError(f"{label} must use an owned remote host")
    path = allow_path if allow_path else ""
    return f"{scheme}://{host}" + ("" if port == 443 else f":{port}") + path


def normalize_proxy_url(value: str) -> str:
    return _normalize_owned_remote_url(
        value,
        scheme="https",
        label="PORTAL_MESSENGER_RELAY_URL",
    )


def normalize_wss_url(value: str) -> str:
    return _normalize_owned_remote_url(
        value,
        scheme="wss",
        label="PORTAL_MESSENGER_RELAY_WSS_URL",
        allow_path="/connect",
    )


def relay_status(env=os.environ):
    required_value = str(env.get("PORTAL_TELEGRAM_RELAY_REQUIRED", "0")).strip().lower()
    required = required_value in {"1", "true", "yes", "on"}
    secret = env.get("PORTAL_MESSENGER_RELAY_SECRET", "")
    status = {"provider": "telegram", "enabled": False, "required": required}
    if len(secret) < 32:
        return status

    proxy_url = env.get("PORTAL_MESSENGER_RELAY_URL", "").strip()
    wss_url = env.get("PORTAL_MESSENGER_RELAY_WSS_URL", "").strip()
    if proxy_url:
        try:
            status["proxy_url"] = normalize_proxy_url(proxy_url)
        except ValueError:
            pass
    if wss_url:
        try:
            status["wss_url"] = normalize_wss_url(wss_url)
        except ValueError:
            pass
    if "proxy_url" not in status and "wss_url" not in status:
        return status
    status["enabled"] = True
    status["realm"] = REALM
    return status


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
    username = f"v2.telegram.{user_id}.{company_id}.{expires}.{nonce}"
    password = _b64url(
        hmac.new(
            env["PORTAL_MESSENGER_RELAY_SECRET"].encode("utf-8"),
            username.encode("utf-8"),
            hashlib.sha256,
        ).digest()
    )
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
    expected = _b64url(
        hmac.new(secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, password):
        return None
    return {
        "user_id": int(user_id),
        "company_id": int(company_id),
        "expires": expires,
        "scope": "telegram",
    }
