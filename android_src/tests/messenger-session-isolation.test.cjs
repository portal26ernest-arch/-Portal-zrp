const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.join(__dirname,'../..');
const read=file=>fs.readFileSync(path.join(root,file),'utf8');
const app=read('android_src/app/src/main/assets/app.js');
const adapter=read('android_src/app/src/main/assets/web_adapter.js');
const android=read('android_src/app/src/main/java/ru/portal/app/MessengerActivity.java');
const androidBridge=read('android_src/app/src/main/java/ru/portal/app/MainActivity.java');
const manifest=read('android_src/app/src/main/AndroidManifest.xml');
const desktop=read('desktop_windows/MessengerWindow.xaml.cs');
const desktopBridge=read('desktop_windows/MainWindow.xaml.cs');
const ios=read('ios_src/PortalIOS/MessengerViewController.swift');
const iosBridge=read('ios_src/PortalIOS/PortalNativeBridge.swift');
const docs=read('docs/NOTIFICATION_CENTERS_AND_MESSENGER.md');

// JS identity is never accepted at any provider profile boundary.
assert.doesNotMatch(app,/messengerIdentity|setMessengerIdentity|company,identity|identity\.company/);
assert.match(app,/async function acceptLogin\(result\)\{try\{window\.PortalNative\?\.clearMessengerSession\?\.\(\)/);
assert.match(app,/function logout\([\s\S]*clearMessengerSession\?\.\(\)[\s\S]*S\.me=null/);
assert.match(app,/httpStatus===401[^\n]*logout\(false,true\)/);
assert.match(app,/DOMContentLoaded[\s\S]*await enterApp\(\)/);
assert.match(app,/DOMContentLoaded[\s\S]*catch\{try\{window\.PortalNative\?\.clearMessengerSession\?\.\(\)/);
assert.match(app,/openMessengerWindow\?\.\(p\)/);

// Android uses one isolated process profile and identity-free CLEAR action.
assert.match(manifest,/\.MessengerActivity[\s\S]*android:process=":messenger"[\s\S]*android:launchMode="singleTask"/);
assert.ok(android.indexOf('WebView.setDataDirectorySuffix("portal_messenger")') < android.indexOf('new WebView(this)'));
assert.match(android,/ACTION_CLEAR_SESSION[\s\S]*clearProviderData\(/);
assert.match(android,/removeAllCookies[\s\S]*WebStorage\.getInstance\(\)\.deleteAllData\(\)/);
assert.match(android,/clearingSession[\s\S]*pendingProvider[\s\S]*clearProviderData/);
assert.match(android,/if \(clearingSession\)[\s\S]*pendingProvider = requestedProvider/);
assert.doesNotMatch(android,/identityKey|company_id|user_id|SHA-256|getStringExtra\("company"|getStringExtra\("user"/);
assert.match(androidBridge,/openMessengerWindow\(String provider\)/);
assert.match(androidBridge,/clearMessengerSession\(\)/);
assert.doesNotMatch(androidBridge,/setMessengerIdentity|validMessengerIdentity/);
assert.match(adapter,/openMessengerWindow: provider =>/);
assert.match(adapter,/clearMessengerSession: \(\) =>/);
assert.doesNotMatch(adapter,/setMessengerIdentity|openMessengerWindow: \(provider, company|clearMessengerSession: \(company/);

// Desktop has exactly one profile directory; custom scheme handlers consume provider only.
assert.match(desktop,/Path\.Combine\(_settingsDir, "MessengerWebView2"\)/);
assert.match(desktopBridge,/custom\.Host\.Equals\("open"[\s\S]*query\["provider"\]/);
assert.match(desktopBridge,/custom\.Host\.Equals\("clear"[\s\S]*ClearMessengerSessionAsync\(\)/);
assert.match(desktopBridge,/OpenMessengerWindowAsync\(string provider\)/);
assert.match(desktopBridge,/messengerClearTask = ClearMessengerSessionAsync\(\)/);
assert.match(desktopBridge,/OpenMessengerWindowAsync\(string provider\)[\s\S]*await _messengerClearTask/);
assert.doesNotMatch(desktop+desktopBridge,/identityKey|company_id|user_id|forIdentifier/);
assert.match(desktop,/ClearBrowsingDataAsync\(CoreWebView2BrowsingDataKinds\.AllProfile\)/);

// iOS uses one default provider store, clearing Telegram/MAX data without PORTAL website data.
assert.match(ios,/config\.websiteDataStore = \.default\(\)/);
assert.match(ios,/static func clear\(completion:[\s\S]*clearProviderData\(in: \.default\(\)/);
assert.match(ios,/domain == "telegram\.org"[\s\S]*domain == "max\.ru"/);
assert.match(iosBridge,/messengerClearInProgress[\s\S]*pendingMessengerProvider/);
assert.doesNotMatch(ios,/forIdentifier|identityKey|company: String|user: String/);
assert.match(ios,/targetFrame\?\.isMainFrame == false[\s\S]*isAllowedTopLevel/);
assert.match(iosBridge,/openMessengerWindow: provider[\s\S]*\{provider:p\}/);
assert.match(iosBridge,/clearMessengerSession: \(\) =>/);
assert.doesNotMatch(iosBridge,/setMessengerIdentity|company: company, user: user/);

for(const host of ['web.telegram.org','web.max.ru']) assert.ok(docs.includes(host));
assert.match(docs,/server\/messenger_adapters\.py` remains unconfigured/i);
assert.match(read('server/messenger_adapters.py'),/return \(configured or \{\}\)\.get\(provider\)/);
assert.match(read('server/test_production.py'),/messenger[\s\S]*role_token\('manager'\),status=403\)[\s\S]*role_token\('director'\),status=403\)/);
console.log('MESSENGER SESSION ISOLATION OK: single profiles, identity-free native APIs, lifecycle clears, provider allowlists, unconfigured server adapters');
