#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

ROOT="/srv/portal-stage7"
REPO="$ROOT/repo"
VENV="$ROOT/venv"
STATE="$ROOT/state"
LOG="$ROOT/stage7-deploy.log"
REPORT="$ROOT/STAGE7_RESULT.txt"
ENV_DIR="/etc/portal-stage7"
ENV_FILE="$ENV_DIR/portal.env"
SECRETS_FILE="$ENV_DIR/db.secrets"
LOGIN_FILE="$ENV_DIR/first-login.txt"
SERVICE="portal-stage7.service"
DB="portal_test_stage7_staging"
[[ "$DB" == portal_test_stage7_* ]] || { echo "ОШИБКА: запрещено использовать не-test staging БД" >&2; exit 1; }
TENANT_ROLE="portal_stage7_tenant"
CONTROL_ROLE="portal_stage7_control"
API_PORT="8770"
BRANCH="${PORTAL_STAGE7_BRANCH:-portal-next-b003}"
EXPECTED_COMMIT="${PORTAL_STAGE7_EXPECTED_COMMIT:-}"
PILOT_SSLIP="${PORTAL_STAGE7_PILOT_SSLIP:-0}"
PILOT_TUNNEL="${PORTAL_STAGE7_PILOT_TUNNEL:-0}"
TUNNEL_PROXY_PORT="8780"
TUNNEL_SERVICE="portal-stage7-tunnel.service"
GATE_BASE="f9dd1b38231e53fba0cb9e96c85cfcc032b7864a"

fail() { echo "ОШИБКА Stage 7: $*" >&2; exit 1; }
[[ "$(id -u)" -eq 0 ]] || fail "скрипт должен запускаться root"
for x in git python3 psql curl openssl systemctl runuser flock sha256sum; do
  command -v "$x" >/dev/null || fail "нет команды $x"
done

# Serialize retries so two operators/runners cannot race over the same staging DB.
install -d -m 0755 "$ROOT"
exec 9>"$ROOT/deploy.lock"
flock -n 9 || fail "другой Stage 7 deploy уже выполняется"

[[ -n "$EXPECTED_COMMIT" && "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] ||
  fail "PORTAL_STAGE7_EXPECTED_COMMIT должен содержать полный pinned commit SHA"

install -d -m 0755 "$ROOT" "$STATE"
install -d -m 0700 "$ENV_DIR"
touch "$LOG"
chmod 0600 "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "=== PORTAL Stage 7 staging deploy: $(date -Is) ==="

echo "[1/9] Обновление проверенного кода"
if [[ -d "$REPO/.git" ]]; then
  [[ -z "$(git -C "$REPO" status --porcelain)" ]] ||
    fail "staging checkout is dirty; refusing to overwrite local files"
  git -C "$REPO" fetch --prune origin "+refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
  git -C "$REPO" cat-file -e "$EXPECTED_COMMIT^{commit}" ||
    fail "pinned commit is unavailable in staging checkout"
else
  git clone --branch "$BRANCH" --single-branch https://github.com/portal26ernest-arch/-Portal-zrp.git "$REPO"
fi
git -C "$REPO" merge-base --is-ancestor "$EXPECTED_COMMIT" "origin/$BRANCH" 2>/dev/null ||
  fail "pinned commit is not contained in origin/$BRANCH"
git -C "$REPO" checkout --detach "$EXPECTED_COMMIT"
ACTUAL="$(git -C "$REPO" rev-parse HEAD)"
git -C "$REPO" merge-base --is-ancestor "$GATE_BASE" "$ACTUAL" ||
  fail "ветка не содержит успешно проверенный Stage 6 gate"
if [[ -n "$EXPECTED_COMMIT" && "$ACTUAL" != "$EXPECTED_COMMIT" ]]; then
  fail "получен неожиданный commit: $ACTUAL"
fi
echo "Commit: $ACTUAL"
chmod -R a+rX "$REPO"
echo "[2/9] Python runtime"
if [[ ! -x "$VENV/bin/python" ]]; then
  rm -rf "$VENV"
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" -q install --upgrade pip
"$VENV/bin/pip" -q install "psycopg[binary]"
chmod -R a+rX "$VENV"

echo "[3/9] Секреты staging-БД"
if [[ ! -f "$SECRETS_FILE" ]]; then
  TENANT_PASSWORD="$(openssl rand -hex 24)"
  CONTROL_PASSWORD="$(openssl rand -hex 24)"
  cat >"$SECRETS_FILE" <<EOF
TENANT_PASSWORD=$TENANT_PASSWORD
CONTROL_PASSWORD=$CONTROL_PASSWORD
EOF
  chmod 0600 "$SECRETS_FILE"
fi
# shellcheck disable=SC1090
source "$SECRETS_FILE"
[[ "$TENANT_PASSWORD" =~ ^[0-9a-f]{48}$ ]] ||
  fail "повреждён staging tenant secret"
[[ "$CONTROL_PASSWORD" =~ ^[0-9a-f]{48}$ ]] ||
  fail "повреждён staging control secret"
runuser -u postgres -- psql -v ON_ERROR_STOP=1 -q <<SQL
DO \$\$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='$TENANT_ROLE') THEN
  CREATE ROLE $TENANT_ROLE LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '$TENANT_PASSWORD';
 ELSE
  ALTER ROLE $TENANT_ROLE WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '$TENANT_PASSWORD';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='$CONTROL_ROLE') THEN
  CREATE ROLE $CONTROL_ROLE LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '$CONTROL_PASSWORD';
 ELSE
  ALTER ROLE $CONTROL_ROLE WITH LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '$CONTROL_PASSWORD';
 END IF;
END
\$\$;
SQL

if ! runuser -u postgres -- psql -Atqc "SELECT 1 FROM pg_database WHERE datname='$DB'" |
  grep -qx 1; then
  runuser -u postgres -- createdb "$DB"
fi

echo "[4/9] Схема PostgreSQL"
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" <<'SQL'
CREATE TABLE IF NOT EXISTS portal_stage7_schema_migrations (
  version TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
SQL
for migration in \
  postgresql_core_stage4b.sql \
  postgresql_stage3.sql \
  postgresql_runtime.sql \
  postgresql_rls_context.sql \
  postgresql_stage5_chat_retention.sql \
  postgresql_stage6_payroll_settlement.sql \
  postgresql_stage4c.sql \
  postgresql_stage8_documents_excel.sql \
  postgresql_stage9_invoice_revisions.sql \
  postgresql_stage10_access_invites.sql
do
  migration_file="$REPO/server/migrations/$migration"
  checksum="$(sha256sum "$migration_file" | awk '{print $1}')"
  existing_checksum="$(runuser -u postgres -- psql -X -Atq -d "$DB" \
    -c "SELECT checksum FROM portal_stage7_schema_migrations WHERE version='$migration'")"
  if [[ -n "$existing_checksum" ]]; then
    [[ "$existing_checksum" == "$checksum" ]] ||
      fail "migration checksum изменился после применения: $migration"
    echo "  migration already applied: $migration"
    continue
  fi
  echo "  migration: $migration"
  runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" -f "$migration_file"
  runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" \
    -c "INSERT INTO portal_stage7_schema_migrations(version,checksum) VALUES('$migration','$checksum')"
done

runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" \
  -c "GRANT SELECT,INSERT,UPDATE ON portal_documents,portal_excel_imports TO $TENANT_ROLE"

runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" <<SQL
INSERT INTO companies(id,name,user_limit,created_at,updated_at)
VALUES(1,'PORTAL',NULL,CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text)
ON CONFLICT(id) DO NOTHING;
SELECT setval(pg_get_serial_sequence('companies','id'),
  GREATEST(COALESCE((SELECT MAX(id) FROM companies),1),1),true);
SELECT portal_provision_company(1);
SQL

echo "[5/9] Права runtime-ролей"
TENANT_TABLES="employees app_users app_sessions portal_clients portal_client_operations manager_client_assignments materials material_movements operation_material_norms work_log payroll_payments payroll_transactions client_invoices client_payments production_jobs production_job_progress audit_log portal_production_migrations portal_production work_material_consumption payroll_employee_identities payroll_settlement_entries"
TENANT_TABLES="$TENANT_TABLES backup_log client_access client_invites client_invoice_items client_name_overrides client_permissions employee_access_requests employee_chat_messages employee_chat_settings employee_invites expense_requests managers marketplace_news payroll_closure_batches"
TENANT_TABLES="$TENANT_TABLES portal_client_requisites portal_company_requisites portal_manager_service_rates production_job_assignments products scheduled_runs system_settings tariff_versions user_roles"
for table in $TENANT_TABLES; do
  runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" \
    -c "GRANT SELECT,INSERT,UPDATE,DELETE ON $table TO $TENANT_ROLE"
done
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" \
  -c "GRANT SELECT,INSERT,UPDATE ON portal_access_invites TO $TENANT_ROLE"
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" \
  -c "REVOKE DELETE ON portal_access_invites FROM $TENANT_ROLE"

runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -q -d "$DB" <<SQL
GRANT CONNECT ON DATABASE $DB TO $TENANT_ROLE,$CONTROL_ROLE;
GRANT USAGE ON SCHEMA public TO $TENANT_ROLE,$CONTROL_ROLE;
GRANT SELECT ON portal_runtime_schema,portal_rls_context_schema TO $TENANT_ROLE;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO $TENANT_ROLE;
GRANT SELECT,INSERT,UPDATE,DELETE ON companies,platform_owners,platform_sessions,platform_audit TO $CONTROL_ROLE;
GRANT SELECT ON portal_company_keys TO $CONTROL_ROLE;
GRANT USAGE,SELECT,UPDATE ON ALL SEQUENCES IN SCHEMA public TO $CONTROL_ROLE;
GRANT EXECUTE ON FUNCTION portal_bind_company(BIGINT,TEXT) TO $TENANT_ROLE;
GRANT EXECUTE ON FUNCTION portal_current_company() TO $TENANT_ROLE,$CONTROL_ROLE;
GRANT EXECUTE ON FUNCTION portal_provision_company(BIGINT) TO $CONTROL_ROLE;
SQL

ROLE_CHECK="$(runuser -u postgres -- psql -Atq -d "$DB" -c \
  "SELECT count(*) FROM pg_roles WHERE rolname IN ('$TENANT_ROLE','$CONTROL_ROLE') AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcreatedb AND NOT rolcreaterole")"
[[ "$ROLE_CHECK" == "2" ]] || fail "runtime-роли PostgreSQL имеют лишние права"

cat >"$ENV_FILE" <<EOF
PORTAL_ENV=test
PORTAL_DB_BACKEND=postgresql
PORTAL_DATABASE_URL=postgresql://$TENANT_ROLE:$TENANT_PASSWORD@127.0.0.1:5432/$DB
PORTAL_CONTROL_DATABASE_URL=postgresql://$CONTROL_ROLE:$CONTROL_PASSWORD@127.0.0.1:5432/$DB
PORTAL_APP_HOST=127.0.0.1
PORTAL_APP_PORT=$API_PORT
PORTAL_PUBLIC_API_URL=http://127.0.0.1:$API_PORT
PORTAL_DOCUMENT_ROOT=$STATE/documents
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
EOF
chmod 0600 "$ENV_FILE"

echo "[6/9] systemd staging API"
if ! id -u portal-stage7 >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$ROOT" --shell /usr/sbin/nologin portal-stage7
fi
install -d -o portal-stage7 -g portal-stage7 -m 0700 "$STATE/documents"

cat >"/etc/systemd/system/$SERVICE" <<EOF
[Unit]
Description=PORTAL Stage 7 Staging API
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=portal-stage7
Group=portal-stage7
WorkingDirectory=$REPO/server
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/bin/python -B $REPO/server/portal_app_server.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadOnlyPaths=$REPO
ReadWritePaths=$ROOT/state
UMask=0077
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null
systemctl restart "$SERVICE"

for _ in $(seq 1 40); do
  if PING="$(curl -fsS --max-time 2 "http://127.0.0.1:$API_PORT/api/ping" 2>/dev/null)"; then
    break
  fi
  sleep 0.25
done
[[ "${PING:-}" == *'"ok": true'* || "${PING:-}" == *'"ok":true'* ]] || {
  systemctl --no-pager --full status "$SERVICE" || true
  fail "staging API не поднялся"
}
echo "Loopback API: OK"

echo "[7/9] Первичный администратор staging"
if [[ "$PING" == *'"setup_required": true'* || "$PING" == *'"setup_required":true'* ]]; then
  [[ ! -f "$LOGIN_FILE" ]] || fail "API просит setup, но first-login уже существует"
  ADMIN_PIN="$(openssl rand -hex 6)"
  BODY="$(printf '{"username":"admin","display_name":"Администратор","pin":"%s"}' "$ADMIN_PIN")"
  curl -fsS --max-time 5 -X POST -H 'Content-Type: application/json'     --data "$BODY" "http://127.0.0.1:$API_PORT/api/setup" >/dev/null
  cat >"$LOGIN_FILE" <<EOF
username=admin
pin=$ADMIN_PIN
EOF
  chmod 0600 "$LOGIN_FILE"
fi
PING="$(curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/api/ping")"
[[ "$PING" != *'"setup_required": true'* && "$PING" != *'"setup_required":true'* ]] ||
  fail "первичный setup не завершён"

echo "[7b/9] Synthetic API/RLS/restart integration"
(
  cd "$REPO/server"
  PORTAL_PG_INTEGRATION=1 \
  PORTAL_PG_TEST_ENV_FILE="$ENV_FILE" \
  PORTAL_PG_EXPECTED_APP_PORT="$API_PORT" \
  PORTAL_PG_EXPECTED_SERVICE="$SERVICE" \
  PORTAL_PG_TEST_REPORT="$STATE/stage7-integration.json" \
    "$VENV/bin/python" -m unittest -v test_postgresql_integration
)

echo "[8/9] HTTPS readiness"
HTTPS_STATUS="pending"
DOMAIN="${PORTAL_STAGE7_DOMAIN:-}"
DOMAIN_SOURCE="explicit"
PUBLIC_URL=""

if [[ -z "$DOMAIN" && "$PILOT_SSLIP" == "1" ]]; then
  SERVER_IPV4="$(ip -4 -o addr show scope global | awk '{split($4,a,"/"); print a[1]; exit}')"
  [[ -n "$SERVER_IPV4" ]] || fail "не найден публичный IPv4 для pilot sslip.io"
  DOMAIN="${SERVER_IPV4//./-}.sslip.io"
  DOMAIN_SOURCE="sslip-pilot"
fi

if [[ -z "$DOMAIN" ]]; then
  DOMAIN_SOURCE="none"
  HTTPS_STATUS="need-domain"
elif [[ "$DOMAIN" != *.* ]]; then
  HTTPS_STATUS="invalid-domain"
elif ! getent ahosts "$DOMAIN" >/dev/null 2>&1; then
  HTTPS_STATUS="dns-pending"
else
  SERVER_IPS="$(hostname -I 2>/dev/null || true)"
  DOMAIN_IPS="$(getent ahosts "$DOMAIN" | awk '{print $1}' | sort -u | tr '\n' ' ')"
  DNS_MATCH=0
  for ip in $DOMAIN_IPS; do
    [[ " $SERVER_IPS " == *" $ip "* ]] && DNS_MATCH=1
  done
  if [[ "$DNS_MATCH" != "1" ]]; then
    HTTPS_STATUS="dns-wrong-server"
  else
    HTTPS_STATUS="dns-ok"
  fi
fi

if [[ "$PILOT_TUNNEL" == "1" && -z "$DOMAIN" ]]; then
  echo "Pilot HTTPS: Cloudflare Quick Tunnel"
  if ! command -v nginx >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq nginx ca-certificates
  fi
  if ! command -v cloudflared >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    install -d -m 0755 /usr/share/keyrings
    CLOUDFLARE_KEY_TMP="$(mktemp)"
    curl -fsSL --retry 3 --retry-delay 2 \
      https://pkg.cloudflare.com/cloudflare-main.gpg -o "$CLOUDFLARE_KEY_TMP"
    install -m 0644 "$CLOUDFLARE_KEY_TMP" /usr/share/keyrings/cloudflare-main.gpg
    rm -f "$CLOUDFLARE_KEY_TMP"
    printf 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main\n' \
      >/etc/apt/sources.list.d/cloudflared.list
    apt-get update -qq
    apt-get install -y -qq cloudflared
  fi
  CLOUDFLARED_BIN="$(command -v cloudflared)"
  [[ -n "$CLOUDFLARED_BIN" && -x "$CLOUDFLARED_BIN" ]] ||
    fail "cloudflared не найден после установки"

  cat >"/etc/nginx/sites-available/portal-stage7-tunnel" <<EOF
server {
    listen 127.0.0.1:$TUNNEL_PROXY_PORT;
    server_name _;
    server_tokens off;
    client_max_body_size 25m;

    location = /api/setup {
        return 403;
    }

    location / {
        proxy_pass http://127.0.0.1:$API_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF
  ln -sfn /etc/nginx/sites-available/portal-stage7-tunnel \
    /etc/nginx/sites-enabled/portal-stage7-tunnel
  nginx -t
  systemctl enable nginx >/dev/null
  systemctl restart nginx
  curl -fsS --max-time 5 "http://127.0.0.1:$TUNNEL_PROXY_PORT/api/ping" >/dev/null ||
    fail "локальный tunnel proxy не отвечает"

  install -d -m 0750 -o portal-stage7 -g portal-stage7 /var/lib/portal-stage7-tunnel
  cat >"/etc/systemd/system/$TUNNEL_SERVICE" <<EOF
[Unit]
Description=PORTAL Stage 7 Pilot Quick Tunnel
After=network-online.target portal-stage7.service nginx.service
Wants=network-online.target

[Service]
Type=simple
User=portal-stage7
Group=portal-stage7
Environment=HOME=/var/lib/portal-stage7-tunnel
WorkingDirectory=/var/lib/portal-stage7-tunnel
ExecStart=$CLOUDFLARED_BIN tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:$TUNNEL_PROXY_PORT
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable "$TUNNEL_SERVICE" >/dev/null
  TUNNEL_SINCE="$(date -Is)"
  systemctl restart "$TUNNEL_SERVICE"

  PUBLIC_URL=""
  for _ in $(seq 1 60); do
    PUBLIC_URL="$(journalctl -u "$TUNNEL_SERVICE" --since "$TUNNEL_SINCE" --no-pager 2>/dev/null |
      grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
    [[ -n "$PUBLIC_URL" ]] && break
    sleep 0.5
  done
  [[ "$PUBLIC_URL" =~ ^https://[a-z0-9-]+\.trycloudflare\.com$ ]] || {
    systemctl --no-pager --full status "$TUNNEL_SERVICE" || true
    fail "Cloudflare Quick Tunnel не выдал HTTPS URL"
  }
  DOMAIN="${PUBLIC_URL#https://}"
  DOMAIN_SOURCE="trycloudflare-pilot"

  TMP_ENV="$(mktemp)"
  grep -v '^PORTAL_PUBLIC_API_URL=' "$ENV_FILE" >"$TMP_ENV"
  printf 'PORTAL_PUBLIC_API_URL=%s\n' "$PUBLIC_URL" >>"$TMP_ENV"
  install -m 0600 "$TMP_ENV" "$ENV_FILE"
  rm -f "$TMP_ENV"
  systemctl restart "$SERVICE"
  systemctl is-active --quiet "$TUNNEL_SERVICE" || fail "Quick Tunnel service не active"
  TUNNEL_PROXY_READY=0
  for _ in $(seq 1 40); do
    if curl -fsS --max-time 2 "http://127.0.0.1:$TUNNEL_PROXY_PORT/api/ping" >/dev/null 2>&1; then
      TUNNEL_PROXY_READY=1
      break
    fi
    sleep 0.25
  done
  [[ "$TUNNEL_PROXY_READY" == "1" ]] || fail "локальный tunnel proxy перестал отвечать"
  HTTPS_STATUS="ok"
fi

if [[ "$HTTPS_STATUS" == "dns-ok" ]]; then
  if ! command -v nginx >/dev/null || ! command -v certbot >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq nginx certbot
  fi

  NGINX_WAS_ACTIVE=0
  systemctl is-active --quiet nginx 2>/dev/null && NGINX_WAS_ACTIVE=1
  systemctl stop nginx 2>/dev/null || true
  if certbot certonly --standalone --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring -d "$DOMAIN"; then
    HTTPS_STATUS="certificate-ok"
  else
    HTTPS_STATUS="certificate-failed"
    [[ "$NGINX_WAS_ACTIVE" == "1" ]] && systemctl start nginx || true
  fi
fi

if [[ "$HTTPS_STATUS" == "certificate-ok" ]]; then
  cat >"/etc/nginx/sites-available/portal-stage7" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    return 301 https://\$host\$request_uri;
}
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN;
    server_tokens off;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    client_max_body_size 25m;

    location = /api/setup {
        return 403;
    }

    location / {
        proxy_pass http://127.0.0.1:$API_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

  ln -sfn /etc/nginx/sites-available/portal-stage7     /etc/nginx/sites-enabled/portal-stage7
  nginx -t
  systemctl enable nginx >/dev/null
  systemctl restart nginx
  # Certbot timer renews the certificate; this deploy hook safely reloads nginx.
  install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
  cat > /etc/letsencrypt/renewal-hooks/deploy/portal-stage7-nginx-reload <<'HOOK'
#!/bin/sh
systemctl reload nginx
HOOK
  chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/portal-stage7-nginx-reload

  if command -v ufw >/dev/null && ufw status | grep -q '^Status: active'; then
    ufw allow 80/tcp >/dev/null
    ufw allow 443/tcp >/dev/null
  fi
  PUBLIC_URL="https://$DOMAIN"
  TMP_ENV="$(mktemp)"
  grep -v '^PORTAL_PUBLIC_API_URL=' "$ENV_FILE" >"$TMP_ENV"
  printf 'PORTAL_PUBLIC_API_URL=%s\n' "$PUBLIC_URL" >>"$TMP_ENV"
  install -m 0600 "$TMP_ENV" "$ENV_FILE"
  rm -f "$TMP_ENV"

  systemctl restart "$SERVICE"
  curl -fsS --max-time 8 --resolve "$DOMAIN:443:127.0.0.1"     "$PUBLIC_URL/api/ping" >/dev/null ||
    fail "локальная TLS-проверка staging API не прошла"
  HTTPS_STATUS="ok"
fi

echo "[9/9] Итоговая проверка"
systemctl is-active --quiet "$SERVICE" ||
  fail "portal-stage7.service не active"

ss -ltn | grep -q "127.0.0.1:$API_PORT" ||
  fail "staging API не слушает loopback:$API_PORT"

if ss -ltn | grep -Eq "0\.0\.0\.0:$API_PORT|\[::\]:$API_PORT"; then
  fail "staging API ошибочно опубликован напрямую в интернет"
fi
if ss -ltn | grep -Eq "0\.0\.0\.0:5432|\[::\]:5432"; then
  fail "PostgreSQL ошибочно опубликован напрямую в интернет"
fi

cat >"$REPORT" <<EOF
PORTAL Stage 7
timestamp=$(date -Is)
commit=$ACTUAL
database=$DB
service=$SERVICE
loopback_api=http://127.0.0.1:$API_PORT
https_status=$HTTPS_STATUS
domain=$DOMAIN
domain_source=$DOMAIN_SOURCE
public_url=${PUBLIC_URL:-}
first_login_file=$LOGIN_FILE
production_database_touched=no
EOF
chmod 0644 "$REPORT"
echo
echo "STAGE7_API_OK"
if [[ "$HTTPS_STATUS" == "ok" ]]; then
  echo "STAGE7_HTTPS_OK $PUBLIC_URL"
else
  echo "STAGE7_HTTPS_PENDING status=$HTTPS_STATUS domain=$DOMAIN"
fi
echo "Первичный логин сохранён только в $LOGIN_FILE (mode 0600)."
echo "Production DB/API не переключались."
echo "Отчёт: $REPORT"
