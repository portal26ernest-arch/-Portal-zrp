const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const gradle = fs.readFileSync(path.join(root, 'app', 'build.gradle'), 'utf8');
const manifest = fs.readFileSync(path.join(root, 'app', 'src', 'main', 'AndroidManifest.xml'), 'utf8');
const releaseWorkflow = fs.readFileSync(path.join(root, '..', '.github', 'workflows', 'android-release.yml'), 'utf8');

function must(condition, message) {
  if (!condition) throw new Error(message);
}

must(manifest.includes('android:usesCleartextTraffic="${usesCleartextTraffic}"'),
  'Manifest must use a per-build cleartext placeholder');
must(manifest.includes('android:allowBackup="false"'),
  'Production client data backup must be disabled');
must(/release\s*\{[\s\S]*?usesCleartextTraffic:\s*"false"/m.test(gradle),
  'Release build must disable cleartext HTTP');
must(/staging\s*\{[\s\S]*?applicationIdSuffix\s+"\.staging"/m.test(gradle),
  'Staging build must use a separate application id');
must(/staging\s*\{[\s\S]*?usesCleartextTraffic:\s*"true"/m.test(gradle),
  'Staging build must allow the local HTTP tunnel');
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
must(releaseWorkflow.includes('build_update_manifest.py'),
  'Signed release must generate a machine-readable update manifest');
must(releaseWorkflow.includes('gh release create') && releaseWorkflow.includes('portal-update.json'),
  'Signed release must publish APK, checksum and manifest through GitHub Releases');
console.log('Android build security checks: OK');
