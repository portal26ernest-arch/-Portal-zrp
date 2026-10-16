# PORTAL Android 5.15 — performance and logout candidate (2026-10-16)

## Scope and status
- Branch: `assistant/android-logout-performance-20261016` from GitHub main `a93d961`.
- Candidate Android 5.15 / versionCode 65; iOS build metadata synchronized for shared assets.
- **NOT a published/signed production release**. On-device logout timing, cold-start, network failover and login still require real Android acceptance.
- No production database, users, PINs, queues, signing keys, VPS, or phone application data modified.

## Defects addressed
1. User-confirmed sign-out previously awaited `POST /api/logout` (up to 35 s of JS waiting plus DNS preflights), leaving the app logged in visually. It now clears local credentials/UI immediately after user confirmation and starts **one** server revocation request using the captured old token. Non-replayable POST is never automatically retried. Server revocation failure prompts an explicit warning. No write can be in progress when sign-out is confirmed.
2. Cached GET refresh could deliver an unscoped `401` event after a newer login. Native bridge now maintains the active token, rejects late invalidations and ignores late cache write/clear on a different session. The credential never appears in JavaScript callbacks.
3. `resolveServerForRequest` previously synchronized across 3 HTTP executor threads during sequential 5.5/7.5 s DNS probes. A single-flight atomic flag replaces the long monitor; other requests proceed without waiting. After both probes fail, an 8 s cooldown prevents immediate duplicate expensive probes.
4. App metadata detection previously accessed `.platform` directly on a JSON string; Android native flag is now parsed correctly.
5. Stale messenger isolation/static tests updated to reflect the actual startup catch guard; Android release/build CI now runs logout/session regressions.

## Behavior and security expectations
- Pending financial or stock writes block interactive sign-out until they finish; no outbound mutation is replayed.
- Local sign-out is immediate but server-side revocation remains best effort under network loss. The client warns if server does not acknowledge; tokens are not retained for retry after local removal.
- Cached cross-company/user isolation remains intact; the Android messenger profile still clears on sign-out and provider change.
- Direct and encrypted DNS routing, TLS hostname verification, and no POST replay remain unchanged.
- Android `requestAsync` network work may continue after a JS timeout; actual cancellation is **not** implemented in this candidate.

## Validation
- Local: Node 37 passing, 2 Playwright skipped without dependencies; standalone Messenger isolation PASS; native-shell and Android build-security PASS; Android/iOS metadata parity PASS; `git diff --check` PASS.
- Required before release: full GitHub Android staging APK + JVM unit, Android UI/Playwright, iOS compile/tests, security CI; physical Samsung Android on original VPN/AdGuard setup, logout under normal/offline/sluggish network, rapid login/logout cycle, no stale 401 invalidation, navigation under 3 parallel requests, unsynced outbox preserved.
- Timings target for physical acceptance: local signed-out screen appears within 1 second after confirmation (excluding consent); UI navigation remains responsive even with failed DNS probes. These are targets, **not measured results**.

## Rollback
Maintain official 5.14 as the existing published release. No production release or automatic push to phones until device acceptance.
