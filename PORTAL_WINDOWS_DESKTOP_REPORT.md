# PORTAL Windows Desktop — staging evidence

Date: 2026-09-30

## Result

A lightweight Windows staging client now exists on branch `assistant-part12-infra-readiness`.

Implementation:
- `desktop/windows/PortalDesktop.ps1`
- `desktop/windows/install.ps1`
- `desktop/windows/uninstall.ps1`
- `desktop/windows/test.ps1`
- `desktop/windows/README.md`
- `.github/workflows/windows-desktop-build.yml`

Architecture:
- system Microsoft Edge app mode when available;
- safe default-browser fallback;
- same PORTAL Web client/API;
- no local master database;
- no passwords/API tokens/signing keys in the package;
- production URL must be HTTPS;
- loopback HTTP allowed only for staging development;
- production rejects a `-dev` wrapper version.

## Commits

- `8a79cb2` — Windows staging wrapper + packaging workflow.
- `6e6a6a2` — Infra readiness workflow and desktop install verification.
- `7f8b904` — fixed Windows packaging copy syntax after first CI failure.

## Local verification

- `desktop/windows/test.ps1` → `PORTAL_WINDOWS_DESKTOP_TEST=PASS`.
- workflow YAML parse → PASS.
- `git diff --check` → PASS.

## GitHub Actions evidence

Initial Windows run:
- run `36642840612` — failed only in package copy syntax;
- thin-client tests and version extraction had already passed;
- failure was fixed in `7f8b904`.

Verified green runs at `7f8b904d061704b778b1bcc1cf192b5700722c27`:
- Windows Desktop staging run `36643347067` — SUCCESS.
- Windows Desktop staging run `36643347847` — SUCCESS.

Produced artifact:
- name: `PORTAL_Windows_3.5-dev-staging`
- artifact id: `11066524988`
- size: 4665 bytes
- GitHub artifact digest: `sha256:509f4c21f6ba2735de85e5aaddbc5ab7d8d011f824ff6ae403356bf54c11d4c2`
- source SHA: `7f8b904d061704b778b1bcc1cf192b5700722c27`

## Roadmap interpretation

Roadmap item 85 is no longer an unimplemented Windows-client item.
Software-completable staging implementation and CI artifact packaging are evidenced.

Remaining production/manual concerns:
- this is a lightweight script-based staging wrapper, not a signed MSI/EXE;
- production endpoint/domain/HTTPS still require owner-controlled deployment;
- production code signing for a native Windows installer, if later required, is an external release-hardening step;
- no production cutover was performed.

The wrapper intentionally keeps business logic server/Web-side so normal PORTAL UI updates do not require reinstalling the desktop shell.
