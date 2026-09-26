const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const gradle = fs.readFileSync(path.join(root, 'app', 'build.gradle'), 'utf8');
const manifest = fs.readFileSync(path.join(root, 'app', 'src', 'main', 'AndroidManifest.xml'), 'utf8');

function must(condition, message) {
  if (!condition) throw new Error(message);
}

must(manifest.includes('android:usesCleartextTraffic="${usesCleartextTraffic}"'),
  'Manifest must use a per-build cleartext placeholder');
must(/release\s*\{[\s\S]*?usesCleartextTraffic:\s*"false"/m.test(gradle),
  'Release build must disable cleartext HTTP');
must(/staging\s*\{[\s\S]*?applicationIdSuffix\s+"\.staging"/m.test(gradle),
  'Staging build must use a separate application id');
must(/staging\s*\{[\s\S]*?usesCleartextTraffic:\s*"true"/m.test(gradle),
  'Staging build must allow the local HTTP tunnel');
console.log('Android build security checks: OK');
