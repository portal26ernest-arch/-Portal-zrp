#!/bin/bash
set -u

ENV_FILE=/etc/portal-production/timeweb-dns.env
TWC=/opt/portal-timeweb-dns/venv/bin/twc
ZONE=vart-portal.ru

[ -r "$ENV_FILE" ] || exit 0
set -a
. "$ENV_FILE"
set +a

[ -n "${CERTBOT_DOMAIN:-}" ] || exit 0

NAME="_acme-challenge.${CERTBOT_DOMAIN}"
SUB="${NAME%.vart-portal.ru}"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

"$TWC" domain record list "$ZONE" -a -o json >"$TMP" || exit 0
IDS=$(SUB="$SUB" python3 - "$TMP" <<'PY'
import json, os, sys
j=json.load(open(sys.argv[1]))
sub=os.environ["SUB"]
for r in j.get("dns_records", []):
    d=r.get("data") or {}
    if r.get("type")=="TXT" and (d.get("subdomain") or "")==sub and r.get("id") is not None:
        print(r["id"])
PY
)
for id in $IDS; do
  "$TWC" domain record remove "$ZONE" "$id" >/dev/null 2>&1 || true
done

# Do not leave a placeholder TXT record behind: it can be cached and later
# mistaken by ACME validation for the current challenge value.
exit 0
