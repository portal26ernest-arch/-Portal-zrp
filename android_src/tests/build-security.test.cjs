const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const gradle = fs.readFileSync(path.join(root, 'app', 'build.gradle'), 'utf8');
const gradleProperties = fs.readFileSync(path.join(root, 'gradle.properties'), 'utf8');
const manifest = fs.readFileSync(path.join(root, 'app', 'src', 'main', 'AndroidManifest.xml'), 'utf8');
const releaseWorkflow = fs.readFileSync(path.join(root, '..', '.github', 'workflows', 'android-release.yml'), 'utf8');
const desktopReleaseWorkflow = fs.readFileSync(path.join(root, '..', '.github', 'workflows', 'windows-desktop.yml'), 'utf8');
const stagingWorkflow = fs.readFileSync(path.join(root, '..', '.github', 'workflows', 'android-build.yml'), 'utf8');
const releaseProperties = fs.readFileSync(path.join(root, 'release.properties'), 'utf8');
const serverDiscovery = fs.readFileSync(path.join(root, '..', 'portal-server.json'), 'utf8');

function must(condition, message) {
  if (!condition) throw new Error(message);
}

must(manifest.includes('android:usesCleartextTraffic="${usesCleartextTraffic}"'),
  'Manifest must use a per-build cleartext placeholder');
must(manifest.includes('android:allowBackup="false"'),
  'Production client data backup must be disabled');
must(/^android\.useAndroidX=true$/m.test(gradleProperties),
  'AndroidX must be enabled for AndroidX runtime dependencies');
must(/release\s*\{[\s\S]*?usesCleartextTraffic:\s*"false"/m.test(gradle),
  'Release build must disable cleartext HTTP');
must(/staging\s*\{[\s\S]*?applicationIdSuffix\s+"\.staging"/m.test(gradle),
  'Staging build must use a separate application id');
must(/staging\s*\{[\s\S]*?usesCleartextTraffic:\s*"true"/m.test(gradle),
  'Staging build must allow the local HTTP tunnel');
must(/staging\s*\{[\s\S]*?signingConfig\s+signingConfigs\.debug/m.test(gradle),
  'Staging build must be explicitly signed for installability');
must(gradle.includes("PORTAL_ANDROID_KEYSTORE") && gradle.includes("portalRelease"),
  'Release signing must be sourced from environment secrets');
must(gradle.includes("PORTAL_ANDROID_KEYSTORE_TYPE") && gradle.includes("storeType releaseKeystoreType"),
  'Release signing must use an explicit keystore type');
must(releaseWorkflow.includes('PORTAL_ANDROID_KEYSTORE_TYPE: PKCS12'),
  'Signed release must use PKCS12 keystore format');
must(releaseWorkflow.includes('portal-release.p12'),
  'Signed release must materialize the keystore as PKCS12');
must(releaseWorkflow.includes('PORTAL_ANDROID_CERT_SHA256'),
  'Signed release must pin the expected certificate SHA-256');
must(releaseWorkflow.includes('grep -q "Android Debug"'),
  'Signed release must reject Android Debug certificates');
must(releaseWorkflow.includes('test "$CHANNEL" = "release"'),
  'Signed release must require release channel metadata');
must(releaseWorkflow.includes('test "$UPDATE_MANIFEST_URL" = "$EXPECTED_MANIFEST_URL"'),
  'Signed release must require the exact stable HTTPS update manifest URL');
must(releaseWorkflow.includes('test "$VERSION_CODE" -gt 2'),
  'Signed release must be newer than the installed b002 versionCode');
must(releaseWorkflow.includes('contents: write'),
  'Signed release needs narrowly scoped contents write permission to publish GitHub Release assets');
must(releaseWorkflow.includes('releases/latest/download/portal-update.json'),
  'Signed release must pin the stable public update manifest URL');
must(releaseProperties.includes('serverDiscoveryUrl=https://raw.githubusercontent.com/portal26ernest-arch/-Portal-zrp/main/portal-server.json'),
  'Release must pin the stable GitHub server-discovery document');
must(gradle.includes("'SERVER_DISCOVERY_URL'"),
  'Android build must embed the server-discovery URL');
const discovery = JSON.parse(serverDiscovery);
must(discovery.schemaVersion === 1 && Number.isInteger(discovery.revision) && discovery.revision > 0 && /^https:\/\//.test(discovery.apiUrl),
  'Server-discovery document must have a versioned HTTPS endpoint');
must(releaseWorkflow.includes('build_update_manifest.py'),
  'Signed release must generate a machine-readable update manifest');
must(releaseWorkflow.includes('Require manual release from current reviewed main') &&
     releaseWorkflow.includes('test "$GITHUB_EVENT_NAME" = "workflow_dispatch"') &&
     releaseWorkflow.includes('git rev-parse refs/remotes/origin/main') &&
     releaseWorkflow.includes('fetch-depth: 0') &&
     !releaseWorkflow.includes('portal-android-v*"'),
  'Android release publishing must be manual-only from the current reviewed main commit');
must(releaseWorkflow.indexOf('Require manual release from current reviewed main') <
     releaseWorkflow.indexOf('Validate release inputs'),
  'Android release provenance must be checked before signing secrets are exposed');
must(desktopReleaseWorkflow.includes('Require manual release from current reviewed main') &&
     desktopReleaseWorkflow.includes("if: github.event_name == 'workflow_dispatch'") &&
     desktopReleaseWorkflow.includes('git rev-parse refs/remotes/origin/main') &&
     desktopReleaseWorkflow.includes('fetch-depth: 0') &&
     !desktopReleaseWorkflow.includes('tags: ["portal-desktop-v*"]'),
  'Desktop release publishing must be manual-only from the current reviewed main commit');
must(releaseWorkflow.includes('Release tag already exists: $TAG') &&
     desktopReleaseWorkflow.includes('Release tag already exists: $TAG') &&
     !releaseWorkflow.includes('--clobber'),
  'Release workflows must fail closed instead of replacing existing release tags or assets');
must(desktopReleaseWorkflow.includes('PORTAL_DESKTOP_UPDATE_SIGNING_PRIVATE_KEY') &&
     desktopReleaseWorkflow.includes('portal-desktop-update.json'),
  'Desktop release must create and publish a signed update manifest');
must(releaseWorkflow.includes('gh release create') && releaseWorkflow.includes('portal-update.json'),
  'Signed release must publish APK, checksum and manifest through GitHub Releases');
must(!stagingWorkflow.includes('trycloudflare.com'),
  'Staging workflow must never commit an expiring Quick Tunnel URL');
must(stagingWorkflow.includes('staging_api_url') && stagingWorkflow.includes('vars.PORTAL_STAGING_API_URL'),
  'Staging workflow must accept a runtime/Actions-variable HTTPS endpoint');
must(stagingWorkflow.includes("'https://portal.invalid'"),
  'Staging workflow must fail disconnected instead of silently using a stale endpoint');
must(gradle.includes("graph.allTasks.any") &&
     gradle.includes("host.endsWith('.sslip.io')") &&
     gradle.includes("host.endsWith('.trycloudflare.com')") &&
     !gradle.includes("releaseTemporarySslipHost") &&
     !gradle.includes("temporarySslipAllowed"),
  'Release task must reject all temporary sslip/trycloudflare endpoints without an exception');
must(releaseWorkflow.includes("https://api.vart-portal.ru") &&
     releaseWorkflow.includes('test "$API_HOST" = "api.vart-portal.ru"') &&
     !releaseWorkflow.includes('PORTAL_RELEASE_TEMPORARY_SSLIP_HOST'),
  'Production Android release must be pinned to the permanent api.vart-portal.ru host');
console.log('Android build security checks: OK');
