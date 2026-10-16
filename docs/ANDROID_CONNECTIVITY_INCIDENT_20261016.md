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
- Implementation commits 0bf7526 and d009a5e were pushed and integrated by PR #84
  into canonical main e11886110bcc373b4222d1c275e34a89bf3ba828.
- Final implementation CI: Android 38948540481 SUCCESS; retained JUnit XML records
  12 tests, zero failures/errors/skips. Android UI 38948586048 SUCCESS; iOS build,
  parity, XCTest and privacy checks 38948585966 SUCCESS; Windows 38948585622 and
  security 38948585778 SUCCESS. Master-control push/PR checks also passed.
- On merged main, Android 38950327229, UI 38950327270, Windows 38950327277,
  security 38950327425 and master-control 38950327253 passed. The automatic iOS
  repeat on main was still running when the release record was prepared; the
  final implementation's iOS gate above was already successful before merge.
- Signed release workflow 38950413046 SUCCESS, including testReleaseUnitTest,
  standard production signer verification and artifact/manifest validation.
  Release portal-android-v5.14 was published 2026-10-16 18:51:14 UTC from exact
  current main e11886110bcc373b4222d1c275e34a89bf3ba828. Android versionCode 64,
  versionName 5.14, buildNumber 64.26. The latest updater release points to 5.14.
- Downloaded production APK SHA-256 matches GitHub's asset digest, the .sha256
  file and portal-update.json:
  c7e01478324a58b6046ad8f64fe3f401351f981c95b697e71014640f08236be2.
  Local artifact validation with the actual CI build metadata returns
  RELEASE_ARTIFACT_OK. Release and previous 5.13 rollback APK remain available:
  https://github.com/portal26ernest-arch/-Portal-zrp/releases/tag/portal-android-v5.14
- VPS source sync explicitly confirmed main e118861; mirror was clean, timer and
  production service active. Runtime remained c55ac9e-mobile512 because this fix
  changes the native client only. Both official origins' /api/ping and /api/ready,
  plus https://vart-portal.ru/web/, returned HTTP 200 after the implementation.
- Physical 5.14 install-over-current and original AdGuard DNS smoke remain OPEN:
  the phone disappeared from ADB before the signed artifact became available.
  No 5.14 installation or physical recovery acceptance is claimed. The owner
  was asked to reconnect the phone. Last verified device state is working 5.13
  with automatic private DNS; the original AdGuard hostname is preserved.
  Next: reconnect/authorize USB, install the signed 5.14 APK with adb install -r,
  verify version/auth/data preservation, restore the original hostname DNS mode
  and verify the working screen plus the fixed PortalNetwork recovery marker.
  If connectivity fails, restore automatic DNS immediately.
- Cause of the third-party edge's network unavailability is not established.
  Recovery does not promise availability when every trusted route is unreachable.

Release publication must use exact current main after required Android and iOS
gates. Physical smoke must check the actual device/DNS path, not substitute PC or
server-only ping results.
