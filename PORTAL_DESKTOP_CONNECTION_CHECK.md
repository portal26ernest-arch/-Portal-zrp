# PORTAL Desktop — проверка подключения (01.10.2026)

Ветка: `codex/desktop-client-connection`. Исходный HEAD: `df63f7d6b4b168b21f0804b5ce96678dca36097c`. Кодовый коммит: `3cc72aed37298f74d92864968957b0c202cab62f`.

## Что установлено

- На текущей машине нет установленной версии PORTAL Desktop, сохранённого `desktop.json` или `PORTAL_SERVER_URL`. Точный пользовательский сбой здесь воспроизвести нельзя без адреса сервера и текста ошибки с той Windows-машины.
- Desktop — WPF/WebView2 оболочка общего `/web/` приложения. Серверный Web handler возвращает HTML по `GET /web/`; локальные `test_web_static` и `test_desktop_update` прошли 7/7.
- По действующему roadmap постоянный production domain/HTTPS ещё не настроен. Desktop намеренно отвергает обычный HTTP к VPS и принимает только HTTPS либо HTTP к loopback. Если сервер отдаёт 404/redirect/non-HTML на `/web/`, это несовместимый endpoint или неразвёрнутый Web-клиент, а не проблема логина.

## Исправлено в клиенте

1. Пустая переменная `PORTAL_SERVER_URL` больше не перекрывает сохранённый адрес.
2. До сохранения адреса клиент проверяет `GET /web/` за 12 секунд и показывает отдельную причину для redirect, HTTP error, non-HTML, timeout и сети/TLS.
3. При повторном подключении используется уже инициализированный WebView2. Ранее повторное создание environment для того же WebView могло завершаться ошибкой.
4. WebView2 работает с InPrivate profile; при выборе другого сервера активный браузерный сеанс очищается. На ПК остаётся только выбранный origin и технические файлы runtime; пользовательские скачанные документы остаются там, куда их сохранил пользователь.
5. До выбора сервера WebView2 navigation закрыта, кроме внутреннего `about:blank`.

Код, документация и Windows CI пакет находятся в GitHub. Компания хранит рабочие данные в PostgreSQL через API; GitHub не используется как база клиентов или финансовых фактов.

## Проверки и предел вывода

- `python -m unittest test_web_static test_desktop_update -q`: 7 passed.
- Более широкий `python -m unittest test_portal_app_server test_web_static test_desktop_update -q`: 21 passed.
- `ops/test_portal_desktop_installer.ps1`: checksum, versioned install, shortcut, duplicate-version rejection и archive traversal — passed на локальном синтетическом пакете.
- WPF XAML XML parse и `git diff --check`: passed.
- [Windows CI run 36849467057](https://github.com/portal26ernest-arch/-Portal-zrp/actions/runs/36849467057): success на кодовом SHA `3cc72ae`; WPF publish, self-contained ZIP, SHA-256, installer safety contracts, установка в disposable per-user profile и upload artifact `PORTAL-Desktop-win-x64-3.5.0` прошли. Локального `dotnet` SDK нет.
- Ни production сервер, ни его данные не менялись. Точный сетевой отказ у пользователя остаётся неподтверждённым, пока не известны адрес без секретов и сообщение приложения.

## Диагностика адреса

В поле сервера указывается только origin, например `https://portal.example.ru`, без `/web/`. Открытие `https://<адрес>/web/` в обычном браузере должно вернуть страницу входа PORTAL, а не redirect/404. Для изолированного локального теста допускается `http://localhost:<порт>`.
