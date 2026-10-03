# PORTAL branch/source reconciliation — 2026-10-04

## Цель

Устранить риск, когда новая версия файла существует только в локальной worktree, боковой Git-ветке или одном VPS-контуре. Канонический источник PORTAL — GitHub `main`; production runtime обновляется отдельно только immutable release одного проверенного SHA.

## Что было найдено

- На момент начала проверки локальная линия 4.7 была на `63ad663`, а `origin/main` уже содержал ещё три корректных release-integrity коммита: `6296e2e`, `06f9b44`, `9953d3e`.
- Уникальный local-first closeout `806cb93` не входил в `main`. Он перенесён поверх актуального `9953d3e` и сохранён в integration-линии.
- Параллельная ветка `assistant/local-first-final-20261004`: code commit `858359b` patch-equivalent уже перенесённому local-first изменению. Финальный `852c923` содержит version/report closeout, который уже аккуратнее представлен текущими `459e719` + `b366513`; повторно переносить его не требуется.
- Ветка `assistant/portal-release-20261003` содержала реально уникальный проверенный iOS App Store/TestFlight pipeline (`34cef85` → `17ff6a1`), которого не было в `main`. Полезные файлы восстановлены в PORTAL 4.8 без отката более новых Web/cache/version изменений.
- Ветка `assistant/catalog-cache-hotfix-20261003` принудительно исключала catalog из persistent cache. Этот старый workaround не переносится: текущий local-first adapter возвращает cache мгновенно, но одновременно выполняет silent server refresh и имеет targeted invalidation, поэтому сохраняет актуализацию без возврата к медленному cold-only catalog.
- Ветка `assistant/tariffs-cache-speed-20261003` содержит ранние варианты bulk tariffs/Excel 2.0. Текущий 4.8 уже содержит Excel template 2.0 с 8 листами и более новый local-first/bounded-read контур. Отдельный старый endpoint-drift blocker перепроверен: production `/api/ping`, `/api/ready`, `/web/`, `/web/index.html`, `/web/production.js`, `/web/web_adapter.js` сейчас отвечают HTTP 200.
- `codex/portal-security-remediation-20261003` и `assistant/excel2-release-20261003` не содержат уникального patch относительно текущей линии, требующего повторного переноса.

## Локальные worktree

Проверены зарегистрированные worktree:
- `portal-closeout-20261003` — текущая integration-линия;
- `portal-local-first-final-20261004` — clean, изменения классифицированы выше;
- `release-integrity` — clean, соответствует `9953d3e`.

Уникальных незакоммиченных файлов в этих worktree на момент проверки не обнаружено.

## VPS inventory до переключения 4.8

- production runtime: immutable release `63ad6637-portal47` / Server 4.7.0;
- canonical source mirror `/srv/portal-source/repo`: clean `63ad6637...` до будущего sync с новым `main`;
- Stage 7 checkout остаётся отдельным тестовым контуром и содержит исторические local hotfix/backups; его нельзя считать source of truth и нельзя слепо hard-reset до отдельного staging rollout;
- старые `portal-test`, `portal-pg-test`, `portal-pg-realcopy-test` — тестовые runtime snapshots, не канонические исходники.

## Новое правило сохранности

1. Перед любой работой: `git fetch --all --prune` и сверка с `origin/main`.
2. Работа только в отдельной branch/worktree.
3. Tests → roadmap → commit → push → GitHub CI → merge в `main`.
4. VPS source mirror автоматически следует за GitHub `main` через `portal-source-sync.timer`.
5. Source sync не активирует production автоматически.
6. Staging/production получают только полный immutable payload одного точного SHA после gate/smoke.
7. Необъяснимое расхождение local/GitHub/source-mirror/runtime = STOP RELEASE.

## TalAnt

TalAnt/WMS/ТСД заморожен владельцем 04.10.2026 до отдельной команды и не является blocker текущего closeout PORTAL 4.8.
