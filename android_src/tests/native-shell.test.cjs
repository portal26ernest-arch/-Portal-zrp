const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

const main=fs.readFileSync(path.join(__dirname,'../app/src/main/java/ru/portal/app/MainActivity.java'),'utf8');
assert.match(main,/SYSTEM_UI_FLAG_IMMERSIVE_STICKY/);
assert.match(main,/SYSTEM_UI_FLAG_HIDE_NAVIGATION/);
assert.match(main,/SYSTEM_UI_FLAG_FULLSCREEN/);
assert.match(main,/onWindowFocusChanged/);
assert.doesNotMatch(main,/api\.telegram\.org|BOT_TOKEN|OWNER_TELEGRAM_ID/);
console.log('Native shell checks: OK');
