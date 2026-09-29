# PORTAL 3.5 staging changelog

Build: `3.5-dev-staging` (versionCode 35), development channel.

- Carries forward the verified Part 11 baseline, including Web template downloads, invoice revisions, scoped Documents, chat, and secure Android updater.
- Part 12 staging candidate is isolated from production. It does not perform a production migration, import, release, or cutover.
- The build artifact includes its SHA-256, version metadata, this changelog, and a concise report of checks performed by the Android build workflow.
- Physical Android install and user-flow review remain a manual owner check after CI.
