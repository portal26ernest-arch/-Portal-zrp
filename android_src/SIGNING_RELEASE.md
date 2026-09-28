# PORTAL Android — постоянная production-подпись

## Подтверждённый baseline

Установленная APK `2026.09.24-b002` была собрана workflow командой
`assembleDebug` на GitHub-hosted runner.

Пакет:
`ru.portal.app`

Старая установленная версия:
- versionCode: `2`
- versionName: `2026.09.24-b002`
- подпись: APK Signature Scheme v2
- subject: `CN=Android Debug, O=Android, C=US`
- SHA-256 сертификата:
  `66336b23d6917a1861538f310ce1bf2f81063af95497d1500534382b4aa8a453`

Это одноразовый debug-сертификат CI, а не постоянный production release-key.
Приватный ключ не сохранялся workflow и не должен использоваться как основа
долгосрочного production-релиза.

## Переход на постоянную подпись

Для PORTAL 3.4 создать один постоянный release-keystore и больше его не менять.
Формат production-keystore: PKCS12.

Локальная утилита:
`python android_src/tools/create_release_keystore.py`

Она просит пароль скрытым вводом непосредственно в терминале, не печатает и не
сохраняет его, создаёт `portal-release.p12` вне репозитория и сохраняет только
публичный SHA-256 сертификата/identity metadata.

Сохранить как минимум две защищённые резервные копии ключа и отдельно зафиксировать
SHA-256 сертификата.

GitHub repository secrets для signed workflow:
- `PORTAL_PUBLIC_API_URL`
- `PORTAL_ANDROID_KEYSTORE_B64`
- `PORTAL_ANDROID_STORE_PASSWORD`
- `PORTAL_ANDROID_KEY_ALIAS`
- `PORTAL_ANDROID_KEY_PASSWORD`
- `PORTAL_ANDROID_CERT_SHA256`

Workflow обязан отклонить:
- HTTP API URL;
- `-dev` версию;
- channel, отличный от `release`;
- versionCode <= 2;
- updateManifestUrl не по HTTPS;
- сертификат `Android Debug`;
- сертификат, SHA-256 которого не совпадает с закреплённым release certificate.

## Первая установка 3.4

Поскольку b002 подписана одноразовым debug-ключом, production 3.4 с постоянным
release-key нельзя установить поверх b002 обычным Android update.

После успешного Stage 7, HTTPS, миграционной сверки и проверки signed APK:

1. Убедиться, что серверные/бизнес-данные сохранены и приложение не является
   единственным хранилищем данных.
2. Сохранить нужные локальные пользовательские настройки, если они появятся.
3. Удалить старую `ru.portal.app` b002.
4. Установить 3.4, подписанную постоянным release-key.
5. Выполнить login и pilot smoke.
6. Проверить встроенное обновление.
7. Все следующие production APK подписывать тем же release-key.

После этого обновления 3.5, 3.6 и далее должны устанавливаться поверх предыдущей
версии без удаления приложения.

## Запрет

Не выпускать production APK случайным debug-ключом и не менять release-key после
первой постоянной production-сборки.
