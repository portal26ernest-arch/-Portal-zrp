# PORTAL — Documents + Excel Part 4

Дата: 29.09.2026
Ветка: `codex-documents-excel-part4`
База: `4b061eb` — завершённый Documents + Excel Part 3.

## Цель

Закрыть проверочные ворота Part 3 и привести MASTER ROADMAP в соответствие с реально существующим Android Documents/Excel-контуром. Не дублировать уже реализованные функции и не помечать Desktop/Web или production как готовые без фактической проверки.

## Обязательный стартовый аудит

Перед изменениями прочитай:
- `PORTAL_DOCUMENTS_EXCEL_PART3_TASK.md`
- `PORTAL_DOCUMENTS_EXCEL_PART3_REPORT.md`
- `PORTAL_MASTER_ROADMAP.md`
- `android_src/app/src/main/assets/documents_excel.js`
- `android_src/app/src/main/java/ru/portal/app/MainActivity.java`
- `server/documents_api.py`
- `server/pdf_documents.py`
- существующие Documents/Excel/payroll/invoice/PostgreSQL tests.

Сначала зафиксируй, что уже реально есть:
- скачивание blank/prefill Excel-шаблона;
- сохранение файла на Android;
- Android WebView file chooser для выбора XLSX;
- upload/preview/apply/result;
- Share Sheet/email intent;
- invoice PDF/payroll PDF routes;
- Documents registration.

Если функция уже есть и покрыта тестом, не переписывай её без причины.

## A. Реальный PDF renderer gate

1. Попытайся запустить реальную генерацию PDF с pinned `reportlab==5.0.1` в ИЗОЛИРОВАННОМ test/venv окружении.
2. Не меняй глобальный Python, системные production packages или VPS production runtime.
3. Если локальная сеть/PyPI недоступна, проверь наличие безопасного локального wheel/cache. Не обходи сетевые ограничения небезопасными способами.
4. Реальный smoke должен проверить как минимум:
   - PDF начинается с корректной PDF signature;
   - invoice PDF генерируется из реальных тестовых данных без придуманных реквизитов;
   - payroll slip генерируется только из closed snapshot;
   - кириллица использует Unicode-capable font;
   - краткий payroll slip не содержит клиентской/операционной детализации;
   - порядок подписей: Управляющий компанией → Управляющий подразделением → Сотрудник.
5. Если renderer физически невозможно запустить в текущем окружении, подготовь полностью runnable automated test и честно оставь gate открытым. Не ставь ложный PASS.

## B. PostgreSQL PDF end-to-end

6. Добавь/дополни PostgreSQL integration test для invoice/payroll generated Documents:
   - company/tenant scope;
   - blob/document metadata registration;
   - download by authorized company;
   - cross-company denial;
   - immutable payroll snapshot / settlements;
   - отсутствие повторной финансовой записи от повторной генерации.
7. Используй только существующий disposable/test PostgreSQL контур или изолированную test DB. Production DB не трогать.
8. Если test PostgreSQL сейчас недоступен — не подменяй SQLite результатом, оставь точный gate в отчёте.

## C. Android Documents/Excel фактическая проверка

9. Проверь native WebView file chooser: `WebChromeClient.onShowFileChooser` + возврат результата.
10. Проверь полный Android flow:
    - скачать blank template;
    - скачать prefill template;
    - сохранить на устройство;
    - выбрать XLSX;
    - preview;
    - явное подтверждение apply;
    - result;
    - скачать/share result.
11. Убедись, что нет широких storage permissions, `file://`, скрытой автоотправки, SMTP/API секретов.
12. Проверь fail-closed поведение при отсутствии company context у Platform Owner и при недостаточных permissions.

## D. Android Java compile gate

13. Повтори проверку доступного локального Android toolchain. Не заявляй отсутствие JDK/SDK, не проверив стандартные пути и repo scripts.
14. Если локального toolchain действительно нет, НЕ устанавливай глобально тяжёлый Android Studio/JDK без отдельной необходимости.
15. Подготовь Part 4 так, чтобы существующий GitHub CI Android build мог проверить Java compile без специальных ручных шагов.
16. Не изменяй CI без необходимости. Если изменение CI требуется, оно должно быть минимальным и не затрагивать production deployment.

## E. Roadmap reconciliation

17. Исправь только фактически устаревшие статусы/описания в `PORTAL_MASTER_ROADMAP.md`.
18. Особо перепроверь пункты 50–68:
    - 50/51 PDF;
    - 53–56 Documents backend + Android UI;
    - 58/59 template download/save;
    - 60/61 share/email;
    - 62 upload filled XLSX;
    - 63 preview/confirmation screen;
    - 64–66 validation/apply;
    - 67 exports;
    - 68 Android↔Desktop central sync.
19. Android-only реализацию не выдавай за Desktop/Web. Если Android готов, а Desktop/Web нет — ставь 🟡 с точной формулировкой.
20. Не закрывай production rollout, permanent domain/HTTPS, Desktop/Web или signing, если они не проверены.

## F. Regression / security

21. Прогони минимум:
- targeted PDF/Documents/Excel server tests;
- PostgreSQL Documents tests, если test DB доступна;
- `node --test android_src/tests/*.test.cjs`;
- Python compile;
- `git diff --check`.
22. Проверь, что Telegram/Termux runtime не возвращён.
23. Не менять тарифы, реальные зарплатные факты, закрытые snapshots, production DB или phone SQLite.
24. Не делать APK version bump, signing, merge, push или production deploy в этой задаче.

## Завершение

25. Создай `PORTAL_DOCUMENTS_EXCEL_PART4_REPORT.md` с:
- что реально было уже реализовано до Part 4;
- что добавлено/исправлено;
- какие gates закрыты;
- точные результаты тестов;
- какие gates остаются открыты и почему.
26. Обнови `PORTAL_MASTER_ROADMAP.md` только по факту.
27. Сделай локальный commit на `codex-documents-excel-part4`.
28. Рабочее дерево в финале должно быть чистым.
29. В финальном сообщении: commit hash, тесты, изменённые файлы, открытые риски и что рекомендуется как следующий блок.

Работай самостоятельно до завершения этого блока. Не задавай пользователю уточняющих вопросов, если безопасный вариант можно определить по коду/roadmap.