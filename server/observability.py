"""Opt-in, privacy-minimized server telemetry.

Only fixed event names and coarse server metadata are sent. No request-derived
value is trusted until it passes a strict allowlist.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

DEFAULT_POSTHOG_HOST = "https://eu.i.posthog.com"
ALLOWED_HOSTS = {DEFAULT_POSTHOG_HOST}
ALLOWED_ROUTE_PARTS = frozenset({
    "api", "v3", "platform", "companies", "audit", "me", "company",
    "dashboard", "clients", "admin", "operations", "work", "mine",
    "payroll", "materials", "jobs", "invoices", "users", "login",
    "invitations", "code-interpreter", "messenger-relay-ticket",
})
SAFE_LABEL = re.compile(r"^[A-Za-z0-9._+-]{1,80}$")
EVENTS = {"portal_server_started", "portal_server_error", "portal_server_slow_request"}


def _trusted_host(value: str) -> str:
    try:
        parsed = urlsplit((value or "").strip())
        if (parsed.scheme != "https" or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.path not in ("", "/") or
                parsed.port not in (None, 443)):
            return ""
        origin = f"https://{(parsed.hostname or '').lower()}"
        return origin if origin in ALLOWED_HOSTS else ""
    except (ValueError, TypeError):
        return ""


def _safe_label(value: str) -> str:
    value = str(value or "")
    value = re.sub(r"[^A-Za-z0-9._+-]+", "-", value).strip("-._+")[:80]
    return value if value and SAFE_LABEL.fullmatch(value) else "unknown"


def _safe_route(value: str) -> str:
    # Accept a path only. URLs, query strings, filenames and arbitrary resource
    # names collapse to the single coarse label "unknown".
    if not isinstance(value, str) or not value.startswith("/") or "?" in value or "#" in value:
        return "unknown"
    parts = value.strip("/").split("/")
    if not parts or any(p not in ALLOWED_ROUTE_PARTS and not p.isdecimal() for p in parts):
        return "unknown"
    return "/" + "/".join("{id}" if p.isdecimal() else p for p in parts)


class PortalObservability:
    def __init__(self, client=None, *, build_id="", environment="", slow_ms=2000):
        self.client = client
        self.build_id = _safe_label(build_id)
        self.environment = _safe_label(environment)
        try:
            self.slow_ms = max(250, int(slow_ms))
        except (TypeError, ValueError):
            self.slow_ms = 2000

    @property
    def enabled(self):
        return self.client is not None

    @classmethod
    def from_env(cls, env=None, *, build_id="", environment="", client_factory=None):
        env = os.environ if env is None else env
        key = (env.get("PORTAL_POSTHOG_PROJECT_KEY") or "").strip()
        if not key:
            return cls(build_id=build_id, environment=environment)
        host = _trusted_host(env.get("PORTAL_POSTHOG_HOST") or DEFAULT_POSTHOG_HOST)
        if not host:
            return cls(build_id=build_id, environment=environment)
        try:
            if client_factory is None:
                from posthog import Posthog
                client_factory = Posthog
            client = client_factory(
                project_api_key=key, host=host, debug=False,
                disable_geoip=True, enable_exception_autocapture=False,
            )
            slow_ms = env.get("PORTAL_POSTHOG_SLOW_MS", "2000")
            return cls(client, build_id=build_id, environment=environment, slow_ms=slow_ms)
        except Exception:
            # Import/configuration failure must not affect server startup.
            return cls(build_id=build_id, environment=environment)

    def _send(self, event, properties=None):
        if not self.client or event not in EVENTS:
            return False
        payload = {
            "$process_person_profile": False,
            "$geoip_disable": True,
            "service": "portal-server",
            "build": self.build_id,
            "environment": self.environment,
        }
        payload.update(properties or {})
        try:
            # A fixed service identity groups deployment events without user or
            # tenant identifiers. Person profile processing is disabled above.
            self.client.capture("portal-server", event, properties=payload)
            return True
        except Exception:
            return False

    def server_started(self):
        return self._send("portal_server_started")

    def request_result(self, *, method, route, status, duration_ms, exception_type=None):
        try:
            status = int(status or 0)
            duration_ms = max(0, int(duration_ms or 0))
        except (TypeError, ValueError):
            return False
        is_error = status >= 500 or bool(exception_type)
        is_slow = duration_ms >= self.slow_ms
        if not (is_error or is_slow):
            return False
        props = {
            "method": method if method in ("GET", "POST") else "OTHER",
            "route": _safe_route(route),
            "status_class": f"{status // 100}xx" if status else "unknown",
            "duration_ms": duration_ms,
        }
        if exception_type:
            # Only a Python class name, never exception text or traceback data.
            name = getattr(exception_type, "__name__", "") if isinstance(exception_type, type) else ""
            props["exception_type"] = _safe_label(name)
        return self._send("portal_server_error" if is_error else "portal_server_slow_request", props)

    def shutdown(self):
        if self.client:
            try:
                self.client.shutdown()
            except Exception:
                pass
