# Android connection incident — 16.10.2026

Canonical status is in `PORTAL_MASTER_ROADMAP.md`. This document records evidence.

## Observed failures and corrections

1. USB initially failed enumeration, then ADB reported unauthorized. Reconnection and
   the owner's USB debugging authorization made the Samsung SM-S908B available.
2. Installed signed Android 5.13/63 (build 63.25) displayed no connection with both
   official server selections. It was already the newest release; reinstalling that
   APK would not fix this network route. With strict AdGuard private DNS, the phone
   resolved primary/reserve to 188.114.97.3/188.114.97.4. A TLS/SNI-preserving PC
   probe pinned to primary 188.114.97.3 also timed out, while normal PC DNS worked.
3. Reversible incident recovery: private DNS changed from hostname mode with
   dns.adguard-dns.com to automatic mode. The configured hostname was preserved.
   The phone then resolved both names to 104.21.92.48; PORTAL displayed connection
   ready. The owner entered credentials on the phone and confirmed the working
   screen opened. Incident evidence: 9a69101, 7ef4b89, merged main PR #83.
4. Android 5.14 adds an application-contained encrypted-DNS recovery path. It is
   restricted to api.vart-portal.ru and reserve-api.vart-portal.ru, activated only
   after an anonymous, TLS-verified PORTAL ping, and expires after 120 seconds.
   System DNS is attempted first. The original HTTPS hostname remains in URL/SNI;
   standard certificate and hostname validation remain enabled. DNS queries use a
   separate unauthenticated client; credentials, company IDs and request bodies
   never go to the resolver. Custom server names never use this recovery resolver.
   API transport does not automatically repeat POST or follow redirects.
5. Android build CI omitted codex/** branches. Added that trigger and native unit
   gates before staging packaging and signed release packaging. Tests cover route
   selection, recovery activation, expiry, custom-host exclusion, DNS address
   boundaries, bounded responses, TLS failures, and no POST replay.
6. iOS native errors did not provide the networkKind used by shared login UI.
   Added matching DNS/TLS/timeout/connect categories and XCTest coverage. The
   documented URLSession/system-encrypted-DNS priority is preserved; see the
   platform limitation in MOBILE_PARITY_CONTRACT.md.

## Preserved state

No PIN reset, permissions change, database migration or data/cache/outbox cleanup.
No VPN changes. No production runtime activation. VPS runtime remains
c55ac9e66f19510c324d03e9f7f87dea62a2a229 / c55ac9e-mobile512; source mirror follows
main separately. The original APK is retained in the official GitHub release.

## Verification status

- 5.13 incident: authenticated physical Android acceptance confirmed by owner.
- Local 5.14 native-shell/security/parity/iOS-release-config/diff checks pass.
- 5.14 Android compilation/native unit tests, full CI, signed publication and
  install-over-current with original AdGuard private DNS are pending.
- Cause of the third-party edge's network unavailability is not established.
  Recovery does not promise availability when every trusted route is unreachable.

Release publication must use exact current main after required Android and iOS
gates. Physical smoke must check the actual device/DNS path, not substitute PC or
server-only ping results.
