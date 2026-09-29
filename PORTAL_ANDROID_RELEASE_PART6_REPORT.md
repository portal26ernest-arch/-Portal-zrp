# PORTAL Android Release & Secure Self-Update — Part 6

Дата: 29.09.2026
Ветка: `codex-android-release-part6`
Исходная база: `36d2d82f79f8ccde93e107ae9a19eb6cfd67ac3a`

## Что было до этой части

- Android показывал состояния проверки обновлений и читал schemaVersion 1 manifest.
- Release workflow собирал APK с release signing из GitHub secrets, сверял SHA-256 сертификата с secret pin, создавал checksum/manifest и публиковал GitHub Release.
- Постоянного production signing key и установки новой production APK поверх уже установленной production сборки не было.

## Что добавлено

- Строгая проверка полей manifest, текущих applicationId/channel, будущего versionCode, даты и текстовых лимитов, SHA-256, а также точного официального PORTAL GitHub release URL.
- Native async download через HTTPS с ручной обработкой максимум пяти редиректов, узким allowlist `github.com` / `release-assets.githubusercontent.com`, запретом userinfo/HTTP/нестандартных портов и без PORTAL auth/session headers.
- APK потоково записывается прямо в приватный `cache/updates` под временным именем без удержания APK целиком в RAM; одновременно считается SHA-256 и контролируется лимит 100 MiB. После SHA-256 и PackageManager проверок файл атомарно переименовывается.
- До Installer сверяются package name, versionCode/versionName и точный SHA-256 signer установленного приложения и APK. Для API 28+ используется `GET_SIGNING_CERTIFICATES`, для API 26/27 — legacy signatures; принимается ровно один совпадающий signer.
- Добавлены `REQUEST_INSTALL_PACKAGES`, app-specific экран разрешения Android и FileProvider URI с APK MIME и read grant. Установка запускается только кнопкой пользователя.
- About показывает build/date/changelog, состояния скачивания и готовности, а также различает основные категории ошибок.
- Release workflow дополнен проверкой package/version из APK и локальным валидатором соответствия release metadata, URL и SHA-256 manifest; временный PKCS#12 удаляется в финальном `always()` cleanup и не публикуется как artifact.

## Security model

Manifest SHA-256 подтверждает целостность переданного файла относительно manifest. PackageManager затем проверяет, что это именно PORTAL, версия совпадает с manifest и выше установленной, а signer точно совпадает с signer установленной копии. Любая ошибка останавливает передачу файла Installer. APK и временные файлы остаются в приватном cache; публичный Downloads не используется.

## Проверки

- `NODE_PATH=C:\Users\darta\Documents\PORTAL-Android\node_modules node --test android_src/tests/*.test.cjs` — **PASS: 28/28**, browser UI/Playwright regression включён, 0 skipped.
- `python -m compileall -q server android_src/tools` — **PASS**.
- Python tool test проверяет валидный metadata/manifest/APK digest и отклонение постороннего asset URL.
- `git diff --check` — выполнен.
- Локальный Gradle/Gradle Wrapper и Java в PATH отсутствуют, поэтому assembleStaging/Java compile локально не запускались. ADB установлен, но в момент проверки подключённых устройств не было. CI release workflow не запускался и его результат не имитировался.

## Открытые gates

- На реальном устройстве пройти Android unknown-app permission экран, возврат в PORTAL, повтор действия, системный installer и установку.
- Создать и безопасно сохранить постоянный production signing key вне репозитория, добавить его secret values и certificate pin в GitHub Actions.
- Выпустить подписанный APK, установить его на тестовое устройство и доказать обновление поверх этой же production-подписи. Поэтому roadmap 83 остаётся частично выполненным.
- До production включения update channel нужен отдельный release gate; текущий `release.properties` оставлен development, номер версии/build и API domain не менялись.

## Будущая настройка production signing

1. На доверенной offline-машине создать постоянный PKCS#12 key по локальной процедуре `android_src/tools/create_release_keystore.py`; не помещать keystore в репозиторий или CI artifacts.
2. Создать проверенные зашифрованные offline backups, отдельно зафиксировать alias и процедуры восстановления; ограничить доступ к паролям.
3. Рассчитать SHA-256 DER certificate и сверить его независимо. Передать PKCS#12 base64, store password, key alias, key password и digest только в GitHub Actions secrets с минимальным доступом.
4. Выпустить через workflow APK и проверить его certificate pin, package/version, опубликованный checksum и manifest.
5. Установить APK на изолированное тестовое устройство, выполнить полный download/signature/install upgrade flow и сохранить несекретные доказательства результата до production release gate.

Настоящий signing key не создавался; production/VPS и реальные данные не затрагивались.
