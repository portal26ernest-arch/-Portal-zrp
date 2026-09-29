# PORTAL Web + PostgreSQL Part 8 — verified report

Дата: 29.09.2026
Ветка: `codex-web-postgres-part8`
База Part 8: `c1a53bc` (Part 7)
Проверенный implementation HEAD до обновления отчёта: `7dd6c7c`

## Итог

Part 8 прошёл реальные staging-gates для Web → HTTP API → PostgreSQL, Documents/Excel и PDF. Production БД, production service и `/srv/portal-stage7` не изменялись: для проверок использовались одноразовые ресурсы в `/tmp` и случайные test DB/roles.

## Реальный Web/PostgreSQL E2E

Web fixture поднимался на VPS под `postgres` с БД префикса `portal_test_web_*` и ролями `portal_web_*`. API слушал loopback; Chromium запускался на Windows и подключался через SSH local tunnel. Business API не мокировался.

Подтверждено:
- вход admin и реальный `/api/v3/meta`;
- Documents list, PDF download, archive и блокировка download после archive;
- реальный XLSX file chooser → preview → explicit confirm/apply → import result download;
- synthetic импорт создал 1 запись только в company A и 0 в company B;
- forged `X-Portal-Company` для другой компании получил HTTP 403;
- logout отозвал token, повторный `/api/me` получил HTTP 401, reload вернул login;
- итог: `BROWSER_EXIT=0`, `FIXTURE_VERIFIED=True`, `CLEANUP_COMPLETE=True`.

Первый прогон выявил дефект самого Playwright-test: ожидаемые 403/401 ошибочно считались console errors. Исправлено commit `481aef1`; неожиданные page/console errors по-прежнему запрещены.

## PostgreSQL/Documents/Excel

Финальный VPS suite на реальном PostgreSQL: **6 tests, OK, 1 skipped**. Единственный skip — browser-only test, потому что Chromium уже был исполнен отдельно через внешний Windows browser-host.

Пройдены:
- runtime roles не superuser и без BYPASSRLS;
- FORCE RLS и cross-company guards для Documents/Excel;
- metadata/download/archive tenant isolation;
- Excel preview без мутаций, apply, retry/idempotency, synthetic failure rollback и immutable result;
- invoice/payroll Documents company scope и финансовая неизменность;
- реальный PDF renderer внутри disposable PostgreSQL fixture.

## Реальный PDF renderer

На VPS найден системный Unicode font `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`. `reportlab==5.0.1` устанавливался только во временный `/tmp` target и после теста удалялся; Stage 7 venv не изменялся.

Standalone real PDF smoke: **1/1 OK**. Подтверждены реальные `%PDF`, `%%EOF`, A4/MediaBox, Unicode/Cyrillic font, порядок подписей расчётного листа и отсутствие клиентской детализации в кратком payroll slip.

Комбинированный ReportLab + PostgreSQL/RLS gate также пройден. Он выявил настоящий production-дефект: одинаковая повторная генерация PDF создавала разные checksums/Document ID из-за недетерминированных PDF metadata. Renderer переведён на ReportLab `invariant=1` в commit `e7f8643`; после этого повторная генерация стала детерминированной и возвращает тот же Document.

Отдельно исправлена проверка Unicode glyph в smoke-test (`ord('Р')`, commit `678b444`) и изолирован payroll period нового PG/PDF test от других test cases (commit `7dd6c7c`).

## Финальная локальная регрессия

- Python server: **199 tests OK, 19 skipped**.
- Node/Android/Web: **31/31 PASS**.
- `python -m compileall -q server android_src/tools`: OK.
- `node --check android_src/tests/web-postgresql.playwright.cjs`: OK.
- `git diff --check`: OK.

Warnings ограничены существующими `datetime.utcnow()` deprecation и отдельными SQLite ResourceWarning; test failures отсутствуют.

## Cleanup и безопасность

После финальных VPS-тестов отдельно подтверждено:
- `DB_CLEAN`: disposable `portal_test_documents_*` / `portal_test_web_*` отсутствуют;
- `ROLE_CLEAN`: disposable `portal_docs_*` / `portal_web_*` роли отсутствуют;
- `TEMP_DEPS_CLEAN`: временный ReportLab target удалён;
- production PostgreSQL не переключалась и не использовалась как test target;
- production Stage 7 service/config не менялись.

## Коммиты Part 8

- `9dee44d` — Web PostgreSQL Part 8 staging E2E gate.
- `481aef1` — корректная обработка ожидаемых HTTP 403/401 в browser E2E.
- `678b444` — корректная Unicode glyph assertion для ReportLab.
- `c8e17a7` — combined real PDF + PostgreSQL verification gate.
- `e7f8643` — deterministic PDF generation через ReportLab invariant mode.
- `7dd6c7c` — независимый historical payroll fixture для полного suite.

## Roadmap после проверки

Переведены в ✅ только подтверждённые gates: **50, 51, 54, 62, 67, 84**.

Остаются открытыми:
- реальное скачивание blank/prefilled Excel template через Web browser;
- Android device/WebView file/save/share/install flows и Java/device gate;
- реальный PostgreSQL browser E2E для Platform Owner/Packer scopes и полная platform parity;
- production rollout/cutover, постоянный production domain/HTTPS и Windows installer;
- полный cross-client Documents sync workflow.

Part 8 готов к интеграции в release-кандидат после обычной merge/rebase проверки; production cutover этим отчётом не разрешается.
