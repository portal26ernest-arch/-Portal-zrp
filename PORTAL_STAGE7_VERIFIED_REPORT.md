# PORTAL — Stage 7 verified report

Дата последней проверки: 28.09.2026.

## Итог

Последняя версия Stage 7 успешно развернута на реальном VPS и прошла live API/RLS/restart integration и внешний HTTPS smoke через Cloudflare Quick Tunnel. Production cutover не выполнялся, production database не затрагивалась.

## Проверенный staging

- Commit на VPS: `31baa268218960f2e06c75e0ead822f81388c512`.
- База: `portal_test_stage7_staging`.
- systemd: `portal-stage7.service` — active/running.
- API: только `127.0.0.1:8770`.
- PostgreSQL: только loopback `127.0.0.1/[::1]:5432`.
- Внешний pilot URL на момент последнего smoke: `https://belong-level-deutschland-jurisdiction.trycloudflare.com`.
- `/api/ping`: `ok=true`, `setup_required=false`.
- Внешний `POST /api/setup`: HTTP 403.
- `production_database_touched=no`.

Quick Tunnel URL временный, меняется и не является постоянным доменом или production endpoint.

## Миграции и изоляция

- История миграций сохраняется по имени файла и checksum; повторный прогон пропускает уже применённые неизменённые миграции, несовпадающий checksum считается ошибкой.
- Отдельная staging БД и отдельный systemd/runtime контур.
- Роли `portal_stage7_control` и `portal_stage7_tenant`: не superuser и без BYPASSRLS.
- RLS/FORCE RLS и tenant isolation проверены; live test покрывает auth, tenant isolation, CRUD и перезапуск сервиса.
- Исправлена последовательность identity для `companies` после seeded `id=1`; synthetic test company создаётся без конфликта с seed.
- Секреты не выводились в отчёт; `/etc/portal-stage7` — mode 0700, `db.secrets` и `first-login.txt` — mode 0600.

## HTTPS/domain gate

SSLIP имя `178-209-127-247.sslip.io` разрешалось на адрес VPS `178.209.127.247`, но Let’s Encrypt HTTP-01 secondary validation не смог получить ответ по TCP/80. Точный блокирующий слой не установлен; firewall/VPN настройки не менялись. Для завершённого staging smoke использован Quick Tunnel. Следовательно, постоянный домен и TLS через собственный домен остаются открытым gate.

## Проверки

- Live VPS integration `test_live_api_crud_rls_and_restart`: passed.
- Stage 7 safety tests: 11/11 passed.
- Полный server regression: 144 passed, 11 skipped (тесты с отдельным live контекстом).
- Python compile для `server/*.py`: passed.
- Android Node/UI/security suite: 17/17 passed.
- `bash -n` для deploy script, PowerShell parser для runner, `git diff --check`: passed.
- GitHub Server workflow для `31baa26`: success. Android UI и APK build workflows прошли на `ad343e3`; более поздние изменения не затрагивали Android source.
- Локальный Gradle APK build не запускался успешно: в окружении отсутствует JDK/Java. Signed release workflow не запускался.

## SSH transport

Direct SSH с Windows зависал после client identification string; маршрут на машине проходил через AdGuard VPN. `plink`/PuTTY отсутствовали, а прямой OpenSSH путь не завершил handshake. Локальный server-banner-first relay позволил пройти handshake. Relay слушает только `127.0.0.1:2223` и перенаправляет на фиксированный VPS `178.209.127.247:22`; deploy runner сохраняет pinned identity, pinned known_hosts и строгую проверку host key. Ключ не встроен в relay. Deploy script перед передачей нормализуется в LF, поскольку рабочая копия Windows хранит его с CRLF.

## Изменения и коммиты

Начиная с базового commit `807944fc61d37e756758c145328a558fb7f78664`, в текущую ветку интегрирована удалённая работа по Stage 7 и Android release readiness, затем добавлены исправления по результатам реального прогона. Основные коммиты:

- `83bf940` — harden Stage 7 staging deploy automation.
- `6080830` — merge Stage 7 verification and release readiness.
- `ee32868` — normalize Stage 7 deploy script transfer.
- `56d554f` — advance staging company identity sequence.
- `31baa26` — bounded DNS retries for HTTPS smoke.

Изменения включают закрепление deploy commit и проверку его принадлежности ветке; запрет небезопасного reset; deploy lock; checksum-aware migration history; усиление systemd; certbot nginx reload hook; доменный приоритет и выбор Quick Tunnel как fallback; pinned SSH transport и relay; ограниченные DNS retries; live auth/tenant/CRUD/restart проверки. Удалённая работа включала укрепление Android signing workflow, SHA-256 certificate pinning, PKCS12 helper и release manifest workflow.

## Этап 6 и данные

Stage 6 не менялся. Имеющийся synthetic VPS gate и документированный backup/restore rehearsal Stage 6 остаются доказательством для того этапа. Отдельный новый Stage 7 backup/restore rehearsal в этом цикле не проводился. Production DB/API не переключались, production данные не удалялись и не изменялись.

## Готовность 3.4

PORTAL 3.4 не является release candidate. Версия и серверный `BUILD_ID` остаются `3.3-dev`; manifest URL пуст. Подготовлены workflow/helper для постоянной подписи, но постоянный release keystore и требуемые GitHub secrets/API URL не настроены; signed APK 3.4 не собран. Дополнительно отсутствует локальный JDK для сборки. Нельзя переходить к выпуску, установке на телефон или production cutover до закрытия release gates и проверки физического pilot.

## Следующие задачи

1. Подтвердить и разрешить внешний вход TCP/80 на VPS для HTTP-01; не открывать PostgreSQL или loopback API.
2. Выбрать постоянное staging имя и проверить его DNS на адрес VPS.
3. Повторить Stage 7 deploy со значением `PORTAL_STAGE7_DOMAIN` и подтвердить сертификат собственного домена.
4. Подготовить и надёжно сохранить постоянный Android release signing key.
5. Настроить release secrets и постоянный HTTPS manifest/API URL в GitHub.
6. Установить JDK в Android build runner или локальное build окружение.
7. После закрытия gate повысить version metadata до 3.4 согласованным commit.
8. Собрать signed APK и проверить package, version, signature и certificate pin.
9. Установить APK на физический телефон и выполнить pilot без production write.
10. Только после отдельного решения владельца выполнить write-freeze, финальный snapshot/import/reconciliation и рассматривать production cutover.

## Откат

Stage 7 изолирован отдельной БД, service, runtime user и loopback API. Откат staging выполняется возвратом deploy к ранее проверенному commit и восстановлением staging-состояния по runbook/backup. Не удалять staging/production базы и не переключать production API в рамках проверки. Любой production cutover требует отдельного решения и проверенного rollback rehearsal.
