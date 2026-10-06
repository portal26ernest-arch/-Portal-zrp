"""Privacy-minimized, fail-open PORTAL server observability.

PostHog is opt-in via PORTAL_POSTHOG_PROJECT_KEY. No user, tenant, token,
request body, query string, document or financial data is captured here.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

DEFAULT_POSTHOG_HOST = "https://eu.i.posthog.com"
ALLOWED_POSTHOG_HOSTS = {DEFAULT_POSTHOG_HOST}


def _normalized_host(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ""
    if parsed.path not in ("", "/") or parsed.port not in (None, 443):
        return ""
    origin = f"https://{(parsed.hostname or '').lower()}"
    return origin if origin in ALLOWED_POSTHOG_HOSTS else ""


class PortalObservability:
    def __init__(self, client=None, *, build_id="", environment="", slow_ms=2000):
        self.client = client
        self.build_id = str(build_id or "")
        self.environment = str(environment or "")
        self.slow_ms = max(250, int(slow_ms or 2000))

    @property
    def enabled(self):
        return self.client is not None

    @classmethod
    def from_env(cls, env=None, *, build_id="", environment="", client_factory=None):
        env = os.environ if env is None else env
        key = (env.get("PORTAL_POSTHOG_PROJECT_KEY") or "").strip()
        if not key:
            return cls(build_id=build_id, environment=environment)

        host = _normalized_host(env.get("PORTAL_POSTHOG_HOST") or DEFAULT_POSTHOG_HOST)
        if not host:
            sys.stderr.write("[observability] disabled: untrusted PostHog host\n")
            return cls(build_id=build_id, environment=environment)

        try:
            if client_factory is None:
                from posthog import Posthog
                client_factory = Posthog
            client = client_factory(
                project_api_key=key,
                host=host,
                debug=False,
                disable_geoip=True,
            )
        except Exception as exc:
            sys.stderr.write(f"[observability] disabled: {type(exc).__name__}\n")
            return cls(build_id=build_id, environment=environment)

        try:
            slow_ms = int(env.get("PORTAL_POSTHOG_SLOW_MS", "2000"))
        except (TypeError, ValueError):
            slow_ms = 2000
        return cls(client, build_id=build_id, environment=environment, slow_ms=slow_ms)

    def _properties(self, extra=None):
        props = {
            "$process_person_profile": False,
            "$geoip_disable": True,
            "service": "portal-server",
            "build": self.build_id,
            "environment": self.environment,
        }
        if extra:
            props.update(extra)
        return props

    def capture(self, event, properties=None):
        if not self.client:
            return False
        try:
            self.client.capture(str(event), properties=self._properties(properties))
            return True
        except Exception:
            # Observability must never become a production dependency.
            return False

    def server_started(self):
        return self.capture("portal_server_started")

    def request_result(self, *, method, route, status, duration_ms, exception_type=None):
        status = int(status or 0)
        duration_ms = max(0, int(duration_ms or 0))
        is_error = status >= 500 or bool(exception_type)
        is_slow = duration_ms >= self.slow_ms
        if not (is_error or is_slow):
            return False
        props = {
            "method": str(method or "")[:12],
            "route": str(route or "unknown")[:160],
            "status_class": f"{status // 100}xx" if status else "unknown",
            "duration_ms": duration_ms,
        }
        if exception_type:
            # Deliberately capture only the exception class, never the message,
            # traceback locals, request body or SQL text.
            props["exception_type"] = str(exception_type)[:120]
        return self.capture("portal_server_error" if is_error else "portal_server_slow_request", props)

    def shutdown(self):
        if not self.client:
            return
        try:
            self.client.shutdown()
        except Exception:
            pass
