# PORTAL 3.2 — baseline audit

Дата аудита: 2026-09-27. Источник: фактическое рабочее дерево `PORTAL-Android` на commit `1fa78b0` (`PORTAL 3.3 migration validation hardening`). Аудит не менял код, БД, тарифы и исторические данные; миграции не запускались. Единственный новый файл — этот отчёт.

Рабочее дерево до аудита уже содержало неотслеживаемые `node_modules/`, APK и его checksum; аудит их не менял. В корне нет `AGENTS.md`.

## 1. Структура проекта

| Область | Текущая реализация |
|---|---|
| Backend | `server/portal_app_server.py` — HTTP API, вход и прежние SQL-маршруты; `portal_tenancy.py` — изоляция и реестр компаний; `production_service.py` + `production_repository.py` — модуль домена производства и финансовых записей; `production_activity.py` — сессии/активность; `portal_postgres.py` — адаптер БД. Запуск: `server/start_portal_app.sh`. Версия в коде заявлена как `PORTAL Server · 3.3-dev`. |
| Android | `android_src/` — Gradle/Java оболочка `MainActivity`, локальные HTML/CSS/JS UI в `app/src/main/assets`; нативное приложение открывает локальный интерфейс и вызывает API. `release.properties` задаёт метаданные сборки. |
| Web | Отдельного web frontend/repository package нет. Пользовательский интерфейс — WebView assets, используемые Android. |
| PostgreSQL | SQL-адаптер, конфигурация и миграции существуют. Runtime gate требует loopback, заданную схему и RLS; production PostgreSQL требует явного `PORTAL_ENABLE_POSTGRES_PRODUCTION=true`. В `.env.example` backend по умолчанию SQLite. Наличие файлов не подтверждает текущий production cutover или состояние удалённой БД. |
| Migrations | SQLite tenancy/schema initialization в `portal_tenancy.py`, доменные версии 3–5 в `production_migrations.py`; шесть PostgreSQL SQL-скриптов в `server/migrations/`; SQLite→PG importer/validator в `migration_import.py`, `migration_validation.py`, CLI. |
| API | HTTP API обслуживается одним `portal_app_server.py`; legacy-маршруты `/api/...` для входа, клиентов, операций, пользователей, выработки/зарплаты, счетов и справочников; `/api/v3/...` для production ledger, заданий, таймеров, тарифов, прав, payroll periods, chat, документов и расходов. Это не отдельное OpenAPI-описание. |
| Authentication | Логин + PIN, PBKDF2-HMAC-SHA256 (180,000 итераций), bearer/session token. Обычная SQLite-сессия живёт до 30 дней и в legacy таблице хранится как token; Platform Owner — отдельный контур, пароль хешируется, token сессии хранится как SHA-256. Есть logout, деактивация/смена доступа отзывает сессии. |
| Roles/permissions | Роли `admin`, `director`, `manager`, `accountant`, `shift`, `packer`; отдельно системная `platform_owner`. `production_permissions.py` задаёт capability-каталог, рекомендованные права и индивидуальные overrides. Старые проверки по ролям остаются fallback при неготовом production repository. |
| Employees | `employees` и `app_users` в legacy schema. Текущая совместимость связывает `employee_id` с историческим `telegram_id`; новые сотрудники получают собственный identity. Менеджерские назначения и персональная выработка завязаны на employee identity. |
| Clients | `portal_clients`, `portal_client_operations`, manager assignments; CRUD/архив, операции и тарифы в API/UI. Клиенты являются company-scoped. |
| Operations/tariffs | Legacy operation rates + append-only ledger `tariffs`/PG `tariff_versions`; для новых работ ставка снапшотится, существующая историческая зарплата не пересчитывается. UI управления версиями тарифов неполный согласно roadmap. |
| Work/production | Legacy `work_log` и ledger `works`; batches, tasks, plans, progress, timers/events, work-to-batch links, material consumption/usage. Поддержаны выработка вне задания, несколько назначенных работников, таймеры, материалы и неизменяемая история. |
| Payroll/payments | Payroll legacy projections/tables плюс production `payroll_periods`, work snapshots, client `invoices`/`payments`, документы. Payroll period close и export в XLSX реализованы; payroll payout/correction workflow как полноценная ledger-модель в production service не обнаружен. Подробно ниже. |
| Tests | `server/test_*.py` unittest suite; `android_src/tests/*.test.cjs` Node test runner и скриптовые UI/regression проверки. PostgreSQL live/VPS тесты требуют отдельной тестовой среды. |
| CI/CD | `.github/workflows/server-tests.yml`, `android-build.yml`, `android-release.yml`. Release workflow только `workflow_dispatch`, допускает только main, требует HTTPS и GitHub Secrets для подписи. |
| Configuration/secrets | `.env.example` — шаблон; `portal_config.py` читает переменные окружения; CI secrets для URL/API и подписи Android; локальные VPS identity/known_hosts исключены в `.gitignore`; runtime `.env`, DB и backups исключены. Значения секретов не читались и в отчёт не включались. |

## 2. Telegram и локальный legacy

В текущем репозитории не обнаружены Telegram SDK/import, Telegram API вызовы, bot polling, callbacks/handlers или активная отправка боту. Поиск включает `server/`, Android и CI; контрольные тесты специально запрещают `api.telegram.org`, BOT token и телефонные Termux-пути в Android runtime. Оставшиеся упоминания — историческая совместимость/документация и поля схемы.

| Остаток | Фактическое место | Решение | Причина |
|---|---|---|---|
| `telegram_id` в `app_users`, `employees`, `work_log`, `payroll_payments`, `payroll_transactions`, `production_job_progress`, `manager_client_assignments` и связанных запросах | Особенно `server/portal_app_server.py`; PostgreSQL core schema сохраняет старые таблицы/поля | **MIGRATE** | Это действующий compatibility identity: `with_employee_id`, employee lookup, личная зарплата/работы и manager scope ещё читают/пишут legacy ID. Сначала переносить mapping на устойчивый employee ID и сверять историю. |
| Runtime alias `employee_id ← telegram_id`, fallback `user.get('telegram_id')` | `portal_app_server.py`, `production_service.py`, Android `core.js`, UI fixture-тесты | **MIGRATE** | Новый API/UI уже используют employee identity, но fallback необходим существующим аккаунтам/записям до data migration. Не удалять поиском. |
| Имена полей `telegram_id` в SQL и compatibility boundary при записи пользователя | `portal_app_server.py` (в том числе `save_user`, `validate_employee`, legacy endpoints) | **MIGRATE** | Это не Telegram transport, а старое имя PK сотрудника, совместимое с телефонной БД. Требует согласованной миграции и обновления старых клиентов/API. |
| Ссылки на Telegram/бот и телефонную БД в roadmap, stage reports, cutover/runbook | `PORTAL_MASTER_ROADMAP.md`, `PRODUCTION_CUTOVER_TZ.md`, `SERVER_MIGRATION_RUNBOOK.md`, stage reports | **KEEP** | Исторические ограничения, происхождение данных и незавершённый cutover важны для безопасной миграции. Обновить после подтверждённого перехода. |
| Утилиты SQLite→PostgreSQL | `server/migrate_sqlite_to_pg.py`, `migration_import.py`, `migration_validation.py` | **KEEP** | Мигратор использует SQLite как source copy, выполняет dry-run/проверки и сохраняет старые поля. Это не старый runtime телефона; нужен для контролируемой миграции и reconciliation. |
| SQLite tenant files/control DB и legacy SQL endpoints | `portal_tenancy.py`, `portal_app_server.py` | **INVESTIGATE** | Это действующий серверный runtime, не только локальный rollback path: `.env.example` default `sqlite`, запускающий скрипт указывает `portal.db`. Не считать остатком бота без уточнения фактического production backend/cutover. |
| Telegram bot token references | Поиск не нашёл runtime references; только тесты/документация запрещают их | **REMOVE** (если найдутся в deployment вне репозитория — отдельно **INVESTIGATE**) | В коде PORTAL активная интеграция отсутствует. Проверить внешние environment/systemd/VPS secrets до любой чистки инфраструктуры; значения здесь не проверялись. |
| Telegram imports/libraries, handlers, callbacks, polling | Не найдено | **REMOVE** (не найдено объектов для удаления) | Нет активных импортов/обработчиков/зависимостей в текущем рабочем дереве. |
| `api.telegram.org`, BOT_TOKEN, OWNER_TELEGRAM_ID, Termux/`/storage/emulated/0/PORTAL-BOT` в Android app runtime | Запрещены в `android_src/tests/legacy-boundary.test.cjs` и native shell test; в runtime не найдены | **REMOVE** (не найдено runtime-кода) | Граница Android runtime явно защищена regression tests. |
| `telegram_id` в тестовых fixture/contract tests | `server/test_production.py`, `android_src/tests/ui.test.cjs` | **KEEP** временно | Fixtures проверяют обратную совместимость; обновлять вместе с миграцией identity, чтобы не потерять тест покрытия legacy boundary. |

## 3. Company isolation

**Текущий фактический SQLite runtime:** tenant company 1 использует исходную `PORTAL_DB`; дополнительные компании — отдельные SQLite файлы, путь вычисляется сервером (`.portal-tenants/company-<id>.db`); отдельная control/platform DB хранит компании, владельцев и системный аудит. Authenticated token выбирает компанию, далее `company_scope` задаёт контекст. Клиентский `company_id`/заголовок не должен переопределять обычный scope; Platform Owner обязан явно выбрать техническую компанию, такой доступ аудируется. Schema добавляет company_id, ограничения и проверку tenant identity. Существующие тесты проверяют коллизии ID, подмену контекста и изоляцию.

**PostgreSQL:** SQL core/production migration tables имеют `company_id`; policies используют закрытый контекст компании и включают `ENABLE` + `FORCE ROW LEVEL SECURITY`. `portal_rls_context.sql` задаёт защищённые ключи/функции bind; runtime проверяет роль без опасных привилегий и наличие RLS. Но наличие schema/RLS в репозитории и предыдущие отчёты о synthetic VPS тестах не подтверждают, что текущий production server обслуживается PostgreSQL. Последние репозиторные отчёты прямо указывают, что production cutover не завершён; конфигурация проекта по умолчанию SQLite.

**Граница риска:** старые маршруты/проекции по-прежнему используют таблицы и SQL прежнего приложения. Любой 3.2 переход с файлов SQLite на централизованную PostgreSQL требует проверки каждого запроса/репозитория и production-like тестов RLS; нельзя полагаться только на company_id в UI.

## 4. Роли и авторизация

- Бизнес-роли: `admin`, `director`, `manager`, `accountant`, `shift`, `packer`. Метки в основном русские; на старой boundary роль сотрудника называется `packer`, новый permission catalog использует русскую метку «Сборщик», UI может показывать «Упаковщик».
- `platform_owner` хранится отдельно от обычных пользователей и не назначается через `/api/users`. Это системная роль с отдельным входом, session hash и явным техническим контекстом компании.
- Capability права (пример: `work.write`, `payroll.own`, `payroll.all`, `payroll.close`, `rates.employee`, `payments.record`) описаны в `production_permissions.py`. Пользовательские overrides добавляют/снимают capability. Права интерфейса — только отображение; backend повторно проверяет capability.
- Менеджер ограничивается активными client assignments даже при отдельно выданной возможности. Права на свою зарплату отделены от доступа к зарплате всей команды.
- Есть transitional fallback к старым role allowlists, если production repository ещё не готов. Это увеличивает риск расхождения старых и новых permission semantics и требует аудита каждого legacy route.
- PIN допускает минимум четыре символа для пользователей; для защиты слабого PIN важны rate limiting/monitoring. Platform Owner credential создаётся локально оператором с большей минимальной длиной.

## 5. Payroll и выплаты — фактический разбор

| Часть | Реальная реализация | Статус/ограничение |
|---|---|---|
| Work entries | `work_log` — старый физический журнал; production ledger `works` хранит employee/user, client/operation, quantity, rate/tariff source, salary/revenue snapshots, timestamps и связь с `legacy_id`. `Production.work()` записывает работу и отказывает при закрытом периоде. | Реализовано; два представления истории требуют сохранения согласованности при миграции. |
| Rates | Legacy operation rates плюс append-only `tariffs` payload и PG `tariff_versions`. Effective-from версии применяются к новым работам; `works` хранит фактический rate/salary snapshot. | Реализовано, UI истории/управления версиями неполный; нельзя переоценивать исторические записи. |
| Accruals | Сдельное начисление при работе: `quantity × employee_rate`; snapshot в work ledger и прежнем work_log. Есть агрегат `payroll_snapshot`/`payroll.own`/`payroll.all`. | Реализовано. Доступны сумма/количество/строки работ; отдельная схема удержаний/налогов не обнаружена. |
| Payments | `payroll_payments` и `payroll_transactions` — legacy tables, API `/api/payroll/mine` суммирует `payroll_transactions.amount` по работнику и периоду; обновления PG добавляют snapshot/date/note/id. Не обнаружен method `Production` для внесения/проведения выплаты. `Production.payment()` — **оплата клиентского счёта**, не зарплатная выплата. | Частично/legacy. Нужна проверка старого endpoint и схемы источника, прежде чем считать payout flow поддержанным. |
| Periods | Доменные `payroll_periods` ledger snapshots; допустимы интервалы 1–15 и 16–последний день месяца. UI/API preview, закрытие только прошедшего периода, запрет пересечения. | Реализовано на production module. |
| Corrections | Work record содержит поля quality `defects` и `correction_of`, но в фактической логике не обнаружен API/service для correction, adjustment или отрицательного/компенсирующего начисления. | Не обнаружено как завершённый payroll workflow; `correction_of` пока поле/заготовка. |
| Closing/locking | `payroll_periods` записывает статус `closed`, закрывающего и неизменяемый snapshot; повтор/пересечение отвергается; work() блокирует новые работы с датой закрытого периода; migration triggers защищают ledger history за исключением явно обновляемых типов. | Закрытие есть. Отдельной процедуры reopen/unlock не обнаружено; correction после закрытия отсутствует. |
| Documents | Для закрытого периода генерируется XLSX из snapshot с контрольными hash/metadata. PDF обозначен как будущий формат. | XLSX реализован; PDF нет. |

Legacy payroll в `portal_app_server.py` живёт рядом с новым payroll API. Перед 3.2 нужно определить канонический источник фактически существующих исторических выплат и сверить его с импортируемой схемой — сами репозитории не содержат production DB для чтения.

## 6. PostgreSQL schema и migrations

Скрипты из `server/migrations/` и их назначение:

1. `postgresql_core_stage4b.sql` — компании/platform owner sessions/audit, app users/sessions, employees, клиенты/операции, assignments, work_log, payroll payments/transactions, client invoices/payments, материалы/движения/norms, production jobs/progress, audit_log; company_id, FK/check constraints и RLS policies.
2. `postgresql_rls_context.sql` — `portal_company_keys`, bind/current-company helper functions, защищённый DB context, маркер версии context schema.
3. `postgresql_stage3.sql` — `portal_production_migrations`, `portal_production` JSON ledger, уникальность номера batch, immutability triggers и RLS.
4. `postgresql_stage4c.sql` — products, tariff_versions, manager_service_rates, managers, employee invites/access requests, client access/roles/permissions/invites/name overrides, employee chat/settings, invoice items/requisites, expense requests, scheduled runs, marketplace news, backup/system settings, production job assignments, payroll closure batches; расширения существующих таблиц и RLS по tenant list.
5. `postgresql_runtime.sql` — runtime schema marker, material consumption, расширения текущих legacy таблиц, проверки данных/связей и immutable protection.
6. `postgresql_stage5_chat_retention.sql` — schema marker и trigger-исключения/правила retention для chat entities.

SQLite production domain сохраняет большую часть Stage 3+ сущностей как JSON в `portal_production(company_id, kind, id, payload, created_at)`, а прежние записи/каталоги — в физической SQLite schema. Это не обычные отдельные PG таблицы для каждого ledger entity.

**Риски порядка/версий:** SQL-файлы имеют stage names и schema marker checks, а application migration использует versions 3–5; унифицированного migration registry/order для всех скриптов в этом репозитории не обнаружено. `ensure_schema()` требует конкретный набор relation names/markers, следовательно применять SQL не в нужном порядке нельзя. Все фактические PG применения на production в рамках этого аудита не запускались.

**Схема legacy данных, известная из PG core:** `companies`, `platform_owners`, `platform_sessions`, `platform_audit`, `employees`, `app_users`, `app_sessions`, `portal_clients`, `portal_client_operations`, `manager_client_assignments`, `work_log`, `payroll_payments`, `payroll_transactions`, `client_invoices`, `client_payments`, `materials`, `material_movements`, `operation_material_norms`, `production_jobs`, `production_job_progress`, `audit_log`.

**Дополнительные отношения из последующих PG migrations/runtime:** `portal_company_keys`, `portal_production_migrations`, `portal_production`, `work_material_consumption`, `portal_runtime_schema`, `portal_rls_context_schema`, `products`, `tariff_versions`, `portal_manager_service_rates`, `managers`, `employee_invites`, `employee_access_requests`, `client_access`, `user_roles`, `client_permissions`, `client_invites`, `client_name_overrides`, `employee_chat_messages`, `employee_chat_settings`, `client_invoice_items`, `portal_company_requisites`, `portal_client_requisites`, `expense_requests`, `scheduled_runs`, `marketplace_news`, `backup_log`, `system_settings`, `production_job_assignments`, `payroll_closure_batches`.

Некоторые отношения создаются/дополняются посредством `ALTER TABLE` и dynamic RLS block, поэтому список — логическая схема целевых миграций, а не утверждение о текущей удалённой БД.

## 7. Хранение секретов

- `.env.example` — только шаблон/placeholder, actual `.env` исключён через `.gitignore`.
- Backend ожидает `PORTAL_DATABASE_URL`, `PORTAL_CONTROL_DATABASE_URL` из защищённого окружения; config скрывает DSN из repr. Скрипт запуска не печатает секреты.
- Android signing и release API URL подаются из GitHub Actions Secrets (`PORTAL_ANDROID_KEYSTORE_B64`, пароли, alias и URL). Workflow пишет keystore только во временный runner path с ограниченными правами.
- VPS key/known_hosts находятся в корне под именами `infra_vps_01*` и исключены из Git. Их значения/содержимое не читались; проверить фактические ACL/ротацию вне репозитория.
- Секреты RLS компании хранятся в `portal_company_keys.secret`; создаются миграционным контекстом в защищённой БД. Проверить права доступа DB roles и backup encryption.
- Обычная SQLite `app_sessions.token` содержит bearer token в открытом виде; в PostgreSQL core также задан `app_sessions.token`. Отдельная Platform Owner сессия хранится hash-only. Это заметное различие хранения токенов.
- Hash PIN и соли хранятся в пользовательских таблицах; тесты проверяют, что значения/токены не попадают в audit/logs.
- Android хранит session token через app storage/localStorage bridge. Это bearer credential; риск зависит от защиты устройства/backup/экспорта и требует отдельной проверки.

Никакие значения секретов в ходе аудита не выводились.

## 8. Тестовый baseline и команды

Команды запускались на текущем checkout, без production DB. Результат:

- `python -m unittest discover -s server -p 'test_*.py' -v` — **101 тест, OK, 11 skipped**, 73.345 с. Skipped тесты помечены как требующие отдельного synthetic VPS PostgreSQL/full-CLI среды. Выводил предупреждения deprecation для `datetime.utcnow()` в `test_production.py`.
- `node --test android_src/tests/*.test.cjs` — **17 passed, 0 failed, 0 skipped** (browser UI regression входит в suite), 12.764 с.
- CI содержит дополнительный server run с `PORTAL_TEST_HTTP=1`; полный отдельный прогон этой переменной при baseline не выполнялся. Команда по workflow: `PORTAL_TEST_HTTP=1 python -m unittest discover -s server -p 'test_*.py' -v` (PowerShell: `$env:PORTAL_TEST_HTTP='1'; python -m unittest discover -s server -p 'test_*.py' -v`).
- Предыдущее report подтверждает Gradle Android staging/release workflow, но сборку Gradle в этом аудите не запускали.

**Live PostgreSQL ограничения:** live API/schema/import/full-VPS тесты сейчас не выполнились в локальном suite и пропущены. Их синтетические результаты в `POSTGRESQL_TEST_REPORT.md` — исторический отчёт, не повторное доказательство состояния среды на дату аудита.

## 9. Английский текст пользовательского Android/Web UI

Просмотрены Android WebView assets и ресурсы. Большинство UI-сообщений/кнопок на русском. Обнаружены конкретные пользовательские строки, противоречащие обязательному правилу PORTAL:

| Файл | Английская строка в UI | Примечание |
|---|---|---|
| `android_src/app/src/main/assets/production.js` | `Online`, `Offline` (настройка интервала присутствия) | Заменить русскими статусами, например «В сети» / «Не в сети»; термины отображаются пользователю. |
| `android_src/app/src/main/assets/production.js` | `Создать snapshot`, `неизменяемый snapshot` | Русская фраза содержит непереведённый термин; заменить на «снимок». |
| `android_src/app/src/main/assets/core.js` | Метка роли `Platform Owner` | Роль показана в списке/профиле; интерфейсную метку локализовать (например, «Владелец платформы»), сохранив идентификатор `platform_owner`. |
| `android_src/app/src/main/assets/production.js` | Уведомление `XLSX готов` | Расширение XLSX допустимо по правилу пользователя, однако пользовательское состояние лучше оформить по-русски: «Файл Excel готов». |

Английские технические идентификаторы, API routes, названия библиотек/протоколов и разрешённые обозначения `PORTAL`, `FBS/FBO`, `GTIN`, `DataMatrix`, `PDF`, `Excel`, `API` не считаются нарушением. Других явных непереведённых английских кнопок/статусов при просмотре известных UI-файлов не выявлено; полнота для сообщений, сформированных внешними данными/непросмотренными строками не гарантируется.

## 10. Что уже реализовано

- Android приложение + API login/session и многокомпанейский tenant boundary на SQLite.
- Разделение Platform Owner и бизнес-ролей; capability permissions с индивидуальными overrides.
- Сотрудники, клиенты, операции, тарифы с историей для новых работ.
- Выработка, партии, задания/назначения, таймер, план/факт, материалы/списания.
- Сдельные salary snapshots, preview/закрытие payroll periods, блокировка работ в закрытый период и XLSX snapshot.
- Клиентские счета и payments, журнал активности/presence/chat, Android build/release workflows.
- PostgreSQL адаптер, целевые schema migrations с RLS, мигратор/валидатор и synthetic migration tests в репозитории.
- Базовые server и Android regression наборы проходят в текущей среде.

## 11. Что реализовано частично

- PostgreSQL migration/runtime groundwork есть, но текущий backend default — SQLite, production cutover не подтверждён.
- Существуют две параллельные бизнес-границы: legacy SQL endpoints и новые `/api/v3`/ledger service.
- Telegram employee IDs ещё являются persistence/API compatibility key в реальных запросах.
- Payroll закрытие/снимки есть; зарплатные выплаты и corrections остаются legacy/неполными.
- Индивидуальные permissions сосуществуют с fallback проверками ролей.
- История тарифов реализована в доменном слое, UI редактирования версий неполон.
- Пользовательские строки в основном русские, но остались отдельные англоязычные labels.
- Есть schema основы для invitations/access requests, но roadmap отмечает неполный пользовательский процесс.

## 12. Чего нет / не подтверждено

- Подтверждения фактического production PostgreSQL endpoint/schema/backend в текущей среде.
- Полного payroll payout/correction/reopen workflow в production ledger.
- Завершённого end-to-end onboarding/invite flow, PDF payroll documents и полного UI истории тарифов.
- Telegram bot runtime в этом репозитории.
- Отдельного web app (веб assets здесь — Android WebView).
- Актуального live PostgreSQL baseline в текущем checkout/окружении.

## 13. Технический долг

- Дублирующие legacy SQL и production repository/ledger модели усложняют единый source of truth.
- Telegram названные поля остаются business IDs, несмотря на удалённый bot runtime.
- Сессионный bearer token обычного пользователя хранится в SQLite открытым; надо спланировать hash-at-rest без потери revoke/lookup.
- Разрозненные SQLite и SQL migration versioning требуют единого проверяемого migration ordering/registry.
- В коде UI присутствуют англоязычные status/role/product terms.
- В backend tests есть предупреждения устаревающего `datetime.utcnow()`.
- Роли/capabilities поддерживают fallback path, создавая риск разных решений на соседних маршрутах.
- Подтверждение backup/restore, production DB grants, external environment secrets и TLS deployment не может быть получено из локального source audit.

## 14. Telegram legacy — итоговая disposition

- **KEEP:** миграционный путь SQLite, исторические отчёты/объяснение происхождения данных, совместимые fixture тесты — до завершения сверки.
- **MIGRATE:** все Telegram-named DB/API mappings на employee identity, сохранив исходные ID как migration mapping и не меняя исторические строки/суммы.
- **REMOVE:** активные Telegram SDK/handlers/polling/token/API URL/Termux runtime элементы — в проверенном checkout их нет; внешнюю инфраструктуру не трогать без инвентаризации.
- **INVESTIGATE:** фактический prod backend/SQLite storage, legacy SQL usage, старые Android версии, содержимое внешних systemd/VPS env и все оставшиеся внешние ссылки по полному deployment inventory.

## 15. Security risks

1. Default SQLite/development configuration и `start_portal_app.sh` не сами по себе production hardening; deployment должен принудительно задавать production env, HTTPS proxy/host policy и защищённые пути хранения.
2. Обычные bearer sessions сохраняются открытым token в БД; компрометация DB раскрывает активные сессии.
3. PIN минимум 4 символа; локальный login rate limiting/lockout в проверенной структуре явно не подтверждён.
4. Production PostgreSQL safety зависит от ролей без BYPASSRLS/SUPERUSER, protected company context и привилегий на control DB. Нужна сверка реальных grant-ов.
5. APK/рабочая сборка присутствует как untracked artifact; перед публичной раздачей проверить подпись, endpoint и канал происхождения артефакта.
6. Секреты внешнего VPS/CI не проверялись на доступность/ротацию, их значения намеренно не читались.
7. `AndroidManifest.xml` задаёт `allowBackup=true`; проверить, соответствует ли допустимая backup политика устройству с bearer session.

## 16. Migration risks

1. Исторические employee/payment/work records keyed по `telegram_id`; неверное отображение в employee_id может смешать/потерять payroll и назначения.
2. Имеются физическая SQLite schema и JSON production ledger одновременно. Импорт должен покрывать обе и сохранять snapshot/ID/денежные значения без повторного тарифицирования.
3. Schema scripts зависят от порядка, маркеров и динамической RLS policy. Применение частичной цепочки оставляет runtime непригодным.
4. Исторические SQLite source могут быть реальными/живыми; мигрировать только согласованные offline copies с верификацией checksum и rollback plan.
5. Sequence, timezone, денежная точность и legacy textual joins требуют reconciliation; документы отмечают, что sequence может не откатываться вместе с транзакцией.
6. Закрытые payroll snapshots и инвойсные суммы должны сохраниться как факты; не пересчитывать исторические суммы актуальными тарифами.
7. SQLite file-per-company и PostgreSQL RLS имеют разные trust boundaries; нельзя включать централизованный DB runtime без теста старых API маршрутов, privilege matrix и tenant collision cases.

## 17. Список файлов, которые вероятно потребуется менять в 3.2

Это предварительный список по текущим найденным границам, а не план уже внесённых изменений:

- `server/portal_app_server.py` — legacy API/auth, employee identity, SQL маршруты и единый tenant-aware repository boundary.
- `server/portal_tenancy.py`, `server/portal_postgres.py`, `server/portal_config.py` — фактический backend/cutover, connection scope и configuration hardening.
- `server/production_service.py`, `server/production_repository.py`, `server/production_migrations.py`, `server/production_permissions.py` — payroll payout/correction/locking и legacy mapping.
- `server/migration_import.py`, `server/migration_validation.py`, `server/migrate_sqlite_to_pg.py`, `server/migration_context.py`, `server/migrations/*.sql` — только если утверждён schema/data transition.
- `server/test_portal_app_server.py`, `server/test_portal_tenancy.py`, `server/test_production.py`, `server/test_migration_*.py`, `server/test_postgresql_*.py` — regression/data migration/security coverage.
- `android_src/app/src/main/assets/core.js`, `app.js`, `screens.js`, `production.js`, возможно `index.html` — русификация UI и новые payroll/API flows.
- `android_src/app/src/main/java/ru/portal/app/MainActivity.java`, `AndroidManifest.xml`, `app/build.gradle`, `release.properties` — если потребуются token storage, endpoint или release policy изменения.
- `.env.example`, `server/start_portal_app.sh`, `.github/workflows/server-tests.yml`, `android-build.yml`, `android-release.yml`, deployment/runbook документы — конфигурация/CI/release/cutover.

## 18. Рекомендуемый порядок изменений

1. Зафиксировать production facts: endpoint/backend, schema version, сохранённые резервные копии и реальные внешние runtime env (без публикации секретов).
2. Утвердить data model/source of truth для employee identity, work/payroll facts и список legacy compatibility клиентов.
3. Составить read-only reconciliation для Telegram ID → employee ID и SQLite → целевая схема; согласовать исторические несопоставленные/дублирующиеся записи.
4. Утвердить целевой PostgreSQL migration order/маркер и privilege/RLS матрицу; проверить её на изолированных synthetic DB, не production.
5. Реализовать/проверить переход API repository boundary и совместимость UI так, чтобы старые данные не пересчитывались.
6. Отдельно определить payroll payments, corrections, reopen/locking и неизменяемость закрытого снимка до разработки.
7. Локализовать весь пользовательский UI/status/error catalog на русский и добавить проверку локализации.
8. Запустить offline server + Android baseline; затем PostgreSQL integration/migration/restart/backup-restore tests в dedicated environment.
9. Только после сверки и подтверждённого approval выполнять production cutover отдельным этапом с freeze, backup, checksum, reconciliation и rollback.

## 19. Блокеры

- Нет подтверждённых фактических production backend/DB details из текущего checkout; без них нельзя безопасно определить целевую последовательность cutover.
- Не установлен канонический источник payroll payments и соответствие старых `telegram_id` новым employees по production данным.
- Live PostgreSQL suite требует выделенной synthetic/VPS среды, отсутствующей в текущем baseline.
- Нужны решения по semantics payroll corrections и выплат: кто/когда может корректировать, как закрытие откатывается/компенсируется и как хранить audit.
- Перед миграцией необходимы инвентаризация и проверка существующих внешних deployment secrets, backups и доступов (без раскрытия значений).

**Аудит остановлен здесь. Реализация PORTAL 3.2 не начиналась.**
