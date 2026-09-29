# PORTAL — Part 10: Web invoice revisions + role matrix E2E

Дата: 29.09.2026  
Ветка: `assistant-part10-web-invoice-e2e`  
База: `0f6f155`  
Финальный проверенный HEAD: `3d440a7`

## Цель

Закрыть оставшиеся реальные browser/PostgreSQL-gates после Part 9 для счетов и ролевой модели Web:
- Director: работа со счётом и отправка на редактирование;
- Manager: редактирование разрешённого счёта и создание новой ревизии;
- Packer: отсутствие финансового интерфейса и серверный запрет;
- Platform Owner: обязательный выбор компании и корректное переключение tenant scope;
- реальное создание и скачивание `invoice_xlsx` через Web;
- проверка на настоящем HTTP API и одноразовом PostgreSQL на VPS без production-данных.

## Реализованный тестовый контур

Добавлен `server/web_pg_part10_fixture_host.py`, который повторно использует проверенный disposable PostgreSQL fixture Part 8.
Fixture создаёт только случайные ресурсы `portal_test_web_*` и `portal_web_*`, synthetic компании/пользователей/работу/счёт и временный HTTP API. Production service, production DB и Stage 7 service не переключаются и не изменяются.

Добавлен `android_src/tests/web-postgresql-part10.playwright.cjs`.
Chromium на ПК обращается к временному API на VPS через отдельный SSH local tunnel. Бизнес-API не мокируется.

## Подтверждённые browser-сценарии

1. **Director**
   - реальный login;
   - открытие раздела счетов;
   - генерация и browser-download настоящего XLSX счёта;
   - перевод счёта `finalized → editing`;
   - серверное подтверждение состояния `editing`.

2. **Manager**
   - реальный login;
   - отсутствие действия «Отправить на редактирование»;
   - доступ к редактированию только уже открытого директором счёта;
   - изменение client rate через UI;
   - сохранение новой версии;
   - серверное подтверждение `finalized`, revision `2`.

3. **Packer**
   - раздел счетов отсутствует в доступном UI;
   - прямой запрос `/api/v3/invoices` возвращает HTTP 403.
4. **Platform Owner**
   - реальный технический login;
   - до выбора компании company-data запрос блокируется HTTP 403;
   - после явного выбора компании A счёт доступен;
   - при переключении scope на компанию B список счетов пуст;
   - действия владельца записываются в owner audit.

## Финальный VPS E2E

Проверенный запуск на commit `3d440a7`:

```text
REMOTE_HEAD=3d440a7
BROWSER_EXIT=0
FIXTURE_VERIFIED=True
INVOICE_REVISION=2
INVOICE_XLSX_DOCUMENTS=1
OWNER_AUDIT_ROWS=16
CLEANUP_COMPLETE=True
POST_DB_COUNT=0
POST_ROLE_COUNT=0
PART10_REAL_WEB_PG_E2E=PASS
```

Это подтверждает полный путь **Chromium → HTTP API → PostgreSQL → Documents/XLSX → invoice revision** и обратную проверку состояния БД.
## Дополнительные проверки

- локальный targeted server regression: **28 tests — OK**;
- локальный Web/Playwright regression: **4/4 PASS**;
- GitHub Web checks на Part 10: **SUCCESS**;
- GitHub Server isolation tests на Part 10: **SUCCESS**;
- `python -m py_compile` нового fixture: PASS;
- `node --check` нового Playwright test: PASS;
- `git diff --check`: PASS.

## Безопасность и cleanup

- Использовались только synthetic данные.
- Production PostgreSQL и production service не использовались как test target.
- После финального E2E: disposable DB = **0**, disposable roles = **0**.
- Временные локальные orchestration-скрипты не добавляются в Git.
- Телефон не использовался для сборки или технического тестирования.

## Оставшиеся gates

- физический Android user-flow/parity: только установка готового APK и пользовательская проверка согласно новому регламенту проекта;
- реальный Web download blank/prefilled Excel template;
- Windows Desktop installer/update;
- официальный безопасный ingestion Ozon/Wildberries;
- production domain/HTTPS и финальный production cutover.

Part 10 готов к включению в release-candidate 3.4.
