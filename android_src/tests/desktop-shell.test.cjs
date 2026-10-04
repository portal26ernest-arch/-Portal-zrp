const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const repo=path.join(__dirname,'../..');
const xaml=fs.readFileSync(path.join(repo,'desktop_windows/MainWindow.xaml'),'utf8');
const code=fs.readFileSync(path.join(repo,'desktop_windows/MainWindow.xaml.cs'),'utf8');
const app=fs.readFileSync(path.join(repo,'android_src/app/src/main/assets/app.js'),'utf8');
const cache=fs.readFileSync(path.join(repo,'desktop_windows/DesktopCacheBridge.cs'),'utf8');
const windowsWorkflow=fs.readFileSync(path.join(repo,'.github/workflows/windows-desktop.yml'),'utf8');
const signature=fs.readFileSync(path.join(repo,'desktop_windows/DesktopUpdateSignature.cs'),'utf8');
assert.match(xaml,/x:Name="HomeButton"[^>]+Click="Home_Click"/);
assert.match(xaml,/PreviewMouseWheel="Browser_PreviewMouseWheel"/);
assert.match(code,/ExecuteScriptAsync\("Boolean\(window\.portalBack && window\.portalBack\(\)\)"\)/);
assert.match(code,/ExecuteScriptAsync\("Boolean\(window\.portalHome && window\.portalHome\(\)\)"\)/);
assert.match(code,/window\.scrollBy\(\{\{top:/);
assert.match(code,/ProcessFailed[\s\S]+_webRecoveryPending[\s\S]+Browser\.Reload\(\)/);
assert.match(app,/window\.portalBack=/);
assert.match(app,/S\.history\.push\(S\.page\)/);
assert.match(app,/window\.portalHome=/);
assert.match(app,/autoCheckUpdates\(\)/);
assert.match(xaml,/Content="Обновить PORTAL"[^>]+Click="CheckUpdate_Click"/);
assert.match(code,/private const int CurrentBuild = 45/);
assert.match(code,/WebViewCompatibilityArguments = "--disable-gpu --disable-gpu-compositing"/);
assert.match(code,/AdditionalBrowserArguments = WebViewCompatibilityArguments/);
assert.match(code,/catch \(HttpRequestException\)[\s\S]+LoadGithubUpdateManifestAsync\(\)/);
assert.match(code,/catch \(TaskCanceledException\)[\s\S]+LoadGithubUpdateManifestAsync\(\)/);
assert.match(code,/if \(_serverOrigin is not null\)[\s\S]+githubManifest = await LoadGithubUpdateManifestAsync\(\)/);
assert.doesNotMatch(code,/Сначала подключитесь к серверу PORTAL/);
assert.match(code,/PORTAL-Desktop\/4\.5\.0/);
assert.match(code,/DownloadAndInstallUpdate\(manifest, downloadUri\)/);
assert.match(code,/PropertyNamingPolicy = JsonNamingPolicy\.SnakeCaseLower/);
assert.match(code,/api\.github\.com\/repos\/\{GithubRepository\}\/releases\?per_page=50/);
assert.match(code,/portal-desktop-v\(\\d\+\)\\\.\(\\d\+\)\\\.0/);
assert.match(code,/AllowedUpdateRedirect\(initial, next\)/);
assert.match(code,/\.githubusercontent\.com/);
assert.match(code,/ZipFile\.OpenRead\(packagePath\)/);
assert.match(code,/SHA-256 пакета обновления не совпадает/);
assert.match(code,/DesktopUpdateSignature\.Verify\(manifest\)/);
assert.match(code,/portal-desktop-update\.json/);
assert.match(signature,/PORTAL-DESKTOP-UPDATE-V1/);
assert.match(signature,/RSASignaturePadding\.Pkcs1/);
assert.match(signature,/rsa\.VerifyData/);
assert.match(signature,/Portal\.Desktop\.desktop-update-signing-public\.pem/);
assert.match(fs.readFileSync(path.join(repo,'desktop_windows/Portal.Desktop.csproj'),'utf8'),/EmbeddedResource Include="desktop-update-signing-public\.pem"/);
assert.match(windowsWorkflow,/PORTAL_DESKTOP_UPDATE_SIGNING_PRIVATE_KEY/);
assert.match(windowsWorkflow,/openssl dgst -sha256 -sign/);
assert.match(windowsWorkflow,/portal-desktop-update\.json/);
assert.match(windowsWorkflow,/test -n "\$PORTAL_DESKTOP_UPDATE_SIGNING_PRIVATE_KEY"/);
assert.match(windowsWorkflow,/cmp "\$derived_public" "\$pinned_public"[\s\S]+openssl dgst -sha256 -verify "\$pinned_public" -signature "\$signature" "\$payload"/);
assert.match(code,/githubManifest\.Build > serverManifest\.Build/);
assert.match(code,/portal-desktop-43-style/);
assert.match(code,/portalDesktop43Patched/);
assert.doesNotMatch(code,/ProbePortalWebAsync/);
assert.match(code,/options\.IsInPrivateModeEnabled = false/);
assert.match(code,/Settings\.IsPasswordAutosaveEnabled = true/);
assert.doesNotMatch(code,/Settings\.IsPasswordAutosaveEnabled = false/);
assert.match(xaml,/встроенный менеджер паролей WebView2/);
assert.match(code,/Browser\.Source = new Uri\(origin \+ "\/web\/"\)/);
assert.match(code,/_pendingPersistOrigin = persist \? origin : null/);
assert.match(code,/AddHostObjectToScript\("portalDesktopCache", _cacheBridge\)/);
assert.match(code,/_cacheBridge\?\.ClearAll\(\)/);
assert.match(code,/Profile\.ClearBrowsingDataAsync\(\)/);
assert.match(cache,/DataProtectionScope\.CurrentUser/);
assert.match(cache,/ProtectedData\.Protect/);
assert.match(cache,/ProtectedData\.Unprotect/);
assert.match(cache,/CompanyDirectory\(string companyId\)/);
assert.match(cache,/long\.TryParse\(companyId/);
assert.match(code,/\['Работа',[\s\S]+\['Управление',[\s\S]+\['Учёт и финансы',[\s\S]+\['Аналитика',[\s\S]+\['Система'/);
assert.match(code,/UpdateDesktopShortcuts\(executable, target, version\)/);
assert.match(code,/Process\.Start\(new ProcessStartInfo\(executable\)/);
assert.match(windowsWorkflow,/Require signed release tag at current reviewed main commit[\s\S]+gpg\.ssh\.allowedSignersFile ops\/release-tag-allowed-signers[\s\S]+git verify-tag \$env:GITHUB_REF_NAME[\s\S]+tagCommit -ne \$eventCommit[\s\S]+eventCommit -ne \$mainCommit/);
assert.ok(windowsWorkflow.indexOf('Require signed release tag at current reviewed main commit') <
  windowsWorkflow.indexOf('Publish self-contained Windows client'),
  'Desktop release provenance must be checked before building a tag-triggered artifact');
assert.ok(windowsWorkflow.indexOf('Create signed Desktop update manifest') <
  windowsWorkflow.indexOf('gh release create'),
  'Desktop release must sign update metadata before publishing it');
assert.match(windowsWorkflow,/Recheck release tag before signing and publishing[\s\S]+refs\/tags\/\$\{GITHUB_REF_NAME\}:refs\/tags\/\$\{GITHUB_REF_NAME\}[\s\S]+GITHUB_SHA/);
assert.match(windowsWorkflow,/git verify-tag "\$GITHUB_REF_NAME"/);
assert.ok(windowsWorkflow.indexOf('Recheck release tag before signing and publishing') <
  windowsWorkflow.indexOf('Create signed Desktop update manifest'),
  'Desktop release must revalidate tag provenance before the private key is exposed');
assert.ok(windowsWorkflow.indexOf('Validate release tag version before signing') <
  windowsWorkflow.indexOf('Create signed Desktop update manifest'),
  'Desktop release must validate the tag version before exposing the private key');
console.log('Desktop shell navigation, branding and self-update checks: OK');
