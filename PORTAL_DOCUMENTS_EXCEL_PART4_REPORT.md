# PORTAL Documents + Excel Part 4

Дата: 29.09.2026
Ветка: `codex-documents-excel-part4`
База: `4b061eb`

## Уже было реализовано к Part 4

- Blank и prefill Excel-шаблоны выдаются через Documents API; Android UI сохраняет их в Downloads через системный picker/MediaStore.
- Android WebView поддерживает XLSX chooser. UI загружает файл в preview, показывает diff и классификацию строк, требует явного подтверждения перед apply, показывает результат и даёт скачать/share import report.
- Android Share Sheet использует внутренний cache, FileProvider `content://`, временный read grant, MIME allowlist и системный chooser. Email, тема и текст передаются выбранному приложению как intent extras; SMTP/API отправки и сохранённых почтовых секретов нет.
- Серверные invoice PDF и краткий payroll slip PDF маршруты уже создавали и регистрировали Documents с company/client/invoice либо company/employee/period scope. Счёт использует существующие строки и реквизиты; payroll требует закрытый период и его snapshot.
- Существующие Documents/Excel/payroll/invoice тесты уже проверяли права, SQLite tenant scope, snapshot/settlement неизменность и Android UI flow. Они не доказывали фактический PDF renderer или PDF PostgreSQL E2E.

## Изменения Part 4

- При ошибке запуска системного XLSX picker native bridge теперь завершает ожидающий WebView callback значением `null`; source test проверяет передачу результата и отмену/ошибку.
- Добавлен runnable PDF route smoke, который создаёт invoice и закрытый payroll период через существующие изолированные server test fixtures. Он генерирует документы через production routes, проверяет PDF signature/EOF/A4, наличие кириллической glyph map Unicode font, отсутствие клиентской и операционной детализации payroll slip, порядок подписей, регистрацию и неизменность invoice/work/payroll settlement при повторной генерации. Тест не добавляет реквизиты invoice.
- Добавлен opt-in disposable PostgreSQL test для invoice/payroll PDF Documents: metadata/blob registration, company scope, authorized download, cross-company denial и повторная генерация без изменения финансовых записей или payroll snapshot/settlements.
- Android build workflow теперь запускается при push в `codex-documents-excel-part4` и выполняет существующую staging APK сборку/Java compile. Signing и deployment workflow не менялись.
- Roadmap пункты 50–68 уточнены: Android-only функции описаны как Android, Desktop/Web и production не отмечены готовыми.

## Проверки

- Server regression: `python -m unittest test_documents_api test_documents_pdf test_excel_import test_excel_template test_portal_documents test_postgresql_documents_schema test_postgresql_integration test_payroll_settlement` — **66 tests, OK, 2 skipped**. PDF renderer smoke пропущен: ReportLab отсутствует; opt-in PostgreSQL regression требует отдельной disposable PG среды.
- Изолированная установка `reportlab==5.0.1`: venv создана; pip install не удался из-за сетевого запрета (`WinError 10013`). `pip cache list reportlab` не нашёл локальных wheels.
- PostgreSQL Documents: `python -m unittest test_documents_postgresql -v` — **4 skipped**, так как в текущем Windows окружении нет `psql`/PostgreSQL fixture. WSL установлен без Linux-дистрибутива. SQLite не использовалась как замена PostgreSQL gate.
- Android UI/source suite: `$env:NODE_PATH='C:\Users\darta\Documents\PORTAL-Android\node_modules'; node --test android_src/tests/*.test.cjs` — **25 passed, 0 failed, 0 skipped**. Включает Playwright Documents/Excel upload-preview-confirm-apply-result flow, owner company selection, permissions, native bridge contracts и retired runtime boundary.
- Python compile: `python -m py_compile documents_api.py pdf_documents.py test_documents_api.py test_documents_pdf.py test_documents_postgresql.py` — **passed**.
- `git diff --check` — **passed**.
- Android Java compile локально не запускался: проверены PATH, стандартные каталоги Java/Android/Gradle, repo scripts/wrapper; `java`, `javac`, `gradle`, Android SDK и Gradle wrapper отсутствуют. Существующий GitHub Android build включён для этой ветки.
- Manifest содержит только `INTERNET` и `ACCESS_NETWORK_STATE` из permissions; широких storage permissions нет. Проверены source/tests на `Uri.fromFile`, внешние `file://`, Telegram/Termux runtime и SMTP/API secrets. Внутренний `file:///android_asset/` используется только для загрузки packaged WebView UI.

## Открытые gates

- **PDF renderer открыт:** нельзя подтвердить реальные PDF bytes/layout до запуска smoke с pinned ReportLab 5.0.1 и Unicode font в окружении с доступным wheel/package source.
- **PDF PostgreSQL E2E открыт:** тест подготовлен, но требует disposable PostgreSQL на поддерживаемом Linux runner и запуска с `PORTAL_DOCUMENTS_PG_INTEGRATION=1`.
- **Android device/Java compile открыты локально:** Playwright и source contracts прошли, но физический Android picker/share/save flow и локальный Gradle compile недоступны. CI workflow для ветки добавлен и сможет проверить compile после push/запуска workflow.
- Desktop/Web Documents/Excel, централизованная Android↔Desktop sync, production rollout, постоянные domain/HTTPS и Android signing остаются незакрытыми.

Production DB/VPS, тарифы, зарплатные факты/snapshots, phone SQLite, APK version/signing и deployment не изменялись. Telegram/Termux runtime не возвращался.
