# Notification centers and Messenger v1

## Notification centers

`GET /api/v3/notification-centers` returns independent `TASKS`, `MESSENGER`, and `ORGANIZER` lists and unread counts. `POST /api/v3/notification-read` accepts `{center, item_id}`. A read receipt is keyed by the authenticated company, user, center, and item, so another account or tenant cannot change or inherit it. The TASKS center projects only work assigned to the signed-in user. ORGANIZER continues to use the existing task and reminder domain; scheduled reminders and their compatibility API are preserved.

The records use the existing company scoped `portal_production` ledger. Migration version 16 allows updates only to `notification_reads`; all Messenger account, conversation, and message rows remain append only. SQLite applies this trigger update during the opt in migration. PostgreSQL operators apply `server/migrations/postgresql_stage17_messenger_notifications.sql` before enabling these endpoints.

## Messenger v1

`GET /api/v3/messenger` lists the signed-in user's personal work accounts and conversations. `POST /api/v3/messenger` supports `create_account` for `telegram` or `max`, and `create_conversation` for an account owned by that user. Request fields are allowlisted; `token`, `password`, `client_secret`, session cookies, and arbitrary credential fields are rejected. The first slice stores account labels and provider metadata only. It does not send messages until an official provider adapter is configured.

`server/messenger_adapters.py` defines the provider boundary. Implementations may be injected only for official Telegram/MAX APIs using secrets managed outside this repository. The default adapter lookup returns no adapter, which keeps the feature visibly unconfigured and prevents fake credentials or unofficial browser/session automation.

Director and manager roles are denied at the server for Messenger regardless of UI visibility. Other users can access only accounts and conversations they own. A platform owner can break glass across the tenant; each Messenger list access creates a metadata-only `god_messenger_access` event in the immutable owner control audit (`platform_audit`). The code path does not append this event to tenant audit. The platform audit remains visible only through owner-only platform audit routes.

## Client behavior

Android and iOS use the shared mobile Web assets for three independent top bar counters and a notification screen. Messenger has a separate screen that records personal work account metadata and clearly reports the adapter state. Desktop launches one process-wide independent WPF Messenger window; it restores its last geometry and maximized state, supports normal minimize/restore, and hides on close so another click restores the same instance. Desktop passes the active authenticated session to that window through an in-process WebView bootstrap, not through a URL or log.

External provider credentials and provider CI/review gates remain deployment work. Until official adapters are configured, conversations are metadata shells and no provider messages are fabricated.
