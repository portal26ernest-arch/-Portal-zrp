#!/data/data/com.termux/files/usr/bin/bash
cd ~/storage/shared/PORTAL-BOT
export PORTAL_DB="${PORTAL_DB:-/storage/emulated/0/PORTAL-BOT/portal.db}"
export PORTAL_APP_HOST="${PORTAL_APP_HOST:-127.0.0.1}"
export PORTAL_APP_PORT="${PORTAL_APP_PORT:-8765}"
python portal_app_server.py
