# PORTAL MASTER ROADMAP

> **ЕДИНСТВЕННЫЙ ИСТОЧНИК ИСТИНЫ ДЛЯ ПРОЕКТА PORTAL.**
>
> Перед ЛЮБОЙ работой — ChatGPT, Codex, GBI, другой агент или человек — сначала прочитать этот файл целиком/релевантные разделы. После работы обновить этот файл в том же коммите: что принято, что сделано, что проверено, что осталось и какой следующий шаг. Никакие задачи, договорённости или замечания не считаются зафиксированными, пока они не внесены сюда.
>
> Код, ТЗ, история изменений и релизные инструкции хранятся централизованно в одном GitHub-репозитории `portal26ernest-arch/-Portal-zrp`. VPS запускает только версии, полученные из этого репозитория. Рабочий ПК и телефон не являются источниками истины и не должны содержать уникальную единственную копию проекта. База компании хранится централизованно в PostgreSQL на VPS; исходники и ТЗ — в GitHub. Это одна логическая система PORTAL с разделением runtime-данных и версионируемого кода.
>
> **Запрещено:** выпускать релиз из боковой/случайной ветки; хранить уникальные изменения только локально; начинать новую задачу без проверки этого файла; удалять ранее подтверждённую функцию ради рефакторинга без явного решения владельца; считать задачу завершённой без теста/контрольного сценария и записи результата сюда.
>
> **ГЛОБАЛЬНОЕ ПРАВИЛО СИНХРОННОГО РАЗВЁРТЫВАНИЯ:** любое изменение общей функциональности PORTAL считается завершённым только тогда, когда оно применено и проверено на ВСЕХ активных контурах, которыми реально пользуются: всех VPS/сервисах, портах, публичных и внутренних URL/ссылках, туннелях, Desktop/Web, Android и iOS-точках подключения. Перед завершением каждой задачи обязательно определить полный список активных endpoint-ов/сервисов, развернуть совместимое изменение на каждом из них и выполнить smoke-проверку каждого. Нельзя сообщать владельцу «исправлено» или «готово», если проверен только один сервер/порт/URL при наличии других активных контуров. Исключение допустимо только по явной команде владельца ограничить изменение конкретным окружением. Тестовые данные при такой проверке не переносятся между окружениями и после smoke-теста удаляются/откатываются.
>
> **ГЛОБАЛЬНОЕ ПРАВИЛО ANDROID ↔ iOS PARITY:** PORTAL Android и PORTAL iOS — два мобильных клиента одной системы, а не отдельные продукты. Любая новая бизнес-функция, модуль, роль, право, экран, серверный контракт или пользовательский workflow, добавляемые в мобильный PORTAL, по умолчанию проектируются и реализуются одновременно для Android и iOS. Платформенные исключения допускаются только когда функция объективно зависит от конкретной ОС либо владелец явно ограничил задачу одной платформой. Общая бизнес-логика и данные должны оставаться на Server/API; мобильные клиенты не создают отдельные мастер-базы.

## 0. Оперативное управление проектом

**Текущая цель релиза:** PORTAL 4.3 — восстановить и свести в одну каноническую линию Android, Desktop/Web и Server после расхождения веток.

**Текущая рабочая ветка:** `assistant/portal-4.3-consolidation-20261002`.

**Канонический процесс каждой задачи:**
1. Прочитать этот файл и проверить текущий статус/зависимости.
2. Внести новую задачу или замечание в раздел «Входящие / Принять в работу».
3. Перевести выбранную задачу в «В работе» с агентом/веткой/датой.
4. Реализовать только в каноническом репозитории; локальная копия допустима лишь как временный рабочий каталог.
5. Прогнать обязательные тесты и записать фактический результат.
6. Перенести задачу в «Сделано / Проверено» либо «Заблокировано», указав commit/SHA и следующий шаг.
7. Push в GitHub обязателен до окончания работы. Deploy на VPS — только из зафиксированного commit/tag.

### Входящие / Принять в работу
- [x] 2026-10-03 — довести PORTAL Excel 2.0 до формы для реального заполнения сотрудниками и внедрить единый шаблон в Android/Desktop/Web/iOS: скрыть служебные ID/машинные строки, оставить понятные поля, добавить русские роли и «Да/Нет», материалы/приход/нормы/выработку и сохранить безопасный preview → apply.
- [x] Завершить консолидацию кода PORTAL 4.3: Android 4.2 + большая finalization-линия + Excel v1.1 + God/Platform Owner + split PostgreSQL + последние Desktop fixes сведены в одну каноническую ветку; release/version bump выполняется только после оставшихся физических/production gates.
- [x] Свести визуальный контракт: синий PORTAL; Desktop/Web — боковая навигация; Android — мобильная навигация без потери модулей. Android UI CI 40/40 и Desktop Windows build подтверждают текущий контракт.
- [ ] Проверить встроенные обновления Android и Desktop поверх уже установленной версии.
- [ ] После консолидации сделать полный release-gate и только затем публиковать Android 4.3 / Desktop 4.3.
- [x] Добавить в PORTAL Desktop безопасное запоминание логина/пароля через встроенный password manager WebView2/Windows: Save/Update Password и автоподстановка разрешены; пароль не пишется открытым текстом в `desktop.json`/репозиторий.
- [x] Добавить в Desktop «Органайзер» workflow «Запросы директору»: управляющий/менеджер создаёт запрос (включая закупку материалов), директор рассматривает, комментирует, назначает ответственного и при необходимости создаёт связанную задачу; tenant isolation, immutable history, безопасные вложения и тесты подтверждены.
- [x] Добавить PORTAL iOS как постоянный мобильный клиент той же системы и готовить распространение через Apple Unlisted App по прямой ссылке; все дальнейшие мобильные функции по умолчанию вести с обязательным Android ↔ iOS parity.

### В работе
- [ ] 2026-10-04 — продолжена проверка скорости Desktop «Тарифы» после hotfix `e7247e6`, ветка `assistant/tariffs-cache-speed-20261003`. Локально `server/test_production.py`: 58/58 OK; `android_src/tests/ui.test.cjs`: 48/48 OK, включая один bulk history request. Production reconciliation blocker: активный URL `https://2a03-6f00-a--1-f426.sslip.io` сейчас отдаёт `/api/ping` 200 (`build=PORTAL Server · 4.7.0`) и `/api/ready` 200, но `/`, `/web/`, `/web/index.html`, `/web/production.js`, `/web/web_adapter.js` отвечают 401/404; это расходится с прежним smoke 03.10, где production Web assets были 200 с `no-store`. VPS/source mirror не менялся. Сначала требуется сверить активный reverse proxy/deploy с канонической линией и восстановить согласованный Web endpoint, затем повторить asset smoke и только после этого Desktop user-flow. Дополнительно реальное открытие/время экрана не измерено: установленная Desktop 5.4.0 запущена, но Computer Use дважды вернул capture timeout. Пункт остаётся открытым.
- [x] 2026-10-03 — Desktop: безопасное «Запомнить пароль». Исходная проверенная реализация `5ea4251` из `assistant/desktop-remember-password-20261003` перенесена поверх актуальной release-линии после `163b69a` без отката Organizer. Включён штатный `IsPasswordAutosaveEnabled`; WebView2 показывает пользователю Save/Update Password и затем автоподставляет сохранённые данные. Пароль не сериализуется в `desktop.json`/код. «Сервер» по-прежнему вызывает полный `Profile.ClearBrowsingDataAsync()`. До интеграции: regression `desktop-shell.test.cjs` OK, `git diff --check` OK; GitHub CI реализации: Windows Desktop `37106375657` SUCCESS, master-control `37106375658` SUCCESS, Android UI `37106375677` SUCCESS, APK `37106375660` SUCCESS. Интегрировано в каноническую release-линию commit `82fb320`; повторный CI на этом commit полностью зелёный: Windows Desktop `37106671925` SUCCESS, master-control `37106671930` SUCCESS, Android UI `37106671944` SUCCESS, APK `37106671929` SUCCESS. Production/VPS/БД не менялись. Остался только пользовательский smoke после установки следующей Desktop-сборки: один раз войти и подтвердить «Сохранить пароль».
- [ ] 2026-10-02 — закрыть production security blocker: заменить Stage 7 PostgreSQL runtime roles на отдельные production-only control/tenant роли без раскрытия секретов; перед изменением сохранить rollback/env backup, после — `/api/ready`, `/api/ping`, restart и privilege-boundary smoke. Production код/данные не мигрировать в этой задаче.
- [x] 2026-10-02 — финальная reconciliation всех assistant/Codex веток завершена: актуальные изменения перенесены, исторические/устаревшие линии закрыты ancestry-merge `ours` только после проверки patch-equivalence или ручного переноса уникального изменения. `git branch --no-merged HEAD` больше не показывает assistant/Codex веток; каноническая линия одна — `assistant/portal-4.3-consolidation-20261002`.
- [x] 2026-10-02 — code/CI gate после reconciliation подтверждён. Локально Android/JS 32 PASS, 0 FAIL, 2 Playwright-only skipped; ops/infra 58/58 OK. Windows full backend discover дал каскадные HTTP fixture `ConnectionResetError [WinError 10054]`, но тот же канонический tree в GitHub Linux CI прошёл полностью: server Python 3.11 — 324/324 OK; Python 3.13 — 324/324 OK; PostgreSQL documents — 37/37 OK; Web — Python 21/21 + Node 9/9; Android UI — 40/40; Android staging build — SUCCESS; Windows Desktop build — SUCCESS. Локальный Windows reset классифицирован как platform/test-harness issue, не как подтверждённая code regression; release всё ещё закрыт физическими update/cutover gates.
  - [x] `codex-finalization-megapack-part12`: перенесено hardening legacy SQLite → PostgreSQL validation, включая защищённый company context, legacy unscoped primary-company snapshot и migration-history versions. Конфликт с более новым employee-identity backfill объединён без потери обеих защит. `test_migration_import + test_migration_validation`: 22/22 OK.
  - [x] `assistant-part12-infra-readiness`: перенесены release/infra gates, HTTPS preflight, off-server backup tooling, rollback rehearsal, release evidence, nginx/systemd production templates и Windows legacy deployment evidence. При конфликтах сохранены более новый canonical employee_id audit/map и reminder scheduler, nginx переведён на безопасный `__PORTAL_LOOPBACK_PORT__`. Release-evidence адаптирован к актуальному `channel=release`. Infra/ops suite: 57/57 OK.
  - [x] `assistant-stage7-verify`: ветка reconciled как историческая verification-линия. Её старые temporary GitHub relay/secret-probe/public-smoke workflows и урезанный Stage 7 deploy не перенесены, потому что текущая каноническая линия уже содержит более новый local banner-first relay, полный набор миграций/runtime dependencies, synthetic PostgreSQL/API restart gate и domain/Cloudflare/sslip режимы. Текущий Stage 7 safety suite: 12/12 OK.
  - [x] `codex/production-cutover` (часть 1): перенесён fail-closed production DB split/readiness gate — production требует PostgreSQL, разные non-test control/tenant DB и разные DB roles с проверкой границ привилегий; добавлен `/api/ready`. `test_portal_app_server + test_migration_import`: 29/29 OK.
  - [x] `codex/production-cutover` (часть 2): перенесён централизованный backup script для split production — control DB + все `portal_prod_company_*` + central storage, SHA-256/`pg_restore --list`, 14-дневная retention и сохранение legacy rollback DB. Infra test: 10/10 OK.
  - [x] `codex/production-cutover` (часть 3): перенесён Android release-security запрет временных/локальных production endpoint-ов и расширен server CI на `ops/**` с проверкой central backup + infra contracts. Более новые универсальные `assistant/**` workflow triggers и dynamic version metadata сохранены. `build-security.test.cjs`: OK; infra: 10/10 OK; backup shell syntax: OK.
  - [x] `codex/production-cutover` (часть 4): исправлена диагностическая метка backend — PostgreSQL теперь логируется с реальным environment вместо устаревшего `PostgreSQL isolated test`. `test_portal_app_server`: 19/19 OK.
  - [x] `codex/production-cutover` полностью reconciled: актуальные protections/backups/build hardening перенесены отдельными проверенными коммитами; ветка затем закрыта merge-strategy `ours`, чтобы старые 3.5 metadata, старые Desktop/UI файлы, временный sslip/Stage7 production pin и уже заменённые документы не могли откатить 4.3 recovery. Каноническими evidence остаются текущие `PORTAL_PRODUCTION_RECONCILIATION.json` + `PORTAL_PRODUCTION_FOLLOWUP_20261002.md` и master roadmap.
  - [x] `assistant-part12-integration`: перенесён единственный ещё уникальный актуальный patch — audit test больше не принимает `created_at` timestamp вроде `11:30` за утечку изменённого значения; при этом сохранены более новые строгие assertions по разрешённым полям. `test_production`: 53/53 OK.
- [x] 2026-10-02 — создана отдельная recovery-worktree и ветка `assistant/portal-4.3-consolidation-20261002` от Android 4.2.
- [x] 2026-10-02 — начато слияние `assistant/production-template-v11-20261001`; конфликты Excel/Server/Desktop разрешаются с сохранением более новых функций и 4.2 update/UI.
- [x] 2026-10-02 — целевые тесты после первого конфликта: Python 73/73 OK; Node UI 10 PASS, 2 skipped из-за отсутствующего Playwright на локальной машине.
- [x] 2026-10-02 — в recovery-линию сведена `assistant/god-global-role-20261002`; сохранены новый Desktop/Web side-nav, login update controls и существующая Platform Owner UI-модель. Targeted tenancy/documents: 33/33 OK; Node UI: 10 PASS, 2 skipped (Playwright локально не установлен).
- [x] 2026-10-02 — сведена `assistant/portal-prod-db-split`; control/tenant PostgreSQL split сохранён. Targeted `test_portal_app_server`: 17/17 OK.
- [x] 2026-10-02 — сведена `assistant/desktop-4.1-render-fix-20261002`; Desktop shell navigation/branding/self-update contract: OK. Локальный `dotnet` на `Ernest-com` отсутствует, поэтому compile/build проверяется GitHub Windows CI после push.
- [x] 2026-10-02 — reconcile скрытого God/Platform Owner входа завершён: старый `technicalLogin` удалён, единый `/api/login` с company_id восстановлен, God скрыт до авторизации; Android 4.2 update-controls до входа и Desktop/Web grouped side-nav сохранены. Локально Node UI 10 PASS / 2 skipped (Playwright отсутствует), targeted server tenancy/app tests 35/35 OK.
- [x] 2026-10-02 — GitHub CI на `139db9f` выявил два точечных остатка merge: browser update-state выбирал скрытый auth status после входа; PostgreSQL owner-audit test ещё ожидал старые `owner_login/technical_access`. Исправлено: update-state ставится только активной auth/app поверхности; PostgreSQL test приведён к `god_login/god_access`. После исправления локально Node source UI 10 PASS / 2 skipped (Playwright отсутствует), targeted server 35/35 OK, PostgreSQL test module компилируется. Повторный полный browser/PG gate — GitHub CI после push.

### Сделано / Проверено
- [x] 2026-10-03 — PORTAL Excel 2.0 доведён до рабочего human-first контракта и встроен в общий Android/Desktop/Web UI с iOS parity. Шаблон содержит 8 листов; системные строки и ID/refs скрыты; русские роли и «Да/Нет» поддерживаются импортом и выдаются выпадающими списками; выработка вводится как «Сотрудник → Клиент → Операция → Количество → Товар/комментарий», а зарплата/выручка рассчитываются сервером по действующим тарифам. В одном файле поддержаны сотрудники, клиенты, операции/тарифы, материалы, приход, нормы и выработка; preview/classification/explicit apply и транзакционный rollback сохранены. Финальная локальная проверка main: Excel/Documents Python 33/33 OK, Documents/Excel Node 9/9 OK; iOS mirror: Python 33/33 и Node 9/9 OK. Реальный smoke скачивания/загрузки на физическом Android/iPhone остаётся release-device gate, а не программным блокером.
- [x] 2026-10-03 — диагностика медленного Desktop-раздела «Тарифы» выявила два независимых узких места. В компании #1 локальный encrypted Desktop cache реально содержит каталог на 78 операций, но прежний TTL был всего 5 минут; последний snapshot 02.10 23:39 к следующему рабочему дню считался просроченным и не ускорял экран. Сам экран дополнительно делал клиентский N+1: 1 запрос `/api/v3/catalog` + 78 отдельных `/api/v3/tariff-history?operation_id=...` = 79 GET на холодной загрузке. Внутри server `/api/v3/catalog` был второй N+1: для каждой из 78 операций `self.tariff()` заново читал весь ledger `tariffs`; теперь catalog загружает `tariffs` один раз и переиспользует snapshot при расчёте действующих ставок. Транспорт с авторизованного ПК также не мгновенный: текущий IPv6 sslip endpoint имеет ~210 ms ICMP RTT и ~260–285 ms warm `/api/ping` по keep-alive (первый TLS запрос ~1.1–2.6 s), тогда как IPv4 VPS `178.209.127.247` даёт ~37 ms ICMP, но отдельный production HTTPS IPv4 hostname пока не настроен. Исправление в ветке `assistant/tariffs-cache-speed-20261003`: server `tariff-history` умеет bulk-read без `operation_id`; UI «Тарифы» делает только 2 GET (catalog + bulk history); Desktop cache TTL увеличен до 24 часов и при cache-hit по-прежнему запускает background refresh. Targeted tariff server test OK; полный `test_production` 57/57 OK; Playwright проверяет один bulk history request. Первый полный UI прогон поймал посторонний flaky timer assertion, изолированный повтор прошёл, затем полный повтор прошёл 46/46. GitHub CI для `e7247e6`: master-control, server isolation, Web, Android UI, Android APK, Windows Desktop и iOS — SUCCESS. Production hotfix развернут хирургически поверх release `c03e9fe-role-matrix`: `production_service.py` + только строка экрана «Тарифы» в production.js + web_adapter cache TTL; сохранены timestamped pre-e7247e6 backups. `portal-production.service` после рестарта active/running, `/api/ping` и `/api/ready` OK; публичные `production.js` и `web_adapter.js` отдают новые markers с `Cache-Control: no-store`. Desktop 5.4 на авторизованном ПК перезапущен, чтобы загрузить новый adapter. Финальный пользовательский smoke скорости «Тарифов» обязателен перед закрытием задачи.
- [x] 2026-10-03 — PORTAL iOS foundation / Unlisted App track завершён и интегрируется в каноническую release-линию. Source commits: `4b255a4`, `cf5b1f3`, `fff82d8`. iOS SwiftUI/WKWebView использует тот же `android_src/app/src/main/assets`, что Android; отдельной копии mobile UI и отдельной мастер-БД нет. Реализован iOS `PortalNative` bridge для Server/API, token/company scope, сохранения и системного Share документов; обновления iPhone помечены как App Store-managed. Добавлены `docs/MOBILE_PARITY_CONTRACT.md`, `ios_src/UNLISTED_RELEASE.md`, parity checker и macOS `iOS CI`. Локально: mobile parity OK, Node/UI 43/43 PASS, plist/py_compile/diff-check OK. GitHub iOS run `37116449772` полностью SUCCESS: parity → XcodeGen → iOS build → Swift unit tests. На исходном mobile commit `4b255a4` также зелёные Android APK, Android UI, Web, Windows Desktop и master-control. До реального Unlisted-релиза остаётся только внешний Apple gate: Developer/App Store Connect, stable owned HTTPS API, signing, TestFlight device-smoke, App Review и одобрение Unlisted.
- [x] 2026-10-03 — модальные окна/`sheet` защищены от случайного закрытия на общей UI-линии и в Desktop. Пользовательский smoke доказал, что первый фикс `aa75a6e` был недостаточен для уже выпущенного Desktop 5.2 из отдельной release-линии. Канонический hardening `deab599`: capture-phase guard блокирует `pointerdown`/`click` вне `#sheet`, Escape и Back; реальный Playwright сценарий backdrop click → Escape → Back → явный `×` проходит, полный `ui.test.cjs` 44/44 PASS. GitHub CI для `deab599`: master-control, iOS, Android APK, Windows Desktop, Web и Android UI — SUCCESS. На VPS усиленный asset развернут с совпадающим SHA-256; loopback `8790`, `8770`, `8780` — `MODAL_LOCK=OK`; production sslip `https://2a03-6f00-a--1-f426.sslip.io` и оба активных Cloudflare URL — `MODAL_LOCK=OK`, `Cache-Control: no-store`. Для нативного Desktop выпущен отдельный hotfix `5.4.0` / build `54` из commits `aa5b345` + `5d4f16a`: WebView2 дополнительно инжектирует modal-lock после каждой навигации и оборачивает `window.portalBack`. Tag/release `portal-desktop-v5.4.0` опубликован, ZIP SHA-256 `1a3feab704c517430f623a7d9edb569129cf8179ec790a9c4e596c066ef84832`; Windows release workflow SUCCESS. На авторизованном ПК 5.4 установлен и запущен из `%LOCALAPPDATA%\PORTAL\Desktop\versions\5.4.0`, WebView2 идентифицирует `5.4.0-ci+5d4f16a...`; 5.2 сохранён для rollback. Финальное закрытие дефекта — только после пользовательского smoke на 5.4.
- [x] 2026-10-03 — «Запросы директору» доведены до production и запущены. Реализация: `65c2147` + fixes `0682b09`; интеграция в каноническую release-линию `assistant/portal-release-20261003`, production commit `be4996e63761a14da7fd8c7dd1dc798468989e76`. Локально: `test_production` 55/55 OK; targeted Organizer 2/2 OK; Node UI 11 PASS / 0 FAIL / 2 Playwright-only skipped; compileall/diff-check OK. GitHub для `be4996e`: master-control, Web и Server workflows — SUCCESS. VPS: stage14 migration видна в tenant company scope, `portal-production.service` active/running на release `be4996e-organizer-requests`, `/api/ping` и `/api/ready` OK, публичный `/web/production.js` содержит новый UI. Desktop перезапущен и получает UI напрямую с production Web endpoint. В текущей компании активного пользователя с ролью Director пока нет, поэтому фактическая отправка запроса требует назначения директора; production-данные для smoke не создавались.
- [x] Введён единый обязательный реестр проекта — этот файл.
- [x] Правило: GitHub — канонический код/ТЗ; VPS — канонический runtime/PostgreSQL; ПК/телефон не хранят уникальную мастер-копию.
- [x] Правило: каждый агент обязан читать и обновлять этот файл до/после работы.
- [x] Добавлен GitHub Actions `master-control-gate.yml`: изменение кода/runtime без одновременного обновления `PORTAL_MASTER_ROADMAP.md` блокируется CI; наличие `AGENTS.md` и master-файла также проверяется.
- [x] На VPS создан единый source mirror `/srv/portal-source/repo`, синхронизированный с recovery-веткой; production service не переключался и runtime не менялся. Добавлен `ops/sync_vps_source_mirror.sh`: синхронизация идёт только из GitHub и fail-closed останавливается при любых локальных изменениях в VPS mirror. Таким образом ПК/телефон больше не могут быть единственным местом хранения изменений.

### Заблокировано / Внешние действия
- [ ] iOS production distribution: нужны Apple Developer membership/App Store Connect, финальный bundle/signing, stable owned HTTPS API, TestFlight physical-device smoke, App Review и одобрение Apple Unlisted App; секреты Apple в Git не хранить.
- [ ] Для компании «Портал» назначить активного пользователя с ролью Director, иначе «Новый запрос директору» не сможет выбрать адресата. Это настройка ролей, а не программный блокер.
- [ ] Production domain/HTTPS и окончательный production cutover остаются отдельным gate.
- [ ] Физический Android install/update gate выполняется только после готового signed release candidate.
- [ ] TalAnt/WMS/ТСД — внешняя интеграция и не блокирует восстановление 4.3.

---

Канонический реестр требований проекта. Восстановлен из прежних больших ТЗ, аудитов и последующих дополнений. Пункты не удалять без явного решения владельца проекта.

Статусы: ✅ реализовано и проверено; 🟡 реализовано частично/нужен production-довод; ⏳ не реализовано; 🔌 отдельная внешняя интеграция.

## A. Платформа, компании, сотрудники и права

1. ✅ God — отдельный глобальный аккаунт управления всеми компаниями; не входит в списки пользователей компаний, не отображается сотрудникам/директорам/администраторам и используется отдельно от обычного рабочего аккаунта сотрудника.
2. ✅ Изоляция компаний на сервере и PostgreSQL RLS.
3. ✅ Роли admin, director, manager, packer, shift, accountant.
4. ✅ Директор: полные бизнес-права только внутри своей компании.
5. ✅ Индивидуальные разрешения поверх ролей.
6. ✅ Создание нового сотрудника без обязательной связи со старым.
7. ✅ Отдельный сценарий «Выдать доступ существующему сотруднику».
8. ✅ Логин/PIN, сессии, отзыв старых сессий после смены доступа.
9. ✅ История входов, Online/Offline, heartbeat.
10. ✅ Безопасный одноразовый invite/access-request lifecycle и Android/Web create/list/accept/approve/revoke UI: hash-at-rest, one-time token, expiry/revoke, idempotency, tenant scope, Manager/Packer denial и Director/Admin decision paths подтверждены Server/Web/disposable PostgreSQL и shared UI. Production cutover отслеживается отдельно.
11. ✅ Безопасная ссылка/одноразовая выдача токена и одобрение директором/admin: логин/PIN не передаются в URL; God без выбранной компании получает отказ, с явной компанией работает в её scope; existing-employee привязывается без создания дубля. Роль/tenant/idempotency/audit matrix и UI acceptance подтверждены.
12. ✅ Серверный лимит активных пользователей, concurrency lock, unlimited PORTAL, God fee/demo/status/limit/module-toggle controls и Director permission-gated company settings реализованы. PostgreSQL подтверждает persistence/validation/audit, стандартный seat limit, PORTAL unlimited, forged-company denial и Manager/Packer denial. Production rollout отслеживается отдельно.
13. ✅ Уникальность логинов; с 3.1 вход должен быть без учёта регистра.
14. ✅ Активность/отключение пользователя без удаления истории.
15. ✅ Company/God audit views разделены и имеют фильтры/пагинацию; company audit доступен авторизованным ролям своей компании, God support-audit — только God. Actor/event/entity/date filters, role/tenant denial и value-free redaction подтверждены shared UI, Server и disposable PostgreSQL.

### A1. Утверждённая матрица ролей и доступа — 03.10.2026

Эта матрица является актуальным нормативным правилом PORTAL и имеет приоритет над более ранними промежуточными трактовками ролей.

- **Директор (director)** — максимальные бизнес-права внутри своей компании.
- **Управляющий (admin)** — максимальные бизнес-права внутри своей компании.
- **Менеджер (manager)** — доступ ко всем рабочим данным и рабочим модулям компании: клиенты, операции и тарифы, задания, склад, счета, документы, отчёты, Органайзер и производственная аналитика. Исключение: менеджер не видит зарплату, начисления, расчётные листы и зарплатную аналитику других сотрудников. Свою выработку и свою зарплату видит. Управление ролями и системными настройками компании остаётся за директором/управляющим, пока отдельно не утверждено иное.
- **Упаковщик / сотрудник (packer)** — доступ только к назначенным/доступным заданиям на сборку/обработку, выполнению этих заданий, внесению собственной выработки и просмотру собственной выработки/зарплаты. Дополнительно упаковщику разрешено брать расходные материалы со склада и фиксировать их фактическое списание. Чужие зарплаты, финансы компании, счета, управленческая аналитика, настройки и управление сотрудниками недоступны.
- **Старший смены (shift)** — роль сохраняется номинально; базовые права по роли на текущем этапе не выдаются.
- **Бухгалтер (accountant)** — роль сохраняется номинально; базовые права по роли на текущем этапе не выдаются.
- **Platform Owner / God (platform_owner)** — отдельный глобальный уровень владельца платформы, не является сотрудником компании.
- Различие бизнес-процессов сохраняется даже при равных максимальных правах Director/Admin: например, управляющий может отправлять директору запрос на закупку, а директор — принимать решение по нему.

✅ Матрица реализована в permission defaults и UI: shift/accountant имеют пустые базовые права; packer по умолчанию ограничен заданиями/выработкой/своей зарплатой и складским read/use; manager получил рабочий read/access-контур без чужой зарплаты и без управления сотрудниками/системными настройками; director/admin получают максимальные базовые capability, специальные бизнес-role gates сохранены. Индивидуальные явные overrides продолжают работать поверх роли, но не обходят role-gates управления сотрудниками/системными настройками. Локально подтверждено: production 57/57 OK, tenancy 18/18 OK, полный Node/Playwright UI 42/42 PASS, compileall и git diff --check OK. Production rollout выполняется только после интеграции в каноническую release-линию и CI. GitHub disposable PostgreSQL gate приведён к этой же матрице: номинальный accountant не может читать/проводить зарплатные выплаты без явных прав. Исправлены также ожидаемые агрегаты выплаты после удаления бухгалтерского платежа из сценария. Payroll settlement unit-contract также обновлён: accountant отнесён к запрещённым default roles, а проверка actor/idempotency использует авторизованного director.

## B. Клиенты, тарифы и производство

16. ✅ Клиенты: создание, изменение, активен/архив.
17. ✅ Карточка клиента 360° объединяет реквизиты и контакты, историю названий, операции и effective-date тарифы, товары, партии/задания, отгрузки/возвраты, документы, счета/дебиторку, экономику и последние работы. Из карточки доступны редактирование клиента/реквизитов, управление операциями, создание новой историчной ставки с возвратом в Client 360 и управление товарами; недоступные источники явно помечаются как частичная загрузка. Shared UI 35/35, Web/disposable PostgreSQL, Android UI и APK CI на `4ed5ce8` прошли.
18. ✅ Операции клиента и ставки сотруднику/клиенту.
19. ✅ Историчность тарифов и effective-date: UI текущих/прошлых версий и создание новой версии; duplicate effective-time запрещён; старая ставка сохраняется в work snapshot; tenant scope проверен. Capability matrix симметрична: `rates.employee` видит/меняет только ставку сотруднику, `rates.client` — только клиентскую цену; POST и idempotent replay одинаково редактируют ответ. Server 3.11/3.13 и Web/disposable PostgreSQL на `a80d3a3` прошли.
20. ✅ Импортированы действующие клиентские тарифы и исключения.
21. ✅ Ввод выработки клиент → операция → количество.
22. ✅ Немедленный расчёт сдельной зарплаты.
23. ✅ Партии товара.
24. ✅ Производственные задания и несколько исполнителей.
25. ✅ Таймер задания: старт/пауза/продолжить/завершить.
26. ✅ «Другая работа» без задания.
27. ✅ Привязка ранее внесённой работы к партии.
28. ✅ План/факт партии и экономика партии: plan salary/revenue фиксируются из effective tariff, materials — из активных operation norms с Decimal/копейками, other — только из явного `finance.read` override; fact использует реальную выработку, списания и batch expenses. Margin/deviation/cost-per-unit/profit-per-unit считаются в integer minor units; без plan rows UI/API честно показывают «Недоступно». Role/tenant denial, plan-source и UI flows подтверждены.
29. ✅ Материалы и остатки.
30. ✅ Нормы материалов и фактическое списание при работе.
31. ✅ Модуль расходов: аренда, логистика, забор из ТК, доставка на маркетплейсы, коммунальные/управленческие и прочие расходы; общекомпанейские расходы отделены от расходов клиента.
32. ✅ Внутренний generic batch workflow PORTAL: назначенные задания/исполнители, план-факт количества, FBS/FBO shipment, состояния частичного/полного возврата, результат возврата, audit и idempotency; service, shared UI и disposable PostgreSQL role/tenant E2E проверены. Внешняя интеграция TalAnt остаётся отдельным контуром 106–117.
33. ✅ Нормализация имён и история без изменения идентичности: Client сохраняет стабильный ID, append-only rename history и постоянный `client_aliases` ledger; старые и утверждённые Knowledge Base варианты привязаны к `client_id`, а shared UI ищет по серверным alias rows без переписывания canonical имени. Employee сохраняет стабильный `employee_id`; Excel rename пишет append-only `employee_name_history` и `employee_aliases`, migration v13 backfill сохраняет утверждённые варианты по employee_id, а import без employee_id при совпадающем/alias-нормализованном ФИО блокируется как неоднозначный. Ни клиенты, ни сотрудники не объединяются по имени.
34. ✅ Алфавитная выдача основных справочников.
35. ✅ Каталог продуктов клиента: стабильные ID, CRUD/архив, поиск и tenant-scoped связь с партиями; Stage 12 PostgreSQL/Web CI и браузерный role flow прошли на Part 12.

## C. Зарплата, финансы и аналитика

36. ✅ Расчётные периоды 1–15 и 16–конец месяца: preview и закрытие реализованы в новом API/Android-контуре.
37. ✅ Закрытие/блокировка зарплатного периода и защита от новых начислений в закрытые даты; будущий период закрыть нельзя.
38. ✅ Начислено/выплачено/остаток по сотруднику: append-only settlement ledger в копейках, закрытый payroll snapshot неизменяем; admin/accountant могут фиксировать выплату, manager/packer не могут, cross-company доступ запрещён. Disposable PostgreSQL role-flow и cleanup подтверждены на `42dd31f`.
39. ✅ Счета клиентам.
40. ✅ Частичные и полные оплаты.
41. ✅ Базовая дебиторка: открытые/оплаченные суммы.
42. ✅ Просрочка и расширенный контроль дебиторки: client-local aging buckets, частичные оплаты, фильтр клиента/периода, пагинация, kopeck reconciliation, timezone boundaries, role/tenant denial и PostgreSQL cleanup проверены Server/Web/disposable PostgreSQL CI на `22ce6f3`; legacy invoices без client link не приписываются клиенту.
43. ✅ Выручка, себестоимость, маржа и прибыль по клиенту/партии: `finance` и batch `economy` используют source-backed выручку, ФОТ, материалы и attributable expenses; общие расходы компании остаются отдельными и не распределяются вымышленно. Маржа клиента/компании и партии считается точными basis points, деньги — в копейках; UI и disposable PostgreSQL reconciliation прошли на `42dd31f`.
44. ✅ «PORTAL Сегодня»: подтверждённые объём за день/месяц, выручка и начисления за день/месяц, скорость команды, открытые/просроченные счета, плановая прибыль с честным состоянием «Недоступна» без плана и выплаты/остаток закрытых payroll-периодов. Payroll-блок показывается только когда backend вернул его по capability. Shared UI regression 57/57, Web, Android UI и APK на `414a101` прошли.
45. ✅ Финансовый радар объединяет только подтверждённые источники: client/company profitability, месячную динамику, число убыточных клиентов, дебиторку/просрочку при `invoices.read` и финансовые записи «Требует внимания». Без `invoices.read` receivables API не вызывается и долговые метрики не показываются. Общие расходы не распределяются по клиентам искусственно. Полный shared UI regression 57/57, Web/disposable PostgreSQL, Android UI и APK на `fa680cd` прошли.
46. 🟡 Аналитика группирует выработку по команде, клиенту, товару, операции и партии; темп/разброс рассчитываются только по timed work, а без него UI честно показывает отсутствие данных. Manager assignment scope проверяется. Качество остаётся недоступно: в текущем источнике нет зафиксированных дефектов; оценка не выдумывается.
47. ✅ Tenant-scoped idempotent reminders, cadence/run/retry metadata, operator runner, and bounded dispatch are implemented and verified. The runner caps dispatch at 500 per run and records processed/deferred counts. Local reminder/operator tests: 15/15. GitHub Server run 36818033879 (#164): Python 3.11/3.13 each 304 tests, 48 skipped, 0 failures; Web run 36818033902 (#157): disposable PostgreSQL 36 tests, 2 gated skips, teardown db=0 roles=0 temp=0. Trusted system timer and production activation remain external and disabled.
48. ✅ Общий payroll Excel в новом APK/VPS-контуре: сводка, сотрудники и детализация.
49. ✅ Excel-расчётные листы по каждому сотруднику формируются отдельными листами.
50. ✅ Серверный A4 PDF-расчётный лист строится только из закрытого payroll snapshot и регистрируется как scoped Document; реальный ReportLab 5.0.1 + Unicode font smoke и PostgreSQL/RLS gate пройдены на изолированном VPS.
51. ✅ PDF «Счёт на оплату» использует существующие invoice/client/company data и строки работ; реальный renderer, повторная детерминированная генерация, scoped Documents и PostgreSQL/RLS E2E подтверждены на изолированном VPS.
52. ✅ Общий payroll XLSX содержит отдельный лист «Выплаты» с сотрудником, периодом, начислено/выплачено/остатком, датами выплат и итогами. Проверены renderer и полный HTTP → Documents → settlement ledger → XLSX поток тестами `test_report_xlsx.py` и `test_payroll_settlement.py`.

## D. Документы и Excel-импорт/экспорт

53. ✅ Общий Documents API подключён к Android/Web UI: список, фильтры, поиск, пагинация, скачивание, архивирование и PDF-действия покрыты shared UI/backend и disposable PostgreSQL. Production rollout отслеживается отдельно.
54. ✅ Blob и document metadata разделены, company-scoped storage и FORCE RLS подтверждены; PDF-specific PostgreSQL E2E с реальным renderer прошёл в одноразовой test DB с cleanup.
55. ✅ Filters/paging Documents API и общий Web list/search UI: client/employee filters capability-gated, company-scoped на сервере и проверены Playwright/PostgreSQL, включая cross-company denial и paging/search scope.
56. ✅ Общий Web-экран Documents и серверные права/archive/download/history покрыты backend, shared browser regression и disposable PostgreSQL; deployment/cutover отслеживается отдельными release-пунктами.
57. ✅ Стандартный PORTAL Excel 2.0: 8 русских листов «Компания / Сотрудники / Клиенты / Операции_Тарифы / Материалы / Приход_материалов / Нормы_материалов / Выработка». Машинные строки и технические ID/refs скрыты, человеческие поля стоят первыми; роли показываются по-русски, активность — «Да/Нет», для роли и активности есть выпадающие списки. Blank/prefill API сохранены для директора и выбранной компании God; openpyxl round trip, tenant isolation и импорт только по видимым человеческим полям проверены.
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
68. ✅ Documents cross-session/history parity: независимые HTTP-сессии одной компании прошли create/list/metadata/download/archive E2E на disposable PostgreSQL с cleanup DB/roles/temp=0; общий Android/Web UI показывает revision/status и «История версий», а regression проверяет ordered version history, archived/current labels и denied history action. Production rollout отслеживается отдельно и не является software-блокером этого пункта.

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
85. 🟡 Windows thin client собран как WPF/WebView2 поверх общего `/web/`. PORTAL Desktop 4.0.0 / build 40 опубликован официальным GitHub Release и успешно собран теговым Windows CI `36899625677`; SHA-256 release ZIP проверен. На целевой Windows-машине `Ernest-com` выполнена реальная per-user установка в versioned каталог и созданы ярлыки. Встроенная кнопка «Обновить PORTAL» самостоятельно проверяет серверный manifest, при недоступном/неподключённом сервере использует официальный GitHub Releases fallback, скачивает HTTPS ZIP, проверяет SHA-256, ограничивает redirect/размер/пути распаковки, ставит новую версию рядом со старой, переключает ярлыки и запускает новый exe. Staging `/api/desktop-update` уже рекламирует 4.0.0/build 40. Открыты постоянный production domain/HTTPS и решение по Windows publisher/code signing для production.
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
102. ✅ Runtime/API contracts используют employee_id; legacy telegram_id остаётся только в явно перечисленных adapter/import/schema/history bridges. Повторный аудит Part 12: P0=0, P1=50; legacy fallback и публичные payroll/work identity inputs устранены, import preflight/backfill verification добавлены. SQLite/application 299 tests OK (47 opt-in skips), disposable PostgreSQL/RLS и Web CI `36767971434` success, Server Python 3.11/3.13 CI `36767971376` success. Полный synthetic CLI import/rollback rehearsal на изолированном VPS и физический cleanup legacy columns остаются следующим этапом; см. `PORTAL_PART12_EMPLOYEE_ID_MIGRATION_REPORT.md`.
103. ✅ Защита от повторных записей/идемпотентность в критичных сценариях.
104. ✅ Regression/unit/integration тесты и GitHub gates.
105. 🟡 Денежные типы и нормализация: runtime money хранится в integer minor units, PostgreSQL compatibility boundary — Decimal/NUMERIC. Read-only сверка связанной legacy-истории подтверждает согласованность major/minor units. Для подтверждённой копии SQLite зафиксированы integrity_check=ok, совпадение SHA-256 с manifest и воспроизводимый read-only migration dry-run; отдельная загрузка копии в disposable PostgreSQL и post-import reconciliation ещё не проведены. Production rows не читались и не изменялись.

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
- 🟡 God/Packer browser scopes закрыты Part 10; Web download blank/prefill template закрыт Part 11. Открыты Android user-flow/parity готовой APK, production rollout и Windows installer.
- Полный отчёт: `PORTAL_WEB_POSTGRES_PART8_REPORT.md`.

## G5. Web + Invoice revisions Part 10 — реальные role/revision gates (29.09.2026)

- ✅ Реальный Chromium → HTTP API → disposable PostgreSQL E2E подтверждён для Director, Manager, Packer и God.
- ✅ Director через Web сформировал и скачал `invoice_xlsx`, затем перевёл счёт `finalized → editing`.
- ✅ Manager через Web изменил разрешённую строку счёта и сохранил `revision 2`; итоговое состояние снова `finalized`.
- ✅ Packer не видит раздел счетов и получает HTTP 403 при прямом запросе invoices API.
- ✅ God до выбора компании получает HTTP 403, после явного выбора компании A работает в её scope, а компания B возвращает пустой список счетов.
- ✅ God audit за тестовый сценарий: 16 записей; чужая компания: 0 счетов.
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
127. ✅ Постоянное UI-правило модальных окон/`sheet`: обычное закрытие выполняется только через явный крестик `×` в самом окне. Клик по свободному фону/подложке, клавиша Escape и системная/браузерная кнопка Back не должны закрывать открытое окно. Внутренние кнопки формы могут закрыть окно только как результат явного действия пользователя (сохранение, подтверждение, отмена). Правило применяется одинаково в Desktop/Web/Android, где используется общий UI.

## J. Part 12 finalization candidate (30.09.2026)

- Base verified: `bc95a942021bb5c43d112f51d2c2e7881059b47a` (Part 11); company knowledge commit `615495c3fef1f134ac651416f60b37809bda6380` is included.
- Candidate Android metadata advanced from 3.4/34 to `3.5-dev-staging`/35. This is a staging build candidate only; no release workflow or production endpoint is authorized by this change.
- Part 12 implementation is in progress. No additional roadmap item is marked complete by this bootstrap checkpoint. Existing Parts 8–11 evidence remains authoritative for their verified items.
- Production cutover, DB mutation, DNS changes, production service/config changes, and real financial operations were not performed.
- Part 12 continuation #3 verified tariff effective-date snapshots, timezone-aware financial month buckets, dashboard daily/monthly figures and source-backed team productivity. At `7917dac` local Server discovery passed 244 tests with 31 skips; Web disposable PostgreSQL and Server passed, and the same client code passed Android UI/APK CI at adjacent SHA `2548d97`. Item 47 moved from ⏳ to 🟡 after operator-run scheduling metadata/tests; the system timer remains open. Current counts: **73 ✅ / 34 🟡 / 7 ⏳ / 12 🔌**.
- Windows installer is not yet implemented; local `dotnet` is unavailable. See `PORTAL_FINALIZATION_PART12_PROGRESS.md` for remaining work and `PORTAL_FINAL_EXTERNAL_BLOCKERS.md` for provider/owner actions.
- Roadmap item 52 is closed on this branch after targeted HTTP/Documents/XLSX integration and workbook tests; payroll ledger facts are read from append-only settlement events and are not written into the closed snapshot.
- Part 12 checkpoint `e85928e`: item 32 is ✅ after internal FBS/FBO shipment and return lifecycle, idempotency, audit and role/tenant tests including Web disposable PostgreSQL. Counts: **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**. Production cutover remains NOT performed.

- Part 12 automatic continuation checkpoint `278fb2e` / server-Web source `06a7e93`: invitation UI role coverage now verifies Director decisions and Packer denial; reminder operator return contract is fixed and Web disposable PostgreSQL plus Server 3.11/3.13 passed. Android UI and staging APK at `278fb2e` passed. Counts remain **74 ✅ / 33 🟡 / 7 ⏳ / 12 🔌**; no completion status changed. Production cutover **NOT performed**.

- Money/identity focused checkpoint `35db147`: current identity scanner still reports P0=0, P1=50 explicit bridges and P2=129 historical/fixture references; audit/infra tests 16/16. Web run `36722642388` passed web and disposable `documents-postgresql` (31 tests, 2 skipped; cleanup db=0/roles=0/temp=0), including bounded linked legacy/canonical money reconciliation. Server run `36722642200` passed Python 3.11 and 3.13 (277 tests per version, 43 skipped). An earlier unfiltered synthetic company scan detected duplicate canonical links and remains a fail-closed data integrity finding; bounded test success does not certify the entire synthetic history. Item 105 remains 🟡; counts stay **75 ✅ / 32 🟡 / 7 ⏳ / 12 🔌**.
- Latest Part 12 Windows/update checkpoint `4a1629c`: Windows CI `36727892734`, Web `36727892853` and Server `36727892708` passed; the Server matrix ran 289 tests on Python 3.11 and 3.13 (43 skips each), and disposable PG ran 31 tests/2 skips with cleanup db=0/roles=0/temp=0. The Web Share/Android client Node suite passed locally 52/52. Item 85 is 🟡, not a signed/released installer; update distribution is optional and requires external trusted publication/signature configuration. The strict synthetic whole-company money scan now passes, while an imported SQLite snapshot remains unknown and item 105 stays 🟡. Counts **75 ✅ / 33 🟡 / 6 ⏳ / 12 🔌**. No production cutover.

### Part 12 continuation — 2026-09-30 (`22ce6f3`)
- Client 360 shipment/return history is now visible in the shared UI with client/tenant filtering and browser regression tests (`664050d`); item 17 remains 🟡 until broader editable-profile acceptance is proven.
- The Web disposable PostgreSQL run at `23bd46f` found a real edge case: historical invoices with no client link caused `receivables()` to raise `KeyError`. The `22ce6f3` correction excludes unlinked rows from the client-only aging report and adds regression assertions. Web and disposable PostgreSQL passed (33 PG tests, 2 gated skips, cleanup `db=0 roles=0 temp=0`); Server 3.11 and 3.13 each passed 294 tests/45 skips; `ops.test_infra_readiness` passed 8/8.
- Item 42 is now ✅. Counts are **76 ✅ / 32 🟡 / 6 ⏳ / 12 🔌**. No production data/service/DNS/cutover or secrets were touched; production cutover NOT performed.
- Item 46 checkpoint `231e3c6`: API/UI expose employee/client/product/operation and batch/operation productivity from tenant-scoped timed work, with canonical labels and variability only after at least two timed samples. Manager assignment and employee self-only scope are tested; PostgreSQL E2E tests team/self/foreign-company scope and batch metrics. No defect source exists, so quality remains unavailable and item 46 stays 🟡. Server unit suite 51/51, browser UI 35/35, infra 8/8; Server 3.11/3.13, Web+PostgreSQL, Android UI and APK checks passed. Counts **79 ✅ / 29 🟡 / 6 ⏳ / 12 🔌**. No production target used.

## K. Final project closeout — 2026-10-01 (baseline `337d239`)

- Current source audit confirms self-service PIN change, central VPS document storage architecture, Desktop connection/WebView compatibility/update path, and bounded reminder dispatch. Desktop source version is 3.5.2; Android development staging is 3.5-dev/versionCode 35. No product semantic version is declared by `PORTALAppServer/1.0`; Server CI validates Python 3.11/3.13 runtimes.
- Item 13 includes the tested case-insensitive login and self-service PIN flow: masked input, confirmation match, God hidden state, preserved current session, revocation of other sessions, and audit without secrets. Existing Server and shared UI tests cover the flow.
- Roadmap statuses are **93 ✅ / 15 🟡 / 6 ⏳ / 12 🔌 (126 conceptual items)**. Item 105 is 🟡; a verified legacy snapshot still requires a separately authorized disposable PostgreSQL import/reconciliation rehearsal. No production facts are used for this gate.
- Remaining 🟡/⏳ statuses are classified in `PORTAL_FINAL_PROJECT_CLOSEOUT_REPORT.md` and contain only real device/browser, provider, production/data, or external migration gates. No software TODO remains.
- Current-baseline local evidence: Server discovery 306 passed / 49 skipped; shared Node 58/58; Android UI 37/37; infra readiness 8/8; compileall and diff check passed. Local PostgreSQL is unavailable. GitHub workflows for the ending documentation SHA must be recorded in the closeout report after push; earlier SHA Actions evidence is not substituted.
- Desktop Windows publish/install smoke requires Windows PowerShell 7/.NET 8 and GitHub Windows runner; those executables are unavailable in this local environment. No production DB/VPS/DNS/secrets/signing/cutover changed.
- The final report and blockers document are `PORTAL_FINAL_PROJECT_CLOSEOUT_REPORT.md` and `PORTAL_FINAL_EXTERNAL_BLOCKERS.md`.


## Finalization Megapack closeout audit - 2026-10-01

Starting SHA `f2a1ac0fb9ad21cf3886b3b72f8a7492237d2287`; ending source SHA `7264d9bd2f83c167eb0c97a2dcc939e82170ef83`; documentation sync `90aa17c779ff622aa3ece1df2c3b963680068f98`. Commits: `7264d9b fix: bound reminder dispatch batches`; `90aa17c docs: classify finalization closeout gates`. Item 33 was already ✅ at the starting SHA; no duplicate alias/history work was performed. Item 47 gained a deterministic 500-dispatch batch cap and deferred-candidate metadata. Local affected checks passed (reminder/operator 15/15, `test_production` 52/52, `test_money_units` 4/4, compileall and diff-check). Current-SHA Server/Web CI is green (run IDs and totals below); item 47 is now software-complete. No disposable PostgreSQL case was added because the patch changes no tenant persistence/schema contract; the earlier item 47 PG evidence remains in the matrix.

Remaining yellow classifications:

- No A items remain open. Item 47 was the last confirmed software gap and is now ? after current-SHA CI.
- **B - manual/physical:** 59 native Android save/chooser; 60 target-browser Web Share; 61 Android system email intent; 63 Android/WebView Excel flow; 86 physical Android parity; item 85 target-PC install/update proof (also C).
- **C - external/provider/production:** 46 needs a real defect/QC source (quality remains unavailable); 77-79 lack verified official public-feed adapters and production live-fetch/scheduler activation; 80 production Android cutover; 83 production signing Secrets/manual release (plus physical update proof); 85 production Windows publication/signing; 93 real off-server backup; 105 a separately authorized disposable rehearsal from actual imported SQLite snapshot (production rows remain untouched); 125 domain/DNS/HTTPS release gate.

No defect/QC source or official Ozon/Wildberries feed was found in the repository, so no synthetic quality counts or news items were created. Item 105 source inventory remains read-only: current PostgreSQL compatibility money is exact Decimal/NUMERIC, canonical runtime money is integer kopecks, and imported SQLite affinities remain unknown without a disposable snapshot. Runtime search for Telegram/Termux references showed only historical schemas, migrations, compatibility tests, and boundary tests; no active Telegram runtime/config/secrets were found.

Current roadmap counts are **93 ✅ / 15 🟡 / 6 ⏳ / 12 🔌**. Current-SHA Server run `36818033879` (#164) and Web run `36818033902` (#157) passed; Server totals are 304/48 skipped on both Python versions, PostgreSQL totals are 36/2 gated skips and teardown confirms `db=0 roles=0 temp=0`.

**Exact NEXT:** no software-completable item remains open. Complete the listed B/C gates when their real device, provider, disposable snapshot or production evidence is available; keep production activation off until owner action.


## L. Production cutover follow-up — 2026-10-02

- ✅ Расхождение `app_users` 5→4 классифицировано: лишняя запись старого server candidate — legacy bootstrap `admin`, а не потерянный сотрудник.
- ✅ В сохранённых телефонных/source snapshots рабочие tenant-аккаунты Company 1: Ernest, V.Belov, E.Miroshnichenko, N.Asafova; live split tenant содержит эти 4 аккаунта.
- ✅ Control DB содержит отдельного Platform Owner; его нельзя считать tenant-пользователем компании.
- ✅ Core counts совпадают между проверенным candidate и split tenant: employees 4, clients 39, operations 78, tariff_versions 403, work_log 8, products 47.
- ✅ Live VPS на 2026-10-02: production service/PostgreSQL/backup timer active; 48 FORCE RLS; daily backup success; retention 14 days.
- ✅ Central snapshot, supplement и final snapshot SHA-256 повторно проверены.
- 🟡 Независимый off-server backup/restore остаётся открытым (item 93).
- ⏳ Свежий post-write-freeze SQLite snapshot после 01.10 не подтверждён (item 96).
- ⏳ Production domain/HTTPS, финальная lineage/reconciliation, signed Android release и authenticated cutover smoke остаются release gates.
- 📄 Evidence: `PORTAL_PRODUCTION_RECONCILIATION.json` schema v2 и `PORTAL_PRODUCTION_FOLLOWUP_20261002.md`.

## M. Production release candidate — 2026-10-03
- TalAnt/WMS/ТСД исключены из блокеров первого официального релиза и остаются отдельным будущим этапом.
- Создана чистая релизная линия `assistant/portal-release-20261003` на базе консолидированного Desktop 4.5; незавершённый Excel 2.0 сохранён отдельно и в релиз не включён.
- Production PostgreSQL переведён со Stage-7 login-ролей на отдельные `portal_prod_*_runtime`; старые Stage-7 роли отключены для LOGIN после успешного `/api/ping` и `/api/ready` smoke.
- Перед изменениями создан fresh pre-cutover backup control DB, tenant DB и central storage; копия вынесена с VPS и SHA-256 совпали.
- Release CI выявил две UI-регрессии в новом модуле счетов: legacy fallback без v3 и доступ к дебиторке для read-only permission. Обе исправлены; повторный Android UI/master-control gate обязателен перед merge.
- Не закрытые внешние gate после программной проверки: собственный production domain/DNS/HTTPS, финальный authenticated device smoke и формальное объявление VPS/PostgreSQL единственным source of truth после успешного cutover.

- Release CI hardening: `main` добавлен в push-триггеры `server-tests.yml` и `android-ui-tests.yml`, чтобы официальный main всегда проверял server isolation и Android UI, а не полагался только на проверки release-ветки.
