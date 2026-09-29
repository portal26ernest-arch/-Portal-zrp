# PORTAL Communications + Marketplace News — Part 5

Дата: 29.09.2026
Ветка: `codex-communications-news-part5`
База: `a94412ab7575751912e8e3fb5336452fe34df0c7`

## До Part 5

- Командный и личный чат, вложения, pinning и 14-дневный retention уже были реализованы.
- В чате не было системного каталога стикеров и структурированного сообщения о невыходе.
- Android-раздел Marketplace News содержал demo-карточки; PostgreSQL Stage 4C уже включал company-scoped `marketplace_news` с уникальностью `(company_id, external_key)`.
- Надёжный общедоступный live-fetch для двух seller источников не был подтверждён.

## Добавлено

- Шесть локальных SVG-стикеров PORTAL и JSON catalog; чат передаёт только ключ из серверного allowlist.
- Subtype `absence_notice` в общем чате, валидация даты и комментария до 300 символов, request-id идемпотентность. Это только chat message и не записывается в payroll, attendance или work_log.
- Company-scoped read API новостей с фильтром `all|ozon|wildberries`, сортировкой по свежести и ограниченными limit/offset.
- Trusted ingestion/upsert boundary на существующую таблицу. Разрешены только HTTPS хосты `seller.ozon.ru` и `seller.wildberries.ru`; URL канонизируется, `external_key` детерминирован, текст очищается и ограничивается.
- Android экран LIVE/empty, вкладки маркетплейсов, escaped title/body и открытие только официальных HTTPS ссылок через Android внешний intent.
- Android staging build workflow включает ветку Part 5.

## Проверки

- Server regression: `python -m unittest discover -s server -p "test_*.py"` — 194 tests passed, 16 skipped (environment-gated PostgreSQL cases).
- Android suite: `NODE_PATH=C:\\Users\\darta\\Documents\\PORTAL-Android\\node_modules node --test android_src/tests/*.test.cjs` — 27 passed, 0 failed, 0 skipped; browser UI regression included via the existing shared Playwright install.
- Python compile: `python -m compileall -q server` — passed.
- `git diff --check` — passed.
- PostgreSQL production DB и VPS не использовались; Android signing/version и deploy не менялись.

## Roadmap

- 69/72/76 закрыты по коду и тестам.
- 77/78 частично реализованы: read API и Android LIVE/empty готовы, публикация данных ожидает ingestion.
- 79 частично реализован: доменный allowlist и dedup boundary готовы; live-fetch и scheduler не подключены и не отмечены завершёнными.

## Открытые gates

- Подключить безопасный источник/операторский ingestion и scheduler только после проверки официального публичного интерфейса без приватной авторизации и brittle scraping.
- Выполнить isolated PostgreSQL migration/schema/runtime smoke для новостного read/upsert контура и staging Android build workflow на ветке.
- Production rollout и deploy не выполнялись.

Рекомендуемый следующий блок: исследовать подтверждённый публичный механизм публикаций Ozon/Wildberries и реализовать контролируемый ingestion scheduler только при доказуемой стабильности и доступности источника.
