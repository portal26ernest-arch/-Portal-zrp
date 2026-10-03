# PORTAL security remediation: activation plan (2026-10-03)

This source candidate addresses audited F1–F5. It is not a deployment record. Integrate its reviewed commit into the canonical release/recovery line named in `PORTAL_MASTER_ROADMAP.md` before any production rollout. Never deploy this side branch directly. Do not publish or advertise a client update until its separate release gates pass.

## Before activation

1. Confirm the live backend process, `systemd` unit, release path, site process, and Android/Windows update manifests by read-only inspection. Record the deployed commit and currently advertised artifact hashes without printing credentials or user data. On 2026-10-03 the live backend was `a81ee432-portal45` from `main`, while the roadmap named `assistant/portal-release-20261003` as canonical. These branches diverge after `be4996e`; the candidate branch now merges the production `main` commit, but that reconciliation has not reached the canonical release branch. Preserve all production hotfixes and pass CI before proceeding. This is a release blocker.
2. Confirm the production PostgreSQL control/tenant role separation and complete the existing roadmap security blocker for production-only roles. Run the synthetic test suite and CI against the exact candidate commit. Inspect the final diff and obtain owner approval for the production maintenance window, service restart, database migration, and site deployment.
3. Verify a fresh, restorable production backup and rollback release. Preserve the current service and environment definitions securely. Do not print `.env`, database URLs, session tokens, private keys, or backup contents in logs.
4. Confirm reverse proxies overwrite `X-Real-IP` and block direct external access to the backend. Set `PORTAL_TRUSTED_LOGIN_PROXIES` to the exact trusted proxy peer addresses (comma-separated) in the deployment configuration. If this is omitted, the limiter uses the peer IP, which may group all nginx clients under loopback. Do not trust a forwarded IP from arbitrary peers.

## Backend cutover

1. Stop the old API worker before changing token storage. Do not allow old and new workers to write session rows concurrently.
2. From the canonical release commit with existing production environment, run the explicit `portal_app_server.py --migrate-stage3 COMPANY_ID` operator command once for **every** registered company ID, including inactive tenants. The command applies version 15 and hashes existing bearer tokens in place; it does not print them or invalidate clients. Keep database backups private. The normal new worker requires version 15 for the primary company and fails closed if it is absent.
3. Verify by aggregate counts only that each company's migration version 15 exists and no `app_sessions.token` value lacks the `h1:` SHA-256 storage-key format. Do not export or display token values.
4. Start the new API release. Check `/api/ready`, `/api/ping`, a synthetic authorized login/logout/PIN rotation, account-role revocation, session-history closure, throttling, tenant boundary, and a financial XLSX export with synthetic text. Watch security-event counts and error rates without logging credentials or documents.
5. If activation fails, stop the new worker and restore the matching backup plus old release as one rollback unit. The old worker cannot read migrated token digests; rolling back code alone will break existing sessions. Prefer a reviewed forward fix when backup restoration would discard legitimate post-cutover writes.

## Site and client release gates

- The fixed `site/server.mjs` is a source snapshot of `/opt/portal-site/server.mjs` at site Git commit `92598a080c86304359ae07b3545faf48fc4941a0`. Reconcile it into the independent site repository, commit its release provenance, and deploy/restart that site only in the approved maintenance window. Verify malformed URL encoding returns a controlled 400 response and the service remains healthy using synthetic requests; do not probe user data.
- Android production release already requires a non-debug signer with pinned certificate fingerprint and HTTPS. Confirm the approved production signing key is configured in CI and validate package ID, version monotonicity, signer continuity, update manifest, and a physical-device update before promotion.
- The existing Windows 4.0 update release is unsigned. SHA-256 sidecars do not authenticate the publisher. Until an approved Windows signing certificate and verified updater trust policy exist, do not publish or advertise a new production Windows update as security-verified. Signing, signer pinning in the installer/updater, downgrade protection, and on-device smoke remain separate release work.

## Evidence and limits

Synthetic backend unit suite: 347 tests passed, 52 skipped. Disposable PostgreSQL suite: 40 passed, 2 skipped, temporary database and roles removed. Isolated Node site test passed. These checks cover code behavior, not production activation, real signing keys, or physical Android/Windows update flows. The full sensitive-endpoint authorization matrix and production security-event review remain coverage gates.
