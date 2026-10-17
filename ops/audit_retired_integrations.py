#!/usr/bin/env python3
"""Read-only inventory of retired external messaging/VPN integrations.

Use --enforce after deliberate removal to fail if executable/active code still
references retired provider integrations. Historical migrations are reported
separately; do not destroy existing user/accounting records.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

PATTERNS = {
    "telegram": re.compile(r"telegram|телеграм|t\.me/|api\.telegram\.org", re.I),
    "max_provider": re.compile(r"max\.ru|MAX_(?:BOT|CHAT|TOKEN|API)|max[_-](?:bot|relay|session|provider|auth|messenger)|(?<![A-Za-z])MAX(?:\s+messenger)?(?![A-Za-z])", re.I),
    "vpn_tor": re.compile(r"\bVPN\b|\bwireguard\b|\bopenvpn\b|\bsocks5?\b|\btorrc\b|portal-messenger-tor|redshield", re.I),
    "messenger": re.compile(r"\bmessenger\b|messenger[_-]|messenger[A-Z]", re.I),
}
EXCLUDED_SELF = {"ops/audit_retired_integrations.py", ".github/workflows/retired-integrations-audit.yml"}
ACTIVE_PREFIXES = ("android_src/", "desktop/", "desktop_windows/", "ios_src/", "server/", "site/", "ops/", ".github/", "deploy/", "tools/")
CODE_SUFFIXES = {".py", ".js", ".cjs", ".mjs", ".java", ".swift", ".cs", ".xaml", ".xml", ".json", ".yml", ".yaml", ".ps1", ".sh", ".html", ".sql", ".toml", ".gradle"}
def classify(path: str) -> str:
    if path.endswith((".md", ".txt")) or path.startswith("docs/"):
        return "docs"
    if "/migrations/" in path or path.startswith("server/migrations/"):
        return "historical_sql"
    if path.startswith(ACTIVE_PREFIXES) and (Path(path).suffix.lower() in CODE_SUFFIXES or Path(path).name.startswith(".env")):
        return "active"
    return "other"

def run() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enforce", action="store_true", help="fail on active references")
    args = parser.parse_args()
    output = subprocess.check_output(["git", "ls-files", "-z"])
    hits = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        if rel in EXCLUDED_SELF:
            continue
        path = Path(rel)
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".zip", ".apk", ".webp"}:
            continue
        try:
            contents = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        rows = []
        for number, line in enumerate(contents.splitlines(), 1):
            kinds = [kind for kind, pattern in PATTERNS.items() if pattern.search(line)]
            if kinds:
                rows.append({"line": number, "kinds": kinds, "preview": line.strip()[:150]})
        if rows:
            hits.append({"path": rel, "tier": classify(rel), "matches": len(rows), "samples": rows[:3]})
    counts = {tier: sum(1 for hit in hits if hit["tier"] == tier) for tier in ("active", "historical_sql", "docs", "other")}
    print("RETIRED_INTEGRATIONS_AUDIT " + json.dumps({"file_counts": counts, "matched_files": hits}, ensure_ascii=False))
    if args.enforce and counts["active"]:
        print("FAIL: retired provider/VPN references remain in active code.")
        return 1
    print("OK: inventory completed; no files modified.")
    return 0

if __name__ == "__main__":
    raise SystemExit(run())
