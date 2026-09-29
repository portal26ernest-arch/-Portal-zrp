# PORTAL — Part 11: Web blank/prefilled Excel template download

Дата: 29.09.2026  
Ветка: `assistant-part11-web-template-download`  
База: `e2942d8`  
Финальный проверенный HEAD: `a397f75`

## Цель

Закрыть оставшийся staging-gate по фактическому скачиванию стандартного Excel-шаблона PORTAL через Web-браузер:
- blank template;
- prefilled template выбранной компании;
- проверка browser download, MIME, имени, содержимого и tenant scope;
- доказательство отсутствия мутаций БД от GET/download операций.

## Реализованный контур

Добавлен `server/web_pg_part11_fixture_host.py`, использующий тот же безопасный disposable PostgreSQL fixture, что Parts 8–10. Он создаёт только случайные `portal_test_web_*` DB/roles и synthetic Director.
Добавлен `android_src/tests/web-postgresql-part11-template-download.playwright.cjs`.

Chromium работает через настоящий Web UI и HTTP API, без mock бизнес-API. Для каждого скачивания тест:
- нажимает реальную кнопку Web UI;
- перехватывает реальный browser download;
- проверяет имя `PORTAL_template_v1.xlsx`;
- проверяет ZIP/XLSX signature;
- сравнивает SHA-256 скачанного файла с base64 payload, повторно полученным от реального API;
- проверяет MIME и canonical `template_version=1.0`.

Также проверяется, что blank и prefilled XLSX имеют разные SHA-256, а Director не может подменить `X-Portal-Company` на другую компанию — HTTP 403.

## Финальный VPS/browser E2E

Проверенный запуск на commit `a397f75`:

```text
REMOTE_HEAD=a397f75
BROWSER_EXIT=0
BLANK_BYTES=5689
PREFILL_BYTES=6094
BLANK_SHA256=cf66db7055dda3d8915c93378e64d7d15f919047d51361f4dbfedd1d70dd3f29
PREFILL_SHA256=9cf246a54a8164756a8a7cb4f71d89f52aae53a7c7c8a62fbfcd94eadf04a06d
PART11_BROWSER_DOWNLOAD=PASS
FIXTURE_VERIFIED=True
BEFORE_COUNTS={"clients":1,"documents":0,"employees":3,"operations":1}
AFTER_COUNTS={"clients":1,"documents":0,"employees":3,"operations":1}
CLEANUP_COMPLETE=True
POST_DB_COUNT=0
POST_ROLE_COUNT=0
PART11_REAL_WEB_TEMPLATE_DOWNLOAD=PASS
```

Blank и prefilled файлы реально скачаны браузером, отличаются по содержимому и полностью совпадают с соответствующим серверным payload.
## Дополнительные проверки

- targeted server suite: **19 tests — OK**;
- `python -m py_compile server/web_pg_part11_fixture_host.py`: PASS;
- `node --check android_src/tests/web-postgresql-part11-template-download.playwright.cjs`: PASS;
- `git diff --check`: PASS;
- GitHub Web checks на `a397f75`: SUCCESS;
- GitHub Server isolation на первой Part 11 реализации: SUCCESS.

## Безопасность

- Web download не создал Documents и не изменил clients/operations/employees.
- Подмена tenant/company scope директором заблокирована HTTP 403.
- После E2E disposable PostgreSQL DB и roles полностью удалены: 0/0.
- Production DB/service и телефон не использовались.

## Оставшиеся соседние gates

- Android user-flow готовой APK;
- Web Share behavior в целевых браузерах;
- cross-client Documents sync workflow;
- Windows Desktop installer/update;
- production rollout/cutover.

Part 11 готов к включению в release-candidate 3.4.
