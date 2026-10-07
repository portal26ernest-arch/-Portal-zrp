#!/usr/bin/env bash
# Daily PORTAL PostgreSQL and document backup. The timer invokes this as root;
# PostgreSQL credentials are never supplied on the command line or written here.
set -Eeuo pipefail
umask 077

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
root=/srv/portal/central/backups
pgdir="$root/postgresql/daily"
stdir="$root/storage/daily"
completion="$root/central-backup-success.json"
# A failed/interrupted run must never leave a fresh-looking success marker.
rm -f -- "$completion"
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
# Publish an atomic inventory only after every dump, restore-list check, tar, and
# SHA sidecar succeeded. The off-site job independently re-hashes each file.
python3 - "$root" "$stamp" "$completion" <<'PYMARKER'
import hashlib, json, os, sys, tempfile
from pathlib import Path
root, stamp, completion = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
files = sorted([*root.glob(f'postgresql/daily/*-{stamp}.dump'), *root.glob(f'postgresql/daily/*-{stamp}.dump.sha256'), *root.glob(f'storage/daily/central-storage-{stamp}.tar.gz'), *root.glob(f'storage/daily/central-storage-{stamp}.tar.gz.sha256')])
expected_dbs = ['portal_prod_control', 'portal_prod_company_1']
actual_dbs = {p.name.split('-', 1)[0] for p in files if p.name.endswith('.dump')}
if not set(expected_dbs).issubset(actual_dbs) or not any(p.name == f'central-storage-{stamp}.tar.gz' for p in files):
    raise SystemExit('central backup inventory is incomplete')
entries=[]
for path in files:
    h=hashlib.sha256(path.read_bytes()).hexdigest()
    entries.append({'path': path.relative_to(root).as_posix(), 'size': path.stat().st_size, 'sha256': h})
data={'schema':1,'completed_at_utc':stamp,'files':entries}
fd,tmp=tempfile.mkstemp(prefix='.central-backup-success.',suffix='.tmp',dir=root)
try:
    with os.fdopen(fd,'w',encoding='utf-8') as f:
        json.dump(data,f,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,completion)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
PYMARKER
echo 'BACKUP_SUCCESS=1 RETENTION_DAYS=14'
