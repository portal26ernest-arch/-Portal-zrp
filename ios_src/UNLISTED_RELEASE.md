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

1. GitHub macOS CI генерирует Xcode project через XcodeGen.
2. Проект компилируется и проходит unit tests без production signing.
3. Android/iOS parity checker подтверждает одинаковую продуктовую версию
   и один источник shared mobile assets.

## Этап 2 — Apple Developer и TestFlight

Для подписанной сборки нужны:
- активная Apple Developer Program membership;
- App Store Connect app record;
- production bundle identifier и signing;
- App Store metadata, privacy answers и обязательные screenshots;
- стабильный принадлежащий PORTAL HTTPS API endpoint.

Первую подписанную iOS-сборку публиковать в TestFlight для реального device-smoke:
вход, роли, компания, выработка, зарплата, склад, документы, счета,
Organizer, сохранение/отправка файлов и все доступные мобильные модули.

TestFlight — только тестовый этап, не конечный способ выдачи сотрудникам.

## Этап 3 — Unlisted App

После готовности production build приложение проходит App Review.
После одобрения запрашивается Unlisted App distribution у Apple.
Финальная ссылка App Store сохраняется как постоянная ссылка PORTAL для iPhone.

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
