#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/portal26ernest-arch/-Portal-zrp.git"
ROOT="${PORTAL_SOURCE_ROOT:-/srv/portal-source}"
BRANCH="${PORTAL_SOURCE_BRANCH:-main}"
EXPECTED="${PORTAL_SOURCE_EXPECTED_COMMIT:-}"
REPO="$ROOT/repo"

case "$BRANCH" in
  ""|*[!A-Za-z0-9._/-]*) echo "Invalid branch name" >&2; exit 2 ;;
esac
if [[ -n "$EXPECTED" && ! "$EXPECTED" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Expected commit must be a full SHA-1" >&2
  exit 2
fi

install -d -m 0750 "$ROOT"
if [[ ! -d "$REPO/.git" ]]; then
  git clone "$REPO_URL" "$REPO"
fi

actual_origin="$(git -C "$REPO" remote get-url origin)"
if [[ "$actual_origin" != "$REPO_URL" ]]; then
  echo "Unexpected origin: $actual_origin" >&2
  exit 3
fi
if [[ -n "$(git -C "$REPO" status --porcelain)" ]]; then
  echo "VPS source mirror has local changes; refusing to overwrite them." >&2
  exit 4
fi

git -C "$REPO" fetch origin --prune
target="origin/$BRANCH"
target_sha="$(git -C "$REPO" rev-parse "$target")"
if [[ -n "$EXPECTED" && "$target_sha" != "$EXPECTED" ]]; then
  echo "Remote branch is $target_sha, expected $EXPECTED" >&2
  exit 5
fi

git -C "$REPO" checkout -B "$BRANCH" "$target"
git -C "$REPO" reset --hard "$target"
head_sha="$(git -C "$REPO" rev-parse HEAD)"
printf 'repository=%s\nbranch=%s\ncommit=%s\nsynced_at=%s\n' \
  "$REPO_URL" "$BRANCH" "$head_sha" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  > "$ROOT/SYNC_STATE"
chmod 0640 "$ROOT/SYNC_STATE"

echo "PORTAL_SOURCE_SYNC_OK branch=$BRANCH commit=$head_sha"
