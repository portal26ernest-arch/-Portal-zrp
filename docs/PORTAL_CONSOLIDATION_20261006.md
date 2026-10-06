# PORTAL consolidation checkpoint — 06.10.2026

## Цель
Свести параллельную работу ChatGPT/Codex/OpenCode/Copilot и старые worktree к одному каноническому GitHub main без потери локальных изменений и без публикации рабочих данных из CSV/служебных артефактов.

## Каноническая база
- main после monitoring merge: 8b6466b5f2cf4fb18574a9b08867b60e5635992d.
- PR #13 self-hosted monitoring слит; CI был зелёным.
- Уникальный Codex commit 9356d5ff15bf6563df85fb29255e2d5bf95ca5b6 сохранён отдельно как rescue/codex-owned-origin-20261006.
- В consolidation-ветке он перенесён поверх актуального main; конфликтов cherry-pick не было.

## Локальный rescue перед очисткой
На Ernest-com создан локальный снимок C:\Users\darta\Documents\PORTAL-Consolidation-20261006-1535.zip.
SHA-256: 4BA9DF1921C9B88C8286B196F06F0A29A1ABFCDED84AFCC6E81F82BC2B0F3708.

В него входят Git bundles, patch-файлы dirty worktree, незатреканные файлы и результаты агентов. Архив намеренно НЕ публикуется в публичный GitHub: в старых Stage7-каталогах есть рабочие CSV с клиентами/тарифами и иные потенциально чувствительные операционные данные.

## Агенты
- Два OpenCode review task tree, стартовавшие 06.10.2026 около 14:32, были признаны зависшими: нулевые result-файлы, отсутствие прогресса в логе, нулевая CPU-активность. Они остановлены вместе только со своими дочерними процессами.
- Общий OpenCode service и Codex app-server не остановлены.
- Copilot Messenger security review завершён и подтвердил риск общего persistent Messenger-профиля между PORTAL-пользователями одного устройства.
- Codex Messenger review завершён и независимо указал на тот же класс риска для iOS/Android.
- До исправления identity-bound storage/logout cleanup Messenger branch не интегрировать в release.

## Messenger
Ветка assistant/messenger-notifications-20261006, commit 33b754e, сохранена в GitHub и содержит Telegram/MAX native web-container integration. Она не считается готовой к merge:
1. provider storage/cookies должны быть изолированы по PORTAL identity;
2. logout/account switch должен закрывать/очищать соответствующую provider session;
3. Android failure WebView.setDataDirectorySuffix должен быть fail-closed для Messenger isolation;
4. iOS не должен использовать общий WKWebsiteDataStore.default() для всех PORTAL identities.

## Старые worktree
Перед любой очисткой сохранены dirty-состояния как patches/untracked-copy в rescue-архиве. Worktree не удалять, пока не доказано одно из двух: изменения уже находятся в main либо перенесены в отдельный GitHub commit/branch.

Особое правило: Stage7 CSV и другие операционные данные не коммитить в публичный репозиторий.

## Consolidation fix
При переносе Codex security/outbox commit на актуальный main native-shell.test.cjs обнаружил Windows line-ending brittle assertion. Product migration сохраняла правильный порядок copy-all -> cleanup; тест исправлен на CRLF/LF-independent проверку.

Локально после исправления:
- node android_src/tests/native-shell.test.cjs — PASS
- node android_src/tests/desktop-shell.test.cjs — PASS
- node android_src/tests/build-security.test.cjs — PASS
- git diff --check — PASS

## Правило продолжения
Одновременно допускается один write-агент на одну интеграционную ветку. Независимые reviewers работают read-only. Любая уникальная локальная работа сначала получает rescue commit/branch или локальный проверяемый rescue snapshot, затем переносится на актуальный origin/main, проходит тесты/CI и только после этого merge.
