#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

fail() {
  echo "portal-offsite-install: $*" >&2
  exit 1
}

REPO=""
SHA=""
INSTALL_ACL=0
DEST="/usr/local/libexec/portal-offsite"
BACKUP_ROOT="/srv/portal/central/backups"

while (($#)); do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --sha) SHA="${2:-}"; shift 2 ;;
    --install-acl) INSTALL_ACL=1; shift ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || fail "run as root"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail "a full exact 40-character Git SHA is required"
[[ -n "$REPO" ]] || fail "--repo is required"
[[ -f /etc/os-release ]] || fail "Ubuntu identification unavailable"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "supported OS is Ubuntu; found ${ID:-unknown}"
[[ -d "$REPO/.git" || -f "$REPO/.git" ]] || fail "--repo must point to a Git checkout"
git -C "$REPO" cat-file -e "$SHA^{commit}" 2>/dev/null || fail "requested commit is absent locally"
remote_sha="$(git -C "$REPO" ls-remote origin refs/heads/main | awk 'NR==1 {print $1}')"
[[ "$remote_sha" == "$SHA" ]] || fail "requested SHA must be the exact current origin/main"

for tool in git tar python3 restic pg_restore; do
  command -v "$tool" >/dev/null 2>&1 || fail "missing required tool: $tool"
done

if ! command -v setfacl >/dev/null 2>&1; then
  (( INSTALL_ACL == 1 )) || fail "setfacl is required; rerun explicitly with --install-acl"
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends acl
fi
command -v setfacl >/dev/null 2>&1 || fail "setfacl remains unavailable"

for timer in portal-offsite-backup.timer portal-offsite-restore-test.timer; do
  if systemctl is-active --quiet "$timer" || systemctl is-enabled --quiet "$timer"; then
    fail "$timer is already active/enabled; refusing preparation over a live off-site schedule"
  fi
done

[[ -d "$BACKUP_ROOT" ]] || fail "central backup root is missing"

getent group portal-backup-readers >/dev/null || groupadd --system portal-backup-readers
if ! id portal-offsite >/dev/null 2>&1; then
  useradd --system --gid portal-backup-readers --home-dir /var/lib/portal-offsite --shell /usr/sbin/nologin portal-offsite
fi
[[ "$(id -gn portal-offsite)" == "portal-backup-readers" ]] || fail "portal-offsite primary group mismatch"
install -d -o portal-offsite -g portal-backup-readers -m 0700 /var/lib/portal-offsite

# Traverse only through parent directories; backup content itself is read-only.
setfacl -m g:portal-backup-readers:--x /srv/portal /srv/portal/central
setfacl -R -m g:portal-backup-readers:r-X "$BACKUP_ROOT"
find "$BACKUP_ROOT" -type d -exec setfacl -m d:g:portal-backup-readers:r-X {} +

tmp="$(mktemp -d /srv/.portal-offsite-install.XXXXXX)"
trap 'rm -rf -- "$tmp"' EXIT
git -C "$REPO" archive "$SHA" \
  ops/portal_offsite_restic.py \
  deploy/systemd/portal-offsite-backup.service \
  deploy/systemd/portal-offsite-backup.timer \
  deploy/systemd/portal-offsite-restore-test.service \
  deploy/systemd/portal-offsite-restore-test.timer | tar -x -C "$tmp"

python3 -m py_compile "$tmp/ops/portal_offsite_restic.py"
release="$DEST/releases/$SHA"
mkdir -p "$DEST/releases"
if [[ -e "$release" ]]; then
  cmp -s "$release/portal_offsite_restic.py" "$tmp/ops/portal_offsite_restic.py" || fail "existing release differs from exact Git payload"
else
  mkdir "$release"
  install -o root -g root -m 0755 "$tmp/ops/portal_offsite_restic.py" "$release/portal_offsite_restic.py"
fi
ln -sfn "$release" "$DEST/current.new"
mv -Tf "$DEST/current.new" "$DEST/current"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
for unit in portal-offsite-backup.service portal-offsite-backup.timer portal-offsite-restore-test.service portal-offsite-restore-test.timer; do
  target="/etc/systemd/system/$unit"
  if [[ -f "$target" ]]; then
    cp -a "$target" "$target.pre-offsite-$stamp"
  fi
  install -o root -g root -m 0644 "$tmp/deploy/systemd/$unit" "$target"
done
systemctl daemon-reload

if [[ -f "$BACKUP_ROOT/central-backup-success.json" ]]; then
  runuser -u portal-offsite -- test -r "$BACKUP_ROOT/central-backup-success.json" || fail "portal-offsite cannot read central backup marker"
fi

echo "PORTAL_OFFSITE_PREPARED_SHA=$SHA"
echo "PORTAL_OFFSITE_CURRENT=$(readlink -f "$DEST/current")"
echo "Off-site timers were NOT enabled or started. Supply protected S3/restic configuration and run preflight/backup/restore-test before activation."
