# PORTAL Android 3.4 — release candidate report

Дата: 29.09.2026  
Ветка: `assistant-release-3.4-candidate`  
Текущий подтверждённый commit: `c46917f`

## Что подтверждено

- GitHub Actions run **#24** для `c46917f` завершён успешно.
- Job `build-apk`: все шаги SUCCESS, включая Java 17, Android SDK 35, Gradle 8.9, staging compile и отдельную проверку APK.
- CI проверил package `ru.portal.app.staging`, versionCode `34`, versionName `3.4-dev-staging` и валидную APK-подпись.
- GitHub artifact: `PORTAL_Android_3.4-dev_staging`.
- ZIP artifact SHA-256: `2ef2256b65bb0b4d7e6c4c4aabcdf7cf0bbd9121b6b18c54c736f6b803a1a7e0`.
- Внутренний APK SHA-256: `737cf287baf8bcd3dcf1728ba2b0a6a2e3be0e9c48844c8cfb760464d2651cb2`.
- SHA внутри приложенного `.sha256` файла совпадает с реально скачанным APK.

## Production signing

- Production release workflow уже существует отдельно от staging workflow.
- Он требует HTTPS API, release channel, non-dev version, versionCode > 2, точный update manifest URL и постоянный сертификат.
- Workflow отклоняет Android Debug certificate и сверяет SHA-256 release certificate с закреплённым secret.
- После сборки workflow формирует APK checksum, `portal-update.json`, валидирует release artifact и публикует GitHub Release.
- Постоянный PKCS12 release-key найден локально.
- Защищённая резервная копия release-key также найдена.
- SHA-256 основного key-файла и резервной копии совпадают: `B09A4509AA6B33826A32621E86A5CE47AEA479CE6DAA719E566411C4CCC2B5B3`.
- Key material не добавлялся в Git и не копировался в эту ветку.

## Локальные release-проверки

- `node android_src/tests/build-security.test.cjs`: OK.
- `python -m unittest android_src.tools.test_validate_release_artifact`: 1/1 OK.
- `python -m py_compile` для release/update/signing helpers: OK.
- `node --check android_src/tests/build-security.test.cjs`: OK.
- `git diff --check`: OK.
- Staging Java/Gradle compile теперь считается подтверждённым CI, а не локальным предположением.

## Что ещё НЕ закрыто

- Физический Android device gate: в момент проверки `adb devices` не показал подключённого устройства.
- Поэтому реальная установка staging APK, file chooser/share/save flow и installer/update smoke на телефоне ещё не выполнены.
- Production signed workflow безопасно ограничен `main` и release metadata; он не запускался из release-candidate ветки.
- Состояние GitHub Actions Secrets значениями не проверялось и секреты не выводились.
- Постоянный production domain/HTTPS и production cutover остаются отдельными воротами.

## Решение

Текущий staging APK 3.4 прошёл реальную GitHub CI сборку и криптографическую проверку артефакта.  
Release candidate готов к следующему этапу интеграции, но production release нельзя объявлять завершённым до physical-device gate, production secrets gate и финального HTTPS/cutover.
