# PORTAL iOS — App Store Connect metadata

Актуально для первой публикации через TestFlight → App Review → Unlisted App.

## Основные поля

- App name: PORTAL
- Subtitle: Работа, учёт и документы
- Primary language: Russian
- Primary category: Business
- Secondary category: Productivity
- Bundle ID: ru.portal.app.ios
- SKU: PORTAL-IOS
- Distribution method before Unlisted approval: Public
- Price: Free
- Age rating target: 4+ при отсутствии новых возрастных факторов
- Privacy Policy URL: https://<PUBLIC_ORIGIN>/web/privacy.html
- Support URL: https://<PUBLIC_ORIGIN>/web/support.html

Apple limits: app name ≤ 30 characters, subtitle ≤ 30 characters,
description ≤ 4000 characters, keywords ≤ 100 bytes.

## Description

PORTAL — рабочая информационная система для сотрудников и руководителей компаний.

Приложение объединяет ежедневную работу в одном защищённом пространстве: производственные задания, выработку, склад расходных материалов, документы, счета, внутренние запросы и доступные пользователю показатели.

Набор разделов и действий зависит от роли и прав пользователя в его компании. Данные синхронизируются с сервером PORTAL; приложение не хранит отдельную мастер-базу компании на iPhone.

Основные возможности:
• вход в рабочий кабинет компании;
• задания и фиксация выполненной работы;
• просмотр собственной выработки и доступных расчётов;
• складские операции в пределах выданных прав;
• документы и счета;
• внутренние рабочие модули и уведомления;
• безопасное разграничение доступа по компаниям и ролям.

PORTAL предназначен для авторизованных пользователей подключённых компаний.

## Keywords

учет,склад,зарплата,документы

## App Review notes

PORTAL is intended for Unlisted App distribution to employees and authorized users of connected companies.
There is no public self-registration. Access is issued by the company administrator/director.
The app uses the PORTAL server over HTTPS and does not use advertising tracking.
Provide the dedicated App Review username/PIN in the App Review credentials fields before submission.
In Review Notes state explicitly that the app is intended for Unlisted App distribution.

## Screenshots

Готовый набор для iPhone 6.9" (portrait, ru-RU):
- 01-login.jpg — вход в PORTAL;
- 02-dashboard.jpg — рабочая главная/показатели;
- 03-sections.jpg — доступные разделы;
- 04-documents.jpg — документы.

Все файлы: 1290×2796, JPEG/RGB без alpha.
Они генерируются из того же shared UI с демонстрационными данными
командой: node ios_src/tools/generate_app_store_screenshots.cjs

Реальные production-данные и персональные сведения в screenshots не используются.
Перед финальным App Review повторно визуально проверить screenshots против текущего release UI.
