# PORTAL iOS — App Privacy answers

Эти ответы должны совпадать с PrivacyInfo.xcprivacy и фактическим поведением приложения.

## Tracking

- Tracking: No
- Data used for third-party advertising: No
- Data used for developer advertising/marketing: No
- Advertising identifier: Not used

## Data linked to the user

PORTAL обрабатывает следующие категории для App Functionality:

- Name — имя/отображаемое имя сотрудника.
- User ID — логин, внутренний ID аккаунта/сотрудника.
- Other Financial Info — зарплата, начисления и иные доступные пользователю финансовые рабочие данные.
- Other User Content — рабочие сообщения, вложения, документы и введённые пользователем рабочие данные.
- Product Interaction — входы, рабочая активность и действия в системе, используемые для функций, безопасности и аудита.

Для каждой категории:
- Linked to User: Yes.
- Used for Tracking: No.
- Purpose: App Functionality.

## Required-reason APIs

PORTAL iOS использует UserDefaults только для настроек приложения
(например, сохранённого адреса сервера). Privacy manifest декларирует:

- NSPrivacyAccessedAPICategoryUserDefaults
- reason CA92.1

## Export compliance

PORTAL использует системный HTTPS/URLSession и не реализует собственную
неэкспортируемую криптографию. Info.plist содержит
ITSAppUsesNonExemptEncryption = NO.

Если в будущем появится собственная криптография или сторонний SDK,
эти ответы и PrivacyInfo.xcprivacy нужно пересмотреть до следующей публикации.
