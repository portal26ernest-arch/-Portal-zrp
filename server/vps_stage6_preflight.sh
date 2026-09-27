#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="${PORTAL_PREFLIGHT_ROOT:-/srv/portal-preflight}"
REPO="${PORTAL_PREFLIGHT_REPO:-$ROOT/repo}"
BRANCH="${PORTAL_PREFLIGHT_BRANCH:-portal-next-b003}"
SUFFIX="${PORTAL_SYNTHETIC_SUFFIX:-20260927s6}"

echo "PORTAL Stage 6 VPS preflight"
echo "Mode: isolated synthetic database only"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ОШИБКА: preflight должен запускаться root, synthetic test будет запущен от postgres." >&2
  exit 2
fi
command -v git >/dev/null
command -v psql >/dev/null
command -v pg_dump >/dev/null
command -v pg_restore >/dev/null
command -v python3 >/dev/null
id postgres >/dev/null 2>&1

install -d -m 0750 "$ROOT"
if [[ -d "$REPO/.git" ]]; then
  git -C "$REPO" fetch --prune origin "$BRANCH"
  git -C "$REPO" checkout -f "$BRANCH"
  git -C "$REPO" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" --single-branch https://github.com/portal26ernest-arch/-Portal-zrp.git "$REPO"
fi

STAGE6_BASE="055c212d9fb65f9b3ad328ba1601ce35b77a043a"
ACTUAL="$(git -C "$REPO" rev-parse HEAD)"
echo "Git commit: $ACTUAL"
if ! git -C "$REPO" merge-base --is-ancestor "$STAGE6_BASE" "$ACTUAL"; then
  echo "ОШИБКА: текущая ветка не содержит проверенный Stage 6 commit $STAGE6_BASE" >&2
  exit 3
fi
echo "Проверенный Stage 6 commit присутствует в истории ветки."

VENV="/tmp/portal-preflight-venv-$SUFFIX"
LOG="/tmp/portal-stage6-preflight-$SUFFIX.log"
rm -rf "$VENV" "/tmp/portal-migration-full-$SUFFIX"
rm -f "$LOG"
python3 -m venv "$VENV"
"$VENV/bin/pip" -q install --upgrade pip
"$VENV/bin/pip" -q install "psycopg[binary]"
chown -R postgres:postgres "$VENV"
chmod 0755 "$ROOT" "$REPO"

install -d -o postgres -g postgres -m 0700 "/tmp/portal-migration-full-$SUFFIX"
install -d -o postgres -g postgres -m 0700 "/tmp/portal-migration-full-$SUFFIX/migrations"
cp "$REPO"/server/migrations/postgresql_*.sql "/tmp/portal-migration-full-$SUFFIX/migrations/"
chown -R postgres:postgres "/tmp/portal-migration-full-$SUFFIX"

echo "PostgreSQL: $(psql --version)"
echo "Создаётся только synthetic DB с суффиксом: $SUFFIX"

set +e
sudo -u postgres env \
  PORTAL_SYNTHETIC_SETUP=1 \
  PORTAL_SYNTHETIC_SUFFIX="$SUFFIX" \
  PYTHONPATH="$REPO/server" \
  "$VENV/bin/python" "$REPO/server/test_migration_full_vps.py" \
  >"$LOG" 2>&1
RC=$?
set -e
cat "$LOG"
if [[ $RC -ne 0 ]]; then
  echo "ОШИБКА: synthetic setup/preflight не прошёл. Production не изменялся." >&2
  exit $RC
fi

echo "STAGE6_SYNTHETIC_SETUP_OK"
echo "Запускается полный CLI gate: импорт, RLS, rollback, backup/restore и API."

set +e
sudo -u postgres env \
  PORTAL_FULL_CLI_INTEGRATION=1 \
  PORTAL_SYNTHETIC_SUFFIX="$SUFFIX" \
  PYTHONPATH="$REPO/server" \
  "$VENV/bin/python" -m unittest -v test_migration_full_cli \
  >>"$LOG" 2>&1
RC=$?
set -e
tail -n 120 "$LOG"
if [[ $RC -ne 0 ]]; then
  echo "ОШИБКА: полный Stage 6 gate не прошёл. Production не изменялся." >&2
  exit $RC
fi

echo "STAGE6_PREFLIGHT_FULL_OK"
echo "Synthetic migration/RLS/rollback/backup-restore/API gate пройден."
echo "Production DB/API не переключались."
