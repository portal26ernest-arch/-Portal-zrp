# PORTAL Telegram Relay

## Scope

The authenticated TLS HTTP CONNECT relay is a transport for the embedded official Telegram Web client only. It is not a device VPN. MAX, PORTAL API traffic, updates, documents, and all other device traffic remain direct. CONNECT carries Telegram's end-to-end TLS; the relay never terminates or inspects it.

Android applies `ProxyController` only inside the dedicated `:messenger` WebView process and clears the override before MAX loads. Desktop uses distinct fixed Telegram and MAX WebView2 profiles; only Telegram can receive proxy arguments or relay authentication. iOS 17+ uses separate fixed persisted stores; only Telegram's store receives Network `ProxyConfiguration` with failover disabled. iOS 16 blocks required Telegram, while MAX remains direct. No provider password, cookie, or session data enters PORTAL.

## Ticket and rollout

Only opening Telegram requests `GET /api/v3/messenger-relay-ticket`. MAX never requests a ticket. The response declares `provider: telegram`, `enabled`, and `required`. `PORTAL_TELEGRAM_RELAY_REQUIRED=0` is the rollout default; set it to `1` only after the relay is ready. If required is true while URL/secret configuration is missing or invalid, the API returns `enabled:false, required:true`; clients must fail closed. An enabled ticket is short-lived, memory-only, contains no relay signing secret, and its signed username uses the `v2.telegram` scope. The validator rejects other ticket formats and reports `scope=telegram`.

Configure the API with `PORTAL_MESSENGER_RELAY_URL=https://relay-eu.vart-portal.ru:9443` and a random `PORTAL_MESSENGER_RELAY_SECRET` of at least 32 characters. Install the same secret only in the API process environment and relay's root-owned environment file. Never commit secrets or put them in tickets beyond short-lived HMAC credentials.

## Relay restrictions

`server/messenger_relay.py` accepts authenticated CONNECT only, TCP/443 only, and by default `telegram.org`, `t.me`, and their subdomains (including `*.web.telegram.org`). It rejects MAX, unrelated hosts, private/reserved/loopback/link-local destinations, and non-CONNECT methods. DNS is resolved by the relay and every candidate address is checked before connecting. Do not broaden the allowlist without a reviewed Telegram transport requirement. Logs contain connection metadata only.

## No-cost Tor upstream on the existing Moscow VPS (code-ready, not activated)

The existing VPS `178.209.127.247` is in Moscow. The no-cost transport option keeps the relay endpoint on this owned VPS and routes only the relay's Telegram outbound TCP connections through a dedicated local Tor SOCKS5 client at `127.0.0.1:19050`. PORTAL API/MAX/other traffic remains direct. `PORTAL_MESSENGER_RELAY_UPSTREAM_SOCKS5` accepts only loopback SOCKS5 URLs; a configured upstream is fail-closed and cannot fall back to direct egress. With the option unset, direct relay egress remains available for an owned Western VPS.

Provider TLS remains end-to-end through CONNECT. A Tor exit can observe the destination hostname/IP and connection timing/volume, but not provider plaintext. Tor may have lower performance and reliability than an owned Western VPS. `ops/portal-messenger-torrc.example` prefers exits in DE/NL/FR/AT/CH/SE/FI and enables strict node policy where supported; this preference does not prove the actual exit country.

Before activation, verify the observed Tor exit country is outside RU and run an authenticated Telegram CONNECT smoke. Do not set `PORTAL_TELEGRAM_RELAY_REQUIRED=1` before the full smoke on supported clients. The Tor bootstrap may prepare the dedicated Tor client but starts/enables the PORTAL relay only when the existing relay secret and TLS cert/key paths pass validation. This code task does not install Tor or verify egress.

## Owned western-europe deployment (not activated)

Use a newly provisioned Ubuntu VPS physically located in Western Europe with a static public IP, provider account access, and a firewall that exposes only SSH administration and the chosen relay TLS port. Oracle Cloud Always Free may be evaluated if its assigned region and egress location are confirmed; the free-tier label alone is not proof of geography or availability. The existing VPS `178.209.127.247` is in the Russian Federation and is not a western egress. Do not use public free proxies. Cloudflare Tunnel is ingress to PORTAL; Cloudflare Workers do not accept inbound CONNECT and cannot serve as this arbitrary outbound CONNECT relay.

Reproducible bootstrap/checklist: `sudo bash ops/bootstrap_messenger_relay_ubuntu.sh` from a complete, reviewed Git checkout on Ubuntu. It prepares the dedicated Tor client; it installs/enables the PORTAL relay only if an existing protected environment file contains a secret of at least 32 characters and readable certificate/key files. It never creates DNS, secrets, certificates, or API configuration. The script has not been run against a provisioned host; no Tor installation or exit geography is claimed.

Bootstrap outline:

1. Provision the host in a verified Western European region and record its provider/region and public IP in the infrastructure change record. Do not alter production DNS during preparation.
2. Install supported Ubuntu security updates and Python 3. The bootstrap creates unprivileged `portal-tor` and `portal` accounts. Limit firewall exposure to SSH and the selected relay TLS port. Do not enable IP forwarding or install a system VPN.
3. Place the reviewed `server/messenger_relay.py`, `server/messenger_relay_auth.py`, and `ops/systemd/portal-messenger-relay.service.example` from one immutable Git SHA on the new host. Create a host-only environment file under `/etc/portal-production/` with mode 0640 and a relay-owned random secret. Keep TLS key material root-owned and readable only by the service group.
4. Obtain a certificate for the future owned name `relay-eu.vart-portal.ru` using an approved DNS/TLS process. Do not create that DNS record as part of this code task. Set certificate/key paths and the listen port in the host environment file.
5. Start the service only after confirming source SHA, certificate hostname, firewall, service sandbox settings, and secret match with the separately approved API configuration. Confirm unauthenticated requests receive 407, MAX/unrelated/private CONNECT requests receive 403, and an authenticated Telegram endpoint can establish a tunnel.
6. Enable server-required mode only through a reviewed full runtime release. Verify Telegram on supported clients and confirm MAX plus PORTAL API/updates/documents remain direct.

This repository change does not provision infrastructure, change DNS, install secrets/Tor, or activate the relay. The service templates and `ops/messenger-relay.env.example` remain examples; they contain placeholders only.
