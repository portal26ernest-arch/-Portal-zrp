const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

const root=path.resolve(__dirname,'..');
const main=fs.readFileSync(path.join(root,'app/src/main/java/ru/portal/app/MainActivity.java'),'utf8');
const ui=fs.readFileSync(path.join(root,'app/src/main/assets/production.js'),'utf8');

assert.match(main,/onShowFileChooser/);
assert.match(main,/FileChooserParams\.parseResult/);
assert.match(main,/image\/jpeg/);
assert.match(main,/application\/pdf/);
assert.match(main,/text\/plain/);
assert.match(main,/\/api\/v3\/chat-file/);
assert.match(main,/\/api\/v3\/document-file/);
assert.match(ui,/id="chatFile"/);
assert.match(ui,/chatAttachment\(/);
assert.match(ui,/saveChatAttachment/);
assert.match(ui,/document-file\?id=/);
assert.match(ui,/saveBase64FileAsync/);
console.log('Documents/chat Android checks: OK');
