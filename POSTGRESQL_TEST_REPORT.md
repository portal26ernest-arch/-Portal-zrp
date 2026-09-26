# PORTAL — изолированный тест API с PostgreSQL

Дата: 25.09.2026. Ветка `portal-next-b003`; исходный HEAD `136a157dcb96340623b2931457c020cead2cff86`. Рабочая база телефона и реальные данные не открывались и не импортировались. Изменения на VPS ограничены тестовым экземпляром.

## Аудит и реализация

- SQLite сохраняется в `portal_tenancy.py` для прежнего режима: файловые базы компаний, создание схемы и служебной базы. Старые маршруты `portal_app_server.py` использовали `sqlite_master`, `PRAGMA`, `BEGIN IMMEDIATE`, `lastrowid`, `INSERT OR ...` и `COLLATE NOCASE`. Производственный `Repository` уже имел часть PostgreSQL SQL, но API, входы, сессии и управление компаниями ещё не имели рабочего PostgreSQL-подключения.
- Выбор backend выполняется через `PORTAL_DB_BACKEND`; PostgreSQL допускается сейчас только с `PORTAL_ENV=test`. Два DSN читаются из защищённого окружения: `PORTAL_DATABASE_URL` для tenant-роли и `PORTAL_CONTROL_DATABASE_URL` для служебной роли. SQLite-код не удалён. При ошибке PostgreSQL нет автоматического перехода на SQLite.
- `portal_postgres.py` адаптирует соединение, параметры и строки результата к текущему API; транзакция завершается commit/rollback с закрытием соединения. Конфигурация компании повторно привязывается после каждой транзакции. В `portal_app_server.py` перенесены необходимые старые SQL-формы и добавлена проверка схемы, роли, RLS и локального адреса при запуске.
- `postgresql_runtime.sql` добавляет недостающие поля и таблицу расхода материалов, значения `company_id` по контексту, защиту истории и маркер версии. `postgresql_rls_context.sql` сохраняет принудительный RLS и привязывает компанию к ключу служебной роли через `pgcrypto`; изменение одного `portal.company_id` больше не открывает другую компанию. Ключи хранятся только в PostgreSQL, tenant-роль не может их читать.

## Изолированное развёртывание

- Код: `/srv/portal/pg-test/server`; отдельный `venv`; сервис `portal-pg-test.service`; конфигурация `/etc/portal/pg-test.env` с правами `root:portal`, `0640`. Значения DSN, ключей, PIN и токенов в отчёте отсутствуют.
- Отдельная PostgreSQL-база `portal_test_api_20260925` и роли `portal_test_tenant_20260925`, `portal_test_control_20260925`. Обе роли без `SUPERUSER` и `BYPASSRLS`, не владеют таблицами. Tenant-роль не читает ключи контекста, Platform Owner и platform audit.
- Тестовый API слушает только `127.0.0.1:8766`. Прежний тестовый SQLite API продолжает слушать `127.0.0.1:8765`. PostgreSQL слушает только `127.0.0.1:5432` и `::1:5432`; правил UFW для 5432 и 8766 нет. Доступ SSH — через проверенный IPv6-адрес VPS.
- Четыре SQL-файла применены к пустой проверочной базе в нужном порядке; дополнительная runtime/RLS-миграция повторно применена успешно. В базе тестового API: 27 таблиц, 20 таблиц с `FORCE ROW LEVEL SECURITY`, 20 политик. После окончательных тестов там 7 исключительно искусственных компаний, включая исходную компанию №1, и 6 искусственных записей старой выработки.

## Фактические проверки

- Локальный серверный набор: **75 tests, OK, 1 skipped**. Пропущен только opt-in тест, который запускается отдельно на VPS. Синтаксическая проверка `compileall` успешна.
- Реальный PostgreSQL + HTTP тест на VPS: **1 интеграционный сценарий, OK** на окончательном коде. Он проверил `/api/ping`, входы A/B, чтение и создание клиента/операции, обновление и архивирование клиента, физическое удаление отдельной временной записи справочника, партии, задания, выработку, неизменность ранее начисленных зарплаты/выручки после новой версии тарифа, счёт и оплату. Финансовую или производственную историю тест не удалял.
- Изоляция A/B проверена через API и напрямую под tenant-ролью: чтение, изменение, удаление чужой записи и вставка с чужим `company_id` запрещены; запрос без контекста не видит строки; подмена заголовка, query/body и простая подмена PostgreSQL GUC не открывают другую компанию. Вход с неверным ключом контекста отвергнут.
- Транзакция с искусственной записью откатилась; защитный триггер запретил удаление выработки и транзакция также откатилась. После штатного перезапуска `portal-pg-test.service` `/api/ping` ответил, партии и выработка сохранились в PostgreSQL. Спонтанных перезапусков сервиса нет.
- `git diff --check` и поиск случайных секретов выполнены; реальные DSN/PIN/токены не добавлены в Git. Старые незакоммиченные APK/SHA оставлены вне изменений.

## Перед безопасным переносом копии рабочей SQLite

1. Получить неизменяемые резервные копии всех телефонных/tenant/control SQLite и сверить фактические старые таблицы, поля, связи, суммы и последовательности ID с PostgreSQL-схемой. Тестовая база содержит только искусственные данные и этого не заменяет.
2. Офлайн-импортёр и валидатор теперь привязывают компанию через защищённый `portal_bind_company`, не возвращая секрет ключа приложению. Прежняя установка одного `portal.company_id` удалена из этих путей. Синтетический live-импорт и выравнивание identity sequences проверены ниже; следующий барьер — испытание на копии фактической структуры и запуск полного CLI с отдельным LOGIN DSN.
3. Проверить PostgreSQL backup и восстановление в ещё одну тестовую БД, конкурентные записи, нагрузку, полный набор старых API и Android/PC сценариев с копией реальной структуры. Отдельно проверить денежные итоги, тарифы, номера партий, счета, платежи, activity и историю аудита.
4. Настроить домен и HTTPS отдельным этапом. Только после успешной сверки копии, восстановления backup и клиентских тестов рассматривать снятие программного запрета PostgreSQL в production и согласованный cutover. До этого телефон остаётся действующей системой.

## Состояние Git

`main` не изменялся. Commit, push, merge, rebase, reset и удаление веток не выполнялись. Изменены `.env.example`, `SERVER_MIGRATION_RUNBOOK.md`, серверные config/tenancy/API/repository/migration файлы, добавлены PostgreSQL-адаптер, две SQL-миграции и тесты. Рабочая SQLite-база телефона не затрагивалась.

## Продолжение подготовки, 25.09.2026

Добавлен `server/migration_context.py`: отдельная миграционная роль создаёт ключ компании в подготовленной БД и привязывает транзакцию через `portal_bind_company` без чтения секретного значения в Python. Валидатор использует существующий ключ только в транзакции чтения. `server/migration_import.py` и `server/validate_pg_migration.py` больше не полагаются на простую установку `portal.company_id`. Добавлены два локальных контрактных теста. Серверный набор на этой промежуточной точке: **77 tests, OK, 1 skipped**; Python `compileall` и `git diff --check` прошли. Следующий раздел содержит результаты последующей live-проверки.

## Синтетический интеграционный тест мигратора, 25.09.2026

На VPS отдельно от работающего API создана пустая БД `portal_migration_synthetic_20260925` и тестовая роль `portal_migration_synthetic_20260925` без LOGIN, `SUPERUSER` и `BYPASSRLS`. Применены четыре SQL-миграции. Тест запускался локально на VPS с `SET ROLE` этой роли; `row_security_active('portal_production')` подтвердил действующий RLS. Исходником была только вновь созданная SQLite с искусственными клиентом, операцией, выработкой, счётом, оплатой, партией, заданием, версией тарифа и финансовыми записями. Существующая БД тестового API не менялась.

Интеграционный импорт строк и денежных итогов прошёл; отдельно прошли чтение под защищённым контекстом, отсутствие данных A в контексте B, отказ чужой вставки, rollback ошибочной транзакции и сохранение исторической суммы. Read-only валидатор сверил строки тестовой PostgreSQL БД с синтетической SQLite-копией; намеренное расхождение суммы было обнаружено. Проверено повышение identity sequences после импорта: следующий ID больше импортированного. **3 отдельных live PostgreSQL сценария прошли** (импорт, валидатор, генераторы ID).

По ходу теста исправлены несовместимость числовых форматов SQLite/PostgreSQL при сверке, значение `user_limit` для старой основной компании и выравнивание identity sequences. Неизменяемость исходной SQLite подтверждена открытием `mode=ro`. Проверялось ядро `transfer_control`/`transfer` под непривилегированной ролью; CLI `--apply` с отдельным LOGIN DSN и полный импорт копии фактической телефонной структуры пока не проверялись. Генераторы PostgreSQL не откатываются транзакционно, поэтому при неуспехе требуется новая пустая тестовая БД. Production, телефонная БД и `main` не затрагивались; реальных данных в PostgreSQL нет.

Итоговая локальная проверка после этих исправлений: **80 серверных тестов, OK, 4 skipped** (три opt-in сценария PostgreSQL мигратора и один opt-in сценарий API запускаются на VPS отдельно); все три сценария мигратора на VPS прошли. `compileall`, `git diff --check` и поиск случайных DSN/private keys в изменённых миграционных файлах и отчётах прошли. Никакого commit, push или merge не выполнялось.
# PORTAL: завершение синтетической проверки этапа 4B

Дата: 26.09.2026. Проект: `C:\Users\darta\Documents\PORTAL-Android`.
Ветка `portal-next-b003`, HEAD `136a157`. Commit/push не выполнялись.
Production, рабочая БД телефона и существующие данные не изменялись.

## 1. SSH

Подтверждённый пользователем ED25519 host key сохранён отдельно в
`C:\Users\darta\Documents\PORTAL-Android\infra_vps_01_known_hosts`:
`SHA256:1rAqR6zXQkP4U0KXvasCwZvHnsITSSjxPzuVCwKFQGc`.
При получении ключа его SHA-256 сравнивался с этим значением до сохранения.
Приватный ключ и глобальный known_hosts не изменялись. Неподтверждённые ключи
отвергаются (Paramiko RejectPolicy); обхода проверки подлинности нет.

Рабочий доступ с Windows: root по IPv6 `2a03:6f00:a::1:f426`, порт 22,
существующий `infra_vps_01`. В финале три последовательных успешных входа,
banner `SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13.19`, команда `id -un` возвращает
root с exit code 0. Использован Python/Paramiko в отдельном локальном каталоге
инструментов; системные SSH-настройки не менялись.

IPv4 `178.209.127.247:22` остаётся ненадёжным. Одновременная диагностика через
IPv6 показала завершённый TCP handshake, затем многократную отправку сервером
43-байтового banner без подтверждения клиента. Сбой находится на пути доставки
после TCP handshake и до аутентификации, а не в проверке приватного ключа.
Конкретный фильтр/узел потери пока не установлен; утверждать, что виноват
именно AdGuard, нельзя. AdGuard продолжает работать, исключение не менялось.

Дополнительное отдельное ограничение: Windows OpenSSH отвергает ACL существующей
копии приватного ключа как слишком широкие. ACL и ключ оставлены без изменений.
Paramiko успешно аутентифицировался тем же ключом. Таким образом, безопасный
рабочий SSH-доступ получен, но штатный `ssh.exe` по IPv4 полностью не восстановлен.

## 2. VPS и сервисы

- Ubuntu 24.04.5; sshd активен, `sshd -t` успешен, слушает IPv4/IPv6 порт 22.
- UFW активен и разрешает 22; защита, порты, конфигурация SSH и firewall не менялись.
- `portal-pg-test.service`: active/running, ExecMainStatus=0, NRestarts=0,
  активен с 25.09.2026 19:43:01 UTC. Reload/restart существующих служб не выполнялись.
- `http://127.0.0.1:8766/api/ping`: HTTP 200, `ok=true`, build
  `2026.09.25-a003-stage3-dev`, `setup_required=true`.
- Прежний тестовый SQLite API остаётся на 127.0.0.1:8765.
- PostgreSQL доступен только на 127.0.0.1/::1:5432; тестовый API наружу не опубликован.
- На диске около 45 GiB свободно; доступная память около 3.3 GiB.
- API/config/tenancy/adapter/production Python-файлы существующего сервиса побайтно
  совпадают с локальными. Четыре старых CLI-файла в `/srv/portal/pg-test/server`
  отличаются; актуальные CLI проверялись отдельно в `/tmp/portal-migration-full-20260926/server`.
  Это не изменяет работающий API; старые CLI не использовались для новой проверки.

## 3. PostgreSQL и изменения тестового окружения

PostgreSQL 16.15. Существующая `portal_test_api_20260925` сохранена:
27 таблиц public, 20 FORCE RLS, 7 компаний — соответствует предыдущему отчёту.
Существующая `portal_migration_synthetic_20260925` не очищалась и не переиспользовалась.

Созданы только новые тестовые БД:

- `portal_test_migration_full_20260926` — полный импорт двух искусственных компаний;
- `portal_test_migration_full_20260926_rollback` — испытание отказа импорта;
- `portal_test_migration_full_20260926_restore` — восстановление backup.

Созданы три отдельные LOGIN-роли migration/tenant/control с суффиксом
`full_20260926`, без SUPERUSER, BYPASSRLS и владения таблицами. Исправлены права
именно нового тестового fixture: migration получила EXECUTE защищённых функций
RLS, control — USAGE/SELECT identity sequences собственных control-таблиц.

Подготовлены отдельные staged-код, venv с psycopg 3.3.6, искусственные SQLite-копии
и защищённый файл DSN/PIN под `/tmp/portal-migration-full-20260926`.
Секреты не включены в отчёт или Git. Копии прежних заменяемых staged-файлов сохранены.
Существующие сервисные файлы/venv и БД не заменялись. Тестовые БД и артефакты
оставлены для проверки; автоматического DROP/очистки не было.

## 4. Полная тестовая SQLite → PostgreSQL миграция

`server/test_migration_full_vps.py` подготовил platform SQLite и две tenant SQLite.
`server/test_migration_full_cli.py` выполнил семь независимых проверок:

1. CLI dry-run и намеренная ошибка NOT NULL во второй компании при `--apply`.
   Все control/tenant таблицы и ключи контекста в rollback-БД остались пустыми.
2. Настоящий CLI `--apply` через migration LOGIN DSN: `IMPORTED_AND_VERIFIED`.
   Импортированы две компании, по 20 tenant-таблиц, control-данные и производственный ledger.
3. Независимый CLI-валидатор подтвердил строки и суммы; намеренная подмена суммы
   в отдельной искусственной копии обнаружена.
4. Все три LOGIN-роли проверены настоящими подключениями; 13 identity sequences
   выровнены, следующие ID больше импортированных.
5. FORCE RLS, отсутствие доступа без контекста, запрет чужой вставки/изменения,
   запрет подмены company GUC, недоступность секретов tenant-роли, неизменность
   истории и транзакционный rollback подтверждены.
6. `pg_dump -Fc` и `pg_restore --exit-on-error` в отдельную restore-БД прошли;
   восстановленная БД повторно сверена с исходными SQLite.
7. Отдельный API-процесс на 127.0.0.1:8767 выполнил входы импортированных пользователей
   A/B, изолированное чтение, отказ подмены компании, создание записи, повторный
   запуск процесса и проверку сохранности записи/сессии/исторических сумм.
   Этот процесс завершён после теста; системный сервис на 8766 не перезапускался.

SHA-256 всех трёх исходных SQLite совпадает до и после тестов. У обеих компаний
legacy salary=7.05, revenue=17.25; ledger salary=705, revenue=1725 сохранены.
После API-проверок в основной новой БД 2 компании, 2 work_log и 30 ledger-записей
(включая добавленные API события); на момент импорта ledger содержал по 13 строк.

Результаты на VPS:
`/tmp/portal-migration-full-20260926/results-1790445168394990699/`.
Локальные копии безопасных отчётов лежат рядом с этим документом.

## 5. Автоматические тесты

| Проверка | Результат |
|---|---|
| Windows, штатный серверный unittest набор | 87 обнаружены; 76 passed, 11 opt-in skipped; OK, 58.643 s |
| VPS Linux, тот же набор с PORTAL_TEST_HTTP=1 | 87 обнаружены; 76 passed, 11 opt-in skipped; OK, 60.000 s |
| Новый полный PostgreSQL/CLI/API набор отдельно | 7/7 passed, 5.406 s |
| Синтаксис всех 27 server Python-файлов | OK, без создания pycache |
| git diff --check | OK |

11 пропусков общего discovery — 7 выполненных отдельно новых тестов и 4 прежних
opt-in теста, привязанных к старым заполненным тестовым БД/сервису. Последние не
перезапускались в текущем заходе; их результат 25.09.2026 сохранён в прежнем
POSTGRESQL_TEST_REPORT.md. Основные сценарии миграции, ролей, RLS, rollback и
повторного запуска API вновь проверены новым изолированным набором.

Дополнительный Windows-прогон с реальными loopback HTTP-соединениями не прошёл:
42 ошибки ConnectionResetError/WinError 10054. Сброс воспроизведён также на отдельном
минимальном HTTP-сервере без кода PORTAL. Это открытая проблема локального сетевого
окружения; она не скрыта пропуском тестов и не исправлялась изменениями PORTAL.
На целевой Linux-системе тот же HTTP-набор прошёл. Предупреждения datetime.utcnow
в старых тестах не влияют на результат.

## 6. Файлы и Git

Изменения этого продолжения:

- `.gitignore`: точечные исключения `infra_vps_01` и `infra_vps_01_known_hosts`;
- `server/test_migration_full_vps.py`: недостающие права новых тестовых LOGIN-ролей;
- новый `server/test_migration_full_cli.py`: полный однократный интеграционный набор;
- `SERVER_MIGRATION_RUNBOOK.md`: проверенная процедура и ограничения повторного запуска;
- `POSTGRESQL_TEST_REPORT.md`: актуальные результаты;
- отдельный локальный `infra_vps_01_known_hosts`: подтверждённый host key, вне Git.

Приватный ключ не изменён. Все ранее существовавшие незакоммиченные файлы сохранены.
Итог: 14 tracked modified и 14 untracked; SSH-файлы игнорируются. APK/SHA сохранены.
В staging index ничего не добавлялось, ветка/HEAD прежние, commit/push не выполнялись.

## 7. Оставшиеся вопросы и готовность

Синтетическая часть этапа 4B, включая полноценный CLI с LOGIN DSN, завершена и
технически готова к отдельному коммиту кода/тестов/документации без SSH-материалов
и посторонних APK. Коммит не выполнен.

Это не означает готовность production-переноса. Не получены и не испытывались
копии реальной телефонной БД, не выполнялись Android/PC клиентские проверки на
таких данных, нагрузка, HTTPS/cutover. Программный production gate сохранён.

Отдельно остаются ненадёжный IPv4 SSH, отказ Windows OpenSSH из-за ACL ключа и
сбросы локального HTTP в Windows. Доступ по IPv6 позволил полностью провести
VPS-проверки, но не устранил эти проблемы. Для дальнейшей IPv4-диагностики нужны
синхронные трассы на стороне Windows/сетевого фильтра; отключать AdGuard или
менять серверную защиту без доказанной причины не требуется.



## Stage 4C real phone copy rehearsal — 26.09.2026

- Verified phone SQLite copy: 41 application tables; integrity_check=ok.
- Lossless import into isolated PostgreSQL completed. Independent validation: 41 tables, 0 row-count mismatches; work_log salary=6650, direct_cost=0, revenue=0.
- Stage 4C compatibility schema adds 23 phone-runtime tables and required legacy columns.
- Security hardening: all Stage 4C tenant policies use portal_current_company(); raw current_setting-based Stage 4C policies are prohibited by a static regression test.
- Clean schema smoke from an empty PostgreSQL database with all five migrations: 50 base tables, 43 FORCE RLS tables, 41 protected portal_company policies, 0 raw current_setting policies.
- Isolated real-copy API reached HTTP 200 on /api/ping and saw the imported users. The API remained loopback-only.
- Real-copy pg_dump -Fc backup created with mode 0600 and restored into a separate database. Restored key counts match: app_users=4, products=47, tariff_versions=403, portal_manager_service_rates=429, work_log=8, salary=6650. Restored Stage 4C policies: 23 protected, 0 raw.
- VPS network remains fail-closed for data services: PostgreSQL and test APIs listen on loopback. UFW already permits 80/443, but no reverse proxy/TLS service is installed yet.
- Android already supports a configurable server URL and HTTPS. Current manifest still permits cleartext HTTP for the transitional phone/test setup; production APK must disable cleartext after HTTPS is available.
- Production cutover has NOT occurred. Final phone write freeze, fresh SQLite snapshot, final import/validation, HTTPS endpoint and Android production switch remain mandatory.


## Android staging and production-readiness pass — 27.09.2026

- Installed phone package is ru.portal.app version 2026.09.24-b002 (versionCode 2), currently debuggable.
- The installed app has no saved portal_settings/server_url override, so it uses its built-in default. Current source default remains the transitional phone endpoint http://127.0.0.1:8765.
- ADB reverse plus an SSH local forward was validated as a safe staging transport to the isolated real-copy API without publishing PostgreSQL or the API to the Internet.
- Android source now separates transport policy by build type: release disables cleartext HTTP; debug/staging permit it for local testing. Staging uses applicationIdSuffix .staging and can coexist with the working app.
- A static Android build-security regression test passes.
- Full Android APK staging build is not yet available on this workstation because a complete JDK/Gradle/Android build toolchain is not installed. Existing UI Playwright test is also opt-in here because the project has no Node package manifest and Playwright is not installed.
- Production signing is intentionally not configured or generated during migration preparation.
- PostgreSQL runtime-role audit on the real-copy DB: tenant/control are not superuser, not BYPASSRLS, not CREATEROLE/CREATEDB; tenant cannot SELECT portal_company_keys; tenant owns zero tables; 43 tables have FORCE RLS.
- VPS health: PostgreSQL and isolated real-copy API active, no recent service errors, approximately 45 GiB disk free and 3.2 GiB memory available at the time of the check.
- portal_app_server PostgreSQL schema validation was refactored so loopback binding is a general PostgreSQL requirement while the portal_test_ database-name guard is test-specific. The separate portal_config production PostgreSQL gate remains closed.
- Full Python regression after the refactor: 91 tests, OK, 11 opt-in skipped.
- Production remains blocked pending HTTPS/domain, complete Android staging, release signing/build validation, final phone write freeze and fresh migration.
