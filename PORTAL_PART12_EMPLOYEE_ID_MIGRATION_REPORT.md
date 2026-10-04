# PORTAL Part 12 / Roadmap 102 — employee_id migration report

## Повторная независимая проверка — 2026-10-04

Эта проверка выполнена по прямому поручению владельца после исходного `PASS` от 2026-09-30 и относится к текущей ветке `codex/part12-employee-id-rerun-20261004`, исходный HEAD `8246b13ce0154e82067dc2d65829da699910dfd8`. Она заменяет только статус и evidence от 2026-09-30 для текущей линии; исторический список изменений ниже относится к первичной миграции.

- Полный повторный `ops/employee_identity_migration_audit.py --fail-on-p0`: **P0=0, P1=50** (41 explicit adapter, 5 import/export, 2 retained schema, 2 API compatibility guards). P2: 161 fixture/history/test/scanner references. Android/iOS/Web/Desktop runtime search не обнаружил Telegram login/SDK/account dependency; legacy fields остаются только в серверном adapter/import/schema/history boundary.
- Второй, более старый `ops/legacy_runtime_audit.py` первоначально ошибочно показал 28 прямых runtime строк, потому что не allowlist-ил централизованный identity adapter и migration boundary. Исправлены категории adapter/import/schema, тестовая инфраструктура перестала считаться product runtime, добавлены проверки Desktop C#/.NET paths. Повторный gate: `runtime_direct_telegram_id=0`, `runtime_bridge=50`, `forbidden_external_runtime=0`.
- Схема/продуктовый runtime в этом re-verification не менялись: подтверждены прежние `employee_id` identity map, company-scoped FK/RLS и additive legacy storage. Новых P0 runtime defects не найдено. Перегенерирована карта `PORTAL_EMPLOYEE_ID_MIGRATION_MAP.md`.
- Server SQLite/application discovery на текущем HEAD: **335 tests OK, 50 skipped**. Skip breakdown: 37 `requires disposable local PostgreSQL fixture`; 7 `requires dedicated synthetic full-CLI VPS databases`; 3 `requires dedicated empty synthetic PostgreSQL database`; 1 `requires isolated PostgreSQL test VPS`; 1 `requires isolated PostgreSQL and browser runtime`; 1 `ReportLab runtime dependency is not installed`. Shared Android/Web browser suite: **48/48 OK**. Совместные release/identity audit suites: **12/12 OK**. YAML parse четырёх затронутых workflow и `git diff --check`: OK.
- Локальная PostgreSQL/Docker среда отсутствует. Current-commit PostgreSQL/RLS, Android CI и iOS parity/build gates ожидают push этой ветки и должны быть записаны после GitHub Actions. Ранее successful disposable PostgreSQL/RLS CI от 2026-09-30 приведён ниже и не подменяет current-commit evidence.
- Новые/повторно изменённые файлы в этой проверке: `.github/workflows/android-ui-tests.yml`, `.github/workflows/ios-ci.yml`, `.github/workflows/server-tests.yml`, `.github/workflows/web-tests.yml`, `ops/legacy_runtime_audit.py`, `ops/test_release_audits.py`, `PORTAL_EMPLOYEE_ID_MIGRATION_MAP.md`, `PORTAL_MASTER_ROADMAP.md`, этот отчёт. Push/CI/SHA — заполнить по факту завершения ветки.

**Промежуточный итог:** source/runtime identity audit — PASS; финальный Roadmap 102 остаётся незакрытым до disposable PostgreSQL/RLS, Android и iOS текущей ветки CI, push и clean tracked working tree.

Дата: 2026-09-30. Ветка: `codex/part12-employee-id`.

## Git и границы работ

- Исходный HEAD текущей работы: `731531815971ac25949d3a79a80a5ba48546a5db` (`codex-finalization-megapack-part12`). Исходный checkout был чистым; ветка `assistant-part12-integration` не изменялась.
- Итоговый кодовый HEAD перед отчётом: `f43c80dbeb8ec356fbe92622f0523e3ee90a15b6`. Итоговый HEAD ветки после коммита самого отчёта определяется `git rev-parse HEAD`; точный SHA сообщается в финальном ответе (SHA коммита нельзя включить в его собственное содержимое).
- Коммиты: `9e8f962` (runtime/API), `a6f6020` (import/RLS), `f43c80d` (PostgreSQL fixture). Все отправлены в `origin/codex/part12-employee-id` без force push.
- Production, production DB, VPS, secrets, signing keys, публикация APK и телефон не затрагивались.

## Аудит Telegram identity

Повторно проверены server/backend, PostgreSQL SQL/migrations, repositories, API/auth/permissions, Android, Web/Desktop, tests/fixtures, docs, CI/scripts. Генератор `ops/employee_identity_migration_audit.py --fail-on-p0` завершился с `P0=0`; актуальная построчная карта — `PORTAL_EMPLOYEE_ID_MIGRATION_MAP.md`.

Автоматический сканер уже имел `P0=0` на исходном Part 12 HEAD, поскольку объявленный compatibility adapter исключён из P0. Ручная проверка нашла и устранила **семь фактических путей** нарушения canonical identity:

1. `canonical_employee_id` возвращал исходный legacy номер при отсутствии Stage 6 identity map.
2. `legacy_employee_id` также принимал canonical ID за legacy номер без карты.
3. `employee_catalog` выдавал raw legacy ключ как `employee_id` на старой схеме.
4. `user_catalog` делал такую же подмену для аккаунтов.
5. Публичные payroll settlement POST/GET принимали `telegram_id` и незаметно переводили его.
6. `/api/work` не отвергал переданный клиентом чужой идентификатор; теперь identity берётся только из сессии, поля `telegram_id` и `employee_id` в этом запросе отвергаются.
7. Связка `user.employee_id` и сохранённого legacy link могла расходиться; теперь mismatch закрывает доступ к identity.

После исправления P0 runtime путей: **0 найдено / 7 устранено ручным аудитом**. Android runtime, Web/Desktop runtime и CI не содержат Telegram SDK, Telegram login или требований к Telegram account. Публичные POST запросы отвергают top-level `telegram_id`; payroll GET отвергает соответствующий query parameter. Новый клиент использует серверную сессию и `employee_id`.

Остаётся **50 P1 ссылок**: 41 в явном `server/employee_identity.py` adapter, 5 в import/export boundary, 2 в legacy schema DDL, 2 в описании retained API/schema boundary. Ещё 140 ссылок относятся к тестам, фикстурам и истории (P2). Столбцы `telegram_id` физически сохранены в исторических таблицах; новая работа сохраняется через проверенное отображение `company_id + employee_id -> legacy_employee_id` до отдельного cleanup. Они не являются публичным или самостоятельным runtime идентификатором. Каталоги и сессии на немигрированной схеме теперь fail closed.

## Схема, backfill и API

Новый DDL в этой доработке не потребовался: существующая Stage 6 миграция создаёт `payroll_employee_identities`, уникальные `(company_id, employee_id)` и `(company_id, legacy_employee_id)`, composite FK к `employees`, индексы, immutable guards и FORCE RLS. Stage 8 documents и payroll settlements ссылаются на `(company_id, employee_id)` через composite FK. Столбцы legacy истории не удалялись.

Добавлен read-only preflight источника SQLite: считает карточки и ссылки из `app_users`, work, payroll, manager assignments и production progress; неоднозначные или несопоставимые ссылки завершают миграцию с таблицей и количеством строк, без персональных значений. Dry-run сообщает crosswalk counts. После Stage 6 backfill реальный import проверяет, что каждая импортированная карточка имеет company-scoped mapping; ошибка прерывает транзакцию. Повторный запуск Stage 6 остаётся идемпотентным через существующий `ON CONFLICT`.

`/api/v3/payroll-settlements` работает только с `employee_id`; `/api/work` не принимает client-supplied identity. HTTP payload больше не принимает top-level `telegram_id`. Для истории и старых SQLite записей translation разрешён только внутри явного adapter. Пользователь с чужим, отсутствующим или конфликтующим employee link не получает canonical identity. Existing Android/Web flows не менялись: они уже посылают `employee_id` или полагаются на authenticated session.

## Security и проверки

- SQLite/application: `python -m unittest discover -s server -p 'test_*.py' -q` — **299 tests, OK, 47 skipped**; повторный verbose прогон дал тот же итог. Проверены employee creation/link, work, payroll, documents, tenants, archived/inactive roles, source preflight и отсутствие записи при ошибке.
- Migration audit: `python ops/employee_identity_migration_audit.py --fail-on-p0` — **P0=0**; `python -m unittest ops.test_employee_identity_migration_audit -q` — **8 passed**.
- Android/Web Node: UI, legacy boundary, web adapter — **36/36 passed**. Пять Android CI parity checks (`build-security`, employee creation modes, native shell, legacy boundary, documents/chat) — **5/5 passed**. Исходный Part 12 staging APK уже имел успешный CI build; Android source/APK в этой доработке не менялись.
- PostgreSQL: [Web CI run 36767971434](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36767971434) — **success**, включая `documents-postgresql` и `web`. Disposable PostgreSQL 16 применил весь набор миграций и повторные идемпотентные миграции. Tests используют restricted non-superuser/NOBYPASSRLS роль, доказывают FORCE RLS на identity map, отсутствие чужих rows, отказ cross-company INSERT, разные canonical IDs при одинаковом legacy key в двух компаниях, company-scoped FK/lookup, backfill и rejection публичного legacy API. Первый run `36767574750` выявил unmapped сотрудника, которого fixture добавляла прямым SQL после миграции; fixture исправлена вызовом mapping sync, повторный run зелёный.
- Server CI: [run 36767971376](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36767971376) — **success** на Python 3.11 и 3.13 с HTTP regression suite.
- `python -m compileall -q server ops` и `git diff --check` — **passed**.

### Пропуски и точные причины

Локальный full suite включает 47 opt-in skips. В каждой строке причина относится к **каждому** тесту указанного класса/набора:

| Тесты | Количество | Точная причина локального skip |
|---|---:|---|
| Все методы `test_documents_postgresql.DocumentsPostgreSQLTest` | 34 | `requires disposable local PostgreSQL fixture`; вместо локального запуска покрыты disposable CI job. В CI два специальных метода дополнительно пропускаются по причинам `requires ReportLab real PDF PostgreSQL gate` и `Web browser gate only`. |
| Все методы `test_migration_full_cli.FullMigrationCLI` | 7 | `requires dedicated synthetic full-CLI VPS databases` |
| Все методы `test_migration_postgresql_live.SyntheticMigrationPostgreSQLTest` | 3 | `requires dedicated empty synthetic PostgreSQL database` |
| `test_postgresql_integration.PostgreSQLIntegration.test_live_api_crud_rls_and_restart` | 1 | `requires isolated PostgreSQL test VPS` |
| `test_web_postgresql_e2e.WebPostgreSQLE2E.test_disposable_postgresql_and_real_http_browser_flows` | 1 | `requires isolated PostgreSQL and browser runtime` |
| `test_documents_pdf.PdfDocumentsTest.test_real_invoice_and_closed_payroll_routes_render_and_register_test_records` | 1 | `ReportLab runtime dependency is not installed` |

Ни один тест не отключался ради прохождения. CI PostgreSQL job закрывает необходимую для item 102 RLS/backfill проверку; полный end-to-end SQLite→PostgreSQL CLI rehearsal остаётся отдельным интеграционным gate.

## Изменённые файлы

`server/employee_identity.py`, `server/portal_app_server.py`, `server/migration_import.py`, `server/migrate_sqlite_to_pg.py`, `server/test_employee_identity.py`, `server/test_portal_app_server.py`, `server/test_portal_tenancy.py`, `server/test_production.py`, `server/test_payroll_settlement.py`, `server/test_migration_import.py`, `server/test_documents_postgresql.py`, `.github/workflows/server-tests.yml`, `.github/workflows/web-tests.yml`, `PORTAL_EMPLOYEE_ID_MIGRATION_MAP.md`, `PORTAL_MASTER_ROADMAP.md`, этот отчёт.

## Остаточные риски и следующий Part

1. Исторические таблицы всё ещё физически содержат legacy key. В следующем Part после репетиции полного импорта можно добавлять `employee_id` непосредственно в оставшиеся ledger tables, backfill и composite FK, переключать storage queries, затем планировать cleanup старых колонок без потери истории.
2. Запустить полный synthetic SQLite→PostgreSQL CLI import/rollback/backup rehearsal на изолированном VPS; текущий CI доказывает PostgreSQL schema/backfill/RLS, но не весь CLI cutover.
3. Отдельно обновить устаревающие GitHub Actions Node runtime зависимости и локальную ReportLab среду; это не блокирует employee identity.

**PART 12 / ROADMAP 102: PASS** для runtime employee identity, compatibility backfill, API и PostgreSQL/RLS boundary. Полный CLI cutover rehearsal и физический cleanup legacy columns остаются следующими контролируемыми этапами.
