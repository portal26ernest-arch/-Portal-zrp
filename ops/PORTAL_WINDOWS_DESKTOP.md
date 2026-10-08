# PORTAL Windows Desktop client

The Windows client is a thin WPF/WebView2 shell over the canonical same-origin `/web/` application. Source, documentation, and CI packages live in GitHub; company records live in central PostgreSQL behind the PORTAL API. The shell stores only the user-selected server origin under the current Windows user's Local AppData. It contains no API keys, passwords, company database, private signing key, or hard-coded production endpoint. The public update-verification key is embedded as a read-only resource. HTTPS is required; HTTP is accepted only for loopback development.

WebView2 starts with an InPrivate profile, so authentication and browsing data are not kept across app restarts. WebView2 may still create technical profile files on disk; files deliberately downloaded by the user remain where the user saved them. Switching servers clears the active WebView2 browsing data before another login. The same WebView2 instance is reused when reconnecting.

The package is a self-contained `win-x64` .NET 8 publish output. It requires the Microsoft Edge WebView2 Evergreen Runtime to be present on the Windows machine; the runtime is not bundled. The installer is a non-elevated, current-user PowerShell script. It verifies the SHA-256 sidecar before writing, rejects archive path traversal, installs into a new versioned directory, and then updates a Start Menu shortcut. Previous version directories are retained for rollback. The script does not download packages or contact a server.

## Build and install

GitHub Actions workflow `windows-desktop.yml` compiles the WPF app on `windows-latest` and publishes the versioned ZIP and SHA-256 sidecar as a CI artifact. This is a build artifact, not a signed release or production rollout. Obtain both files from the trusted repository's Actions run and execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install_portal_desktop.ps1 -PackagePath .\PORTAL-Desktop-win-x64-3.8.0.zip -Version 3.8.0
```

The checksum detects artifact corruption and mismatched files; by itself it does not authenticate the publisher. Do not install packages from untrusted runs or locations. Production signing, release publication, update-channel policy, and visual verification on a supported Windows machine remain release gates.

The shell blocks navigation to origins other than the configured origin and disables WebView developer tools, context menus, and pop-up windows. Only the origin is persisted; authentication/session handling stays with the shared Web client.

## Connection troubleshooting

Enter the HTTPS origin only, for example `https://portal.example.ru`, without `/web/`, credentials, query parameters, or a trailing application path. The client checks `GET /web/` before storing the origin and shows whether the response is a redirect, an HTTP error, a non-HTML response, a timeout, or a network/TLS failure. An empty `PORTAL_SERVER_URL` environment variable does not override a saved origin. The selected origin is saved only after a successful probe and WebView2 initialization.

For isolated development, `http://localhost:PORT` or `http://127.0.0.1:PORT` is allowed. Plain HTTP to a VPS address is intentionally rejected. A server with no reachable HTTPS route or no `/web/` deployment cannot be connected to by the Windows client; configure an approved HTTPS endpoint rather than disabling transport protection.

## Update channel

The Desktop shell checks a same-origin `GET /api/desktop-update` manifest. The server advertises nothing unless these values are configured: `PORTAL_DESKTOP_UPDATE_VERSION`, `PORTAL_DESKTOP_UPDATE_BUILD`, `PORTAL_DESKTOP_UPDATE_URL`, `PORTAL_DESKTOP_UPDATE_SHA256`, and `PORTAL_DESKTOP_UPDATE_SIGNATURE`. The signature is RSA-3072/SHA-256 over the canonical UTF-8 payload `PORTAL-DESKTOP-UPDATE-V1\n{build}\n{version}\n{download_url}\n{sha256-lowercase}\n`. The public key is pinned in `desktop_windows/desktop-update-signing-public.pem`; the private key is never installed on production servers.

From Desktop 3.8.0 onward the user does not manually download or unpack update archives. The **«Обновить PORTAL»** button first asks the PORTAL server for a rollout manifest; if that endpoint is not configured, it falls back to the official public GitHub Releases feed for this repository. Both sources must provide an RSA signature that validates against the pinned key before the package URL is used. The client still compares the downloaded ZIP's SHA-256 against the signed manifest, follows redirects only from the official GitHub release URL to GitHub's HTTPS content hosts, enforces package and expanded-size limits, extracts only safe archive paths into a new versioned directory, updates shortcuts, launches the new `PORTAL.Desktop.exe`, and closes the old process. Previous version directories remain available for rollback.

Official Desktop releases are published only by manually dispatching `.github/workflows/windows-desktop.yml` from the current reviewed `main`. The workflow fails closed unless its dispatch SHA is still the exact current `origin/main`, builds and tests the package, signs `portal-desktop-update.json` with the GitHub Actions secret `PORTAL_DESKTOP_UPDATE_SIGNING_PRIVATE_KEY`, and then creates the immutable `portal-desktop-vX.Y.Z` release/tag targeted at that exact SHA. A pre-existing tag or release causes publication to fail rather than overwrite it. The private signing key is never published or installed on production; the client verifies the manifest with the pinned public key in `desktop_windows/desktop-update-signing-public.pem`. Copy the published manifest's `signature` value into protected production configuration as `PORTAL_DESKTOP_UPDATE_SIGNATURE` alongside that release's version/build/URL/hash when the server-side update channel is enabled. Plain HTTP is limited to loopback staging; production update URLs require HTTPS.

## Release candidate 5.12.10 / build 72

Before publishing `portal-desktop-v5.12.10`, build a fresh CI artifact from the current reviewed `main` source and perform an install-over smoke on Ernest-com over 5.12.9. Confirm the packaged executable reports FileVersion `5.12.10.72`, starts normally with the existing per-user profile, keeps the configured `https://reserve-api.vart-portal.ru` origin, and reaches PORTAL without resetting user data. Only after that physical Windows smoke passes may the manual release workflow be dispatched from the exact current main; the workflow signs the update manifest and creates the release/tag itself.
