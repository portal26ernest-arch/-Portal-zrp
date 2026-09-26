#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"
export PORTAL_DB="${PORTAL_DB:-$SCRIPT_DIR/portal.db}"
export PORTAL_APP_HOST="${PORTAL_APP_HOST:-127.0.0.1}"
export PORTAL_APP_PORT="${PORTAL_APP_PORT:-8765}"
exec python3 "$SCRIPT_DIR/portal_app_server.py"
