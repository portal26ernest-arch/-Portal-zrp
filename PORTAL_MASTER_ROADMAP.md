# PORTAL MASTER ROADMAP

Канонический реестр требований проекта. Восстановлен из прежних больших ТЗ: блока реализации, 20-пунктового аудита и последующих дополнений. Пункты не удалять без явного решения владельца проекта.

Статусы: ✅ реализовано и проверено; 🟡 реализовано частично/нужен production-довод; ⏳ не реализовано; 🔌 отдельная внешняя интеграция.

## A. Платформа, компании, сотрудники и права

1. ✅ Platform Owner и управление несколькими компаниями.
2. ✅ Изоляция компаний на сервере и PostgreSQL RLS.
3. ✅ Роли admin, director, manager, packer, shift, accountant.
4. ✅ Директор: полные бизнес-права только внутри своей компании.
5. ✅ Индивидуальные разрешения поверх ролей.
6. ✅ Создание нового сотрудника без обязательной связи со старым.
7. ✅ Отдельный сценарий «Выдать доступ существующему сотруднику».
8. ✅ Логин/PIN, сессии, отзыв старых сессий после смены доступа.
9. ✅ История входов, Online/Offline, heartbeat.
10. 🟡 Безопасный одноразовый invite/access-request lifecycle и Android/Web create/list/accept/approve/revoke UI реализованы; Stage 10 hash-at-rest, идемпотентность, tenant scope и role denial подтверждены disposable PostgreSQL. Полная матрица ролей и production rollout остаются открытыми.
11. 🟡 Безопасная ссылка/одноразовая выдача токена и одобрение директором/admin реализованы; логин/PIN не передаются в URL. PostgreSQL проверяет отказ Platform Owner без выбора компании, действие только после явного выбора и привязку к существующему сотруднику без дублирования employee; полная роль-матрица и production rollout остаются открытыми.
12. 🟡 Серверный лимит активных пользователей, concurrency lock, unlimited PORTAL и Platform Owner fee/demo/status/limit UI реализованы; стандартный лимит и отказ сверх доступных мест проверены через PostgreSQL API. Module toggles и полнота director settings UI требуют отдельного завершения.
13. ✅ Уникальность логинов; с 3.1 вход должен быть без учёта регистра.
14. ✅ Активность/отключение пользователя без удаления истории.
15. 🟡 Company/owner audit views с фильтрами и пагинацией реализованы; Platform Owner authorization/filtering и отказ company admin/packer подтверждены disposable PostgreSQL. Остаются policy matrix и release/production gates.

## B. Клиенты, тарифы и производство

16. ✅ Клиенты: создание, изменение, активен/архив.
17. 🟡 Карточка клиента 360°: статистика и реквизиты есть, редактирование всех блоков неполное.
18. ✅ Операции клиента и ставки сотруднику/клиенту.
19. 🟡 Историчность тарифов и effective-date: UI текущих/прошлых версий и создание новой версии есть; Server/Web disposable PostgreSQL проверили повтор даты, effective boundary и сохранение старой ставки в work snapshot. Полная policy matrix и rollout остаются открытыми.
20. ✅ Импортированы действующие клиентские тарифы и исключения.
21. ✅ Ввод выработки клиент → операция → количество.
22. ✅ Немедленный расчёт сдельной зарплаты.
23. ✅ Партии товара.
24. ✅ Производственные задания и несколько исполнителей.
25. ✅ Таймер задания: старт/пауза/продолжить/завершить.
26. ✅ «Другая работа» без задания.
27. ✅ Привязка ранее внесённой работы к партии.
28. 🟡 План/факт партии и экономика партии.
29. ✅ Материалы и остатки.
30. ✅ Нормы материалов и фактическое списание при работе.
31. ✅ Модуль расходов: аренда, логистика, забор из ТК, доставка на маркетплейсы, коммунальные/управленческие и прочие расходы; общекомпанейские расходы отделены от расходов клиента.
32. 🟡 FBS/FBO/возвраты как операции есть; полноценные управляемые складские сценарии ещё не завершены.
33. 🟡 Нормализация имён клиентов/сотрудников и история переименований.
34. ✅ Алфавитная выдача основных справочников.
35. ✅ Каталог продуктов клиента: стабильные ID, CRUD/архив, поиск и tenant-scoped связь с партиями; Stage 12 PostgreSQL/Web CI и браузерный role flow прошли на Part 12.

## C. Зарплата, финансы и аналитика

36. ✅ Расчётные периоды 1–15 и 16–конец месяца: preview и закрытие реализованы в новом API/Android-контуре.
37. ✅ Закрытие/блокировка зарплатного периода и защита от новых начислений в закрытые даты; будущий период закрыть нельзя.
38. 🟡 Начислено/выплачено/остаток по сотруднику.
39. ✅ Счета клиентам.
40. ✅ Частичные и полные оплаты.
41. ✅ Базовая дебиторка: открытые/оплаченные суммы.
42. 🟡 Просрочка и расширенный контроль дебиторки.
43. 🟡 Выручка, себестоимость, маржа и прибыль по клиенту/партии.
44. 🟡 «PORTAL Сегодня» показывает подтверждённые объём, выручку и начисления за день/месяц, выплаты закрытого периода и открытые счета; без плана прибыль отмечается как недоступная. Полный набор метрик и rollout ещё не закрыты.
45. 🟡 Финансовый радар показывает дебиторку, просрочку, требующие внимания записи и сигналы убыточности клиентов; помесячная сводка учитывает часовой пояс компании. Полный набор источников и rollout остаются открытыми.
46. 🟡 Производительность команды в единицах/час считается только по выработке с зафиксированным временем; без времени UI сообщает, что данных нет. Сравнения клиентов/партий и качества неполны.
47. 🟡 Источники напоминаний, tenant-scoped идемпотентная доставка, cadence/run/retry metadata и disabled-by-default операторский runner реализованы и проверены. Автоматический системный timer и постоянная настройка расписания ещё не подключены.
48. ✅ Общий payroll Excel в новом APK/VPS-контуре: сводка, сотрудники и детализация.
49. ✅ Excel-расчётные листы по каждому сотруднику формируются отдельными листами.
50. ✅ Серверный A4 PDF-расчётный лист строится только из закрытого payroll snapshot и регистрируется как scoped Document; реальный ReportLab 5.0.1 + Unicode font smoke и PostgreSQL/RLS gate пройдены на изолированном VPS.
51. ✅ PDF «Счёт на оплату» использует существующие invoice/client/company data и строки работ; реальный renderer, повторная детерминированная генерация, scoped Documents и PostgreSQL/RLS E2E подтверждены на изолированном VPS.
52. ✅ Общий payroll XLSX содержит отдельный лист «Выплаты» с сотрудником, периодом, начислено/выплачено/остатком, датами выплат и итогами. Проверены renderer и полный HTTP → Documents → settlement ledger → XLSX поток тестами `test_report_xlsx.py` и `test_payroll_settlement.py`.

## D. Документы и Excel-импорт/экспорт

53. 🟡 Общий Documents API подключён к Android/Web UI; в Web реализованы список, фильтры, поиск, пагинация, скачивание, архивирование и PDF-действия. Production rollout ещё не проверен.
54. ✅ Blob и document metadata разделены, company-scoped storage и FORCE RLS подтверждены; PDF-specific PostgreSQL E2E с реальным renderer прошёл в одноразовой test DB с cleanup.
55. 🟡 Filters/paging Documents API и общий Web list/search UI реализованы; серверные regression-тесты фильтрации проходят, полная browser-матрица остаётся для staging.
56. 🟡 Общий Web-экран Documents и серверные права/archive покрыты backend-тестами и browser smoke; production deployment ещё не проверен.
57. ✅ Стандартный Excel-шаблон PORTAL v1.0: четыре русских листа, blank/prefill API для директора и выбранной компании Platform Owner; openpyxl round trip и изоляция проверены.
58. ✅ Web blank/prefilled Excel template download подтверждён реальным Chromium → HTTP API → disposable PostgreSQL E2E: реальные browser downloads, XLSX signature, MIME/filename, SHA-256 совпадение с server payload, разные blank/prefill contents и cross-company HTTP 403.
59. 🟡 Android bridge сохраняет поддерживаемые файлы в Downloads через system picker/MediaStore; source/UI tests есть, Java compile и проверка на устройстве открыты.
60. 🟡 Web Share API с безопасным download fallback реализован; фактическое поведение Share в целевых браузерах ещё нужно проверить.
61. 🟡 Email/тема/текст передаются в системный Android intent; отправка остаётся под контролем выбранного приложения, SMTP/API отправка не добавлена.
62. ✅ Web Excel chooser прошёл реальный Chromium → HTTP API → PostgreSQL staging round-trip: file input, preview, явное подтверждение, apply и скачивание результата.
63. 🟡 Общий Android/Web Excel UI содержит chooser, preview/classifications, явное подтверждение apply и download/share результата; реальный Web XLSX staging round-trip пройден, Android device/WebView flow ещё требует проверки.
64. ✅ Backend-валидация Excel: версия/листы/колонки, типы/роли/деньги/даты, ссылки, конфликты тарифов и лимиты ZIP/XML/строк проверены.
65. ✅ Backend: дубли, неоднозначные identity, unique-конфликты и идемпотентный повтор import_id/checksum проверены, включая реальную PostgreSQL.
66. ✅ Backend: явный apply к выбранной компании, атомарный rollback, неизменяемый результат и отчёт в Documents проверены в SQLite и одноразовой PostgreSQL. Production rollout не выполнялся.
67. ✅ Payroll XLSX export и invoice/payroll PDF routes реализованы; реальный ReportLab renderer и PDF PostgreSQL E2E с tenant isolation/immutability подтверждены.
68. 🟡 Общий Documents API и Web-скачивание доступны; независимые HTTP-сессии одной компании прошли create/list/metadata/download/archive E2E на disposable PostgreSQL (Part 12 Web #33, cleanup DB/roles/temp=0). Production rollout и оставшаяся UI revision/history parity не проверены.

## E. Внутренние коммуникации

69. ✅ Внутренний чат сотрудников поддерживает текст, вложения и переиспользуемый каталог системных стикеров PORTAL с allowlist ключей.
70. ✅ Общая комната сотрудников реализована с company isolation.
71. ✅ Личные/приватные комнаты сотрудников реализованы с проверкой участников.
72. ✅ В общем командном чате доступно структурированное сообщение «невыход» с датой и необязательным комментарием; оно не влияет на payroll, attendance или work_log.
73. ✅ Фото и файловые вложения чата: JPG/PNG/WebP/PDF/TXT до 2 МБ, проверка доступа к личной комнате, скачивание и сохранение на Android.
74. ✅ Физическое автоудаление обычных сообщений и их пользовательских вложений старше 14 дней реализовано.
75. ✅ Закреплённые сообщения сохраняются независимо от возраста; после открепления снова подпадают под retention.
76. ✅ Системный каталог «Стикеры PORTAL» хранит отдельные локальные SVG assets; сообщения ссылаются только на ключ.
77. 🟡 Раздел новостей Ozon переведён на company-scoped read API и пустое/LIVE состояние; автоматическое получение публикаций ещё не подключено.
78. 🟡 Раздел новостей Wildberries переведён на company-scoped read API и пустое/LIVE состояние; автоматическое получение публикаций ещё не подключено.
79. 🟡 Trusted ingestion boundary ограничивает HTTPS официальными seller-доменами и дедуплицирует по canonical external_key; scheduler и live-fetch остаются открытым gate.

### Part 5 — Communications + Marketplace News (29.09.2026)

- Закрыто: системный sticker catalog/assets, серверный allowlist ключей и отображение в командном чате.
- Закрыто: структурированный absence_notice в общем чате, валидация даты/комментария, повтор POST по request_id идемпотентен; payroll/attendance/work_log не меняются.
- Закрыто: company-scoped marketplace_news read API, фильтр и pagination; trusted ingestion upsert ограничен `seller.ozon.ru` и `seller.wildberries.ru`.
- Открыто: официальные live источники, безопасно доступные без авторизации и brittle scraping, не подключены; ingestion scheduler/operator gate остаётся отдельной работой.
- Открыто: production PostgreSQL migration/schema/runtime smoke для news API и Android staging APK build на этой ветке требуют отдельного окружения/CI run.

## F. Android, Desktop/Web и обновления

80. 🟡 Android-приложение: основной функционал есть, production cutover ещё не завершён.
81. ✅ Полноэкранный immersive-режим Android с восстановлением после возврата фокуса.
82. ✅ Встроенная проверка, безопасная загрузка, checksum/package/version/signer validation и системный Android Installer реализованы; Node контрактные тесты проходят. Отдельный gate: проверить разрешение неизвестных приложений и реальную установку/обновление на устройстве.
83. 🟡 Release workflow проверяет подпись и pin сертификата, APK package/version metadata и соответствие manifest артефакту. Production signing key и резервная копия существуют и совпадают; staging CI run 24 на commit c46917f успешно собрал и проверил installable signed staging APK. Открыты production GitHub Secrets/manual release gate и доказательство установки/обновления на физическом устройстве.
84. ✅ Первый функциональный Web-клиент подтверждён реальным Chromium → HTTP API → disposable PostgreSQL staging E2E: login/meta, Documents, archive/download, Excel preview/apply/result, cross-company denial и logout/revocation.
85. ⏳ Windows installer/обновление Desktop-клиента.
86. 🟡 Core UI и permission model общие для Android/Web; реальный Chromium → HTTP API → disposable PostgreSQL E2E подтверждён для admin/director/manager/packer и Platform Owner, включая явный выбор компании и cross-company scope. Открытой остаётся только физическая Android user-flow/parity проверка готовой APK без технических прогонов на телефоне.
87. ✅ Десятичная нумерация сборок 3.0 → 3.1 → … → 3.9 → 4.0.
88. ✅ GitHub CI: серверные тесты, Android UI и сборка APK, отдельные Web/Playwright checks.

## G. VPS, база, безопасность и миграция

89. ✅ PostgreSQL на купленном VPS.
90. ✅ Реальная копия телефонной SQLite перенесена и сверена на VPS.
91. ✅ RLS/изоляция компаний и fail-closed проверки схемы.
92. ✅ Backup/restore rehearsal PostgreSQL.
93. 🟡 Вторичная/off-server backup-копия production.
94. ⏳ Домен и DNS production API.
95. ⏳ HTTPS/reverse proxy production.
96. ⏳ Финальный write-freeze телефона и свежий snapshot SQLite.
97. ⏳ Финальный импорт в production PostgreSQL.
98. ⏳ Независимая сверка финального импорта и финансовых сумм.
99. ⏳ Production cutover: реальные записи начинают идти только в VPS.
100. ✅ Rollback-процедура спроектирована; финальный production rehearsal ещё нужен.
101. ✅ Опасные runtime-зависимости Telegram/Termux удалены из новой архитектуры.
102. 🟡 Runtime/API переведены на employee_id через compatibility boundary; физические legacy-колонки telegram_id пока сохранены для истории.
103. ✅ Защита от повторных записей/идемпотентность в критичных сценариях.
104. ✅ Regression/unit/integration тесты и GitHub gates.
105. 🟡 Денежные расчёты: новый производственный слой использует cents; legacy REAL-поля ещё требуют дальнейшей нормализации.

## G1. Stage 7 staging — повторно проверено 28.09.2026

- ✅ Последний изолированный staging deploy на VPS подтверждён на commit `31baa268218960f2e06c75e0ead822f81388c512`.
- ✅ Staging БД: `portal_test_stage7_staging`; production БД не переключалась и не изменялась.
- ✅ API слушает только `127.0.0.1:8770`.
- ✅ PostgreSQL слушает только loopback `127.0.0.1/[::1]:5432`.
- ✅ `portal-stage7.service` active/running под отдельным runtime-контуром.
- ✅ Внешний HTTPS smoke подтверждён через временный Cloudflare Quick Tunnel; URL меняется и не является постоянным доменом.
- ✅ `/api/ping` возвращает healthy и `setup_required=false`.
- ✅ Внешний `POST /api/setup` блокируется HTTP 403.
- ✅ Runtime-роли `portal_stage7_tenant` и `portal_stage7_control` не superuser и без BYPASSRLS.
- ✅ RLS включён на 45 таблицах staging.
- ✅ Секреты и first-login-файл имеют mode 0600; каталог `/etc/portal-stage7` — 0700.
- ✅ Live API CRUD/RLS/isolation/restart integration прошёл на VPS; локально Stage 7 safety tests: 11/11, полный server regression: 144 OK, 11 skipped.
- ✅ Для проблемного SSH-пути реализован локальный server-banner-first relay; pinned host key и pinned identity сохранены.
- 🟡 SSLIP DNS указывал на VPS, но внешний HTTP-01 challenge не смог получить ответ от TCP/80; точный блокирующий firewall-слой не установлен. Quick Tunnel остаётся временным pilot-каналом.
- ⏳ Постоянный staging/production domain и постоянный HTTPS остаются отдельным gate.
- ⏳ Production cutover не выполнялся.

## G2. Documents + Excel Part 3 — локальный частичный срез (29.09.2026)

- 🟡 Android Share Sheet для ready Documents/Excel шаблонов/безопасного import result добавлен: FileProvider content://, внутренний cache, MIME allowlist, read grant и chooser. Source contract tests прошли; staging Java/Gradle compile подтверждён GitHub CI 29.09.2026. Реальный share/save flow на физическом Android ещё требует device gate.
- 🟡 PDF «Счёт на оплату» и краткий PDF «Расчётный лист» реализованы локально из invoice/closed-payroll snapshots и scoped Documents API; invoice/payroll route tests проверяют права, tenant scope и неизменность фактов с тестовым renderer. Реальный A4 smoke пропущен без ReportLab/Unicode font; PostgreSQL PDF end-to-end остаётся открытым.
- ⏳ Part 3 production/Android release gates открыты. Тестовый итог и ограничения см. `PORTAL_DOCUMENTS_EXCEL_PART3_REPORT.md`.

## G3. Documents + Excel Part 4 — проверки и сверка статусов (29.09.2026)

- 🟡 До Part 4 уже существовали Android blank/prefill template download и сохранение, XLSX picker/upload/preview/явный apply/result, Share Sheet/email intent, invoice/payroll PDF routes и Documents registration. Part 4 не дублировал эти функции.
- 🟡 Ошибка запуска Android file chooser теперь завершает ожидающий WebView callback значением null; source contract test проверяет успешный и отменённый/ошибочный возврат. Staging Java compile подтверждён CI; реальный Android device/WebView flow остаётся открытым.
- 🟡 Добавлены runnable PDF route smoke с реальными изолированными test API records и PostgreSQL PDF generated-Documents integration test. Оба требуют исполнения в среде с pinned renderer/изолированным PostgreSQL соответственно.
- ⏳ Production rollout, Desktop/Web client/sync и постоянные домен/HTTPS остаются открыты. Android production-signing workflow и постоянный key подготовлены; до релиза остаются GitHub Secrets/manual release gate и физическая установка/обновление.
- Точные команды и ограничения см. `PORTAL_DOCUMENTS_EXCEL_PART4_REPORT.md`.

## G4. Web + PostgreSQL Part 8 — реальные staging-gates (29.09.2026)

- ✅ Реальный Chromium → HTTP API → disposable PostgreSQL E2E пройден: login/meta, Documents download/archive, XLSX preview/apply/result, cross-company 403 и logout/revocation 401.
- ✅ Финальный PostgreSQL Documents/Excel/PDF suite: 6 tests OK, 1 browser-only skip; browser gate выполнен отдельно через Windows Chromium и SSH tunnel.
- ✅ Реальный ReportLab 5.0.1 + DejaVuSans PDF smoke: 1/1 OK; A4, Unicode/Cyrillic, signature order и financial immutability подтверждены.
- ✅ Найден и исправлен production-дефект недетерминированных PDF: ReportLab `invariant=1`, повторная генерация возвращает тот же scoped Document.
- ✅ Финальная локальная регрессия Part 8: Python 199 OK / 19 skipped, Node 31/31 PASS, compileall/node-check/diff-check OK.
- ✅ После VPS-тестов: disposable DB/roles и временные ReportLab dependencies удалены; production Stage 7/production DB не менялись.
- 🟡 Platform Owner/Packer browser scopes закрыты Part 10; Web download blank/prefill template закрыт Part 11. Открыты Android user-flow/parity готовой APK, production rollout и Windows installer.
- Полный отчёт: `PORTAL_WEB_POSTGRES_PART8_REPORT.md`.

## G5. Web + Invoice revisions Part 10 — реальные role/revision gates (29.09.2026)

- ✅ Реальный Chromium → HTTP API → disposable PostgreSQL E2E подтверждён для Director, Manager, Packer и Platform Owner.
- ✅ Director через Web сформировал и скачал `invoice_xlsx`, затем перевёл счёт `finalized → editing`.
- ✅ Manager через Web изменил разрешённую строку счёта и сохранил `revision 2`; итоговое состояние снова `finalized`.
- ✅ Packer не видит раздел счетов и получает HTTP 403 при прямом запросе invoices API.
- ✅ Platform Owner до выбора компании получает HTTP 403, после явного выбора компании A работает в её scope, а компания B возвращает пустой список счетов.
- ✅ Owner audit за тестовый сценарий: 16 записей; чужая компания: 0 счетов.
- ✅ Финальный результат: `BROWSER_EXIT=0`, `FIXTURE_VERIFIED=True`, `INVOICE_REVISION=2`, `INVOICE_XLSX_DOCUMENTS=1`, `PART10_REAL_WEB_PG_E2E=PASS`.
- ✅ Cleanup доказан: после теста disposable DB = 0, disposable roles = 0; production DB/service не изменялись.
- ✅ GitHub Web и Server CI для ветки Part 10 прошли; локально targeted server 28/28 и Web/Playwright 4/4.
- 🟡 Web blank/prefill download закрыт Part 11. Остаются Android user-flow/parity готовой APK, Windows installer, production domain/HTTPS и production cutover.
- Полный отчёт: `PORTAL_PART10_WEB_INVOICE_E2E_REPORT.md`.

## G6. Web Excel template download Part 11 — реальный staging-gate (29.09.2026)

- ✅ Blank и prefilled PORTAL Excel templates реально скачаны через Chromium Web UI с настоящего HTTP API поверх disposable PostgreSQL.
- ✅ Browser download и server payload полностью совпали по SHA-256; оба файла имеют корректный XLSX/ZIP signature и MIME.
- ✅ Blank и prefilled содержимое различаются: 5689 и 6094 байта соответственно в проверенном запуске.
- ✅ Director не может подменить company scope: forged `X-Portal-Company` получил HTTP 403.
- ✅ GET/download шаблонов не изменяет clients/operations/employees/Documents: before/after counts идентичны.
- ✅ Финальный результат: `BROWSER_EXIT=0`, `PART11_BROWSER_DOWNLOAD=PASS`, `FIXTURE_VERIFIED=True`, `PART11_REAL_WEB_TEMPLATE_DOWNLOAD=PASS`.
- ✅ Cleanup: disposable DB = 0, disposable roles = 0; production DB/service не использовались как test target.
- Полный отчёт: `PORTAL_PART11_WEB_TEMPLATE_DOWNLOAD_REPORT.md`.

## H. WMS TalAnt, ТСД и сканирование

106. 🔌 Интеграционный слой PORTAL ↔ TalAnt через официальный API без изменения TalAnt.
107. 🔌 Авторизация/tenant/company/warehouse-доступ TalAnt.
108. 🔌 Номенклатура: ID, SKU, GTIN, штрихкоды и КИЗ.
109. 🔌 Остатки, ячейки, складские движения.
110. 🔌 WMS-заказы WB/Ozon FBS/FBO.
111. 🔌 Сборка, упаковка, маркировка и отгрузка через API TalAnt.
112. 🔌 Приёмка, размещение, перемещения, возвраты, инвентаризация.
113. 🔌 Webhooks/события TalAnt.
114. 🔌 Идемпотентность, подтверждения и защита от дублей TalAnt.
115. 🔌 Sandbox/тестовая среда TalAnt.
116. 🔌 Android-ТСД со встроенным аппаратным сканером.
117. 🔌 Поток сканирования GTIN/штрихкод/DataMatrix/КИЗ → PORTAL → TalAnt → подтверждение.

## I. Постоянные правила развития

118. ✅ Не удалять подтверждённые функции и тарифы ради рефакторинга.
119. ✅ Все изменения вести в одном основном проекте/репозитории с номерами сборок.
120. ✅ Release-проверки и технические прогоны выполняются в GitHub/GitHub Actions и на VPS; телефон используется только для скачивания/установки готовой APK и обычной пользовательской проверки.
121. ✅ Телефон после production cutover — только клиент, не сервер.
122. ✅ Не допускать одновременную production-запись в старую SQLite и новую PostgreSQL.
123. ✅ Каждую новую функцию закрывать тестом или явным контрольным сценарием.
124. ✅ Этот файл является постоянным checklist: перед release проверять все ⏳/🟡 пункты и не терять их между сборками.
125. 🟡 Stage 7 baseline и последняя версия кода подтверждены в PORTAL_STAGE7_VERIFIED_REPORT.md: отдельная test-БД, checksum-история migrations, loopback API/PostgreSQL, runtime-роли, RLS, live CRUD/tenant isolation/restart и внешний HTTPS Quick Tunnel smoke. SSLIP DNS разрешается на VPS, но HTTP-01 на TCP/80 не прошёл; постоянный домен/HTTPS и 3.4 release gate остаются открыты.
126. ✅ Канонический визуальный регламент preview APK хранится в `docs/PORTAL_UI_BLUEPRINT_PREVIEW_APK.md`. Каждая preview APK должна сохранять утверждённую карту меню/экранов, директорский `PORTAL Сегодня`, состояния LIVE/PREVIEW/FUTURE и запрет на мёртвые кнопки.

## J. Part 12 finalization candidate (30.09.2026)

- Base verified: `bc95a942021bb5c43d112f51d2c2e7881059b47a` (Part 11); company knowledge commit `615495c3fef1f134ac651416f60b37809bda6380` is included.
- Candidate Android metadata advanced from 3.4/34 to `3.5-dev-staging`/35. This is a staging build candidate only; no release workflow or production endpoint is authorized by this change.
- Part 12 implementation is in progress. No additional roadmap item is marked complete by this bootstrap checkpoint. Existing Parts 8–11 evidence remains authoritative for their verified items.
- Production cutover, DB mutation, DNS changes, production service/config changes, and real financial operations were not performed.
- Part 12 continuation #3 verified tariff effective-date snapshots, timezone-aware financial month buckets, dashboard daily/monthly figures and source-backed team productivity. At `7917dac` local Server discovery passed 244 tests with 31 skips; Web disposable PostgreSQL and Server passed, and the same client code passed Android UI/APK CI at adjacent SHA `2548d97`. Item 47 moved from ⏳ to 🟡 after operator-run scheduling metadata/tests; the system timer remains open. Current counts: **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**.
- Windows installer is not yet implemented; local `dotnet` is unavailable. See `PORTAL_FINALIZATION_PART12_PROGRESS.md` for remaining work and `PORTAL_FINAL_EXTERNAL_BLOCKERS.md` for provider/owner actions.
- Roadmap item 52 is closed on this branch after targeted HTTP/Documents/XLSX integration and workbook tests; payroll ledger facts are read from append-only settlement events and are not written into the closed snapshot.
