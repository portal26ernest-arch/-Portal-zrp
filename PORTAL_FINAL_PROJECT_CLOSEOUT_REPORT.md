# PORTAL Final Project Closeout

Date: 2026-10-01
Status: **SOFTWARE COMPLETE — external gates remain**

## Baseline and ending state

- Starting SHA: `337d2399cd206f0029a171aa4e503e52c82ca0e9` (`feat: add self-service PIN change`).
- Starting branch: `codex-finalization-megapack-part12`, tracking `origin/codex-finalization-megapack-part12`.
- At start, git status was clean.
- Ending source SHA: `337d2399cd206f0029a171aa4e503e52c82ca0e9`. No application source changed in this closeout; the pushed branch adds only the closeout documentation recorded here.
- Android: `3.5-dev` / versionCode 35 (development staging; `android_src/release.properties`).
- Windows Desktop: `3.5.2` (`desktop_windows/Portal.Desktop.csproj`).
- Server: the server reports the HTTP identification string `PORTALAppServer/1.0`; no separate semantic Server release version is declared in source. Server CI runs on Python 3.11 and 3.13 (runtime versions, not product versions).

## Audit outcome

No remaining software-completable A-gap was found in the audited current tree. The reported current-sha evidence at start already covered the self-service PIN change, bounded reminder dispatch, Desktop connection diagnostics/WebView compatibility/update manifest, and central storage documentation. The PIN flow is masked, verifies confirmation, hides for Platform Owner, and the current session remains usable while other sessions are revoked; audit paths are covered by the existing server and UI tests and must never record the PIN.

The post-`7264d9b` delta is now reflected in this closeout: central VPS document storage and its staging/production boundary; Desktop 3.5.1 connection/WebView fixes with 3.5.2 compatibility packaging and the secret-free update contract; and self-service PIN change. No production action, data change, secret access, code change, or application behavior change was made in this closeout. The only software documentation defect discovered was the damaged status text for roadmap item 105; it has been restored as 🟡 with its actual disposable-import gate.

Roadmap count, counting conceptual numbered items (including grouped ranges): **93 ✅ / 15 🟡 / 6 ⏳ / 12 🔌 (126 total)**. These are evidence statuses, not production approval. See `PORTAL_MASTER_ROADMAP.md` and the synchronized readiness matrix.

## Verification

At starting SHA `337d2399cd206f0029a171aa4e503e52c82ca0e9`:

- Full Server `python -m unittest discover -s server -p 'test_*.py'`: **306 passed, 49 skipped, 0 failed** (Python 3.13 local). Skips include PostgreSQL integration tests because no local disposable PostgreSQL service was configured.
- Shared Android/Web Node suite: **58 passed, 0 failed** (node --test android_src/tests/*.test.cjs).
- Android UI/Playwright: **37 passed, 0 failed** (`node --test android_src/tests/ui.test.cjs`).
- `ops.test_infra_readiness`: **8 passed**.
- Targeted Server tests (portal_app_server, production, reminder jobs/operator, money units): **87 passed, 0 failed**.
- All shipped JavaScript assets and CJS tests passed node --check; workflow YAML parsing and Windows installer safety contracts passed.
- `python -m compileall -q server ops`: passed.
- `git diff --check`: passed after final documentation synchronization.
- Disposable PostgreSQL was not available locally. Prior successful Web CI on the exact starting/source SHA provides the disposable PostgreSQL evidence; no PostgreSQL run was triggered on the documentation-only ending SHA.
- Windows installer safety contracts passed locally under Windows PowerShell: checksum, versioned install, shortcut, duplicate-version rejection, and archive traversal rejection. WPF/.NET publish was unavailable because dotnet is absent. No Windows workflow run ID was supplied for the ending source SHA.
- Closeout changes are documentation-only; source-based Android, Server and Web workflows did not trigger on the push due their path filters.

GitHub Actions at tested runtime source SHA 337d2399cd206f0029a171aa4e503e52c82ca0e9: Android APK run 36861242054 — SUCCESS; Web run 36861242048 — SUCCESS; Android UI run 36861242142 — SUCCESS; Server isolation run 36861242135 — SUCCESS. This is also the ending source SHA; subsequent commits only synchronize documentation.

No production database, VPS configuration, DNS, production secrets, signing material, or cutover state was changed. No credentials or customer financial facts were added to Git.
The documentation-only pushes did not trigger path-filtered source workflows. gh is unavailable locally, so no manual rerun/dispatch was possible. The tested runtime tree is identical to the ending source SHA above.

## External/manual gates

| Class | Roadmap items | Required evidence to close |
|---|---|---|
| B — real device/browser/PC | 59 Android chooser/save; 60 target-browser Share; 61 Android email intent; 63 Android/WebView Excel; 85 Windows target-PC install/update; 86 physical Android parity | Ordinary user smoke on the target Android device/browser/Windows PC using the built artifacts; record device/OS/browser and results. Item 85 additionally needs production publication evidence (C). |
| C — provider/production/data | 46 quality/defects; 47 trusted production timer/activation; 77–79 official marketplace feed and live activation; 80 Android production cutover; 83 production signing/manual release; 85 signed/trusted Windows publication; 93 off-server backup; 105 imported SQLite disposable rehearsal; 125 domain/DNS/HTTPS | A canonical QC source; approved production timer/provider/domain/secrets/release actions; separately authorized disposable import of the verified SQLite copy and reconciliation; configured off-server backup target plus restore evidence. Keep reminders/news production-disabled until real deployment evidence exists. |
| D — separate integration | 106–117 TalAnt/WMS/ТСД | Official TalAnt API documentation, authorized sandbox/credentials, agreed scope and hardware/device evidence. No direct DB access or TalAnt code changes. |
| C — final migration/cutover | 94–99 | Owner-authorized domain/network/certificate, import freeze/snapshot/reconciliation, controlled production cutover and rollback evidence. |

No source-backed defect metric or official marketplace news feed was invented. No physical evidence was fabricated. Production DB/VPS/DNS/secrets/signing/cutover were not changed. Production credentials, signing material, or customer financial facts were not added to Git.

## Exact next actions

1. Owner/provider supplies a permanent domain and authorized production network/certificate path.
2. Owner provisions and verifies protected production secrets/signing and explicitly authorizes release/cutover.
3. Owner performs target Android/browser/Windows install/update smoke and records evidence.
4. Owner selects an off-server backup provider and runs an isolated restore rehearsal.
5. Owner authorizes the imported-SQLite copy rehearsal in a disposable PostgreSQL target.
6. If pursued, obtain official marketplace and TalAnt provider interfaces before activating those integrations.

No software TODO remains in the closeout scope.
