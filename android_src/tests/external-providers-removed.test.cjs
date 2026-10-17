'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const repo=path.resolve(__dirname,'../..');
const read=p=>fs.readFileSync(path.join(repo,p),'utf8');
const root='android_src/app/src/main/assets/';
const runtime={
  core:read(root+'core.js'),
  app:read(root+'app.js'),
  index:read(root+'index.html'),
  notifications:read(root+'notification_centers.js'),
  webAdapter:read(root+'web_adapter.js'),
  android:read('android_src/app/src/main/java/ru/portal/app/MainActivity.java'),
  androidManifest:read('android_src/app/src/main/AndroidManifest.xml'),
  desktop:read('desktop_windows/MainWindow.xaml.cs'),
  ios:read('ios_src/PortalIOS/PortalNativeBridge.swift'),
  api:read('server/portal_app_server.py'),
  service:read('server/production_service.py'),
  repository:read('server/production_repository.py')
};
test('retired external providers have no active app/bridge/router entry points',()=>{
  const unwanted=/openMessengerWindow|clearMessengerSession|MessengerActivity|MessengerWindow|messenger-relay-ticket|portal-messenger:\/\/|web\.telegram\.org|web\.max\.ru|screens\.messenger\s*=|id:'messenger'|data-action="openMessenger"/i;
  for(const [name,code] of Object.entries(runtime))
    assert.doesNotMatch(code,unwanted,name);
  assert.doesNotMatch(runtime.service,/action\s*==\s*['"]messenger['"]/);
  assert.doesNotMatch(runtime.repository,/['"]messenger_(accounts|conversations|messages)['"]/);
  assert.doesNotMatch(runtime.api,/action\s+in\s+\{'messenger'/);
  assert.doesNotMatch(runtime.notifications,/centerLabels[^;]*MESSENGER/);
});
test('legacy provider components and relay executables stay removed',()=>{
  for(const filename of [
    root+'messenger_notifications.js',
    'android_src/app/src/main/java/ru/portal/app/MessengerActivity.java',
    'android_src/app/src/main/java/ru/portal/app/TelegramWssLocalProxy.java',
    'desktop_windows/MessengerWindow.xaml.cs',
    'desktop_windows/MessengerWssLocalProxy.cs',
    'ios_src/PortalIOS/MessengerViewController.swift',
    'server/messenger_relay.py',
    'server/messenger_relay_ws.py',
    'server/messenger_adapters.py'
  ])assert.ok(!fs.existsSync(path.join(repo,filename)),filename);
});
test('PORTAL employee chat, staff pages, and safe legacy migration remain intact',()=>{
  assert.match(runtime.core,/id:'teamChat'/);
  assert.match(runtime.notifications,/center==='TASKS'\|\|center\.center==='ORGANIZER'/);
  assert.match(runtime.api,/employee_id/);
  assert.ok(fs.existsSync(path.join(repo,'tools/ssh_banner_first_relay.py')),'keep independent SSH staging helper');
  const cleanup=read('ios_src/PortalIOS/RetiredProviderDataCleanup.swift');
  const app=read('ios_src/PortalIOS/PortalIOSApp.swift');
  assert.match(app,/RetiredProviderDataCleanup\.performOnce\(\)/);
  assert.match(cleanup,/WKWebsiteDataStore\(forIdentifier: identifier\)/);
  assert.match(cleanup,/host\.hasSuffix\("\.telegram\.org"\)/);
  assert.match(cleanup,/host\.hasSuffix\("\.max\.ru"\)/);
  assert.doesNotMatch(cleanup,/WKWebsiteDataStore\.default\(\)\.removeData\(ofTypes: types, modifiedSince: \.distantPast\)/);
});
