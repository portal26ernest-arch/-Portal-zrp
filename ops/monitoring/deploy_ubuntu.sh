#!/usr/bin/env bash
set -Eeuo pipefail

# Install the monitoring stack from one exact, already-pushed Git commit.
# No DNS, firewall, or external port changes are made by this script.

readonly DEST=/srv/portal-monitoring
readonly SECRETS=/etc/portal-monitoring/secrets
readonly MIN_DISK_GB=10
readonly MIN_MEM_MB=2048
INSTALL_DOCKER=0
DEPLOY=0
SHA=""
REPO="$(git rev-parse --show-toplevel 2>/dev/null || true)"

usage() { echo "Usage: $0 --sha <full-40-char-commit> [--repo <git-checkout>] [--install-docker] [--deploy]"; }
fail() { echo "ERROR: $*" >&2; exit 1; }
while (($#)); do
  case "$1" in
    --sha) (($# >= 2)) || { usage; exit 2; }; SHA=$2; shift 2 ;;
    --repo) (($# >= 2)) || { usage; exit 2; }; REPO=$2; shift 2 ;;
    --install-docker) INSTALL_DOCKER=1; shift ;;
    --deploy) DEPLOY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
done

[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail "a full exact 40-character Git SHA is required"
[[ $EUID -eq 0 ]] || fail "run as root for system preflight/deployment"
[[ -f /etc/os-release ]] || fail "Ubuntu identification unavailable"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == ubuntu ]] || fail "supported OS is Ubuntu; found ${ID:-unknown}"
[[ -d "$REPO/.git" || -f "$REPO/.git" ]] || fail "--repo must point to a Git checkout"
git -C "$REPO" cat-file -e "$SHA^{commit}" 2>/dev/null || fail "requested commit is absent locally"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$SHA" ]] || fail "checkout HEAD must equal requested SHA"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=all)" ]] || fail "repository is not clean"
git -C "$REPO" remote get-url origin >/dev/null 2>&1 || fail "origin remote is required to verify pushed SHA"
remote_refs=$(git -C "$REPO" ls-remote origin 2>/dev/null) || fail "cannot verify pushed commit with origin"
printf '%s\n' "$remote_refs" | awk -v sha="$SHA" '$1==sha {found=1} END{exit !found}' || fail "exact SHA is not advertised by origin; push it before deployment"

available_kb=$(df -Pk /srv 2>/dev/null | awk 'NR==2 {print $4}')
[[ "${available_kb:-0}" =~ ^[0-9]+$ ]] || fail "cannot determine free disk on /srv"
(( available_kb >= MIN_DISK_GB * 1024 * 1024 )) || fail "need at least ${MIN_DISK_GB} GiB free on /srv"
mem_mb=$(awk '/MemTotal:/ {print int($2/1024)}' /proc/meminfo)
(( mem_mb >= MIN_MEM_MB )) || fail "need at least ${MIN_MEM_MB} MiB RAM"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  (( INSTALL_DOCKER == 1 )) || fail "Docker Engine/Compose missing; rerun explicitly with --install-docker"
  # Official Docker Ubuntu repository only. Never run apt-key or third-party installers.
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  arch=$(dpkg --print-architecture)
  codename=${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}
  [[ -n "$codename" ]] || fail "Ubuntu codename unavailable"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$arch" "$codename" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi
command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 || fail "Docker Engine and Compose plugin are required"

monitoring_dir="$REPO/ops/monitoring"
[[ -d "$monitoring_dir" ]] || fail "monitoring payload missing from requested commit"
mkdir -p "$SECRETS"
chmod 0700 /etc/portal-monitoring "$SECRETS"
secret="$SECRETS/grafana_admin_password"
[[ -s "$secret" ]] || fail "missing $secret; create a unique strong secret out-of-band (not printed or generated here)"
[[ ! -L "$secret" ]] || fail "password secret must be a regular file, not a symlink"
chmod 0600 "$secret"
secret_len=$(wc -c < "$secret")
(( secret_len >= 20 )) || fail "Grafana admin password secret is too weak (minimum 20 bytes)"
python3 - "$secret" <<'PY'
import pathlib, sys
value = pathlib.Path(sys.argv[1]).read_bytes().rstrip(b"\r\n")
classes = sum((any(65 <= c <= 90 for c in value), any(97 <= c <= 122 for c in value),
               any(48 <= c <= 57 for c in value), any(c < 48 or c > 122 for c in value)))
if len(value) < 20 or len(set(value)) < 10 or classes < 3:
    raise SystemExit("ERROR: Grafana admin password secret is weak; provide a unique high-entropy secret out-of-band")
PY

tmp=$(mktemp -d /srv/.portal-monitoring.XXXXXX)
ACTIVE_SWITCH=0
PREVIOUS_TARGET=""
cleanup() {
  status=$?
  if (( status != 0 && ACTIVE_SWITCH == 1 )) && [[ -n "$PREVIOUS_TARGET" ]]; then
    ln -sfn "$PREVIOUS_TARGET" "$DEST/current.rollback"
    mv -Tf "$DEST/current.rollback" "$DEST/current"
    (cd "$DEST/current" && PORTAL_MONITORING_SECRETS_DIR="$SECRETS" docker compose up -d) || true
    echo "Deployment failed; previous release restored. Review: cd $DEST/current && docker compose logs --tail=100" >&2
  elif (( status != 0 && ACTIVE_SWITCH == 1 )); then
    (cd "$DEST/current" && PORTAL_MONITORING_SECRETS_DIR="$SECRETS" docker compose down) || true
    echo "First deployment failed; stack stopped and named volumes retained. Review the candidate before retrying." >&2
  fi
  rm -rf -- "$tmp"
  return "$status"
}
trap cleanup EXIT
git -C "$REPO" archive "$SHA" ops/monitoring | tar -x -C "$tmp"
payload="$tmp/ops/monitoring"
[[ -d "$payload" ]] || fail "could not extract complete monitoring directory from exact SHA"
python3 "$payload/validate_monitoring.py"
docker compose -f "$payload/docker-compose.yml" config --quiet
docker run --rm --entrypoint /bin/promtool -v "$payload/prometheus:/etc/prometheus:ro" prom/prometheus:v3.15.0 check config /etc/prometheus/prometheus.yml
docker run --rm --entrypoint /bin/promtool -v "$payload/prometheus:/etc/prometheus:ro" prom/prometheus:v3.15.0 check rules /etc/prometheus/rules/portal.rules.yml
docker run --rm --entrypoint /bin/amtool -v "$payload/alertmanager:/etc/alertmanager:ro" prom/alertmanager:v0.34.1 check-config /etc/alertmanager/alertmanager.yml
docker run --rm --entrypoint /bin/blackbox_exporter -v "$payload/blackbox:/etc/blackbox_exporter:ro" prom/blackbox-exporter:v0.28.0 --config.file=/etc/blackbox_exporter/blackbox.yml --config.check

if (( DEPLOY == 0 )); then
  echo "Preflight passed for exact SHA $SHA. No stack changes made; add --deploy to install/start."
  exit 0
fi

mkdir -p "$DEST"
mkdir -p "$DEST/releases"
release="$DEST/releases/$SHA"
if [[ -e "$release" ]]; then
  diff -qr "$release" "$payload" >/dev/null || fail "existing release directory differs from exact commit payload"
else
  mkdir "$release"
  cp -a "$payload/." "$release/"
fi
if [[ -L "$DEST/current" ]]; then
  PREVIOUS_TARGET=$(readlink -f "$DEST/current")
  ln -sfn "$PREVIOUS_TARGET" "$DEST/previous.new"
  mv -Tf "$DEST/previous.new" "$DEST/previous"
elif [[ -e "$DEST/current" ]]; then
  fail "$DEST/current exists but is not a symlink; preserve and reconcile it manually"
fi
ln -sfn "$release" "$DEST/current.new"
mv -Tf "$DEST/current.new" "$DEST/current"
ACTIVE_SWITCH=1
cd "$DEST/current"
export PORTAL_MONITORING_SECRETS_DIR="$SECRETS"
docker compose up -d --remove-orphans

check_local() {
  local url=$1; local i
  for i in {1..30}; do curl --fail --silent --show-error "$url" >/dev/null 2>&1 && return 0; sleep 2; done
  return 1
}
check_local http://127.0.0.1:3000/api/health || fail "Grafana loopback health check failed"
check_local http://127.0.0.1:3001/ || fail "Uptime Kuma loopback check failed"
check_local http://127.0.0.1:9090/-/ready || fail "Prometheus loopback readiness failed"
check_local http://127.0.0.1:9093/-/ready || fail "Alertmanager loopback readiness failed"
check_local 'http://127.0.0.1:9090/api/v1/query?query=up' || fail "Prometheus query probe failed"
for url in https://api.vart-portal.ru/api/ping https://api.vart-portal.ru/api/ready https://vart-portal.ru/web/ https://reserve-api.vart-portal.ru/api/ping; do
  curl --fail --silent --show-error --max-time 15 "$url" >/dev/null || fail "public probe failed: $url"
done
ACTIVE_SWITCH=0
echo "Monitoring stack started from $SHA. Management services remain loopback-only."
if [[ -n "$PREVIOUS_TARGET" ]]; then
  echo "Rollback: ln -sfn \"$PREVIOUS_TARGET\" $DEST/current.rollback && mv -Tf $DEST/current.rollback $DEST/current && cd $DEST/current && PORTAL_MONITORING_SECRETS_DIR=$SECRETS docker compose up -d. Keep all release directories and named volumes."
else
  echo "First-install rollback: cd $DEST/current && PORTAL_MONITORING_SECRETS_DIR=$SECRETS docker compose down. This preserves named volumes."
fi
echo "Independent-host gate remains open: this host cannot detect its own total failure."
