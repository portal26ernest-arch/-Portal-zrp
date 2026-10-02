#!/usr/bin/env bash
# Daily PORTAL PostgreSQL and document backup. The timer invokes this as root;
# PostgreSQL credentials are never supplied on the command line or written here.
set -Eeuo pipefail
umask 077

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
root=/srv/portal/central/backups
pgdir="$root/postgresql/daily"
stdir="$root/storage/daily"
install -d -m 0750 "$pgdir" "$stdir"

tenant_list="$(runuser -u postgres -- psql -d postgres -Atqc \
  "SELECT datname FROM pg_database WHERE datname ~ '^portal_prod_company_[0-9]+$' ORDER BY datname")"
if ! printf '%s\n' "$tenant_list" | grep -qx portal_prod_company_1; then
  echo 'Required PORTAL production tenant database is missing' >&2
  exit 1
fi
if ! runuser -u postgres -- psql -d postgres -Atqc \
  "SELECT 1 FROM pg_database WHERE datname='portal_prod_control'" | grep -qx 1; then
  echo 'Required PORTAL control database is missing' >&2
  exit 1
fi

backup_database() {
  local db="$1" tmp="$pgdir/.$1-$stamp.dump.tmp" final="$pgdir/$1-$stamp.dump"
  runuser -u postgres -- pg_dump -Fc -d "$db" > "$tmp"
  pg_restore --list "$tmp" >/dev/null
  mv -- "$tmp" "$final"
  sha256sum "$final" > "$final.sha256"
  printf 'BACKED_UP_DB=%s BYTES=%s\n' "$db" "$(stat -c %s "$final")"
}

backup_database portal_prod_control
while IFS= read -r tenant_db; do
  [[ -z "$tenant_db" ]] || backup_database "$tenant_db"
done <<< "$tenant_list"

# Preserve the previous central DBs while they remain a possible rollback source.
for legacy_db in portal_production portal_stage7_staging; do
  if runuser -u postgres -- psql -d postgres -Atqc \
    "SELECT 1 FROM pg_database WHERE datname='$legacy_db'" | grep -qx 1; then
    backup_database "$legacy_db"
  fi
done

storage_tmp="$stdir/.central-storage-$stamp.tar.gz.tmp"
storage_final="$stdir/central-storage-$stamp.tar.gz"
tar -C /srv/portal/central/storage -czf "$storage_tmp" documents uploads
mv -- "$storage_tmp" "$storage_final"
sha256sum "$storage_final" > "$storage_final.sha256"
printf 'BACKED_UP_STORAGE bytes=%s\n' "$(stat -c %s "$storage_final")"

# Only this script's daily directory is pruned. Manual cutover checkpoints in
# the parent directories are retained for an explicit rollback decision.
find "$pgdir" -maxdepth 1 -type f -mtime +13 -delete
find "$stdir" -maxdepth 1 -type f -mtime +13 -delete
echo 'BACKUP_SUCCESS=1 RETENTION_DAYS=14'
