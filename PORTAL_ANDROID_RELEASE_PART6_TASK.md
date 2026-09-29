# PORTAL — Android Release & Secure Self-Update Part 6

Дата: 29.09.2026
Ветка: `codex-android-release-part6`
База: `36d2d82f79f8ccde93e107ae9a19eb6cfd67ac3a`

## Цель

Закрыть максимально возможную часть roadmap 82–83 без production deploy:
- 82 — встроенная проверка обновлений уже есть; довести до безопасной загрузки и запуска системной установки APK;
- 83 — подписанный release workflow уже есть; добавить проверку, что загруженная APK совместима с установленной подписью PORTAL до передачи Android Package Installer.

Не создавать/не коммитить настоящий signing key. Не менять production/VPS, реальные данные, API domain, release version/build number без отдельного release gate.

## Стартовый аудит — обязательно

Перед кодом прочитать и не дублировать:
- `PORTAL_MASTER_ROADMAP.md`;
- `.github/workflows/android-release.yml`;
- `.github/workflows/android-build.yml`;
- `android_src/release.properties`;
- `android_src/app/build.gradle`;
- `android_src/app/src/main/AndroidManifest.xml`;
- `android_src/app/src/main/java/ru/portal/app/MainActivity.java`;
- `android_src/app/src/main/assets/core.js`;
- `android_src/app/src/main/assets/app.js`;
- `android_src/tools/build_update_manifest.py`;
- `android_src/tools/create_release_keystore.py`;
- Android build/native/UI/security tests.

Существующие release signing, cert SHA-256 pinning, GitHub Release publish и manifest generation считать базой и сохранять.

## A. Update manifest hardening

1. Расширять schema только если действительно нужно. Совместимость с текущим schemaVersion=1 не ломать без веской причины.
2. Android должен валидировать:
   - applicationId === текущему;
   - channel === текущему;
   - versionCode > текущего для install;
   - versionName/buildNumber/date/changelog limits;
   - apkUrl HTTPS;
   - sha256 ровно 64 hex.
3. Для release APK URL разрешить только официальный GitHub release channel PORTAL. Не принимать arbitrary HTTPS host из manifest.
4. Redirect chain при скачивании:
   - максимум 5 redirects;
   - каждый hop только HTTPS;
   - без userinfo;
   - host только allowlist, необходимый для GitHub Release assets;
   - запрет downgrade на HTTP;
   - no auth/company headers/cookies.
5. Manifest URL также должен быть HTTPS; не допускать arbitrary scheme/credentials.

## B. Secure APK download

6. Добавить native async method, вызываемый из WebView, например `downloadAndInstallUpdate(...)`.
7. Загружать APK только во внутренний/private cache app, не в публичный Downloads.
8. Использовать временное имя + атомарное завершение после успешной проверки.
9. Ограничить размер APK разумным hard limit (например <= 100 MiB) и Content-Length/stream limit.
10. Не использовать Base64 для APK.
11. Вычислить SHA-256 скачанного APK и сравнить constant-time/normalised compare с manifest sha256.
12. При mismatch удалить файл и вернуть понятную ошибку.
13. Старые update cache files очищать по времени/лимиту.
14. Никаких токенов/сессий PORTAL в запросе к GitHub.

## C. APK identity/signature verification BEFORE installer

15. До запуска системного installer проверить archive через Android PackageManager:
   - packageName == текущий BuildConfig.APPLICATION_ID;
   - archive versionCode > текущего BuildConfig.VERSION_CODE;
   - archive versionCode == versionCode из manifest;
   - желательно versionName == manifest versionName;
   - APK имеет signing certificate.
16. Получить SHA-256 signing certificate установленного приложения и загруженного APK.
17. Разрешить install только если signing lineage/certificate совместима с установленным PORTAL.
18. Для текущей архитектуры без key rotation достаточно exact current signer match, но код оформить так, чтобы не ослаблять проверку. Не принимать Debug/другой signer.
19. Не полагаться только на manifest sha256: обе проверки обязательны — file hash + app signing identity.
20. Если Android API различается, поддержать minSdk 26 корректно:
   - GET_SIGNING_CERTIFICATES там, где доступно;
   - безопасный legacy fallback для API 26/27.
21. Добавить unit/source contract tests для signer/package/version/hash rules.

## D. Android Package Installer flow

22. Добавить только минимально необходимое разрешение `android.permission.REQUEST_INSTALL_PACKAGES`.
23. Не использовать silent install/root/ADB/Device Owner tricks.
24. Если `canRequestPackageInstalls()` false:
   - открыть системный экран разрешения установки неизвестных приложений именно для package PORTAL;
   - показать пользователю понятный текст, что Android требует разрешение;
   - после возврата пользователь повторяет установку или безопасно продолжает flow.
25. После всех проверок передать APK системному Package Installer через FileProvider `content://`, MIME `application/vnd.android.package-archive`, `FLAG_GRANT_READ_URI_PERMISSION`.
26. FileProvider paths расширить минимально только под private update cache; не открывать весь cache/files root.
27. Никакого `file://`, broad exported provider или world-readable файлов.
28. Installer intent должен быть user-driven: реальная кнопка «Скачать и установить», а не автоматическая установка при check.
29. Не запускать installer для latest/unconfigured/error state.

## E. UI/UX

30. В «О программе» при state=available показать:
   - версия / build;
   - дата;
   - changelog;
   - кнопку `Скачать и установить`.
31. Во время download показывать состояние `Загружаем и проверяем…`, блокировать двойной tap.
32. После проверки перед системным installer показать/вернуть state `Готово к установке`.
33. Ошибки различать минимум:
   - download/network;
   - invalid URL/redirect;
   - size limit;
   - checksum mismatch;
   - package mismatch;
   - version mismatch/downgrade;
   - signature mismatch;
   - install permission required;
   - no installer.
34. Не раскрывать internal paths, cert bytes, secrets.
35. Существующие states unconfigured/error/latest/available сохранить.

## F. Release workflow hardening

36. Не переписывать существующий signed release pipeline.
37. Добавить fail-closed проверки только если их нет:
   - release build реально подписан;
   - cert digest == secret pin;
   - package/applicationId == ru.portal.app;
   - versionCode/versionName в APK соответствуют release.properties;
   - manifest sha256 == опубликованной APK;
   - manifest apkUrl указывает на exact tag/asset текущего release.
38. Если возможно без внешних secrets, добавить script/test для локальной валидации release metadata и manifest contract.
39. Secret values никогда не печатать.
40. Keystore material удалять/не сохранять как artifact; оставить только APK, checksum, public update manifest.
41. Не менять GitHub permissions шире существующего contents: write.

## G. Tests

42. Добавить/расширить native-shell/build-security/UI tests:
   - REQUEST_INSTALL_PACKAGES присутствует только для app;
   - FileProvider остаётся non-exported;
   - update cache path narrowly scoped;
   - no file://;
   - user-driven install action;
   - official host allowlist and redirect cap;
   - max APK bytes;
   - checksum verification;
   - package name verification;
   - version upgrade/no downgrade;
   - installed/archive signer equality;
   - Package Installer intent + MIME + read grant;
   - unknown-app permission flow;
   - states latest/error/available/install.
43. Прогнать:
   - `node --test android_src/tests/*.test.cjs` с существующим shared NODE_PATH при необходимости;
   - Python tests/tool tests relevant to update manifest;
   - `python -m compileall -q server android_src/tools` (или корректный эквивалент);
   - `git diff --check`.
44. Если локальный Gradle/SDK доступен — `assembleStaging`/Java compile. Если нет, зафиксировать gate честно; CI workflow не подменять ложным PASS.
45. Не менять production release.properties на release channel и не генерировать production APK без реального signing secret.

## H. Roadmap/report

46. Обновить roadmap только по факту:
   - 82 можно отметить ✅ только если check + download + verify + installer flow реализованы и локальные tests зелёные; реальный device overlay/install при отсутствии устройства отметить отдельным gate.
   - 83 не отмечать ✅ без реального постоянного signing key + proof update-over-installed-production-APK. Кодовый/CI contract можно отметить 🟡 с подробностями.
47. Создать `PORTAL_ANDROID_RELEASE_PART6_REPORT.md`:
   - что уже было;
   - что добавлено;
   - security model;
   - tests;
   - открытые gates;
   - точные шаги для будущего production signing setup, без секретов.
48. Создать локальный commit. Не push, не merge, не deploy.
49. Финальный worktree чистый.
50. Финальный ответ: commit hash, тесты, что закрыто, что осталось gate.

Работай самостоятельно. Не задавай уточняющих вопросов. Не возвращай Telegram/Termux runtime.