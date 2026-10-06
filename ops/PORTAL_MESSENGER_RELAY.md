# PORTAL Messenger Relay

## Purpose

PORTAL Messenger Relay is an application-scoped fallback transport for the embedded Telegram/MAX clients. It is **not** a device VPN and must never be configured as a public general-purpose proxy.

- Android keeps Messenger in the dedicated `:messenger` process. `androidx.webkit.ProxyController` therefore affects only that Messenger WebView process, not PORTAL API traffic or the rest of the phone.
- Windows Desktop uses a separate WebView2 environment/profile for Messenger and applies `--proxy-server` only to that environment.
- Direct provider access stays the default on Android. Main-frame failures, or repeated provider network failures, trigger one automatic Relay attempt; the user can also force/toggle the Relay channel from the Messenger header.
- Desktop uses Relay whenever an authenticated ticket is available, otherwise it stays direct.

The official provider login stays inside the provider WebView. PORTAL does not receive Telegram/MAX passwords, confirmation codes, cookies or provider session storage.

## Ticket flow

1. The authenticated PORTAL UI requests `GET /api/v3/messenger-relay-ticket`.
2. The production API checks the normal Messenger company-module and role restrictions. Director and manager roles remain denied by the existing Messenger policy.
3. If `PORTAL_MESSENGER_RELAY_URL` and a deployment-only `PORTAL_MESSENGER_RELAY_SECRET` are configured, the API returns a short-lived username/password pair signed with HMAC-SHA256. The secret itself is never returned.
4. Android passes the ticket only to the non-exported `MessengerActivity`; Desktop passes it to the native host through WebView2 `postMessage`, never through a URL.
5. The HTTPS proxy challenges with `407 Proxy Authentication Required`. Android `HttpAuthHandler` and WebView2 `BasicAuthenticationRequested` answer only for the PORTAL Relay challenge.

Tickets expire in at most 24 hours. They are intentionally held only in process memory and are not written to Git, PORTAL documents, company backups or provider storage.

## Relay restrictions

`server/messenger_relay.py` accepts only authenticated HTTP `CONNECT` requests. It rejects all other proxy methods, allows only TCP/443, resolves destination DNS itself, rejects private/loopback/link-local/reserved IPs, and permits only configured provider suffixes (default: `telegram.org`, `t.me`, `max.ru`). This prevents the service from becoming an open proxy or SSRF tunnel.

Operational logs contain only technical connection metadata: source IP, PORTAL user/company numeric identifiers and destination hostname. The relay never terminates provider TLS and cannot read message contents, Telegram/MAX credentials, cookies or chat payloads.

## Deployment gate

Do not advertise the Relay to clients until all of the following are true:

1. Create owned DNS for `relay.vart-portal.ru` (or another owned hostname) to the selected VPS.
2. Issue a TLS certificate for that exact hostname, copy/deploy the certificate material into `/etc/portal-production/relay/`, and restrict the private key to the relay service account/group (for example root:portal with mode 0640).
3. Generate one random `PORTAL_MESSENGER_RELAY_SECRET` of at least 32 characters and install the same value in both the PORTAL API environment and `/etc/portal-production/messenger-relay.env`. Never put it in the repository.
4. Review `ops/messenger-relay.env.example`; prefer a dedicated listener such as TCP/9443 unless a separate IP/443 is available. Open only that port in the firewall.
5. Install `ops/systemd/portal-messenger-relay.service.example`, daemon-reload, enable/start the service, and verify it is not reachable as an unauthenticated proxy.
6. Set `PORTAL_MESSENGER_RELAY_URL=https://relay.vart-portal.ru:9443` in the production API environment and restart the API during an approved maintenance window.
7. Smoke-test: unauthenticated CONNECT -> 407; valid ticket to Telegram/MAX -> 200; CONNECT to an unrelated host/private address -> 403; then test Telegram/MAX from Android and Windows with direct access intentionally unavailable.

If the API variables are absent or invalid, `/api/v3/messenger-relay-ticket` returns `{enabled:false}` and clients remain on direct access. This fail-quiet behavior allows code rollout before Relay infrastructure activation.
