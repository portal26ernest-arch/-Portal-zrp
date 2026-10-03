# PORTAL iOS — Unlisted App release runbook

Целевая модель распространения: Apple App Store Unlisted App.
Пользователь получает прямую ссылку PORTAL и устанавливает приложение через App Store.
В поиске, категориях и публичных подборках App Store приложение не должно отображаться.

Официальная справка Apple:
https://developer.apple.com/support/unlisted-app-distribution/

## Архитектура

PORTAL iOS — тонкий клиент той же системы PORTAL.
Он использует тот же Server/API/PostgreSQL и тот же mobile UI assets,
что PORTAL Android. Отдельной iOS мастер-базы нет.

Текущий bundle identifier: ru.portal.app.ios.
Перед первой публикацией его нужно окончательно подтвердить в Apple Developer/App Store Connect.

## Этап 1 — техническая сборка

1. GitHub macOS 26 CI генерирует Xcode project через XcodeGen и проверяет Xcode 26+.
2. Проект компилируется и проходит unit tests без production signing.
3. Android/iOS parity checker подтверждает одинаковую продуктовую версию и один источник shared mobile assets.
4. Release-validator проверяет privacy manifest, App Store icon, export-compliance metadata и запрещает production API на IP/sslip/trycloudflare/placeholder.

## Этап 2 — Apple Developer и TestFlight

Для подписанной сборки нужны:
- активная Apple Developer Program membership;
- App Store Connect app record для `ru.portal.app.ios`;
- Apple Distribution certificate в PKCS#12 и App Store provisioning profile;
- Team App Store Connect API key (Key ID + Issuer ID + один раз скачанный `.p8`);
- App Store metadata, privacy answers и обязательные screenshots;
- стабильный принадлежащий PORTAL HTTPS API endpoint.

В GitHub Secrets должны быть настроены:
- `PORTAL_PUBLIC_API_URL`;
- `PORTAL_IOS_TEAM_ID`;
- `PORTAL_IOS_CERTIFICATE_P12_BASE64`;
- `PORTAL_IOS_CERTIFICATE_PASSWORD`;
- `PORTAL_IOS_PROVISIONING_PROFILE_BASE64`;
- `PORTAL_ASC_KEY_ID`;
- `PORTAL_ASC_ISSUER_ID`;
- `PORTAL_ASC_PRIVATE_KEY_P8_BASE64`.

Workflow `.github/workflows/ios-release.yml` запускается вручную. Он собирает signed archive, проверяет bundle/version/API/privacy/signature, экспортирует IPA, валидирует IPA через App Store Connect и по флагу `upload_to_testflight=true` загружает его в TestFlight.

Первую подписанную iOS-сборку публиковать в TestFlight для реального device-smoke: вход, роли, компания, выработка, зарплата, склад, документы, счета, Organizer, сохранение/отправка файлов и все доступные мобильные модули.

TestFlight — только тестовый этап, не конечный способ выдачи сотрудникам.

## Этап 3 — Unlisted App

App Store record сначала создаётся с методом распространения Public. Перед запросом Unlisted приложение должно быть готово к финальной публикации и отправлено в App Review; в Review Notes обязательно указать намерение распространять PORTAL как Unlisted App. Затем подаётся отдельный запрос Apple на Unlisted App distribution.

После одобрения Apple метод распространения станет Unlisted, а Apple выдаст прямую App Store ссылку. Финальная ссылка сохраняется как постоянная ссылка PORTAL для iPhone.

Новые версии отправляются в App Store Connect под тем же приложением.
После одобрения пользователи получают обновления через App Store;
новую установочную ссылку для каждой версии создавать не требуется.

## Production gate

Unlisted release запрещён до выполнения всех пунктов:
- iOS CI green;
- Android regression green;
- stable owned HTTPS API;
- Apple signing configured without secrets in Git;
- TestFlight physical-device smoke green;
- privacy/App Store metadata complete;
- app icon and final screenshots ready;
- App Review passed;
- Unlisted distribution approved by Apple;
- final App Store link recorded in PORTAL master roadmap/release evidence.

Секреты Apple, certificates, private keys и App Store Connect API keys
не коммитятся в репозиторий.
