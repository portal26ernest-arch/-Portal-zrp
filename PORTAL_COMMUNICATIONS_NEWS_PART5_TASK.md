# PORTAL — Communications + Marketplace News Part 5

Дата: 29.09.2026
Ветка: `codex-communications-news-part5`
База: `a94412ab7575751912e8e3fb5336452fe34df0c7`

## Цель

Закрыть следующий незавершённый блок master roadmap:
- 69/76 — системные «Стикеры PORTAL» как переиспользуемый каталог;
- 72 — отдельный безопасный сценарий «невыход» внутри командного чата;
- 77–79 — Android-раздел новостей Ozon/Wildberries на существующем backend-контуре `marketplace_news`, только с официальными источниками и защитой от дублей.

Не трогать production/VPS, реальные зарплатные данные, тарифы, phone SQLite, APK signing/version bump и production deploy.

## Обязательный стартовый аудит

Перед изменениями прочитай:
- `PORTAL_MASTER_ROADMAP.md`;
- `docs/PORTAL_UI_BLUEPRINT_PREVIEW_APK.md`, особенно разделы Chat и Новости;
- `android_src/app/src/main/assets/core.js`;
- `android_src/app/src/main/assets/production.js`;
- `android_src/app/src/main/assets/preview.js`;
- текущие chat API/domain/repository/migrations/tests;
- `server/migrations/postgresql_stage4c.sql` — существующая таблица `marketplace_news`;
- текущую permission model и company scope.

Не дублируй уже работающие общий/личный чат, вложения, pinning и 14-day retention.

## A. Системные «Стикеры PORTAL»

1. Создай небольшой системный каталог переиспользуемых стикеров PORTAL как отдельные assets + manifest/catalog.
2. Стикеры должны быть внутренними системными ресурсами, а не пользовательскими upload-файлами и не копироваться как новый blob при каждом сообщении.
3. Минимальный полезный набор, нейтральный для работы:
   - «Принято»;
   - «В работе»;
   - «Готово»;
   - «Нужна помощь»;
   - «Важно»;
   - «Спасибо».
4. Не использовать сторонние бренды/логотипы/чужие copyrighted sticker packs.
5. Если используешь SVG, файлы должны быть локальными, простыми и безопасными, без внешних ссылок/scripts.
6. Chat message со sticker должен хранить только системный `sticker_key`/тип и отображаться одинаково после reload.
7. Sticker нельзя подменить произвольным path/url; только ключ из server-side allowlist/catalog.
8. Retention/pinning — как у обычного chat message, но системный asset физически не удаляется вместе с сообщением.
9. Добавь Android chooser/grid в текущий экран командного чата, не ломая текст/attachments/private rooms.

## B. Сценарий «Невыход»

10. Добавь отдельное действие в командном чате: «Сообщить о невыходе».
11. Минимальные поля:
   - дата смены/дня;
   - короткий комментарий/причина — необязательно, с разумным лимитом.
12. Сохраняй это как структурированное chat/system message subtype `absence_notice` (или эквивалент), а не как payroll/work record.
13. Никаких автоматических штрафов, удержаний, удаления смен, изменения зарплаты, attendance или work_log.
14. Сообщение должно быть видимо в общем корпоративном чате с явной подписью автора и датой невыхода.
15. Доступ: авторизованный сотрудник своей компании, по существующему `chat.write`; просмотр — существующий `chat.read`.
16. Retention/pinning — как у обычного сообщения.
17. Валидация: корректная дата, comment length, tenant/company scope, idempotency по request id как в существующем chat POST.
18. Добавь тесты, что cross-company/неавторизованный пользователь не может создать/читать такой notice.

## C. Marketplace News backend

19. Используй существующую таблицу `marketplace_news`, не создавай параллельную сущность без необходимости.
20. Добавь read API для Android:
   - список;
   - фильтр `all|ozon|wildberries`;
   - сортировка newest first;
   - разумный limit/pagination;
   - поля: source, title, short body/summary, published_at, official url, regulation flag.
21. News — company-scoped через существующий tenant context/RLS, но одни и те же официальные публикации могут быть записаны в разные компании через ingestion.
22. Обычные сотрудники не должны иметь произвольный write endpoint для news.
23. Добавь server-side ingestion/upsert boundary для trusted internal job/admin tooling:
   - source только `ozon` или `wildberries`;
   - URL только HTTPS;
   - строгий allowlist официальных hostnames;
   - canonicalization URL;
   - детерминированный `external_key`;
   - повтор той же публикации не создаёт дубль;
   - title/body/date limits/validation;
   - no HTML/script injection.
24. Для Part 5 официальными доменами считать минимум:
   - Ozon seller materials: `seller.ozon.ru`;
   - Wildberries seller portal/instructions: `seller.wildberries.ru`.
   Дополнительные домены не добавлять без доказуемой официальности.
25. Не хранить логины/cookies/токены маркетплейсов в APK или репозитории.
26. Не скрапить персональные/private WB news, требующие seller login. Не обходить auth, captcha или anti-bot.
27. Если автоматический live-fetch из публичного официального источника нельзя надёжно сделать без brittle scraping или auth, НЕ выдумывать его. Реализуй безопасную ingestion boundary + тестовый fixture и честно оставь fetch scheduler как отдельный gate.
28. Никакие demo fixtures не должны отображаться как реальные новости.

## D. Android News LIVE/PREVIEW behavior

29. Переведи `screens.news` с чистого demo-preview на production-aware экран:
   - если API доступен и есть реальные items — показывать LIVE;
   - вкладки Все / Ozon / Wildberries;
   - карточка: marketplace, дата, заголовок, краткое содержание, «Открыть первоисточник»;
   - URL открывать только через безопасный внешний HTTPS intent/browser flow;
   - не вставлять raw HTML от источника.
30. Если API пуст/источник ещё не подключён — показывать честный empty/preview state, без фейковых «свежих» заголовков.
31. Сохранить визуальный регламент `PORTAL_UI_BLUEPRINT_PREVIEW_APK.md`.
32. Убедись, что role/capability access соответствует существующему разделу News и Platform Owner без выбранной company fail-closed там, где company context обязателен.

## E. Tests / security

33. Добавь targeted server tests:
   - sticker allowlist;
   - sticker persistence/retention behavior;
   - absence notice validation + tenant isolation;
   - news official-domain allowlist;
   - dedup/upsert by external_key;
   - malformed/non-HTTPS/non-official URL rejection;
   - news read permissions/company scope;
   - no news arbitrary write by normal employee.
34. Добавь Android JS/UI tests:
   - sticker catalog/selection/render;
   - absence form/post/render;
   - news live list/filter/empty state;
   - URL escaping / no raw HTML;
   - official-source link behavior.
35. Прогони минимум:
   - targeted server tests;
   - полный релевантный server regression;
   - `node --test android_src/tests/*.test.cjs`;
   - Python compile;
   - `git diff --check`.
36. PostgreSQL-specific changes/test — только в disposable/test PG. Production DB не трогать.
37. Telegram/Termux runtime не возвращать.
38. Не хранить secrets в APK/source.

## F. Roadmap / CI / завершение

39. Обнови `PORTAL_MASTER_ROADMAP.md` только по факту:
   - 69/72/76 — по реальной реализации и тестам;
   - 77/78/79 — не ставить ✅, если live automatic source fetching фактически не подключён/не проверен.
40. Добавь секцию Part 5 с точными закрытыми и открытыми gates.
41. Если Android CI workflow не запускается на ветке `codex-communications-news-part5`, разрешено минимально добавить эту ветку в существующий staging Android build workflow. Signing/deploy не менять.
42. Создай `PORTAL_COMMUNICATIONS_NEWS_PART5_REPORT.md` с:
   - что было до Part 5;
   - что добавлено;
   - тесты;
   - какие пункты roadmap изменились;
   - какие gates остались открыты.
43. Сделай локальный commit. Не push, не merge, не deploy.
44. Рабочее дерево в финале должно быть чистым.
45. Финальный ответ: commit hash, изменённые файлы, тесты, открытые gates и рекомендуемый следующий блок.

Работай самостоятельно. Не задавай пользователю уточняющих вопросов, если безопасный вариант определяется по существующему коду/roadmap.