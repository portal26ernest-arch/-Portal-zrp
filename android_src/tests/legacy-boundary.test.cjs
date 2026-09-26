const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

const root=path.resolve(__dirname,'../..');
const runtime=[
  'server/portal_app_server.py','server/portal_config.py','server/start_portal_app.sh',
  'server/production_repository.py','server/production_service.py',
  'android_src/app/src/main/java/ru/portal/app/MainActivity.java',
  'android_src/app/src/main/assets/app.js','android_src/app/src/main/assets/core.js',
  'android_src/app/src/main/assets/screens.js','android_src/app/src/main/assets/production.js'
];
const forbidden=/api\.telegram\.org|BOT_TOKEN|OWNER_TELEGRAM_ID|\/storage\/emulated\/0\/PORTAL-BOT|com\.termux|data\/data\/com\.termux/i;
for(const rel of runtime){
  const source=fs.readFileSync(path.join(root,rel),'utf8');
  assert.doesNotMatch(source,forbidden,rel+' contains retired phone/Telegram runtime dependency');
}
console.log('Legacy runtime boundary checks: OK');
