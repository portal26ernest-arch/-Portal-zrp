# PORTAL central storage status — 2026-10-01

## Central VPS storage

Paid VPS: `178.209.127.247`.
Central root: `/srv/portal/central`.

Prepared directories:
- `repository/` — Git bundle/current source snapshot links.
- `storage/documents/` — future generated company documents.
- `storage/uploads/` — future uploaded attachments.
- `migration/` — phone SQLite snapshots and migration evidence.
- `releases/android/` and `releases/windows/` — release artifacts.
- `archive/` — historical worktrees/one-off project material.
- `backups/` — future PostgreSQL/file backups.
- `private/` — root-only operational private material when explicitly approved.
- `incoming/20261001/` — immutable first consolidated upload.

## Verified first upload

Local PORTAL data was inventoried across Documents/Downloads/Desktop. Raw local PORTAL folders total about 1.27 GB, but most of that is reproducible JDK/Gradle/node/build cache. The first essential consolidated upload is about 42 MB.

The VPS copy contains 26 files. The uploaded `00_manifest/checksums.sha256` was verified on the VPS: every listed file returned `OK`.

Included evidence:
- Git all-refs bundle and current source ZIP.
- Dirty-worktree patches/untracked archives found during consolidation.
- Phone SQLite snapshot and migration material.
- Android staging release artifact/checksum/changelog/report.
- Historical non-Git PORTAL project folders and deployment material.

Reproducible caches were intentionally excluded. Production signing key bytes were also excluded from the general archive; only key inventory/checksum metadata is present. Do not make the application VPS the only recovery location for signing keys.

## Current HTTPS staging

Stage 7 was redeployed from commit `95457bac0d0f2c0ded0ddb0b0cb9b636b9df52a6` against the isolated staging PostgreSQL database. Production DB/API were not switched.

Fixed sslip hostname `178-209-127-247.sslip.io` resolves correctly, but Let's Encrypt HTTP-01 validation still cannot fetch the external challenge, so it is not accepted as the release endpoint.

Working temporary HTTPS endpoint:
`https://jobs-interests-spring-neo.trycloudflare.com`

External `/api/ping`, setup lock and staging API checks passed. This Quick Tunnel is for immediate device testing only; it is not the permanent production domain.

## Remaining centralization/release gates

- A real owned domain has not been supplied for PORTAL. Production DNS/HTTPS therefore remains open.
- Windows release artifact still needs to be placed under `releases/windows/`.
- Production document service should use `/srv/portal/central/storage/documents/production` at cutover; staging data must remain isolated.
- Configure independent off-server backup before deleting local originals.
- Do not delete source folders on the PC until server copy, checksum and restore verification are complete.
