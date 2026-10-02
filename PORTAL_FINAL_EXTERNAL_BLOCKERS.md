# PORTAL final external and manual gates

Scope: gates that require real devices, owners, providers, production resources, or a separate integration. There are no remaining software-completable items in the Part 12 closeout scope. Roadmap **93 ✅ / 15 🟡 / 6 ⏳ / 12 🔌**; see `PORTAL_FINAL_PROJECT_CLOSEOUT_REPORT.md`.

| Class | Item(s) | External evidence/action required |
|---|---|---|
| B | 59, 61, 63, 86 | Physical Android smoke for native save/chooser, email intent, Excel/WebView flow, and shared UI parity using the final CI APK. |
| B | 60 | Share behavior in the target supported browser. |
| B/C | 85 | Ordinary install/update validation on a supported Windows PC with WebView2 Evergreen Runtime; for distribution, owner/provider must also supply trusted publication and any required signing identity. |
| C | 46 | Supply a canonical QC/defect source before exposing a quality metric. Until then quality remains unavailable. |
| C | 47 | Configure and verify a trusted production system timer and owner-authorized activation. Reminder dispatch stays disabled absent deployment evidence. |
| C | 77–79 | Provide an official public marketplace feed/API and authorized production activation. No scraping or invented provider data. |
| C | 80, 83 | Owner-authorized Android production cutover and protected signing secrets/manual release approval. |
| C | 93 | Select/configure an independent off-server backup target and perform an isolated restore rehearsal. |
| C | 105 | Separately authorize importing the verified SQLite copy into a disposable PostgreSQL target and complete post-import read-only reconciliation. Production rows remain untouched. |
| C | 94–99, 125 | Supply owned domain, DNS/network path and certificate; authorize final import, controlled cutover and rollback rehearsal. Temporary HTTPS tunnel is not a production domain. |
| D | 106–117 | TalAnt/WMS/ТСД remains a separate official-API integration. Requires provider API documentation, authorized sandbox/credentials, agreed scope, and device evidence. No TalAnt database access or code modification. |

No production DB/VPS/DNS/secrets/signing/cutover action has been performed by this closeout. No external gate is marked green without its evidence.
