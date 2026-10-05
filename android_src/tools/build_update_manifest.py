#!/usr/bin/env python3
"""Build a deterministic PORTAL Android update manifest for GitHub Releases."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def load_properties(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise ValueError(f"Некорректная строка release.properties: {raw}")
        out[key.strip()] = value.strip()
    if os.environ.get("PORTAL_BUILD_NUMBER"):
        out["buildNumber"] = os.environ["PORTAL_BUILD_NUMBER"]
    if os.environ.get("PORTAL_BUILD_DATE"):
        out["buildDate"] = os.environ["PORTAL_BUILD_DATE"]
    return out


def require_https(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError(f"{label} должен быть HTTPS URL без userinfo")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--properties", default="android_src/release.properties")
    parser.add_argument("--apk", required=True)
    parser.add_argument("--apk-url", required=True)
    parser.add_argument("--changelog", default="Обновление PORTAL.")
    parser.add_argument("--out", default="portal-update.json")
    args = parser.parse_args()

    props = load_properties(Path(args.properties))
    apk = Path(args.apk)
    if not apk.is_file():
        raise SystemExit("ОШИБКА: APK не найден")

    version_name = props.get("versionName", "")
    version_code = int(props.get("versionCode", "0"))
    build_number = props.get("buildNumber", "")
    channel = props.get("channel", "")
    if not version_name or version_code <= 0 or not build_number:
        raise SystemExit("ОШИБКА: неполные release metadata")
    if channel != "release":
        raise SystemExit("ОШИБКА: manifest разрешён только для release-канала")
    if len(args.changelog) > 4000:
        raise SystemExit("ОШИБКА: описание изменений длиннее 4000 символов")

    apk_url = require_https(args.apk_url, "apkUrl")
    sha256 = hashlib.sha256(apk.read_bytes()).hexdigest()
    published_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    manifest = {
        "schemaVersion": 1,
        "applicationId": "ru.portal.app",
        "channel": "release",
        "versionCode": version_code,
        "versionName": version_name,
        "buildNumber": build_number,
        "publishedAt": published_at,
        "changelog": args.changelog or "Обновление PORTAL.",
        "apkUrl": apk_url,
        "sha256": sha256,
    }
    Path(args.out).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"MANIFEST_OK {args.out}")
    print(f"APK_SHA256 {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
