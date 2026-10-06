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
assert.match(app,/openMessengerWindow\?\.\(p,relay\)/);
assert.match(app,/provider:'telegram',enabled:false,required:true/);
assert.match(app,/if\(p==='telegram'&&!preActivation\)\{toast\(/);
assert.match(app,/preActivation=ticket\.enabled===false&&ticket\.required===false/);

// Android uses one isolated process profile and identity-free CLEAR action.
assert.match(manifest,/\.MessengerActivity[\s\S]*android:process=":messenger"[\s\S]*android:launchMode="singleTask"/);
assert.ok(android.indexOf('WebView.setDataDirectorySuffix("portal_messenger")') < android.indexOf('new WebView(this)'));
assert.match(android,/ACTION_CLEAR_SESSION[\s\S]*clearProviderData\(/);
assert.match(android,/removeAllCookies[\s\S]*WebStorage\.getInstance\(\)\.deleteAllData\(\)/);
assert.match(android,/clearingSession[\s\S]*pendingProvider[\s\S]*clearProviderData/);
assert.match(android,/if \(clearingSession\)[\s\S]*pendingProvider = requestedProvider/);
assert.doesNotMatch(android,/identityKey|company_id|user_id|SHA-256|getStringExtra\("company"|getStringExtra\("user"/);
assert.match(android,/private boolean relayRequired = true/);
assert.match(android,/relayRequired = true;[\s\S]*if \(raw == null \|\| raw\.isBlank\(\)\) return/);
assert.match(android,/Instant\.parse\(data\.getString\("expires_at"\)\)/);
assert.doesNotMatch(android,/relayTried|directNetworkErrors/);
const relayListener=android.indexOf('setProxyOverride(config');
const telegramLoad=android.indexOf('loadCurrent();',relayListener);
assert.ok(relayListener>=0&&telegramLoad>relayListener,'Telegram must load only after the proxy override listener');
const clearListener=android.indexOf('clearProxyOverride(');
assert.ok(clearListener>=0&&android.indexOf('loadCurrent();',clearListener)>clearListener,'MAX must load only after proxy clear listener');
assert.match(androidBridge,/openMessengerWindow\(String provider, String relayJson\)/);
assert.match(androidBridge,/clearMessengerSession\(\)/);
assert.doesNotMatch(androidBridge,/setMessengerIdentity|validMessengerIdentity/);
assert.match(adapter,/openMessengerWindow: \(provider,relayJson=''\) =>/);
assert.match(adapter,/clearMessengerSession: \(\) =>/);
assert.doesNotMatch(adapter,/setMessengerIdentity|openMessengerWindow: \(provider, company|clearMessengerSession: \(company/);

// Desktop uses distinct fixed provider profiles and never shares the Telegram proxy with MAX.
assert.match(desktop,/MessengerWebView2-Telegram/);
assert.match(desktop,/MessengerWebView2-Max/);
assert.match(desktop,/InitializeViewAsync\(MaxWebView2, MaxProfileName, null, false\)/);
assert.match(desktop,/InitializeViewAsync\(TelegramWebView2, TelegramProfileName,[\s\S]*--proxy-server=/);
assert.match(desktop,/if \(telegram\) view\.CoreWebView2\.BasicAuthenticationRequested/);
assert.match(desktop,/DateTimeOffset\.TryParse\(expires\.GetString\(\)[\s\S]*expiry <= DateTimeOffset\.UtcNow/);
assert.doesNotMatch(desktop,/proxy-bypass-list/);
assert.match(desktop,/InitializeViewAsync\(MaxWebView2, MaxProfileName, null, false\)/);
assert.match(desktopBridge,/custom\.Host\.Equals\("open"[\s\S]*query\["provider"\]/);
assert.match(desktopBridge,/custom\.Host\.Equals\("clear"[\s\S]*ClearMessengerSessionAsync\(\)/);
assert.match(desktopBridge,/OpenMessengerWindowAsync\(string provider = "telegram", string\? relayJson = null\)/);
assert.match(desktopBridge,/messengerClearTask = ClearMessengerSessionAsync\(\)/);
assert.match(desktopBridge,/OpenMessengerWindowAsync\(string provider = "telegram", string\? relayJson = null\)[\s\S]*await _messengerClearTask/);
assert.doesNotMatch(desktop+desktopBridge,/identityKey|company_id|user_id/);
assert.match(desktop,/ClearBrowsingDataAsync\(CoreWebView2BrowsingDataKinds\.AllProfile\)/);

// iOS uses two fixed provider stores and never mutates the PORTAL default store proxy.
assert.match(ios,/68C88C71-9F9B-4D43-9D85-514C0B9065E2/);
assert.match(ios,/7F1B82E8-7E0A-4B93-B10D-271CD988C09A/);
assert.match(ios,/WKWebsiteDataStore\(forIdentifier: identifier\)/);
assert.match(ios,/static func clear\(completion:[\s\S]*providerStore\("telegram"\)[\s\S]*providerStore\("max"\)/);
assert.doesNotMatch(ios,/browser\.configuration\.websiteDataStore\.proxyConfigurations/);
assert.match(ios,/proxy\.allowFailover = false/);
assert.match(ios,/proxy\.applyCredential\(username: ticket\.username, password: ticket\.password\)/);
assert.match(ios,/expiryDate > Date\(\)/);
assert.match(ios,/if providerData\.fixed, provider == "telegram"/);
assert.match(ios,/domain == "telegram\.org"[\s\S]*domain == "max\.ru"/);
assert.match(iosBridge,/messengerClearInProgress[\s\S]*pendingMessengerProvider/);
assert.doesNotMatch(ios,/identityKey|company: String|user: String/);
assert.match(ios,/targetFrame\?\.isMainFrame == false[\s\S]*isAllowedTopLevel/);
assert.match(iosBridge,/openMessengerWindow: \(provider, relayJson\)[\s\S]*\{provider:p, relay: p==='telegram'/);
assert.match(iosBridge,/clearMessengerSession: \(\) =>/);
assert.doesNotMatch(iosBridge,/setMessengerIdentity|company: company, user: user/);

for(const host of ['web.telegram.org','web.max.ru']) assert.ok(docs.includes(host));
assert.match(docs,/server\/messenger_adapters\.py` remains unconfigured/i);
assert.match(read('server/messenger_adapters.py'),/return \(configured or \{\}\)\.get\(provider\)/);
assert.match(read('server/test_production.py'),/messenger[\s\S]*role_token\('manager'\),status=403\)[\s\S]*role_token\('director'\),status=403\)/);
console.log('MESSENGER SESSION ISOLATION OK: single profiles, identity-free native APIs, lifecycle clears, provider allowlists, unconfigured server adapters');
