# PORTAL — Codex Part 9: счета, XLSX-документы и revisions

База: commit 4e0d7ce, ветка codex-invoice-documents-part9.
Цель: закрыть функциональные остатки документов и счетов, не вмешиваясь в release 3.4/CI/signing.

## Жёсткая граница с параллельной работой ассистента
НЕ изменять:
- .github/workflows/**
- android_src/gradle.properties
- android_src/app/build.gradle
- android_src/tests/build-security.test.cjs
- signing/release/deploy/tunnel scripts
- PORTAL_MASTER_ROADMAP.md
- номера версии/сборки APK
Не выполнять merge/rebase в другие ветки. Не deploy в production/VPS. Не трогать реальные данные, секреты, signing key.
Работать только в этой ветке/worktree. В конце сделать локальные commits, но не push без необходимости.

## Блок A — invoice_xlsx
Реализовать настоящий генератор document_type=invoice_xlsx через существующий /api/v3/document-generate.
Источник данных только существующий invoice snapshot + company/client requisites + строки счета.
Документ: «Счёт на оплату», реквизиты исполнителя и клиента, таблица Операция / Количество / Цена / Сумма, итог.
Не выдумывать отсутствующие значения: fail closed с понятной ошибкой.
XLSX должен быть пригоден для печати A4 и иметь корректные русские подписи.
Повторная генерация одного и того же неизменившегося snapshot должна быть детерминированной/idempotent и возвращать тот же Document, как PDF.
## Блок B — payroll_slip_xlsx
Реализовать настоящий document_type=payroll_slip_xlsx через тот же document-generate.
Использовать только CLOSED payroll period snapshot.
Краткий расчётный лист без клиентов, операций и детальной выработки.
Обязательные поля: компания, «Расчётный лист», период/год, ФИО, итоговая сумма, дата.
Порядок подписей строго: Управляющий компанией → Управляющий подразделением → Сотрудник.
Генерация не должна менять work/payroll settlements/snapshots.
Повторная генерация неизменного snapshot — deterministic/idempotent.
Добавить регистрацию в Documents с правильными category, employee_id, payroll_period_id, filename, MIME, revision metadata.

## Блок C — жизненный цикл счета и «Отправить на редактирование»
Реализовать безопасный workflow finalized → editing → finalized с revision history.
Сразу после формирования счет считается заблокированным для обычного редактирования.
Только admin/director своей компании могут выполнить «Отправить на редактирование».
Manager своей компании может редактировать только счет, находящийся в editing.
Редактирование не должно менять исходные work records, payroll, закрытые snapshots или уже созданные старые Documents.
При повторном финальном сохранении создать новую revision/snapshot счета; прежняя revision должна оставаться доступной для истории и аудита.
Если по счету уже есть платежи, редактирование суммы/строк запретить fail closed, чтобы не разрушить ledger.
Cross-company доступ, подмена company header/id и повтор запроса должны быть безопасно обработаны.
Использовать существующую permissions/domain архитектуру; новые permission codes добавлять только если действительно нужны и с тестами defaults.
## Блок D — UI без редизайна
В существующем экране счетов добавить:
- «XLSX счёта» рядом с PDF;
- для admin/director — «Отправить на редактирование» там, где это допустимо;
- для manager — форму редактирования только при editing;
- отображение state/revision понятным русским текстом.
В payroll/documents flow добавить создание и сохранение payroll_slip_xlsx рядом с PDF.
Не менять общий дизайн, dashboard, greeting, навигацию и release shell.
Не трогать preview-макеты, если они не нужны для функционального теста.

## Проверки
Добавить/расширить server tests и android_src Node/UI tests.
Обязательно проверить permissions, tenant isolation, revision history, payment lock, idempotency, immutable financial facts.
Добавить PostgreSQL schema/migration tests только если workflow требует новой структуры; миграция должна быть backward-compatible.
Проверить реальные XLSX bytes через openpyxl: файл открывается, листы/ячейки/формулы/print settings ожидаемы.
Запустить максимально полный локальный Python suite и node --test android_src/tests/*.test.cjs.
Запустить compileall, node --check для измененных JS, git diff --check.
Не считать environment skip успехом, но не менять production окружение ради его устранения.

## Финал
Создать CODEX_PART9_INVOICE_XLSX_REVISIONS_REPORT.md с: что реализовано, файлы, тесты, skipped/risks, commits.
Перед финалом git status должен быть чистым.
Сделать логичные локальные commits в этой ветке.
В финальном ответе указать commit SHAs и точный список незакрытых рисков, если они останутся.
