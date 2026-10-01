"""Public, secret-free PORTAL Desktop update manifest."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

_FIELDS = {
    "version": "PORTAL_DESKTOP_UPDATE_VERSION",
    "build": "PORTAL_DESKTOP_UPDATE_BUILD",
    "download_url": "PORTAL_DESKTOP_UPDATE_URL",
    "sha256": "PORTAL_DESKTOP_UPDATE_SHA256",
}
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _safe_download_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    if not parsed.path.lower().endswith(".zip"):
        return False
    if parsed.scheme == "https" and parsed.netloc:
        return True
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}


def load_manifest(environ) -> dict | None:
    values = {key: str(environ.get(env_name, "")).strip() for key, env_name in _FIELDS.items()}
    if not any(values.values()):
        return None
    if not all(values.values()):
        raise RuntimeError("Desktop update manifest is incomplete")
    try:
        build = int(values["build"])
    except ValueError as exc:
        raise RuntimeError("Desktop update build is invalid") from exc
    if build <= 0 or build > 2_147_483_647:
        raise RuntimeError("Desktop update build is invalid")
    if not re.fullmatch(r"\d+\.\d+\.\d+", values["version"]):
        raise RuntimeError("Desktop update version is invalid")
    if not _SHA256.fullmatch(values["sha256"]):
        raise RuntimeError("Desktop update SHA-256 is invalid")
    if not _safe_download_url(values["download_url"]):
        raise RuntimeError("Desktop update URL must use HTTPS")

    return {
        "build": build,
        "version": values["version"],
        "download_url": values["download_url"],
        "sha256": values["sha256"].lower(),
    }
