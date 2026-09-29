# PORTAL Windows Desktop

Lightweight Windows wrapper for the existing PORTAL Web client.

- Uses Microsoft Edge app mode when Edge is installed.
- Falls back to the Windows default browser if Edge is unavailable.
- Does not contain or copy the company master database.
- Does not store API tokens, passwords, signing keys or other secrets.
- Configuration contains only portal URL, channel and desktop wrapper version.
- HTTPS is mandatory, except loopback HTTP for staging development.
- Production rejects a "-dev" version.

## Install

From an extracted package:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -PortalUrl https://portal.example -Channel production -Version 3.6

Use -DesktopShortcut if a desktop shortcut is wanted.

## Update strategy

The business UI remains server/Web delivered, so ordinary product UI updates do not require reinstalling the wrapper.
A new wrapper package is needed only when launcher/installer behavior changes. Re-running install.ps1 replaces
the wrapper files and rewrites non-secret configuration.

## Staging safety

Use -DryRun on install/launcher/uninstall for validation without filesystem or process side effects.
