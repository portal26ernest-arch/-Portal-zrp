# PORTAL — overnight continuation report

Дата: 28.09.2026
Рабочая ветка: `portal-next-b003`
Исходный локальный commit: `807944fc61d37e756758c145328a558fb7f78664`
Последний функциональный/deploy commit: `31baa268218960f2e06c75e0ead822f81388c512`

## Результат

Stage 7 staging развёрнут на реальном VPS на последнем commit и прошёл live CRUD, авторизацию, tenant isolation/RLS, restart и внешний HTTPS smoke через временный Cloudflare Quick Tunnel. Внешний `/api/ping` вернул `ok=true`, `setup_required=false`; внешний `POST /api/setup` вернул HTTP 403. Итоговый файл VPS сообщил `production_database_touched=no`.

Stage 6 не регрессировал. Production cutover, изменение production БД и удаление пользовательских данных не выполнялись. Stage 7 готов для дальнейшего staging пилота через временный tunnel, но не является постоянным доменным/production HTTPS gate. PORTAL 3.4 не готов к выпуску.

## Что было сделано

Интегрирована удалённая работа, появившаяся в `origin/portal-next-b003` после общего базового commit: отчёт Stage 7, SSH relay, Android release-signing hardening, сертификатный pinning, PKCS12 helper и release manifest workflow. Поверх интеграции закреплён deploy commit, добавлены deploy lock, чистота staging checkout, checksum-учёт миграций и усиление systemd.

Реальный прогон выявил два дефекта. Во-первых, Windows передавал deploy script с CRLF, и удалённый bash не мог надёжно его исполнить; runner теперь передаёт нормализованный LF. Во-вторых, seeded `companies.id=1` оставлял identity sequence позади, из-за чего тестовая компания конфликтовала с seed; sequence теперь выставляется после seed, добавлена регрессия, а live интеграция прошла. DNS smoke также получил ограниченные повторы с backoff 2/4/8/12 секунд.

Runner проверяет pinned commit/ветку и host key, запрещает небезопасный reset, использует локальный banner-first SSH relay для проблемного маршрута, записывает migration checksums, проверяет auth/tenant isolation/CRUD/restart и сохраняет результат в staging. API и PostgreSQL остаются loopback-only. Runtime роли без superuser и BYPASSRLS; staging использует отдельную БД. Секреты не выводятся в лог отчёта.

Stage 7 включает 11 локальных safety checks, checksum migration history, доменный приоритет, SSLIP как pilot путь и Quick Tunnel fallback. Повторная migration проверка в deployment пропустила совпадающие ранее применённые миграции. Последняя внешняя проверка зафиксирована в `reports/stage7-runner-20260928-211449.log`.

## Сетевой путь и HTTPS

Маршрут Windows к VPS шёл через AdGuard VPN. Direct OpenSSH зависал после client identification; `plink`/PuTTY не установлены. Banner-first relay исправил handshake и использовал тот же pinned identity/known_hosts со строгой host key проверкой. Relay привязан к `127.0.0.1:2223`, VPS endpoint зафиксирован как `178.209.127.247:22`.

`178-209-127-247.sslip.io` разрешался на VPS, но Let’s Encrypt HTTP-01 не смог получить внешний ответ на TCP/80. Не установлено, на каком firewall-слое блокируется вход, и никаких firewall/VPN настроек не меняли. Поэтому smoke выполнен через Cloudflare Quick Tunnel: `https://belong-level-deutschland-jurisdiction.trycloudflare.com`. Tunnel временный, URL может смениться.

## Проверки и CI

- Полный server unittest: 144 passed, 11 skipped (отдельный live контекст).
- Stage 7 focused safety tests: 11/11 passed.
- Python compile `server/*.py`: passed.
- Android Node/UI/security: 17/17 passed.
- Live VPS `test_live_api_crud_rls_and_restart`: passed.
- `bash -n`, PowerShell parser, `git diff --check`: passed.
- GitHub Server workflow для `31baa26`: success.
- Android UI и APK build workflows для `ad343e3`: success; последующие изменения Android source не затрагивали.
- Попытка локальной Android сборки заблокирована отсутствующим JDK/Java. Signed release workflow не запускался.

11 skipped server tests требуют отдельного live PostgreSQL/VPS контекста. Новый Stage 7 backup/restore rehearsal в этом цикле не проводился. Stage 6 синтетический VPS gate и его ранее проведённый backup/restore rehearsal сохранены; Stage 6 код и данные не менялись.

## Готовность релиза и границы

В `android_src/release.properties` и серверном `BUILD_ID` остаётся `3.3-dev`; manifest URL пуст. Постоянный Android signing key, нужные GitHub secrets и постоянный API/manifest URL не подготовлены. Подготовлены signing helper/workflow и certificate pin checks, но signed APK 3.4 не создан. Для локальной сборки также нет JDK. Значит 3.4 — не release candidate.

Перед release нужны постоянный домен/TLS, API и manifest URL, постоянный signing key/secrets, build, проверка signature/certificate pin, физический телефонный pilot. Только после этого и отдельного решения владельца возможны write-freeze, финальный snapshot SQLite, импорт/reconciliation и cutover.

## Изменённые области и история

Ключевые commits после исходного общего base:

- `83bf940` — staging deploy hardening.
- `6080830` — merge подтверждения Stage 7 и release readiness.
- `ee32868` — исправление CRLF/LF передачи deploy script.
- `56d554f` — исправление companies identity sequence.
- `31baa26` — bounded DNS retries для внешнего HTTPS smoke.

См. [PORTAL_STAGE7_VERIFIED_REPORT.md](PORTAL_STAGE7_VERIFIED_REPORT.md) и [PORTAL_MASTER_ROADMAP.md](PORTAL_MASTER_ROADMAP.md) для полного staging evidence и checklist. Исторические untracked файлы и `node_modules/` оставлены без изменений и не включались в работу/коммиты.

## Следующие 10 шагов

1. Разрешить внешний TCP/80 к VPS для HTTP-01 и проверить доступность с публичной стороны; не открывать PostgreSQL/API.
2. Выбрать постоянный staging hostname и настроить A/AAAA записи на VPS.
3. Повторить Stage 7 deploy с `PORTAL_STAGE7_DOMAIN`; проверить постоянный TLS и API smoke.
4. Создать и безопасно сохранить постоянный Android signing key.
5. Настроить GitHub release secrets и постоянные API/manifest URL.
6. Подготовить Android build host с JDK.
7. После подтверждения release gate обновить version metadata до 3.4.
8. Собрать signed APK, проверить package/version/signature/certificate pin и manifest.
9. Установить APK на физическое устройство и провести ограниченный pilot без production writes.
10. Отдельно утвердить write-freeze, final snapshot, импорт и reconciliation; cutover выполнять только после rollback rehearsal и явного решения владельца.

## Откат

Для текущего результата production rollback не нужен: production не затрагивалась. При проблеме staging возвращать deploy к предыдущему проверенному commit по runbook и восстанавливать только staging из резервной копии. Не удалять базы и не менять production endpoint без отдельного разрешения и завершённой проверки отката.

## Одно точное действие владельца на утро

Попросить VPS/сети администратора проверить путь входящего HTTP и разрешить TCP/80 до `178.209.127.247` для ACME HTTP-01, не открывая порты PostgreSQL или API; после подтверждения задать выбранный `PORTAL_STAGE7_DOMAIN` и повторить `pwsh -NoProfile -File tools/run_stage7.ps1`.
