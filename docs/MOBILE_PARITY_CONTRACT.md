# PORTAL Mobile Parity Contract

Дата фиксации: 03.10.2026.

## Решение владельца

PORTAL Android и PORTAL iOS являются двумя мобильными клиентами одной системы.
Они не развиваются как отдельные продукты.

Любая новая мобильная бизнес-функция по умолчанию должна появляться одновременно
на Android и iOS, если владелец явно не ограничил задачу одной платформой
или функция объективно зависит от конкретной ОС.

## Единый источник мобильного интерфейса

Канонический HTML/CSS/JavaScript мобильного интерфейса:
android_src/app/src/main/assets.

Android загружает эти assets в Android WebView.
iOS подключает этот же каталог как resources и загружает его в WKWebView.
Копировать или форкать эти assets в ios_src запрещено.

Это означает, что экраны, роли, права, модули, формы и workflows,
реализованные в общем UI, меняются один раз и попадают в обе мобильные сборки.

## Что остаётся нативным

Нативная оболочка Android отвечает за Android WebView, системное хранение/отправку
файлов и Android APK update installer.

Нативная оболочка iOS отвечает за WKWebView, системное хранение/отправку файлов
и App Store-managed update flow.

Обе оболочки обязаны реализовывать совместимый PortalNative bridge
для общего UI и обращаться к одному PORTAL Server/API.

## Данные и сервер

Отдельная iOS-база компании запрещена.
Отдельная Android мастер-база компании запрещена.
Канонические данные находятся на VPS/PostgreSQL и выдаются через защищённый API.

Права, tenant isolation, тарифы, зарплата, склад, документы, счета, Organizer,
аналитика и последующие модули должны определяться сервером, а не дублироваться
разными правилами внутри двух мобильных клиентов.

## Release gate

Изменение мобильной функции не считается завершённым, пока:
1. общий UI/Server contract проверен;
2. Android regression/CI зелёный;
3. iOS parity check зелёный;
4. iOS compile/tests зелёные;
5. платформенные отличия явно задокументированы;
6. master roadmap обновлён.

ios_src/tools/check_mobile_parity.py блокирует рассинхронизацию номера версии
Android/iOS и появление отдельной копии shared assets внутри iOS.

Для production-релизов версия PORTAL должна синхронно отражаться
в Android и iOS metadata; номера платформенных build могут меняться только
осознанно и должны оставаться трассируемыми в release notes.

## Сетевое восстановление 5.14 — 16.10.2026

Android сохраняет выбранный системный DNS и обычный сетевой путь. Если health probe
неудачен, только `api.vart-portal.ru` и `reserve-api.vart-portal.ru` могут быть
разрешены через app-scoped DNS-over-HTTPS. В DNS-запрос попадает только имя сервера,
без токена, компании или тела API-запроса. Новый путь активируется на 120 секунд
после анонимного `/api/ping` с проверкой PORTAL-ответа; HTTPS URL/Host/SNI и обычная
проверка сертификата сохраняются. POST не повторяется автоматически.

Объективное отличие iOS: используемый URLSession не предоставляет аналогичный
per-request DNS override; app-level encrypted-DNS fallback Apple сохраняет
приоритет системного encrypted DNS пользователя. Поэтому обходить его через
подмену HTTPS hostname или отключение trust evaluation запрещено. iOS сохраняет
системную сетевую политику; категории `dns/tls/timeout/connect/network` ошибок
согласованы с Android и существующим общим экраном входа. Версии обеих оболочек —
5.14/64; iOS compile/XCTest остаются обязательным gate Android-релиза.

Основание ограничения: [Apple: requireEncryptedNameResolution](https://developer.apple.com/documentation/network/nwparameters/privacycontext/requireencryptednameresolution(_:fallbackresolver:))
и [WWDC20: Enable encrypted DNS](https://developer.apple.com/videos/play/wwdc2020/10047/).
