# PORTAL Web + PostgreSQL Staging Part 8

Дата: 29.09.2026  
Ветка: `codex-web-postgres-part8`  
База: `c1a53bc33a136836a170f68f2548182a77a0c6e4`

## Результат

Добавлен opt-in gate `server/test_web_postgresql_e2e.py`. Он повторно использует существующий disposable Documents/PostgreSQL fixture, а не создаёт параллельный migration/fixture стек. Переменная `PORTAL_WEB_PG_E2E=1` выбирает отдельные случайные ресурсы `portal_test_web_*`, `portal_web_t_*`, `portal_web_c_*`. Fixture применяет актуальные миграции Stage 8, включает FORCE RLS проверки существующих Documents/Excel тестов, запускает API на loopback и сохраняет blobs во временном каталоге. Cleanup останавливает HTTP server, восстанавливает настройки, удаляет только имена с ожидаемым prefix и удаляет temp directory.

Для режима Web добавлен `android_src/tests/web-postgresql.playwright.cjs`: реальный `/web/`, login и `/api/v3/meta`, переход на Documents, попытка подменить company header и проверка отзыва сессии через `/api/logout`. В тесте отсутствует `page.route` и mock бизнес API. PIN и токены передаются только дочернему процессу через environment и не печатаются.

## Проверки в этой среде

- Android/Web Node suite: **31 passed, 0 failed, 0 skipped**.
- Существующий mocked Web Playwright smoke: **1 passed**.
- `python -m unittest discover -p test_*.py`: **197 tests, OK, 17 skipped** (environment gates).
- `python -m compileall -q server android_src/tools`: **успешно**.
- `git diff --check`: **успешно**.
- Targeted `test_documents_api`, `test_documents_pdf`, `test_excel_import`, `test_web_postgresql_e2e`: **28 tests, OK, 2 skipped** (environment gates).

## Ограничения исполнения

Реальный PostgreSQL Web gate **не запускался**: в текущей Windows-среде отсутствуют `psql`, `pg_ctl`, `initdb`, `psycopg`, локальный PostgreSQL, WSL Linux runtime и Docker/Podman. ReportLab также отсутствует. Поэтому disposable DB/roles не создавались и cleanup proof реального запуска отсутствует. Новая Playwright ветка требует Chromium и Node `playwright` в среде запуска; до PG среды она не проверена.

PDF checks в имеющемся PostgreSQL fixture используют синтетические bytes через patched renderer. Они не считаются real PDF renderer gate. Отдельный `test_documents_pdf.py` не заменяет renderer отсутствие mock-ом, но в данной среде его ReportLab runtime prerequisite отсутствует.

Platform Owner реальный Web scope не подтверждён этим Part 8 fixture; роль и credentials Owner не создаются. Excel preview/apply, rollback и idempotency покрываются существующими API tests на disposable PostgreSQL fixture, но браузерный XLSX round-trip с file chooser этим gate не подтверждён.

## Roadmap

Roadmap не повышен: пункты 84 и 86 остаются 🟡, пункты PDF 50/51 остаются 🟡, 85 остаётся ⏳. Другие пункты 53–68 не менялись без нового подтверждения. Не было основания отмечать PostgreSQL Web E2E, role parity или реальный PDF renderer как пройденные.

## Рекомендуемый Part 9

Запустить opt-in gate на изолированном Linux PostgreSQL staging runner с pinned Python/ReportLab/Unicode font и Chromium; получить подтверждённое завершение cleanup. Затем добавить браузерный XLSX round-trip с preview/apply/result и отдельно решить безопасную модель synthetic Platform Owner fixture. По итогам обновлять только те roadmap пункты, которые реально прошли.
