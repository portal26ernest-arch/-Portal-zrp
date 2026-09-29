#!/usr/bin/env python3
"""Fail-closed local contract check for a release APK and update manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_update_manifest import load_properties


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--properties", required=True, type=Path)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    props = load_properties(args.properties)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    version = props["versionName"]
    if props.get("channel") != "release" or args.tag != f"portal-android-v{version}":
        raise SystemExit("release channel/tag mismatch")
    expected_url = f"https://github.com/{args.repository}/releases/download/{args.tag}/PORTAL_Android_{version}_release.apk"
    digest_obj = hashlib.sha256()
    with args.apk.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest_obj.update(chunk)
    digest = digest_obj.hexdigest()
    expected = {
        "schemaVersion": 1,
        "applicationId": "ru.portal.app",
        "channel": "release",
        "versionCode": int(props["versionCode"]),
        "versionName": version,
        "buildNumber": props["buildNumber"],
        "apkUrl": expected_url,
        "sha256": digest,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise SystemExit("release manifest does not match APK/release metadata")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"]):
        raise SystemExit("invalid manifest SHA-256")
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT.*Z", manifest.get("publishedAt", "")):
        raise SystemExit("invalid manifest publishedAt")
    print("RELEASE_ARTIFACT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
