const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');

const source=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/screens.js'),'utf8');
assert.match(source,/Создать нового сотрудника/);
assert.match(source,/Выдать доступ существующему/);
assert.match(source,/existingEmployeeWrap" hidden/);
assert.match(source,/body\.create_employee=!existing/);
assert.match(source,/if\(existing&&!employee\)throw new Error\('Выберите существующего сотрудника'\)/);
console.log('Employee creation mode checks: OK');
