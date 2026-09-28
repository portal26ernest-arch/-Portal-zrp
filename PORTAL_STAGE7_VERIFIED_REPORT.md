# PORTAL — Stage 7 verified report

Дата проверки: 28.09.2026.

## Итог

Stage 7 staging подтверждён на реальном VPS. Production cutover не выполнялся.

## Проверенный staging

- Commit, реально развернутый на VPS:
  `59a19530678bd4ca7de3bea493f88d77fe11c08b`
- База:
  `portal_test_stage7_staging`
- systemd:
  `portal-stage7.service` — active/running
- API:
  `127.0.0.1:8770`
- PostgreSQL:
  только `127.0.0.1/[::1]:5432`
- HTTPS:
  подтверждён через Cloudflare Quick Tunnel
- Проверенный pilot URL на момент smoke:
  `https://redeem-francis-animals-signing.trycloudflare.com`
- `/api/ping`:
  `{"ok": true, "build": "PORTAL Server · 3.3-dev", "setup_required": false}`
- Внешний `POST /api/setup`:
  HTTP 403
- `production_database_touched=no`

Quick Tunnel является временным pilot-каналом и не считается production domain.

## PostgreSQL / RLS

- `portal_stage7_control`: superuser=false, bypassrls=false
- `portal_stage7_tenant`: superuser=false, bypassrls=false
- RLS включён на 45 таблицах staging.
- production PostgreSQL не переключалась на staging API.

## Секреты и права

- `/etc/portal-stage7`: mode 0700
- `/etc/portal-stage7/db.secrets`: mode 0600
- `/etc/portal-stage7/first-login.txt`: mode 0600
- значения секретов в отчёт не выводились.

## Проверки кода

Чистая интеграционная версия Stage 7:
- secret material scan: OK
- Stage 7 safety tests: 9/9 OK
- `bash -n server/vps_stage7_staging_deploy.sh`: OK
- full server regression: 142 OK, 11 skipped
- `git diff --check`: OK

Skipped-тесты соответствуют тестам, которым требуется отдельный live PostgreSQL/VPS-контекст.

## SSH diagnosis

Прямой SSH к VPS зависал после отправки client identification string, хотя raw TCP получал server banner.
Низкоуровневый тест подтвердил, что путь работает, если сначала принять SSH banner сервера, а затем отправить client banner.

Для staging verification реализован:
`tools/ssh_banner_first_relay.py`

Безопасность relay:
- слушает только `127.0.0.1:2223`;
- удалённый адрес зафиксирован на `178.209.127.247:22`;
- runner продолжает использовать pinned private identity, pinned known_hosts и StrictHostKeyChecking;
- private key в relay не встроен.

## Что НЕ сделано

- production domain/DNS;
- постоянный production HTTPS;
- финальный write-freeze телефона;
- финальный production import;
- production cutover;
- version bump до 3.4;
- постоянный Android release signing key;
- signed production APK 3.4.

## Следующий gate

1. Зафиксировать проверенный Stage 7 код в `portal-next-b003`.
2. Подготовить постоянный Android release signing key.
3. Перевести metadata на PORTAL 3.4 только после release-gate.
4. Собрать signed APK 3.4.
5. Проверить APK package/version/signature/HTTPS.
6. Установить 3.4 на физический телефон и выполнить pilot.
7. Только после pilot — финальный snapshot SQLite и отдельное решение о production cutover.
