from __future__ import annotations

import argparse
import ipaddress
import pathlib
import plistlib
import re
import struct
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[2]
IOS = ROOT / "ios_src" / "PortalIOS"
INFO = IOS / "Info.plist"
PRIVACY = IOS / "PrivacyInfo.xcprivacy"
ICON = IOS / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon.png"
PROJECT = ROOT / "ios_src" / "project.yml"
ASSETS = ROOT / "android_src" / "app" / "src" / "main" / "assets"

def fail(message: str) -> None:
    raise SystemExit(f"IOS RELEASE CONFIG FAIL: {message}")

def stable_https(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return False
        if parsed.port not in (None, 443) or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            return False
        if host == "portal.invalid" or host == "localhost" or host.endswith(".localhost"):
            return False
        if host.endswith(".sslip.io") or host.endswith(".trycloudflare.com"):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return True
    except ValueError:
        return False

def validate_png() -> None:
    raw = ICON.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) < 33:
        fail("AppIcon.png is not a valid PNG")
    length = struct.unpack(">I", raw[8:12])[0]
    if raw[12:16] != b"IHDR" or length != 13:
        fail("AppIcon.png has invalid IHDR")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", raw[16:26])
    if (width, height) != (1024, 1024):
        fail("AppIcon.png must be exactly 1024x1024")
    if bit_depth != 8 or color_type in (4, 6):
        fail("AppIcon.png must be 8-bit RGB without alpha")

def validate_privacy() -> None:
    with PRIVACY.open("rb") as handle:
        data = plistlib.load(handle)
    if data.get("NSPrivacyTracking") is not False:
        fail("privacy manifest must explicitly disable tracking")
    accessed = data.get("NSPrivacyAccessedAPITypes") or []
    defaults = [
        row for row in accessed
        if row.get("NSPrivacyAccessedAPIType") == "NSPrivacyAccessedAPICategoryUserDefaults"
    ]
    if len(defaults) != 1 or "CA92.1" not in defaults[0].get("NSPrivacyAccessedAPITypeReasons", []):
        fail("UserDefaults required-reason API must declare CA92.1")
    required = {
        "NSPrivacyCollectedDataTypeName",
        "NSPrivacyCollectedDataTypeUserID",
        "NSPrivacyCollectedDataTypeOtherFinancialInfo",
        "NSPrivacyCollectedDataTypeOtherUserContent",
        "NSPrivacyCollectedDataTypeProductInteraction",
    }
    collected = {row.get("NSPrivacyCollectedDataType") for row in data.get("NSPrivacyCollectedDataTypes", [])}
    if not required.issubset(collected):
        fail("privacy manifest is missing PORTAL collected data categories")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url")
    parser.add_argument("--team-id")
    args = parser.parse_args()

    with INFO.open("rb") as handle:
        info = plistlib.load(handle)
    if info.get("PORTALDefaultAPIURL") != "$(PORTAL_API_URL)":
        fail("Info.plist must receive PORTAL_API_URL from build settings")
    if info.get("ITSAppUsesNonExemptEncryption") is not False:
        fail("PORTAL uses only exempt system encryption and must declare that explicitly")

    project = PROJECT.read_text(encoding="utf-8")
    if "ASSETCATALOG_COMPILER_APPICON_NAME: AppIcon" not in project:
        fail("AppIcon asset catalog is not selected")
    if "PORTAL_API_URL:" not in project:
        fail("PORTAL_API_URL build setting is missing")

    validate_png()
    validate_privacy()

    for name in ("privacy.html", "support.html"):
        if not (ASSETS / name).is_file():
            fail(f"public {name} page is missing")

    if args.api_url and not stable_https(args.api_url):
        fail("production API must be a stable owned HTTPS origin, not IP/sslip/trycloudflare/placeholder")
    if args.team_id and re.fullmatch(r"[A-Z0-9]{10}", args.team_id) is None:
        fail("Apple Team ID must be 10 uppercase letters/digits")

    print("IOS RELEASE CONFIG OK")

if __name__ == "__main__":
    main()
