# PORTAL Windows Desktop client

The Windows client is a thin WPF/WebView2 shell over the canonical same-origin `/web/` application. It stores only the user-selected server origin under the current Windows user's Local AppData. It contains no API keys, passwords, company database, signing material, or hard-coded production endpoint. HTTPS is required; HTTP is accepted only for loopback development.

The package is a self-contained `win-x64` .NET 8 publish output. It requires the Microsoft Edge WebView2 Evergreen Runtime to be present on the Windows machine; the runtime is not bundled. The installer is a non-elevated, current-user PowerShell script. It verifies the SHA-256 sidecar before writing, rejects archive path traversal, installs into a new versioned directory, and then updates a Start Menu shortcut. Previous version directories are retained for rollback. The script does not download packages or contact a server.

## Build and install

GitHub Actions workflow `windows-desktop.yml` compiles the WPF app on `windows-latest` and publishes the versioned ZIP and SHA-256 sidecar as a CI artifact. This is a build artifact, not a signed release or production rollout. Obtain both files from the trusted repository's Actions run and execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_portal_desktop.ps1 -PackagePath .\PORTAL-Desktop-win-x64-3.5.0.zip -Version 3.5.0
```

The checksum detects artifact corruption and mismatched files; by itself it does not authenticate the publisher. Do not install packages from untrusted runs or locations. Production signing, release publication, update-channel policy, and visual verification on a supported Windows machine remain release gates.

The shell blocks navigation to origins other than the configured origin and disables WebView developer tools, context menus, and pop-up windows. Only the origin is persisted; authentication/session handling stays with the shared Web client.

## Update channel

The Desktop shell checks a same-origin `GET /api/desktop-update` manifest. The server advertises nothing unless all four secret-free environment values are configured: `PORTAL_DESKTOP_UPDATE_VERSION`, `PORTAL_DESKTOP_UPDATE_BUILD`, `PORTAL_DESKTOP_UPDATE_URL`, and `PORTAL_DESKTOP_UPDATE_SHA256`.

The manifest accepts HTTPS download URLs; plain HTTP is limited to loopback staging. The client rejects redirects, validates a 64-hex SHA-256, enforces a 250 MiB maximum, and only then launches the downloaded installer. The server manifest contains no credentials, tokens, signing keys, or company data.

This implements the update contract, not a production publication. A trusted hosted installer URL, publisher/code signing if required, and an ordinary Windows install/update validation remain release gates.
