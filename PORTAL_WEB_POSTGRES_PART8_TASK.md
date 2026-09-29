# PORTAL — Web + PostgreSQL Staging Part 8

Дата: 29.09.2026
Ветка: `codex-web-postgres-part8`
База: `c1a53bc33a136836a170f68f2548182a77a0c6e4`

## Постоянные ограничения

1. Production, production DB, реальная телефонная SQLite и реальные рабочие данные НЕ ТРОГАТЬ.
2. Работать только с изолированным test/staging PostgreSQL, synthetic fixtures и test API.
3. APK локально НЕ собирать. Android APK — только GitHub Actions.
4. Не push, не merge, не deploy в production.
5. Не менять production DNS/HTTPS/firewall/system services.
6. Не выводить DSN, PIN, токены, private keys и другие секреты в отчёт/логи/Git.
7. Не использовать старый Telegram/Termux runtime.
8. Если существующий Stage 7 service используется для read-only/smoke, не менять его данные без явно изолированного synthetic fixture. Предпочтение: disposable randomly named DB/roles или отдельный temporary API process.

## Цель

Закрыть главный gate после Part 7: доказать, что Web-клиент PORTAL работает не только на mocked API, а через реальный HTTP PORTAL API поверх изолированного PostgreSQL с RLS.

Основные roadmap пункты:
- 84 Desktop/Web client — staging E2E;
- 86 Android/Web permission parity — реальный API scope;
- 53–68 Documents/Excel — реальный Web flow;
- 50/51/67 — PDF route renderer/runtime gate там, где окружение позволяет.

## A. Сначала аудит существующих fixtures

Прочитать:
- `PORTAL_DESKTOP_WEB_PART7_REPORT.md`
- `PORTAL_MASTER_ROADMAP.md`
- `POSTGRESQL_TEST_REPORT.md`
- `PORTAL_STAGE7_VERIFIED_REPORT.md`
- `server/test_documents_postgresql.py`
- `server/test_postgresql_integration.py`
- `server/test_documents_pdf.py`
- `server/vps_stage7_staging_deploy.sh`
- `server/migrations/postgresql_stage8_documents_excel.sql`
- `android_src/tests/web-smoke.playwright.cjs`
- `server/web_static.py`

Не дублировать готовые PG fixtures. Расширить их или добавить отдельный disposable fixture.

## B. Изолированный PostgreSQL Web E2E

Создать runnable test, например:
- `server/test_web_postgresql_e2e.py`
или разумный аналог.

Тест должен:
1. Запускаться только opt-in env flag, например `PORTAL_WEB_PG_E2E=1`.
2. Создавать случайно именованную test DB `portal_test_web_*`.
3. Создавать отдельные restricted tenant/control roles:
   - NOSUPERUSER
   - NOBYPASSRLS
   - NOCREATEDB
   - NOCREATEROLE.
4. Применить все актуальные migrations, включая stage8 Documents/Excel.
5. Создать минимум две synthetic компании A/B.
6. Создать synthetic users:
   - director/admin company A;
   - packer company A;
   - director/admin company B;
   - при возможности synthetic Platform Owner/control scope.
7. Создать synthetic client/operation/tariff/work/invoice/payroll fixtures только в test DB.
8. Поднять temporary PORTAL HTTP API на loopback случайном порту.
9. Поднять/использовать Web static `/web/` с того же API process.
10. После завершения гарантированно:
    - остановить server;
    - удалить только созданную случайную DB;
    - удалить только созданные роли;
    - удалить temp blobs/files.
11. Fail-closed cleanup: проверять prefix до DROP.

## C. Реальный browser flow через Playwright

Добавить Playwright E2E, который ходит в настоящий temporary API/DB, без route mocking для бизнес-API.

Минимум:
1. GET `/web/` -> UI грузится.
2. Login director company A реальным API.
3. `/api/v3/meta`/capabilities приходят реально из PostgreSQL.
4. Director видит Documents и Excel.
5. Packer не видит финансовые/admin/Documents функции.
6. Cross-company A/B:
   - director A не может читать B Documents;
   - подмена `X-Portal-Company`/owner scope не открывает B.
7. Web logout закрывает session UI и повторное API использование revoked/expired session ведёт себя по текущему contract.
8. Не должно быть uncaught page errors/console errors.

## D. Documents реальный flow

В Web через реальный API/PostgreSQL:
1. Открыть Documents.
2. Получить/создать минимум один ready document.
3. Проверить list/search/filter/pagination хотя бы базовым сценарием.
4. Скачать документ browser path безопасно.
5. Archive -> документ больше не downloadable.
6. Company B не видит документ A.
7. Если browser test не может удобно проверить физический файл, проверить download event + server payload/MIME/name.

## E. PDF real renderer

Если в test/VPS окружении доступен pinned ReportLab + Unicode font:
1. Реально сгенерировать PDF «Счёт на оплату».
2. Реально сгенерировать краткий PDF «Расчётный лист» из CLOSED payroll snapshot.
3. Проверить:
   - начинается `%PDF-`;
   - имеет `%%EOF`;
   - не пустой разумный размер;
   - MIME/filename;
   - Documents registration;
   - company scope;
   - PDF generation не меняет invoice/work/payroll financial facts;
   - подписи расчётного листа в порядке:
     Управляющий компанией → Управляющий подразделением → Сотрудник.
4. Если renderer/font реально недоступен — не подменять mock и не ставить ✅. Точно записать gate.

## F. Excel полный реальный round-trip

Через Web + real API/PostgreSQL:
1. Скачать blank/prefilled PORTAL v1.0 XLSX.
2. Сформировать synthetic XLSX изменение, например новый client/operation или безопасное обновление existing synthetic record.
3. Browser file chooser -> upload.
4. Preview:
   - new/update/unchanged;
   - no invalid/conflict для валидного fixture.
5. Apply доступен только после preview/confirm.
6. Apply.
7. Result document/download.
8. Проверить PostgreSQL напрямую или через API: изменение применилось только company A.
9. Company B unchanged.
10. Повтор apply/import idempotent по существующему контракту.
11. Invalid/conflict workbook НЕ мутирует DB.
12. Не менять закрытые payroll snapshots и прошлые финансовые факты.

## G. Platform Owner scope

Если existing test architecture позволяет безопасно создать Platform Owner:
1. Реальный owner login.
2. Owner до выбора компании не может читать company data.
3. После выбора A видит A.
4. Переключение A->B не показывает stale A data.
5. Подмена scope заголовком/body/query без разрешённого owner context fail-closed.
Если safe owner fixture слишком велик для Part 8 — не придумывать; оставить точный gap.

## H. Security

Проверить:
- RLS FORCE остаётся на relevant tables;
- runtime tenant/control roles не superuser/BYPASSRLS;
- Web token не появляется в URL/query/download filename/log;
- arbitrary absolute fetch в web adapter запрещён;
- static traversal guards работают;
- test secrets не попали в git diff;
- disposable DB/roles удалены после success и failure.

## I. Tests

Минимум прогнать:
1. новый local/source Web test;
2. `NODE_PATH=C:\Users\darta\Documents\PORTAL-Android\node_modules node --test android_src/tests/*.test.cjs`;
3. targeted server Documents/Excel/PDF/Web;
4. полный `python -m unittest discover -p test_*.py`;
5. PostgreSQL opt-in E2E в disposable environment;
6. Python compileall;
7. `git diff --check`.
APK НЕ СОБИРАТЬ локально.

## J. VPS execution

Если для реального PostgreSQL E2E нужен Linux/VPS:
- использовать уже подтверждённый SSH path/known host/identity;
- staged code копировать только в новый временный каталог, например `/tmp/portal-web-part8-<id>`;
- не заменять `/srv/portal`, systemd unit или protected production/stage service;
- disposable DB test запускать как postgres/root строго по fixture;
- после теста cleanup;
- безопасные итоговые результаты можно скопировать локально, секреты нельзя.

## K. Roadmap/report

Создать `PORTAL_WEB_POSTGRES_PART8_REPORT.md`:
- exact commit/base;
- fixture architecture;
- DB/roles prefixes;
- Web flows;
- Documents result;
- Excel result;
- PDF real renderer result;
- owner scope result;
- RLS/security result;
- exact test counts;
- cleanup proof;
- remaining gaps;
- recommended Part 9.

Roadmap менять только по подтверждённому:
- 84 можно ✅ только если real PostgreSQL Web E2E действительно прошёл;
- 86 ✅ только если достаточная role/platform parity реально подтверждена;
- 50/51/67 ✅ только при real renderer + PG E2E без mocks;
- 53–68 повышать только проверенные подпункты;
- 85 Windows installer оставить ⏳.

## L. Финал

1. Локальный commit.
2. Worktree clean.
3. Не push.
4. Не merge.
5. Не deploy.
6. В финальном сообщении указать:
   - commit hash;
   - exact test counts;
   - что реально проверено на PostgreSQL;
   - что осталось.
7. Не задавать уточняющих вопросов. Работай самостоятельно и fail-closed.
