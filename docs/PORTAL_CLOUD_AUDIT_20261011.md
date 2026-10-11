# PORTAL: аудит исходников и локальные исправления — 11.10.2026

## Границы и состояние

База: `main` / `c55ac9e66f19510c324d03e9f7f87dea62a2a229`.
Рабочая ветка: `assistant/portal-audit-local-20261011`. После fetch локальный HEAD
совпадал с origin/main. Рабочая копия до задачи была чистой.
Рассмотрены README, AGENTS, релевантные разделы master roadmap, правила release integrity,
архитектура Server/API, общая Web UI, текущий WPF Desktop, авторизация,
SQLite/PostgreSQL boundary и конфигурации CI. Это аудит исходников и локальных
регрессий, не penetration test и не проверка действующего runtime.

Git read через существующую платформенную аутентификацию работает.
GitHub API для open PR и main Actions отвечает Forbidden. Поэтому актуальные
статусы PR/Actions не подтверждены; наличие workflow в Git не означает зелёный CI.
Production/VPS, SSH, DNS, deploy, рабочие базы и секреты не использовались.
Проект «Игра» не открывался и не изменялся. Merge запрещён.

## Архитектура и проверки границ

- Server: `portal_app_server.py` / ThreadingHTTPServer; `portal_config.py` явно
  выбирает backend. Production требует PostgreSQL и отдельные tenant/control DSN;
  локальные проверки использовали только синтетические SQLite/in-memory fixtures.
- Авторизация: login throttle, хеширование сессий, tenant scope и отдельный
  Platform Owner boundary присутствуют. Общий UI обрабатывает HTTP 401 через
  logout, поэтому catch фоновой проверки `/api/me` сам по себе не доказывает
  обход авторизации. Локальные тесты не подтверждают RLS действующей БД.
- PostgreSQL pool ограничен; ожидание свободного соединения и connect timeout —
  по 10 секунд. Проверка borrowed connection выполняет SELECT 1 и rollback.
  Нет измерений текущей загрузки пула, RTT или плана запросов production.
- Web: same-origin adapter, ограниченные API paths, session/company/permission
  cache scope; POST нельзя безопасно автоматически повторять после потери ответа.
- Desktop: актуальная оболочка — `desktop_windows/`, а `desktop/windows/README.md`
  описывает старый Edge launcher. WPF использует normal WebView profile и
  encrypted cache/outbox; старые документы с InPrivate уже не описывают код.
- Мобильные клиенты разделяют assets. Изменение adapter затрагивает Web/Desktop;
  при существующем native PortalNative adapter не устанавливается.

## Подключение Desktop: что доказано кодом

1. `MainWindow_Loaded` без явно заданного server URL сначала ждёт
   `ConnectFirstAvailablePortalServerAsync`. Два automatic origin проверяются
   параллельно, но внутри каждого `/api/ping` и `/web/` последовательны и имеют
   общий 10-секундный budget. Затем WebView начинает собственную навигацию.
   Не следует ошибочно считать эти две automatic пробы последовательными.
2. Если обе пробы automatic endpoints неудачны, показывается setup, даже при
   наличии local cache: изначально загруженная Web UI ещё не существует.
   Local-first business data не устраняет dependency на начальную загрузку shell.
3. `PortalConnectProxy.ConnectIpv4Async` разрешает DNS, отбрасывает IPv6 и
   перебирает IPv4 последовательно. Token связан с закрытием приложения;
   отдельного connection deadline для адреса нет. Это источник потенциального
   ожидания ОС, а не измеренная причина задержки на рабочем ПК.
4. Browser proxy принудителен с `--proxy-bypass-list=<-loopback>`; CONNECT bridge
   разрешает только два официальных hostname. Это конфликтует с поддержкой
   произвольного/custom и HTTP loopback origin в UI: HTTP GET proxy получает 405,
   custom CONNECT — 403. Нужен отдельный нативный regression/fix для маршрутизации.
5. `RefreshOfficialServerAsync` наследует общий HttpClient.Timeout = 5 минут и
   не задаёт свой cancellation token для discovery/body. Это manual update/check
   path, а не доказательство пятиминутной паузы при обычном старте.
6. Web/Desktop adapter до исправления создавал отдельный запрос для каждого
   одинакового чтения, включая background cache refresh. Локальный regression
   подтвердил два GET вместо одного для двух concurrent callers. Это исправлено.

Без Windows/WebView2, трассировки рабочего ПК и разрешённых сетевых измерений
нельзя установить основной источник пользовательской задержки или назвать
фактическое ускорение в секундах. Исторические отчёты о сетевых адресах не
подменяют измерения текущих официальных endpoints.

## Исправлено в этой ветке

### JSON API

Обычные routes принимали Python JSON extensions NaN/Infinity/-Infinity и
float overflow 1e999. Теперь parsing отклоняет их ValueError; обычные int/float
сохраняются, а settlement decimal spelling сохраняется как строка.
Тест до исправления показал пять отдельных ошибочных принятия значения.
HTTP regression использует реальные HTTP bytes через MemorySocket, без внешнего
сокета; authenticated POST `/api/admin/clients` должен вернуть 400.

### Concurrent GET и целостность кэша

Только cache-eligible authenticated GET с совпадающими path/query, token,
company, scope и generation разделяют Promise. После завершения/error запись
удаляется; POST не объединяется и не повторяется. Cache hits остаются мгновенными,
а их background refresh объединяется.
Успешный POST и смена cache identity/company изменяют generation. Ответ
предыдущего чтения больше не перезаписывает кэш после mutation/identity change.
Регрессия до исправления воспроизвела stale overwrite.
Серверная авторизация остаётся обязательной; local cache не является authority.

Новый JS suite добавлен в existing Web CI. Python suite автоматически включается
в existing server CI discovery. Сам CI не изменён для доступа к production.

## Приоритетный план остатка

| Приоритет | Работа | Следующая безопасная проверка |
| --- | --- | --- |
| P1 | Deadline/cancellation для Desktop DNS/connect/discovery и ограничение discovery body при отсутствии Content-Length | Portable .NET tests с fake handlers и локальными socket fixtures; затем Windows CI |
| P1 | Исправить forced proxy для loopback/custom origin | Windows/WebView2 local fake API, allowed-host и HTTPS regression; не менять системный proxy |
| P1 | Offline startup при сохранённом origin/cache без обхода server validation и outbox migration | Нативный тест отключённой сети, отдельно восстановление session/tenant и stale permissions |
| P1 | Ограничить зависшие HTTP client reads / concurrency, согласовать с reverse-proxy timeout | Исключительно disposable localhost partial-body/load tests; проверить edge policy отдельно |
| P2 | Измерить Startup DNS/TCP/TLS, health, WebView init, navigation, first API и cache hit | Тайминги без tokens/body/PII; локальный synthetic delay matrix, потом отдельное разрешение на реальные измерения |
| P2 | Проверить PostgreSQL pool/RLS/query count при burst startup | Только отдельный disposable PostgreSQL после изменения разрешённого scope; не рабочая БД |
| P2 | Native integration coverage вместо одних source-string guards | Portable connection-policy suite, Windows CI, Android/iOS CI для applicable shared changes |
| P2 | Dependency vulnerability scan и lock transitive dependencies | Отдельный registry-only аудит; в этой задаче CVE scan не выполнялся |
| P3 | Reconcile исторические Desktop/architecture документы | Сверять с фактическим кодом; root README уже обновлён |

## Воспроизводимость и ограничения проверки

Тестовый runner вне Git: `/workspace/.portal-cloud-safe/run_audit_tests.py`.
Он запускает Python и Node с очищенным allowlist окружением; live flags=0,
ключи/DSN не наследуются. Python audit checks запрещают внешние сокеты,
дочерние процессы и SQLite/запись вне собственного локального каталога.
Из broad local regression исключены целиком:
`test_documents_postgresql`, `test_migration_full_cli`, `test_migration_full_vps`,
`test_migration_postgresql_live`, `test_postgresql_integration`,
`test_web_postgresql_e2e`, `test_messenger_relay`, `test_messenger_relay_ws`.

Первый расширенный прогон: новый HTTP test ошибочно использовал POST route,
возвращающий 405; исправлен на поддерживаемый `/api/admin/clients`.
Document fixture конфликтовал с унаследованным local API document root; runner
больше не навязывает fixtures этот root. Четыре local relay socket tests были
заблокированы guards; весь модуль исключён, ограничения не ослаблены.
Эти результаты не замалчиваются и не означают production application failures.

Финальный повторный прогон: **345 Python tests PASS, 0 failures/errors/skips**;
**24 Node tests/check files PASS, 0 failures/skips**. Это безопасная local subset,
не полный production/native/integration gate.
Команда: `/workspace/.portal-cloud-safe/venv/bin/python -I -B /workspace/.portal-cloud-safe/run_audit_tests.py`.
Лог текущего прогона: `/workspace/.portal-cloud-safe/audit-tests-final.log`.
Отдельный localhost smoke нового Server: `/api/ping`, `/api/ready`, `/web/`,
`/web/core.js`, `/web/web_adapter.js` — HTTP 200, readiness=true, тела непустые.
`control.py check` подтвердил SQLite, отсутствие ключей/DSN и отключение интеграций.
csproj/XAML XML syntax и `git diff --check` прошли. Независимый read-only review
не нашёл блокирующих регрессий; его замечания о тестах учтены.
Windows/.NET SDK в среде отсутствует; native build и physical Desktop smoke
не выполнялись. Проверка csproj/XAML XML не заменяет компиляцию.
Браузерные Playwright и live PostgreSQL gates не выполнялись.
Python hooks не являются kernel security boundary против намеренно вредоносного
native-кода. Production fixes, CI success и readiness действующих клиентов
из локальных результатов не следуют.
