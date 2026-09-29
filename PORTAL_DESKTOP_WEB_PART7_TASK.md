# PORTAL — Desktop/Web Part 7

Дата: 29.09.2026
Ветка: `codex-desktop-web-part7`
База: `853e6c3233458a773c914404552646c047e06239`

## Постоянное правило сборки

APK собираем ТОЛЬКО через GitHub Actions. Не устанавливать локально Gradle/JDK ради Android-сборки и не выполнять локальную APK-сборку.
В этой задаче production/VPS не трогать, push/merge/deploy не делать.

## Цель

Реализовать первый полноценный Desktop/Web-клиент PORTAL поверх того же API/PostgreSQL и того же UI/permission model, без копирования/расхождения Android-функций.

Roadmap:
- 84 — полноценный Desktop/Web-клиент на едином API/PostgreSQL;
- 86 — единый UX и права Android/Desktop/Web;
- 68, 53–63 — закрыть Web-часть Documents/Excel там, где backend уже существует;
- 85 Windows installer НЕ закрывать в этом блоке: сначала нужен рабочий Web.

## Архитектурное правило

1. Не создавать второй независимый frontend с копией бизнес-логики.
2. Использовать те же `core.js`, `app.js`, `screens.js`, `production.js`, `preview.js`, `documents_excel.js`, `ui.css`, SVG/sticker assets, что и Android.
3. Для Web добавить минимальный browser adapter, совместимый с существующим `PortalNative` API там, где это разумно.
4. Web работает same-origin с PORTAL server; не нужен произвольный server URL в браузере.
5. Server остаётся security authority; UI permission checks только presentation layer.

## A. Web shell / static serving

6. Добавить web entry point `/web/` или `/app/` на server.
7. Static assets отдавать из общего Android assets source либо другого единого canonical source без ручного duplicate tree.
8. Разрешить только строгий allowlist статических файлов/путей:
   - index/web shell;
   - css/js;
   - brand-mark.svg;
   - stickers/*.svg / catalog.json.
9. Запрет path traversal, hidden files, arbitrary filesystem reads.
10. Правильные MIME types, nosniff, no-store для HTML/JS/CSS во время development/test, либо безопасная cache policy с versioning.
11. CSP для Web:
   - default-src 'self';
   - script/style/img/font только необходимое;
   - connect-src 'self';
   - object-src 'none';
   - base-uri 'none';
   - frame-ancestors 'none';
   - form-action 'self' или 'none' по фактической модели.
12. Добавить минимум:
   - X-Content-Type-Options: nosniff
   - Referrer-Policy
   - X-Frame-Options DENY или эквивалент CSP.
13. API routes не должны конфликтовать со static routes.
14. Web static serving должен работать и на SQLite test, и на PostgreSQL runtime без доступа к production data.

## B. Browser PortalNative adapter

15. Создать `web_adapter.js`/эквивалент, который устанавливает `window.PortalNative` только в браузере.
16. Реализовать совместимые методы:
   - `getServerUrl()` -> текущий origin;
   - `setServerUrl()` -> fail-closed/no-op для произвольного другого origin;
   - `requestAsync()` -> same-origin fetch API;
   - `requestForCompany()` если реально требуется legacy fallback;
   - `checkUpdates()` -> Web не должен предлагать Android APK update;
   - `saveBase64FileAsync()` -> Blob + browser download;
   - `shareBase64FileAsync()` -> Web Share API когда доступно; безопасный fallback на download, без silent mail send.
17. Не отправлять токен в query string/local URL.
18. Authorization только через существующий header/API contract, как Android.
19. Company scope для Platform Owner передавать тем же способом, что Android bridge/server ожидают.
20. Не разрешать adapter fetch произвольных absolute URLs; только `/api/...`.
21. Не сохранять server secrets.
22. Session token storage:
   - сохранить текущую совместимость, но явно оценить localStorage risk;
   - если безопасно и без большого server refactor можно перейти Web на sessionStorage — сделать;
   - не ослаблять Android persistent-session behavior.
23. Logout очищает browser-side session полностью.

## C. Existing UI compatibility

24. Web должен открывать тот же login/owner/company flow.
25. Role/capability visibility должна совпадать с Android:
   - platform_owner;
   - director/admin;
   - manager;
   - accountant;
   - shift;
   - packer.
26. В Web не показывать Android-only controls как рабочие:
   - Android APK update/install;
   - native server URL picker;
   - Android-only permission flows.
27. Вместо этого показывать корректное Web-состояние:
   - «Web-клиент обновляется автоматически» или эквивалент для About;
   - connection settings скрыть/адаптировать к текущему origin.
28. Theme / responsive layout сохранить.
29. Desktop viewport должен использовать больше ширины без ломания мобильного Android UI. Допустима только additive CSS media query.
30. Не делать отдельные права для Web.

## D. Documents + Excel in Web

31. Реализовать/проверить Web equivalents:
   - Documents list/filter/search/pagination;
   - document download;
   - archive;
   - PDF generation actions;
   - blank/prefill Excel template download;
   - XLSX chooser/upload;
   - preview;
   - explicit confirm/apply;
   - import result download/share fallback.
32. Browser download должен использовать Blob/ObjectURL и revokeObjectURL.
33. XLSX chooser должен работать через обычный `<input type=file>`; никакой широкодоступной local filesystem permission.
34. Share:
   - Web Share API только при наличии;
   - fallback download;
   - email не отправлять автоматически и не хранить SMTP credentials.
35. Company scope Platform Owner fail-closed так же, как Android.

## E. Files / chat / links

36. Chat attachments download должны работать в Web через тот же safe browser download helper.
37. Marketplace official links открывать только после существующей official-domain validation; no raw HTML.
38. External links через `window.open(...,'_blank','noopener,noreferrer')` либо эквивалент.
39. Sticker assets работают из same-origin static path.

## F. Server/web security tests

40. Добавить server tests:
   - /web/ returns HTML;
   - allowed assets return expected MIME;
   - traversal `../`, percent-encoded traversal, backslash, query tricks rejected;
   - arbitrary file names rejected;
   - CSP/security headers present;
   - /api routes unchanged.
41. Добавить browser adapter unit/source tests:
   - only relative /api paths;
   - auth header;
   - company scope;
   - no query token;
   - network error returns existing API-shaped failure;
   - safe download MIME/name/size allowlist;
   - ObjectURL revoked;
   - Web Share fallback.
42. Добавить Playwright Web smoke:
   - загрузка /web/;
   - login flow через mocked/safe test API;
   - at least director and packer role menu parity;
   - owner requires company;
   - Documents/Excel screen opens and file chooser exists;
   - Android APK install action absent in Web;
   - no uncaught console/page errors.
43. Existing Android tests MUST remain green.

## G. CI

44. APK build всё ещё только GitHub Actions.
45. Не создавать локальную Android build requirement.
46. Расширить существующий GitHub test workflow или отдельный lightweight web test workflow только если необходимо:
   - server unit tests;
   - Node/Playwright web tests.
47. Не добавлять Windows installer пока.
48. Не расширять GitHub permissions без необходимости.
49. Не push.

## H. Roadmap/report

50. Обновить roadmap по факту:
   - 84: можно поставить 🟡 или ✅ только исходя из реальной функциональной полноты Web;
   - 86: не ✅, если есть известные platform-specific gaps;
   - 53–63/68 уточнить Web-status только по реально проверенным flows;
   - 85 оставить ⏳.
51. Создать `PORTAL_DESKTOP_WEB_PART7_REPORT.md`:
   - архитектура;
   - shared UI approach;
   - implemented browser adapter;
   - Documents/Excel Web coverage;
   - security headers/static serving;
   - tests;
   - remaining gaps;
   - recommended Part 8.
52. Прогнать:
   - targeted server web tests;
   - relevant server regression;
   - `NODE_PATH=C:\Users\darta\Documents\PORTAL-Android\node_modules node --test android_src/tests/*.test.cjs`;
   - новые web tests;
   - Python compileall;
   - `git diff --check`.
53. Локальную APK НЕ собирать.
54. Сделать локальный commit.
55. Worktree должен быть чистым.
56. Не push, не merge, не deploy.

Работай самостоятельно, не задавай уточняющих вопросов.