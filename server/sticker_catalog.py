"""Validated shared catalog for server-approved internal chat stickers."""
from pathlib import Path
import json
import re

ASSETS = Path(__file__).resolve().parents[1] / "android_src" / "app" / "src" / "main" / "assets"
CATALOG = ASSETS / "stickers" / "catalog.json"
SAFE_KEY = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
SAFE_ASSET = re.compile(r"[a-z0-9_]+\.(?:svg|png|webp|gif)\Z", re.IGNORECASE)


def catalog_entries(*, enabled_only=False):
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("stickers"), list):
        raise ValueError("Invalid sticker catalog")
    seen = set()
    result = []
    for item in data["stickers"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid sticker entry")
        key, asset, label, enabled = item.get("key"), item.get("asset"), item.get("label"), item.get("enabled")
        if not isinstance(key, str) or not SAFE_KEY.fullmatch(key) or key in seen:
            raise ValueError("Invalid or duplicate sticker key")
        if not isinstance(asset, str) or not SAFE_ASSET.fullmatch(asset) or "/" in asset or "\\" in asset:
            raise ValueError("Invalid sticker asset name")
        if not isinstance(label, str) or not label.strip() or len(label) > 80 or type(enabled) is not bool:
            raise ValueError("Invalid sticker metadata")
        seen.add(key)
        if enabled and not (ASSETS / "stickers" / asset).is_file():
            raise ValueError("Enabled sticker asset is missing")
        if enabled_only and not enabled:
            continue
        result.append({"key": key, "label": label, "asset": asset, "enabled": enabled})
    return result


def allowed_sticker_keys():
    return {entry["key"] for entry in catalog_entries(enabled_only=True)}
