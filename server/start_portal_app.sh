#!/data/data/com.termux/files/usr/bin/bash
set -e
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"
export PORTAL_DB="${PORTAL_DB:-/storage/emulated/0/PORTAL-BOT/portal.db}"
export PORTAL_APP_HOST="${PORTAL_APP_HOST:-0.0.0.0}"
export PORTAL_APP_PORT="${PORTAL_APP_PORT:-8765}"
exec python "$SCRIPT_DIR/portal_app_server.py"
