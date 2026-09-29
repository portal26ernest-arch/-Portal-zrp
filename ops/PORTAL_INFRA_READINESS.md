# PORTAL infrastructure readiness — assistant parallel track

This track is isolated from Codex Part 12 A–D implementation.

## Added
- provider-neutral PostgreSQL backup helper using pg_dump custom format;
- pg_restore --list verification before publication;
- SHA-256 sidecar and JSON manifest;
- optional age encryption by public recipient file;
- retention pruning only after successful backup;
- disposable restore rehearsal restricted to portal_test_restore_* databases;
- nginx production HTTPS reverse-proxy template, with API remaining loopback-only;
- hardened systemd backup service/timer examples.

## Safety boundaries
- No production DB/service/DNS was modified.
- Credentials are not accepted as CLI DSNs and are not stored in repository files.
- Restore rehearsal refuses arbitrary database names and creates its own portal_test_restore_* target.
- Production cutover still requires explicit owner approval.
- An actual off-server target/provider remains an external deployment choice.

## Next verification
- unit/static tests for guards and templates;
- Python syntax checks;
- git diff --check;
- disposable PostgreSQL rehearsal on VPS only after merge/cherry-pick into the active Part 12 integration branch.


## Off-server export transport

- `ops/offsite_backup.py` verifies the manifest, SHA-256 and checksum sidecar before export.
- Filesystem transport supports a mounted/network/off-server target with atomic copy and post-copy hash verification.
- Rclone transport uses an externally configured remote and never accepts embedded passwords/tokens/access keys.
- Real provider credentials and the final off-server destination remain owner/provider deployment inputs; they are not committed.
- Unit coverage is in `ops/test_offsite_backup.py`.


## HTTPS endpoint preflight

- `ops/https_endpoint_preflight.py` performs read-only production endpoint checks.
- Requires a credential-free standard-port HTTPS URL.
- Verifies trusted TLS, certificate lifetime threshold, `/api/ping`, HSTS and core security headers.
- Verifies plain HTTP redirects safely to the same HTTPS hostname.
- Can optionally prove that the internal API port (for example 8770) is not reachable publicly.
- A failed TLS/header/ping/redirect/public-port check returns NO-GO; the tool never changes DNS, proxy, certificate, service or database state.
- Unit coverage is in `ops/test_https_endpoint_preflight.py`.


## PORTAL API service template

- `deploy/systemd/portal-api.service` runs the API as the non-root `portal` user with systemd hardening.
- `deploy/systemd/portal.env.example` pins the API to `127.0.0.1:8765` and deliberately leaves production PostgreSQL enablement false.
- The nginx template now uses `__PORTAL_LOOPBACK_PORT__` instead of a stale hard-coded port, preventing proxy/application port drift.
- Real database DSNs remain outside Git in the protected server environment file.
