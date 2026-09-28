# PORTAL — Documents + Excel, Part 2

Дата: 29.09.2026  
Ветка: `codex-documents-excel-part2`  
База: `56095d3` (Part 1 Documents/Excel + динамическое приветствие)

## Статус

Part 2 реализован и локально проверен. Production/VPS не развёртывались и не изменялись. Production DB, телефонная SQLite, тарифы, зарплатная история и закрытые payroll snapshots не затрагивались.

## Реализовано

- Раздел **«Документы»** переведён на живой Part 1 API: список документов выбранной компании, поиск, фильтры по типу/категории/датам/статусу, пагинация, размер, дата, revision и визуальное состояние архива.
- Ready-документы можно сохранить через существующий Android native bridge. Архивные документы не предлагают скачивание. Архивирование доступно только при `documents.manage`, требует подтверждения и сохраняет историю.
- Сохранена существующая возможность создать расчётный документ через `newPayrollDocument`.
- Раздел **«Импорт Excel»** переведён из Preview в production UI.
- Поддержаны blank и prefilled шаблоны PORTAL, сведения о версии и четырёх листах: **Компания, Сотрудники, Клиенты, Операции_Тарифы**.
- Выбор XLSX проверяет расширение, ненулевой размер и лимит 10 МиБ. Excel на Android не исполняется и не разбирается формулами — проверку делает сервер.
- Preview показывает `new / update / unchanged / conflict / invalid`, безопасные ошибки и изменения. При conflict/invalid применение недоступно.
- Apply выполняется только после отдельного подтверждения. UI защищён от двойного запуска.
- При потерянном/ошибочном ответе apply клиент запрашивает terminal result по `import_id`: уже применённый импорт не создаётся повторно, failed-импорт показывается как полностью отменённый.
- Stale/expired preview предлагает выполнить новую проверку файла.
- `preview_token`, `import_id` и выбранный файл существуют только в runtime state и не пишутся в localStorage/preferences.
- HTTP error теперь сохраняет `status` и безопасное `data`, чтобы UI корректно различал terminal 409/400 без ослабления серверной проверки.
- Platform Owner может открыть импорт только после явного выбора компании и при полном наборе capabilities. Директор/администратор также должны иметь весь обязательный набор прав.
- В native saver добавлен MIME `application/json` для скачивания безопасного `import_result`. Ручная загрузка JSON не добавлялась.

## API

### Документы
- `GET /api/v3/documents`
- `GET /api/v3/document-file?id=…`
- `POST /api/v3/document-archive`

Используются `q`, `document_type`, `category`, `date_from`, `date_to`, `status`, `page`, `limit`.

### Excel
- `GET /api/v3/document-template-info`
- `GET /api/v3/document-template-blank`
- `GET /api/v3/document-template`
- `POST /api/v3/excel-import-preview`
- `POST /api/v3/excel-import-apply`
- `GET /api/v3/excel-import-result?id=…`
- `GET /api/v3/document-file?id=…` для result document

## Права

Импорт требует одновременно:
`imports.manage`, `users.manage`, `clients.manage`, `rates.employee`, `rates.client`, `company.settings`, `documents.manage`, `documents.read`.

Роль: директор/администратор своей компании либо Platform Owner с явно выбранной компанией. Сервер остаётся окончательным источником авторизации и tenant/client isolation.

## Сохранение файлов

Используется существующий `PortalNative.saveBase64FileAsync`:
- Android 10+ — MediaStore → `Downloads/PORTAL`;
- старые Android — app-specific Downloads;
- строгий filename/MIME/size validation;
- XLSX, PDF и JSON result;
- `file://` наружу не используется.

Системного Share Sheet bridge в текущем native shell нет. Небезопасный обход не добавлялся. Share Sheet/email через системный intent остаются отдельным native этапом.

## Проверки

| Проверка | Результат |
|---|---|
| Все Android/JS/contract/browser тесты: `node --test android_src/tests/*.test.cjs` с существующим Playwright из основной dev-копии | **23/23 passed, 0 failed** |
| Browser UI regression | **PASS**, включая Documents + Excel live flow |
| Documents + Excel live browser flow | **PASS**: download, archive, filter, blank template, preview, apply, double-submit guard, JSON result download, conflict block, failed rollback, stale preview |
| Part 1 серверные targeted tests: `test_documents_api test_excel_import test_excel_template test_portal_documents test_postgresql_documents_schema` | **38/38 OK** |
| Android Java compile: `:app:compileStagingJavaWithJavac` через локальные Gradle 8.9 / JDK 17 / Android SDK 35 | **BUILD SUCCESSFUL**, 16 tasks |
| JavaScript parse check | **PASS** внутри общего Node набора, включая `documents_excel.js` |
| Native shell checks | **PASS**, включая JSON MIME allowlist |
| `git diff --check` | **PASS** |

Live PostgreSQL Part 1 повторно не разворачивался в рамках Part 2, поскольку серверный код Part 1 здесь не изменялся; его отдельные live-PG проверки зафиксированы в `PORTAL_DOCUMENTS_EXCEL_PART1_REPORT.md`.

## Изменённые файлы

- `android_src/app/src/main/assets/documents_excel.js`
- `android_src/app/src/main/assets/index.html`
- `android_src/app/src/main/assets/core.js`
- `android_src/app/src/main/assets/app.js`
- `android_src/app/src/main/assets/ui.css`
- `android_src/app/src/main/java/ru/portal/app/MainActivity.java`
- `android_src/tests/documents-excel.test.cjs`
- `android_src/tests/native-shell.test.cjs`
- `android_src/tests/ui.test.cjs`
- `PORTAL_DOCUMENTS_EXCEL_PART2_TASK.md`
- `PORTAL_DOCUMENTS_EXCEL_PART2_REPORT.md`

## Не делалось

- production/VPS deploy;
- изменение production DB;
- изменение телефонной SQLite;
- изменение тарифов, зарплатных фактов и закрытых периодов;
- production APK / signing / version bump;
- Share Sheet/FileProvider;
- email SMTP/API;
- TalAnt/WMS/ТСД.

Поскольку APK в этой задаче не выпускался, номер версии не повышался. Следующая реально выпускаемая видимая сборка должна получить следующий согласованный номер.
