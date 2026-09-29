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
