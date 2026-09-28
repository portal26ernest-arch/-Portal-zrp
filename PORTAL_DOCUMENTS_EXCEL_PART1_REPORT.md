# PORTAL — Documents + Excel, Part 1

Дата: 29.09.2026. Серверная часть задания завершена и проверена. Развёртывание на рабочем контуре не выполнялось.

## Ветка и коммиты

Рабочая копия: `C:\Users\darta\Documents\PORTAL-Android`.
Ветка: `codex-documents-excel-part1`.
Базовый HEAD: `e883faf4da5ba71e55bbabf9e46207f8d660506b`.

| № | Коммит | Содержание |
|---|---|---|
| 1 | `f743f02` | Add tenant Documents metadata storage and authorized API |
| 2 | `2b4a3b6` | Add canonical Russian Excel template and scoped prefill |
| 3 | `a5352ad` | Add read-only Excel import preview and conflict validation |
| 4 | `48ead2c` | Apply staged Excel imports atomically with immutable result documents |
| 5 | Коммит, содержащий этот отчёт | Verify Documents PostgreSQL isolation and record Part 1 completion |

Полные SHA: `git log --oneline e883faf4da5ba71e55bbabf9e46207f8d660506b..HEAD`. Коммиты локальные; push, PR и удалённый CI в этой задаче не выполнялись.

## Изменённые файлы

| Файлы | Назначение |
|---|---|
| `server/document_domain.py` | Documents model/API domain, permissions, filters, upload/download/archive, dedup, storage interface/local adapter |
| `server/documents_schema.py`, `server/production_migrations.py` | Явная SQLite-миграция v7, ссылки, tenant guards и immutable history |
| `server/documents_api.py`, `server/portal_app_server.py` | Маршруты, request limits, storage config, payroll compatibility, read-only preview |
| `server/excel_template.py`, `server/portal_documents.py` | Шаблон v1.0, company-scoped prefill, совместимый facade |
| `server/portal_excel_workbook.py` | Детерминированный ZIP и bounded OOXML parser |
| `server/excel_import.py`, `server/excel_apply.py` | Preview/diff/validation/HMAC, транзакции, retry, rollback, отчёт |
| `server/production_permissions.py` | Capability imports.manage |
| `server/migrations/postgresql_stage8_documents_excel.sql` | Новая additive PostgreSQL-миграция, JSONB, FORCE RLS/FKs/triggers/grants, provisioning v7 |
| `server/vps_stage7_staging_deploy.sh` | Будущий порядок миграции, grants, приватный writable document root |
| `server/test_documents_api.py`, `server/test_excel_import.py` | Permissions, isolation, storage, preview/apply/rollback/idempotence/security |
| `server/test_excel_template.py`, `server/test_portal_documents.py` | XLSX mapping, независимый reader/round trip, детерминизм и tenant prefill |
| `server/test_postgresql_documents_schema.py`, `server/test_documents_postgresql.py` | Статический SQL-контракт и disposable live PostgreSQL/HTTP fixture |
| `server/requirements-test.txt`, `.github/workflows/server-tests.yml` | openpyxl 3.1.5 только для тестов независимого reader |
| `.gitignore` | Исключён приватный каталог .portal-documents |
| `PORTAL_MASTER_ROADMAP.md`, этот отчёт | Проверенные результаты и границы |

Runtime XLSX использует стандартную библиотеку Python, без новой серверной зависимости.

## Documents и storage

Модель поддерживает все девять типов из задания: payroll_xlsx, payroll_slip_xlsx/pdf, invoice_xlsx/pdf, report_xlsx/pdf, import_template_xlsx, import_result. Поля: company/id/type/category/title/original_filename/storage_key/MIME/size/SHA-256, scoped client/employee/invoice/payroll_period references, actor/kind/UTC created_at/document_date, status, JSON metadata, source_kind, revision/previous_id.

Байты новых документов находятся вне SQL payload. Storage key `<company_id>/<sha256>` не зависит от пользовательского имени. Адаптер проверяет scope, traversal/symlinks, размер/checksum, использует приватный временный файл, fsync и atomic replace; временный файл удаляется в finally. Доверенный PORTAL_DOCUMENT_ROOT задаёт корень; default — .portal-documents рядом с DB path. Отсутствие/повреждение bytes возвращает download error, сохраняя metadata/history.

Retry request_id связан с immutable fingerprint; одинаковый ready-документ от того же actor с теми же метаданными/связями повторно не создаётся. Новая ревизия сохраняет previous_id. Архив допускает только ready → archived без изменения других полей; delete запрещён. Архивный документ доступен через авторизованный metadata API, скрыт из обычного списка и недоступен для download.

Legacy документы portal_production читаются compatibility projection; inline bytes/история не переписывались. Старые payroll-поля ответа, включая period_id, сохранены.

## Endpoints

Префикс `/api/v3/`; сохраняется существующий JSON/base64 transport.

| Метод/маршрут | Действие |
|---|---|
| GET documents | Старый list response; при query-параметрах — items/total/page/limit |
| GET document-metadata?id=… | Авторизованные метаданные |
| GET document-file?id=… | Авторизованное скачивание ready-файла |
| POST documents action=upload / document-upload | Проверка/регистрация файла |
| POST documents action=archive / document-archive | Архив |
| POST documents action=generate / document-generate | Payroll XLSX из закрытого snapshot; старое document_type=payroll поддержано |
| GET/POST document-template-blank | Скачать blank / зарегистрировать в Documents |
| GET/POST document-template | Скачать prefill выбранной компании / зарегистрировать |
| GET document-template-info | Версия, четыре листа, mapping |
| POST excel-import-preview | Workbook → diff/classifications/checksum/import_id/preview_token |
| POST excel-import-apply | Exact file + import_id + preview_token, explicit atomic apply |
| GET excel-import-result?id=… | Сохранённый terminal результат |

Documents filters: document_type/category/date_from/date_to/client_id/employee_id/status/q/page/limit; limit ≤ 200, параметризованный поиск. storage_key, fingerprint и request receipts не выдаются клиенту.

Apply success: HTTP 200/status=applied. Invalid/conflict plan или сбой применения: HTTP 409/status=failed, ноль применённых строк и result document. Повреждённый token, чужой scope, изменённый файл/справочники отклоняются до применения.

## Excel и безопасный импорт

Листы точно в порядке **Компания, Сотрудники, Клиенты, Операции_Тарифы**. Row 1 — marker v1.0; row 2 — machine keys; row 3 — русские заголовки. Freeze A4, ширины, автофильтр. Prefill — whitelist полей одной компании, без PIN/hash/salt/session tokens и legacy Telegram alias. Денежные строки/реквизиты сохраняют точные копейки/ведущие нули; строки с формулоподобным содержимым не исполняются.

Preview классифицирует new/update/unchanged/conflict/invalid и возвращает before/normalized/changes. Проверяет sheets/version/headers, роли/status/IDs/money/dates, duplicate/unique conflicts, ambiguous references/identity, cross-company references, backdate/overlap. Даты нормализуются в UTC; равные instants конфликтуют независимо от точности записи.

Новый сотрудник получает самостоятельный canonical payroll_employee_id; внутренний отрицательный compatibility alias не становится финансовым ключом. Слияние по одному имени запрещено. Новые PIN/access и активация отключённого account проходят существующий Access API с company user limit. Импорт может изменить роль/отключить существующий связанный account в пределах capabilities автора, с отзывом сессий. Изменение собственного доступа и отключение последнего администратора блокируются. Пустой user_id означает только profile edit.

Существующие физические portal_client_operations.employee_rate/client_rate не обновляются. Изменённый тариф добавляется будущей immutable версией. Work/payroll/invoice facts и закрытые snapshots не переписываются. Текущая модель поддерживает начало версии; непустой effective_to отклоняется. Новая операция получает собственный baseline.

HMAC token связан с company/actor/kind/checksum/catalog snapshot/plan, срок — 30 минут. Перезапуск требует нового preview. Apply свежо проверяет права/план под company lock. SAVEPOINT охватывает все catalog changes и success report. При ошибке изменения полностью откатываются, затем сохраняются failure job/report/audit. Applied import_id/checksum возвращает прежний receipt без повторного применения. Failed job можно повторить после исправления/нового preview; прошлый error report остаётся.

Import result содержит checksum/counts/sheet/row/new IDs/error codes без имён, raw workbook или exception text и сохраняется в Documents.

Лимиты: файл 10 MiB; JSON transport 14 MiB; ZIP ≤ 256 entries/40 MiB expanded/ratio 200; XML-part ≤ 4 MiB; общий import ≤ 2000 data rows/50000 cells/1000 chars per cell. Reject macros, external relationships/embeddings, formulas, encrypted/traversal/duplicate ZIP parts, DTD/ENTITY/не-UTF8 XML.

## Permissions, RLS, audit

Documents read/manage проверяются отдельно. Manager видит только документы назначенных клиентов; payroll требует payroll.all. Platform Owner обязан явно выбрать компанию. Blank/info требуют documents.read; prefill/preview/apply/result требуют imports.manage, users.manage, clients.manage, rates.employee/client, company.settings, documents.manage/read и роль admin/director либо technical owner.

Обе новые PG-таблицы: ENABLE/FORCE RLS, protected portal_current_company() в DEFAULT/USING/WITH CHECK; company FK и composite scoped references; JSONB shapes, idempotence uniqueness, status/date checks/indexes. Restricted runtime — NOSUPERUSER/NOBYPASSRLS; grants на новые таблицы SELECT/INSERT/UPDATE без DELETE/PUBLIC. Provisioning сохраняет markers 3–7.

Audit: document_generated/uploaded/archived, import_applied/failed и import_preview_created. Для «preview — ноль записей в БД» preview event пишется в structured process/service log только с IDs/counts; DB provenance сохраняется при explicit apply. Preview не пишет jobs/Documents/activity/platform audit. В exception audit не попадают тексты ошибок/PII.

## Миграция и совместимость

Добавлен только новый SQL-файл postgresql_stage8_documents_excel.sql после Stage6/Stage4c; внутренний production marker v7. Старые SQL migration files не менялись. Скрипт будущего staging deploy добавляет checksum-ordered migration, минимальные grants и PORTAL_DOCUMENT_ROOT=$STATE/documents с portal-stage7 owner/mode0700. Этот deploy-скрипт не запускался.

SQLite schema меняется только через существующий explicit migrate entry point, не обычным server startup. PostgreSQL требует операторского применения нового SQL. Legacy document/import/invoice/payroll tables сохранены.

## Проверки — точные результаты

Все данные синтетические. Python — bundled runtime, openpyxl 3.1.5.

| Команда/проверка | Результат |
|---|---|
| Из server: python -m unittest test_documents_api test_excel_import test_excel_template test_portal_documents test_postgresql_documents_schema -v | **38 tests, OK**, без skips; reports/documents-part1-targeted.log |
| PORTAL_TEST_HTTP=1 python -m unittest discover -s server -p 'test_*.py' -v | **185 total, 171 passed, 14 skipped, OK**, 200.844 s; reports/documents-part1-final-http.log |
| Как postgres: PORTAL_DOCUMENTS_PG_INTEGRATION=1 python -m unittest test_documents_postgresql -v | **3 tests, OK**, 4.634 s, реальные loopback HTTP sockets; reports/documents-part1-live-pg.log |
| openpyxl load/save + bounded parse round trip | Включено в targeted/full: четыре листа, версия, русские headers, freeze panes и значения проходят |
| python -m compileall -q server | Exit 0 |
| Git Bash bash -n для LF-копии staging deploy | Exit 0 |
| git diff --check / staged diff check | Прошли |

14 skips полной регрессии: 3 новой disposable PG fixture (отдельно прошли на VPS), 7 прежних full migration CLI, 3 legacy live migration, 1 прежний Stage7 API/restart integration. Последние 11 не запускались без отдельных fixture DB/services и не заявляются как passed.

Live fixture создаёт случайную portal_test_documents_* базу и две restricted роли, не принимает production DSN. Применяет все восемь SQL migrations и повторно новую; synthetic компании имеют colliding IDs. Проверяет JSONB/grants/FORCE RLS/forged context, cross-company HTTP list/metadata/download/archive, atomic rollback/retry/idempotence/immutable jobs. В cleanup удалены только созданные fixture DB/roles. Stage7 DB/service не менялись. Подготовительные ошибки самой fixture (особый company1 user_limit, admin-only setval, HTTP setup) исправлены до успешного финального прогона.

## Оставшееся для Part 2 / rollout

- Android/Desktop screens загрузки/preview/подтверждения, Documents folders/search/history, сохранения/share/email/синхронизации.
- Генераторы invoice XLSX/PDF, payroll slip PDF и других reports. Metadata/upload типов поддержаны; здесь генерация payroll XLSX/template/import result.
- Object storage, reconciliation/retention. При rollback может остаться unreferenced content-addressed blob: он намеренно не удаляется в транзакции, чтобы не удалить файл параллельной регистрации. Temp files удаляются.
- Отдельный контролируемый перенос старых inline bytes, если потребуется; здесь compatibility сохраняет историю.
- Согласованный rollout ветки/SQL и проверка рабочего staging/UI.

## Явные границы

Production DB, production cutover и телефонная SQLite **не затрагивались**. Действующие production тарифы и закрытая финансовая история **не менялись**. Секреты/production PII в Git diff/отчёт **не включались**.

В этой задаче Android UI/navigation/assets, release.properties, APK и version/build файлы **не изменялись и не коммитились**. Имеющиеся параллельные незакоммиченные Android-правки и PORTAL_CURRENT_AUDIT_20260929.md сохранены отдельно и не включены в коммиты Documents/Excel.
