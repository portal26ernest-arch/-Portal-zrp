#!/usr/bin/env bash
set -euo pipefail

# Prepare a dedicated Tor client and, only when its existing TLS/secret config is
# valid, the Telegram relay. Never creates relay secrets, DNS, TLS, or API config.
if [[ "${EUID}" -ne 0 ]]; then echo "Run as root on the owned VPS." >&2; exit 1; fi
if [[ ! -r /etc/os-release ]] || ! . /etc/os-release || "${ID:-}" != ubuntu; then
  echo "This bootstrap supports Ubuntu only." >&2; exit 1
fi
REPO_ROOT="${PORTAL_RELAY_REPO_ROOT:-/srv/portal-messenger-relay/current}"
ENV_FILE=/etc/portal-production/messenger-relay.env
SERVICE_SRC="${REPO_ROOT}/ops/systemd/portal-messenger-relay.service.example"
TORRC_SRC="${REPO_ROOT}/ops/portal-messenger-torrc.example"
TOR_SERVICE_SRC="${REPO_ROOT}/ops/systemd/portal-messenger-tor.service.example"
if [[ ! -f "${REPO_ROOT}/server/messenger_relay.py" || ! -f "${REPO_ROOT}/server/messenger_relay_auth.py" || ! -f "${SERVICE_SRC}" ]]; then
  echo "Expected a complete, reviewed Git checkout at ${REPO_ROOT}." >&2; exit 1
fi
[[ -f "${TORRC_SRC}" && -f "${TOR_SERVICE_SRC}" ]] || { echo "Tor deployment examples missing." >&2; exit 1; }
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tor python3 ca-certificates
getent group portal-tor >/dev/null || groupadd --system portal-tor
id portal-tor >/dev/null 2>&1 || useradd --system --gid portal-tor --home-dir /var/lib/portal-messenger-tor --shell /usr/sbin/nologin portal-tor
install -d -o portal-tor -g portal-tor -m 0700 /var/lib/portal-messenger-tor
install -d -o root -g root -m 0755 /etc/tor
install -o root -g root -m 0644 "${TORRC_SRC}" /etc/tor/portal-messenger-torrc
install -o root -g root -m 0644 "${TOR_SERVICE_SRC}" /etc/systemd/system/portal-messenger-tor.service
systemctl daemon-reload
systemctl enable --now portal-messenger-tor.service

# Relay activation is conditional on an already supplied protected config.
RELAY_CONFIG_OK=false
if [[ -f "${ENV_FILE}" ]] && python3 - "${ENV_FILE}" <<'PY'
import ssl
import sys

settings = {}
with open(sys.argv[1], encoding="utf-8") as env_file:
    for line in env_file:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            settings[name] = value
secret = settings.get("PORTAL_MESSENGER_RELAY_SECRET", "")
cert = settings.get("PORTAL_MESSENGER_RELAY_CERT", "")
key = settings.get("PORTAL_MESSENGER_RELAY_KEY", "")
if len(secret) < 32 or not cert or not key:
    raise SystemExit(1)
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.load_cert_chain(certfile=cert, keyfile=key)
PY
then
  RELAY_CONFIG_OK=true
fi
if [[ "${RELAY_CONFIG_OK}" != true ]]; then
  echo "Dedicated Tor client is prepared. Relay was not enabled: existing TLS+secret config did not pass validation."
  exit 0
fi
getent group portal >/dev/null || groupadd --system portal
id portal >/dev/null 2>&1 || useradd --system --gid portal --home-dir /nonexistent --shell /usr/sbin/nologin portal
install -d -o root -g root -m 0755 /etc/portal-production /srv/portal-messenger-relay
install -d -o root -g portal -m 0750 /etc/portal-production/relay
chown root:portal "${ENV_FILE}"; chmod 0640 "${ENV_FILE}"
install -o root -g root -m 0644 "${SERVICE_SRC}" /etc/systemd/system/portal-messenger-relay.service
install -d -o root -g root -m 0755 /etc/systemd/system/portal-messenger-relay.service.d
cat > /etc/systemd/system/portal-messenger-relay.service.d/tor-upstream.conf <<'EOF'
[Service]
Environment=PORTAL_MESSENGER_RELAY_UPSTREAM_SOCKS5=socks5://127.0.0.1:19050
EOF
systemctl daemon-reload
systemctl enable --now portal-messenger-relay.service
systemctl --no-pager --full status portal-messenger-relay.service
