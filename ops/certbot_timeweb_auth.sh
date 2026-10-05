#!/bin/bash
set -euo pipefail

ENV_FILE=/etc/portal-production/timeweb-dns.env
TWC=/opt/portal-timeweb-dns/venv/bin/twc
ZONE=vart-portal.ru
TTL=60

[ -r "$ENV_FILE" ] || { echo "Timeweb token file missing" >&2; exit 1; }
set -a
. "$ENV_FILE"
set +a

: "${CERTBOT_DOMAIN:?CERTBOT_DOMAIN missing}"
: "${CERTBOT_VALIDATION:?CERTBOT_VALIDATION missing}"

NAME="_acme-challenge.${CERTBOT_DOMAIN}"
SUB="${NAME%.vart-portal.ru}"
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

remove_existing() {
  "$TWC" domain record list "$ZONE" -a -o json >"$TMP"
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
    "$TWC" domain record remove "$ZONE" "$id" >/dev/null
  done
}

remove_existing
"$TWC" domain record add "$NAME" --type TXT --value "$CERTBOT_VALIDATION" --ttl "$TTL" -o json >/dev/null

# Wait until the exact challenge is visible not only on Timeweb authoritative
# servers, but also through independent public recursive resolvers. This avoids
# Let's Encrypt seeing a previously cached TXT value.
AUTH_NS=(ns1.timeweb.ru ns2.timeweb.ru ns3.timeweb.org ns4.timeweb.org)
PUBLIC_DNS=(1.1.1.1 8.8.8.8)
deadline=$((SECONDS+1200))

has_value() {
  local resolver="$1"
  dig -4 +time=3 +tries=1 @"$resolver" "$NAME" TXT +short 2>/dev/null |
    tr -d '"' |
    grep -Fx -- "$CERTBOT_VALIDATION" >/dev/null
}

while (( SECONDS < deadline )); do
  ok=1
  for ns in "${AUTH_NS[@]}"; do
    has_value "$ns" || { ok=0; break; }
  done
  if (( ok == 1 )); then
    for resolver in "${PUBLIC_DNS[@]}"; do
      has_value "$resolver" || { ok=0; break; }
    done
  fi
  if (( ok == 1 )); then
    # Give any additional CA-side resolver caches a small safety margin.
    sleep 60
    echo "DNS challenge propagated for $NAME" >&2
    exit 0
  fi
  sleep 10
done

echo "DNS propagation timeout for $NAME" >&2
exit 1
