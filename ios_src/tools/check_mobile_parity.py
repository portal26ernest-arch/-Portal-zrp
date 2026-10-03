from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
ANDROID_RELEASE = ROOT / "android_src" / "release.properties"
IOS_PROJECT = ROOT / "ios_src" / "project.yml"
IOS_BRIDGE = ROOT / "ios_src" / "PortalIOS" / "PortalNativeBridge.swift"
IOS_LOCAL_CACHE = ROOT / "ios_src" / "PortalIOS" / "PortalLocalCache.swift"


def fail(message: str) -> None:
    print(f"MOBILE PARITY FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_properties(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result

android = read_properties(ANDROID_RELEASE)
project = IOS_PROJECT.read_text(encoding="utf-8")
bridge = IOS_BRIDGE.read_text(encoding="utf-8")
local_cache = IOS_LOCAL_CACHE.read_text(encoding="utf-8") if IOS_LOCAL_CACHE.exists() else ""

version_name = android.get("versionName")
version_code = android.get("versionCode")
if not version_name or not version_code:
    fail("android release.properties has no versionName/versionCode")

ios_version = re.search(r'^\s*MARKETING_VERSION:\s*"?([^"\r\n]+)"?\s*$', project, re.M)
ios_build = re.search(r'^\s*CURRENT_PROJECT_VERSION:\s*"?([^"\r\n]+)"?\s*$', project, re.M)
if not ios_version or ios_version.group(1).strip() != version_name:
    fail(f"iOS MARKETING_VERSION must match Android versionName={version_name}")
if not ios_build or ios_build.group(1).strip() != version_code:
    fail(f"iOS CURRENT_PROJECT_VERSION must match Android versionCode={version_code}")

shared_assets = "../android_src/app/src/main/assets"
if shared_assets not in project:
    fail("iOS must package the canonical shared mobile assets directly")

for header in ('"X-Portal-Client"', '"Authorization"', '"X-Portal-Company"'):
    if header not in bridge:
        fail(f"iOS bridge is missing required API header contract {header}")

for marker in ('PortalLocalCache()', 'cacheCompany', 'isCacheable(path)', 'cached["cached"] = true', 'invalidateCache(serverOrigin:', 'portalNativeReply', 'queueMutation', 'pendingMutations'):
    if marker not in bridge:
        fail(f"iOS bridge is missing local-first cache/outbox contract {marker}")
for marker in ('AES.GCM', 'kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly', 'company-cache', 'company-outbox', 'func delete(serverOrigin:', 'maxOutboxItems = 1000', '30 * 24 * 60 * 60'):
    if marker not in local_cache:
        fail(f"iOS local cache is missing protection/retention contract {marker}")

duplicated_assets = ROOT / "ios_src" / "PortalIOS" / "assets"
if duplicated_assets.exists():
    fail("do not fork/copy shared UI into ios_src/PortalIOS/assets")

print(
    "MOBILE PARITY OK: "
    f"Android/iOS version {version_name} ({version_code}), "
    "shared assets are single-source, API bridge headers and encrypted local cache present"
)
