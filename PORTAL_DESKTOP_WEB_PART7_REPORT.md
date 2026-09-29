# PORTAL Desktop/Web — Part 7

Дата: 29.09.2026
Ветка: `codex-desktop-web-part7`
База: `853e6c3233458a773c914404552646c047e06239`

## Архитектура

Первый Web-клиент PORTAL построен без отдельной копии frontend-бизнес-логики. Маршрут `/web/` использует тот же канонический набор UI-assets, что и Android: `index.html`, `core.js`, `app.js`, `screens.js`, `production.js`, `preview.js`, `documents_excel.js`, стили, бренд-asset и системные стикеры.

`server/web_static.py` отдаёт только разрешённый allowlist файлов из общего каталога Android assets. API и серверная модель прав остаются общими для Android и Web; Web не получает отдельную бизнес-логику или отдельную модель ролей.

## Browser adapter

Добавлен `web_adapter.js`, который активируется только в HTTP(S)-браузере, когда native Android bridge отсутствует.

- API-запросы разрешены только same-origin и только по `/api/...`.
- Разрешены только используемые клиентом методы GET/POST.
- Токен передаётся только в `Authorization: Bearer`, не в query string.
- Company scope передаётся через существующий `X-Portal-Company` и валидируется до отправки.
- Произвольный server URL в Web не поддерживается: `getServerUrl()` возвращает текущий origin, `setServerUrl()` fail-closed.
- Web-сессия хранится в `sessionStorage`; Android сохраняет существующее поведение с `localStorage`.
- Logout очищает browser session.
- Download использует ограниченный MIME/extension allowlist, лимит 20 MiB, Blob/ObjectURL и обязательный `revokeObjectURL`.
- Web Share используется только при поддержке браузером. Если Share недоступен — выполняется безопасный download fallback. Если пользователь отменил системное меню Share, файл автоматически не скачивается.
- SMTP/API email-отправка и почтовые секреты не добавлялись.

## Web UI

Web использует общий login, Platform Owner company selection, роли/capabilities, темы, Documents, Excel, чат и остальные общие экраны.

Android-only элементы скрыты в Web:
- настройка произвольного адреса сервера;
- проверка/установка Android APK;
- Android permission/install flow.

В разделе «О программе» Web показывает, что Web-клиент обновляется автоматически. Добавлен desktop breakpoint для более широкой рабочей области, без глобального превращения всех списков в многоколоночный layout.

## Documents / Excel

Общий Web UI использует существующие серверные контракты:
- Documents list/filter/search/pagination;
- download/archive;
- PDF actions;
- blank/prefilled Excel templates;
- обычный browser `input[type=file]` для XLSX;
- preview/classifications;
- explicit apply confirmation;
- import result download/share fallback.

Полный реальный XLSX round-trip с PostgreSQL staging остаётся отдельным Part 8 gate; текущий Chromium smoke проверяет наличие и работу общего экрана и file chooser на безопасном mocked API.

## Static serving security

`/web` и `/web/` обслуживаются отдельным строгим static handler. Не обслуживаются `/webjunk` и произвольные похожие prefixes.

Блокируются traversal, percent/double-percent traversal, backslash, query/fragment tricks, hidden и неразрешённые имена файлов. Ответы содержат:
- `Content-Security-Policy` с `connect-src 'self'`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`;
- `X-Content-Type-Options: nosniff`;
- `Referrer-Policy: no-referrer`;
- `X-Frame-Options: DENY`;
- `Cache-Control: no-store`.

## Проверки

- Полный Android/Web Node + Playwright suite: **31/31 PASS, 0 failed, 0 skipped**.
- Отдельный Web adapter + Chromium smoke: **4/4 PASS**.
- Targeted server Web/Documents/Excel regression: **45/45 PASS**.
- Полный server regression: **196 tests OK, 16 skipped**, ошибок нет; skips относятся к environment-gated сценариям.
- `python -m compileall -q server android_src/tools` — **PASS**.
- `git diff --check` — **PASS**.
- GitHub Web CI использует pinned `playwright@1.62.1` и read-only `contents` permission.

APK локально намеренно не собиралась: по постоянному правилу проекта **Android APK собираем только через GitHub Actions**.

## Roadmap после Part 7

- №84 Desktop/Web — **🟡**: первый функциональный Web-клиент готов; нужен staging E2E с реальным PostgreSQL и прикладными flows.
- №85 Windows installer/update — **⏳**, не входит в Part 7.
- №86 Android/Web parity — **🟡**: общий UI и permission model используются совместно, но остаются platform-specific download/share и staging parity gates.
- Documents/Excel Web-часть отражена в пунктах 53, 55, 56, 58, 60, 62, 63 и 68 без ложного production-ready статуса.

## Открытые gates / рекомендуемый Part 8

1. Изолированный PostgreSQL staging E2E: login/owner scope, Documents, PDF, Excel preview/apply/result.
2. Полная матрица ролей director/admin/manager/accountant/shift/packer в Web на реальном API.
3. Проверка browser downloads и Web Share/fallback на целевых desktop-браузерах.
4. Определение политики Web re-authentication/session lifetime.
5. После этого — решение по Windows Desktop wrapper/installer (roadmap 85), не раньше.

Production/VPS, production DB, реальные данные, push, merge и deploy в Part 7 не затрагивались.
