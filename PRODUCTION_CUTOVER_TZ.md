# PORTAL — Production Cutover ТЗ

Статус: ускоренная подготовка B003. Production ещё не переключён.
Главный принцип: ускоряем автоматизацией и параллельными проверками, но не допускаем двух одновременно пишущих серверов.

## 1. Критерии готовности VPS
- PostgreSQL работает только на loopback/private interface и не публикуется наружу.
- Runtime tenant/control роли: без SUPERUSER, BYPASSRLS, CREATEROLE, CREATEDB.
- Tenant не владеет таблицами и не читает portal_company_keys.
- Все company-scoped таблицы имеют ENABLE + FORCE RLS и защищённый company context.
- Все Stage 4B/4C миграции применяются с ON_ERROR_STOP и проверяются тестами.
- Production API работает отдельным systemd service под непривилегированным пользователем.
- API слушает loopback; внешний доступ только через HTTPS reverse proxy.
- EnvironmentFile вне Git, права 0640 или строже; секреты не логируются.
- Автозапуск, restart, journal и health endpoint проверены.
- Диск/RAM имеют безопасный запас.

## 2. HTTPS и внешний адрес
- Выбран стабильный production hostname PORTAL.
- DNS указывает на VPS.
- TLS-сертификат действующий и автоматически обновляемый.
- HTTP перенаправляется на HTTPS; API напрямую наружу не публикуется.
- PORTAL_PUBLIC_API_URL содержит только https:// URL без credentials/query/fragment.
- Проверены TLS, hostname, срок сертификата и внешний /api/ping.
- До выполнения этих пунктов production PostgreSQL gate не снимается.

## 3. Android / GitHub Actions
- Staging package: ru.portal.app.staging; устанавливается рядом с рабочим ru.portal.app.
- Staging использует только тестовый transport и real-copy PostgreSQL.
- Release запрещает cleartext HTTP.
- Release URL задаётся через GitHub Secret PORTAL_PUBLIC_API_URL и обязан быть HTTPS.
- Постоянный Android signing key хранится только как GitHub Secret/защищённая резервная копия.
- Пароли keystore и alias не хранятся в Git.
- GitHub Actions проверяет security policy до сборки.
- Release workflow проверяет подпись через apksigner.
- APK публикуется как artifact вместе с SHA-256.
- versionName/versionCode/buildNumber уникальны; -dev запрещён для release.
- Перед финалом staging APK проходит login, clients, operations, work, payroll и restart test.

## 4. Данные и финальная миграция
- До cutover рабочий телефон остаётся источником истины.
- Перед финальным snapshot новые записи на телефоне останавливаются.
- Проверяется отсутствие SQLite WAL/SHM либо выполняется корректный SQLite backup.
- Финальный portal.db копируется read-only; фиксируются размер и SHA-256.
- Копия хранится минимум в двух местах, одно — вне VPS.
- Выполняются PRAGMA integrity_check и migration dry-run.
- Production PostgreSQL создаётся свежим; импорт выполняется одной транзакцией.
- При любой ошибке импорт rollback; переключение запрещено.
- Сверяются row counts всех исходных таблиц, ключевые ID и денежные итоги.
- Проверяются users, clients, operations, products, tariffs, work, payroll, invoices/payments.
- После импорта выполняется независимая validation, не только importer self-check.

## 5. Cutover
- Снять финальный backup телефона и зафиксировать его hash.
- Импортировать snapshot в production PostgreSQL.
- Повторить validation и RLS/security tests.
- Запустить production API за HTTPS.
- Проверить API с компьютера и staging Android.
- Собрать подписанный release APK в GitHub Actions.
- Проверить SHA-256, подпись, package id, versionCode и HTTPS URL.
- Установить release как обновление рабочего PORTAL только после GO-контроля.
- Выполнить login и минимальный production smoke test.
- Создать одну контролируемую запись и убедиться в PostgreSQL persistence.
- Перезапустить API и повторно проверить запись.
- После cutover старый телефонный server не принимает новые записи.
- Одновременная запись в SQLite и PostgreSQL запрещена.

## 6. Backup и rollback
- Перед cutover: SQLite snapshot + pg_dump -Fc.
- После успешного импорта: новый pg_dump -Fc.
- Restore тестируется в отдельной БД.
- При ошибке до первой production-записи: вернуть приложение на телефонный server.
- При ошибке после production-записей: сначала учесть новые VPS-записи; слепой откат запрещён.
- Старый телефонный DB/server сохраняется как rollback checkpoint до окончания наблюдения.

## 7. Финальные GO/NO-GO
GO только если: GitHub CI зелёный; HTTPS зелёный; signed APK зелёный; final DB validation зелёная; RLS зелёный; backup+restore зелёный; Android smoke зелёный.
NO-GO при любом mismatch данных, ошибке RLS, unsigned/debug release, HTTP production URL, отсутствующем backup или невозможности restore.
Телефон можно отключить от компьютера только после финального snapshot, успешного production import, Android cutover и контрольной проверки persistence.
Финальная фраза разрешения: **✅ ТЕЛЕФОН МОЖНО ОТКЛЮЧАТЬ ОТ КОМПЬЮТЕРА**.


## Build numbering and VPS-first rule — 2026-09-27

- User-facing PORTAL builds use decimal sequence: 3.0, 3.1, 3.2 ... 3.9, 4.0.
- Android versionCode remains a monotonically increasing integer; buildNumber/versionName expose the decimal PORTAL build.
- Every new build increments exactly one step; a reused build number is forbidden.
- The purchased VPS is the primary integration environment after local unit/security checks. Do not repeat the same full integration suite on the phone server.
- The Android phone is a client after production cutover, not an application/database server.
- Until final cutover, the phone SQLite is the authoritative live source and is used for the final write-freeze snapshot.
- Production cutover requires HTTPS, a verified final import, backup/restore proof and explicit approval before accepting real writes.
- Never accept simultaneous production writes on the old phone SQLite and the new PostgreSQL service.

## Android fullscreen requirement

- PORTAL Android uses immersive sticky fullscreen mode.
- The system navigation/status UI may be temporarily revealed by Android gestures but must not permanently cover PORTAL controls.
- Returning focus to PORTAL must restore immersive mode.
- CI must reject removal of the fullscreen native-shell flags.
