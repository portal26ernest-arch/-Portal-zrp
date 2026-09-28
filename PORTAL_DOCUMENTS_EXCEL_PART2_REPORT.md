# PORTAL — Documents + Excel, Part 2

Дата: 29.09.2026  
Ветка: `codex-documents-excel-part2`  
База: `56095d3` (Part 1 Documents/Excel + динамическое приветствие)

## Реализовано

- Вместо Documents preview-заглушки подключён экран списка выбранной компании: title, тип/категория, дата, размер, статус, revision, поиск, серверные фильтры и постраничная загрузка. Архивные файлы помечены и не скачиваются. Архивирование показывается только при `documents.manage` и требует подтверждения.
- Подключён Excel flow: сведения о шаблоне, blank/prefill download, выбор XLSX, локальная проверка расширения/размера, preview с пятью классификациями и безопасными строками diff/errors, отдельное подтверждение apply, terminal status и загрузка JSON result document. Apply недоступен при conflict/invalid и защищён от двойного запуска.
- Preview credentials и файл существуют только в runtime-памяти экрана. При потерянном ответе apply запрашивается terminal result по `import_id`: уже применённая операция отображается как ранее завершённая, без создания второго импорта.
- Добавлены loading, empty и retry/error состояния для списка документов и загрузки шаблона. HTTP 401 продолжает сбрасывать сессию на экран входа; 403/404/409/5xx/offline показываются через общую обработку API и сообщения экранов.
- Excel Import переведён из preview в production feature; сохранены требования capability-проверок и явного выбора компании Platform Owner. Manager scope не воспроизводится локально: сервер остаётся источником tenant/client-доступа.
- В существующий Android file save bridge добавлен MIME `application/json`, необходимый для сохранения безопасного отчёта импорта. Используется прежний системный file picker и MediaStore/приватный app storage; `file://` не создаётся.

## Экраны и API

Экран **Документы** использует `GET /api/v3/documents` с `q`, `category`, `document_type`, датами, `status`, `page`, `limit`; `GET /api/v3/document-file?id=…` для ready-файлов; `POST /api/v3/document-archive` для архива.

Экран **Импорт Excel** использует `GET /api/v3/document-template-info`, `GET /api/v3/document-template-blank`, `GET /api/v3/document-template`, `POST /api/v3/excel-import-preview`, `POST /api/v3/excel-import-apply`, `GET /api/v3/excel-import-result?id=…` и скачивание результата через `GET /api/v3/document-file?id=…`.

Для prefill/preview/apply/result клиент проверяет `imports.manage`, `users.manage`, `clients.manage`, `rates.employee`, `rates.client`, `company.settings`, `documents.manage`, `documents.read` и подходящую роль. Blank template и список/скачивание требуют `documents.read`; архив требует также `documents.manage`. Серверные разрешения не ослаблялись.

## Сохранение и ограничения

XLSX, PDF и JSON сохраняются через существующий `saveBase64FileAsync`: на Android 10+ — `Downloads/PORTAL` через MediaStore; на более ранних версиях — app-specific Downloads. Нативный MIME allowlist ограничен этими типами для данного потока. Email не отправляется с сервера.

В проекте отсутствует системный Share Sheet bridge. Его добавление потребовало бы отдельного native share/FileProvider потока; небезопасная передача URI не добавлялась. Сохранение на устройство и загрузка результата работают внутри текущей архитектуры. APK не собирался, version/build properties не менялись.

## Тесты и проверки

| Проверка | Результат |
|---|---|
| Существующие Android security/chat/employee/legacy/native проверки + новые Documents/Excel contract checks | **9 tests, 9 passed, 0 failed** |
| `node --check` для всех JS в `android_src/app/src/main/assets` | **Успешно** |
| Part 1 Documents/Excel серверная регрессия: `python -m unittest test_documents_api test_excel_import test_excel_template test_portal_documents test_postgresql_documents_schema -v` | **38 tests, OK** |
| Полный `node --test tests/*.test.cjs` | **9 passed; UI suite не загрузился**, так как отсутствует `playwright` (`MODULE_NOT_FOUND`) |
| Установка CI-зависимости `playwright@1.62.1` через `npm.cmd install --no-save --package-lock=false` | Заблокирована локальным `EACCES` при доступе к npm registry/cache |
| Gradle unit/build check | Недоступен: в `android_src` нет Gradle wrapper и команда `gradle` отсутствует |
| `git diff --check` | Пройдено |

Браузерные сценарии Playwright и Gradle проверки нельзя объявить пройденными. Новые исполняемые contract checks подтверждают wiring API, фильтры/пагинацию, MIME allowlist, file picker/save bridge, роли и основные apply states; они не заменяют полноценный browser UI прогон.

## Изменённые файлы

- `android_src/app/src/main/assets/documents_excel.js` — Documents и Excel Import экраны.
- `android_src/app/src/main/assets/index.html` — подключение нового экрана.
- `android_src/app/src/main/assets/core.js` — Excel Import помечен production feature.
- `android_src/app/src/main/assets/app.js` — сохранение HTTP status/body в API error для безопасной обработки terminal response.
- `android_src/app/src/main/assets/ui.css` — адаптивные фильтры и визуальная маркировка архивных записей.
- `android_src/app/src/main/java/ru/portal/app/MainActivity.java` — JSON в MIME allowlist существующего saver.
- `android_src/tests/documents-excel.test.cjs`, `android_src/tests/native-shell.test.cjs`, `android_src/tests/ui.test.cjs` — UI/API/native contract checks, including role visibility for Excel Import.
- `PORTAL_DOCUMENTS_EXCEL_PART2_TASK.md`, `CODEX_PART2_PROMPT.txt` — локальные входные материалы, включены в репозиторий для чистого рабочего дерева.

## Git и безопасность

Локальные commits: `8e769d2` — Android Documents/Excel UI, native JSON MIME и проверки; `76189ed` — этот отчёт и исходное задание. Push, PR, merge и deploy не выполнялись. Production/VPS, production БД, телефонная SQLite, тарифы, зарплаты и закрытые snapshots не затрагивались. Серверные файлы Part 1 не менялись.

## Осталось

- Установить Playwright в доступном CI/dev окружении и пройти browser UI regression suite.
- Выполнить Gradle checks в Android SDK/Gradle окружении.
- Отдельным native этапом добавить системный Share Sheet с безопасным content URI, если он потребуется.
