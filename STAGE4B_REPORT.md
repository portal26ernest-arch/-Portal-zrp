# PORTAL — отчёт Этапа 4B: сервер и PostgreSQL

Дата: 25.09.2026. Ветка `portal-next-b003`. Фактическая контрольная точка 4A — `6013ac331e3eb8f169975183d9c7da719ff93347` (в последнем задании указано `6813…`, такого HEAD нет). Продолжены уже начатые незакоммиченные изменения 4B. Рабочая БД телефона и production-сервер не открывались; commit, push, merge, reset/Undo и изменение `main` не выполнялись. Старые APK/SHA остались вне изменений.

## Готово сейчас

- `postgresql_core_stage4b.sql` описывает известные компании, Platform Owner/control plane, пользователей/сессии, клиентов/операции, старую выработку и зарплату, материалы, счета/оплаты и аудит. Tenant-таблицы получают `company_id`, RLS и `FORCE ROW LEVEL SECURITY`; финансовая/производственная история защищена от удаления. Stage 3 ledger SQL уточнён: уникальный номер партии, обязательный номер, неизменный `created_at`, tenant RLS. Версионные тарифы, партии, задания, permissions, план/факт, финансы, активность и таймеры хранятся в этом ledger с `company_id`.
- `migrate_sqlite_to_pg.py` — отдельный будущий переносчик **копий** SQLite. По умолчанию dry-run выполняет `integrity_check`, проверяет обязательные таблицы/поля, число и ID компаний, границы `company_id` и ключевые связи. Старую базу без multi-company относит к основной компании PORTAL с ID 1. `--apply` требует DSN из защищённого окружения и импортирует в пустую подготовленную PostgreSQL БД одной транзакцией; каждый перенесённый table сверяется по количеству и SHA-256 строк. При несовпадении — `FAILED`, транзакция откатывается, адрес сервера не меняется. Исторические текстовые client/operation, employee mapping, даты, ID и денежные значения копируются без пересчёта. JSON-отчёт содержит счётчики и денежные итоги без строк и секретов.
- Отдельный `validate_pg_migration.py` выполняет read-only повторную сверку уже company-scoped копии и PostgreSQL. Список проверяемых таблиц, включая зарплату, счета, платежи, ledger и активность, находится в `migration_validation.py`.
- `portal_config.py` централизует development/test/production environment, адрес API, host/port и выбор БД; `.env.example` не содержит паролей. Production требует HTTPS URL. Android default API URL задаётся при сборке через `PORTAL_API_URL` или Gradle `portalApiUrl`, при этом существующая настройка адреса в приложении сохраняется. Один и тот же API предназначен для Android и будущего PC/Web.
- `SERVER_MIGRATION_RUNBOOK.md` содержит порядок backup → копия → Ubuntu/изолированная БД → dry-run → import/сверка → HTTPS → Android/PC проверки → cutover → restore test → наблюдение и rollback. Описаны отдельные пользователь, каталог, сервис, БД/роли, логи и backup PORTAL на общем VPS; PostgreSQL не должен быть публично доступен.
- Будущий чат только описан: закрытые company-scoped таблицы, системные файлы «Стикеров PORTAL» однократно, сообщения со ссылками/ID, физическая очистка обычных сообщений и вложений через 14 дней, исключение закреплённых руководством. UI, БД и scheduler чата не создавались.

Файлы 4B: `.env.example`, `SERVER_MIGRATION_RUNBOOK.md`, `STAGE4B_REPORT.md`, `server/portal_config.py`, `server/portal_app_server.py`, `server/migrations/postgresql_core_stage4b.sql`, `server/migrations/postgresql_stage3.sql`, `server/migration_import.py`, `server/migrate_sqlite_to_pg.py`, `server/migration_validation.py`, `server/validate_pg_migration.py`, `server/test_migration_import.py`, `server/test_migration_validation.py`, `android_src/app/build.gradle`, `android_src/app/src/main/java/ru/portal/app/MainActivity.java`.

## Тесты

- Полный серверный набор на временных SQLite БД: **60/60 прошли** (47 прежних + 13 новых). Новые offline тесты проверяют контракт PostgreSQL схемы/RLS, SQL adapter, read-only SQLite copy, legacy mapping к компании 1, сохранение текста и сумм, права/версии тарифов/партии/задания/выработку/активность/счета через ledger snapshots, отказ при несовпадении/неполной схеме/чужом `company_id`, rollback целевой транзакции и конфигурацию.
- Браузерный набор Edge/Playwright: **11/11 прошли**. Python `compileall`: успешно. `git diff --check`: успешно. Поиск известных сигнатур ключей и токенов в исходниках: совпадений нет. Результаты после окончательной проверки фиксируются ниже при сдаче.
- Это **unit/schema/offline SQLite tests**. `psql`, сервер PostgreSQL и `psycopg` на текущем компьютере отсутствуют; реальная PostgreSQL schema execution, import и integration/API tests **не выполнялись**. Локальный Android SDK отсутствует; production APK не выпускался.

## Что требует реального Linux/PostgreSQL сервера

Текущий HTTP сервер и старые маршруты всё ещё используют SQLite и отдельные файлы компаний. Для безопасности `PORTAL_DB_BACKEND=postgresql` сейчас останавливает сервер с явным сообщением: **PostgreSQL runtime не готов к cutover**. До использования PostgreSQL необходимо перенести control plane, auth/session и старые SQL маршруты на центральную БД, проверить контракт реальной схемы по копии `portal.db`, затем выполнить полноценные PostgreSQL integration/API тесты, включая RLS, конкуренцию, транзакции и восстановление backup. Core DDL — проверяемый проект схемы, а не доказательство успешного развёртывания.

## Что проверить на копии реальной `portal.db`

Состав таблиц и дополнительных колонок, все tenant-файлы и platform DB, `company_id`, старые записи без multi-company, сотрудников/клиентов/операции, исторические текстовые связи, payroll и старые ставки, последовательность и уникальность партий, версии тарифов, plan/fact, материалы, счета/оплаты, audit, activity/timing. Сверить денежные суммы по каждой компании и периоду независимо от хешей. При дополнительных таблицах или другом типе колонок обновить целевую схему и план миграции; инструмент остановится, не пропуская молча данные.

## Пошаговый план фактического переезда

Полная инструкция — `SERVER_MIGRATION_RUNBOOK.md`: backup телефона → неизменяемая копия SQLite → изолированные Ubuntu сервис/БД/роли → проверенная PostgreSQL схема → dry-run → атомарный импорт → автоматическая и ручная сверка → HTTPS и Android/PC тест → финальный backup при остановленной записи → повторная сверка → переключение → тест восстановления backup → наблюдение → только потом отказ от телефона как сервера.

## Риски и rollback

Главный риск — неперенесённые старые поля/API и отсутствие реального PostgreSQL runtime/integration test. Дополнительно: tenant leakage, расхождение денег/ID, неполный финальный снимок, двойная запись, роль с `BYPASSRLS`, неподтверждённый restore. Любая такая проблема блокирует cutover. До переключения старая система продолжает работать, исходная SQLite не меняется. После переключения для rollback сначала остановить запись на VPS и сохранить созданные там операции; возвращать адрес на телефон только после плана сверки этих операций. Нельзя молча потерять записи или одновременно принимать запись на обеих сторонах.
