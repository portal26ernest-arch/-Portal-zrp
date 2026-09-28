# PORTAL — Documents + Excel, Part 2

Дата: 29.09.2026
Рабочая ветка: codex-documents-excel-part2
База: 56095d3 (Part 1 Documents/Excel + динамическое приветствие)
Рабочая копия: C:\Users\darta\Documents\PORTAL-Documents-Part2

## Цель

Довести пользовательскую часть Android PORTAL для уже реализованного серверного контура Documents + Excel:
1. полноценный экран «Документы»;
2. полноценный экран Excel-импорта с загрузкой файла -> preview -> явное подтверждение -> apply -> результат;
3. скачать стандартный blank/prefill шаблон;
4. скачать документ/результат импорта;
5. удобные состояния loading/empty/error/success;
6. сохранить строгую ролевую и tenant-изоляцию;
7. покрыть UI/контракт тестами.

Это Part 2. Не переделывать заново серверную Part 1 без необходимости.

## Сначала обязательно

- Прочитать PORTAL_DOCUMENTS_EXCEL_PART1_REPORT.md.
- Прочитать PORTAL_MASTER_ROADMAP.md.
- Изучить android_src и существующий JS/API слой до изменений.
- Проверить уже существующие Android bridge/FileProvider/share/download механизмы перед добавлением новых.
- Не угадывать API: использовать уже существующие /api/v3 endpoints из Part 1.
- До изменений зафиксировать baseline тестов.

## Экран «Документы»

Сделать реальный рабочий экран вместо preview-заглушки.

Минимум:
- список документов выбранной компании;
- title, type/category, дата, размер, статус, revision;
- поиск q;
- фильтры category/document_type/date/status там, где API уже поддерживает;
- пагинация/«Показать ещё» без загрузки бесконечного массива;
- скрывать внутренние storage_key/fingerprint/request receipts;
- открыть/скачать ready-документ;
- архивный документ не скачивать и визуально помечать;
- архивирование только если текущая роль реально имеет documents.manage;
- корректно обрабатывать 401/403/404/409/5xx и offline;
- Platform Owner работает только после явного выбора компании как и в остальных экранах;
- manager не должен увидеть документы чужих/неназначенных клиентов;
- никаких обходов серверных прав на клиенте.

## Экран Excel Import

Заменить preview-заглушку на полноценный flow:

### Шаблон
- «Скачать пустой шаблон».
- «Скачать шаблон с данными компании».
- Показывать версию шаблона и четыре листа: Компания, Сотрудники, Клиенты, Операции_Тарифы.
- Не выводить/не экспортировать PIN, hash, salt, session tokens.

### Загрузка
- выбор .xlsx с устройства;
- до отправки показать имя и размер;
- ограничение UI согласовать с сервером (10 MiB);
- неподходящий формат/слишком большой файл отклонять понятным сообщением;
- не читать Excel формулами/не исполнять содержимое на клиенте.

### Preview
- POST excel-import-preview;
- показать сводку new/update/unchanged/conflict/invalid;
- показать строки с sheet/row/classification и безопасными diff/ошибками;
- до явного подтверждения никаких apply;
- conflict/invalid = кнопка применения недоступна;
- хранить preview_token/import_id/checksum только в runtime UI state, не в логах/постоянных preferences.

### Apply
- отдельная кнопка «Применить изменения»;
- дополнительное подтверждение;
- повторно отправлять exact file + import_id + preview_token согласно API;
- статус applied -> показать counts + ссылку/кнопку на result document;
- 409 failed -> показать, что импорт полностью отменён, и безопасный error report;
- stale/expired token или изменившиеся справочники -> предложить сделать новый preview;
- защита от двойного нажатия;
- idempotent retry не должен визуально создавать второй импорт.

## Save / share

Если в текущем Android проекте уже есть безопасный native bridge для файлов:
- подключить скачивание шаблонов и документов к системному сохранению/Share Sheet;
- имя файла брать только из безопасно нормализованного server filename;
- MIME ограничить ожидаемыми XLSX/PDF/JSON;
- не давать file:// наружу; использовать существующий FileProvider/content URI;
- временные файлы не делать world-readable.

Если bridge отсутствует или добавление требует отдельной крупной native-архитектуры:
- не делать небезопасный костыль;
- реализовать корректное скачивание внутри текущей архитектуры;
- явно записать в отчёт остаток для следующего шага Android native bridge.

Email не отправлять напрямую с сервера и не хранить SMTP/API-секреты в APK. Если есть системный share intent — email должен быть одним из вариантов Share Sheet.

## UX

- Визуально продолжить текущий стиль PORTAL и директорского dashboard.
- Тексты на русском.
- Крупные touch-targets.
- Нормально работать на телефоне и планшете.
- Не ломать роли packer/manager/director/admin/platform_owner.
- Динамическое приветствие из 56095d3 сохранить.

## Безопасность

Запрещено:
- production deploy;
- изменение production DB;
- перенос/перезапись старой телефонной SQLite;
- изменение действующих тарифов/зарплат/закрытых payroll snapshots;
- добавление секретов в APK/Git;
- прямой доступ Android к PostgreSQL;
- ослабление RLS/permissions ради UI;
- удаление legacy history;
- изменение TalAnt/WMS блока;
- Telegram compatibility не возвращать в новую архитектуру.

## Версия

Текущий preview был 3.4.
Если реально создаётся новая APK/видимая сборка в рамках этой задачи — следующая версия 3.5.
Не менять production signing key и не публиковать production APK.

## Тесты

Обязательно:
- текущие android_src/tests;
- тесты Documents/Excel Part 1 не должны регрессировать;
- новые UI tests минимум для:
  * документы: list/empty/search/pagination/download/archive permission/error;
  * template blank/prefill;
  * file validation;
  * preview classifications;
  * conflict/invalid blocks apply;
  * successful apply;
  * failed rollback response;
  * stale preview;
  * double-submit/idempotent UI;
  * role visibility;
  * owner company context;
  * expired session -> login;
- JS parse tests;
- git diff --check.

Если native Android bridge меняется — добавить/запустить соответствующие Gradle unit/instrumentation checks, если они доступны без physical device.

## Git

- Работать только в этой ветке/worktree.
- Делать небольшие логичные локальные commits.
- Не push, не PR, не merge.
- Не трогать другие worktree.
- Не использовать git reset --hard/clean для чужих файлов.

## Итоговый отчёт

Создать PORTAL_DOCUMENTS_EXCEL_PART2_REPORT.md:
- что реализовано;
- какие экраны/endpoints;
- права;
- save/share поведение;
- тесты с точными цифрами;
- какие файлы/коммиты;
- что осталось;
- явно подтвердить, что production/VPS не тронуты.

В финале оставить рабочее дерево чистым. Если обнаружится блокирующая проблема — не обходить безопасность, а зафиксировать её в отчёте и завершить максимум безопасной части.
