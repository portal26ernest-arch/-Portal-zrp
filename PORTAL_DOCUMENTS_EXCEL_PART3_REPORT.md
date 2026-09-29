# PORTAL Documents + Excel Part 3

Date: 2026-09-29
Branch: `codex-documents-excel-part3`
Base: `64ea667`

## Implemented locally

- Android Share Sheet for ready Documents, Excel templates, and import result JSON. The native bridge accepts only PDF/XLSX/JSON with matching extensions and MIME, writes into internal `cache/shared/`, shares an AndroidX FileProvider `content://` URI with a temporary read grant and chooser, and accepts optional email/subject/text extras. The decoded-file limit is 20 MiB, encoded input is limited to 28 MiB, and cache usage is capped at 40 MiB. No broad storage permission, SMTP/API or saved mail credentials were added.
- Server PDF routes through `POST /api/v3/document-generate`: `invoice_pdf` takes `invoice_id`; `payroll_slip_pdf` takes `payroll_period_id` and `employee_id`. Generated files are registered through the existing Documents store with company/client/invoice or company/employee/period scope and metadata.
- Invoice generation requires `documents.manage` and `invoices.read`, uses the selected company, scoped invoice, client and existing requisites, and work operation/quantity/price/amount. It fails closed if lines or required line data are absent. It does not invent missing values.
- Payroll slip generation requires `documents.manage`, `payroll.all`, and `payroll.settlement.read`; it requires a closed period and an employee in that period snapshot. It includes no client/work details. Signature order is company manager, department manager, employee. The test compares snapshots and payroll settlements before/after generation.
- UI exposes PDF creation for available invoices and employees in closed periods, saves the generated PDF, and exposes sharing only for ready documents/templates/import result. Existing Part 2 Documents and Excel flow remained covered by UI tests.

## Files changed

- `PORTAL_DOCUMENTS_EXCEL_PART3_TASK.md`
- `PORTAL_DOCUMENTS_EXCEL_PART3_REPORT.md`, `PORTAL_MASTER_ROADMAP.md`
- `android_src/app/build.gradle`, `android_src/app/src/main/AndroidManifest.xml`, `android_src/app/src/main/res/xml/share_paths.xml`
- `android_src/app/src/main/assets/documents_excel.js`, `android_src/app/src/main/assets/production.js`
- `android_src/app/src/main/java/ru/portal/app/MainActivity.java`
- `android_src/tests/documents-excel.test.cjs`, `android_src/tests/native-shell.test.cjs`
- `android_src/tests/ui.test.cjs`
- `server/documents_api.py`, `server/portal_app_server.py`, `server/pdf_documents.py`
- `server/requirements.txt`, `server/requirements-test.txt`
- `server/test_documents_api.py`, `server/test_documents_pdf.py`

## Verification

- `node --test android_src/tests/*.test.cjs` with `NODE_PATH=C:\Users\darta\Documents\PORTAL-Android\node_modules`: **25 passed, 0 failed, 0 skipped**. Includes browser regressions and Documents/Excel live flow.
- The browser regression test now waits for the archive refresh to finish before exercising the document filter; this removes an observed request-order race.
- Full targeted server command `python -m unittest test_documents_api test_documents_pdf test_excel_import test_excel_template test_portal_documents test_postgresql_documents_schema test_production`: **64 tests, 63 passed, 1 skipped, 0 failed**. The skip is the real PDF renderer smoke test because ReportLab is unavailable.
- Generator-focused rerun after payroll immutable-facts assertions: `python -m unittest test_documents_api test_documents_pdf`: **11 tests, 10 passed, 1 skipped, 0 failed**.
- `python -m py_compile server/documents_api.py server/pdf_documents.py server/test_documents_api.py server/test_documents_pdf.py`: **passed**.
- `git diff --check HEAD`: **passed**.
- ReportLab dependency check failed with `ModuleNotFoundError`. Installing pinned `server/requirements-test.txt` in an isolated local venv failed because the environment cannot connect to PyPI (`WinError 10013`); neither global packages nor production services were changed.
- Android staging Java compilation is **not verified**. The retry found no `gradlew.bat`, `gradle`, `java`, or `javac` on PATH, and no `ANDROID_HOME`/`ANDROID_SDK_ROOT` configured. A prior offline Gradle 8.9/JDK 17 attempt also stopped during dependency resolution because required Android/Guava artifacts were uncached, before Java compilation.
- PostgreSQL schema/Documents tests ran using existing isolated fixtures. There is no PostgreSQL PDF end-to-end test.

## Remaining risks

- Actual ReportLab PDF bytes and A4 layout were not rendered or visually inspected in this environment. The server build/runtime needs the pinned ReportLab package and a Unicode font (configure `PORTAL_PDF_FONT` or provide one of the supported system font paths).
- Android Java compile and PostgreSQL PDF end-to-end verification remain open. Production gates remain open.
- No production/VPS, database, phone SQLite, tariff, payroll fact/snapshot, APK/signing/version or deployment changes were made.
