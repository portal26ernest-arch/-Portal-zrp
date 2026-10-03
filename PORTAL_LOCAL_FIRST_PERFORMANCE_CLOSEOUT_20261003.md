[Reading 90 lines from start (total: 90 lines, 0 remaining)]

# PORTAL local-first / performance closeout — 2026-10-03

## Scope and baseline

Baseline source is `main@63ad6637af95cdd9cb9c82b2ff172b08f1f1a962` (PORTAL 4.7 performance line).
Read-only production verification on 2026-10-03 confirmed:
- `portal-production.service` active;
- `/api/ping` reports `PORTAL Server · 4.7.0` and PostgreSQL;
- `/api/ready` returns `ready=true`;
- runtime source is release `63ad6637-portal47`;
- `PORTAL_PG_POOL_SIZE` is unset in the service environment, so production uses the configured PostgreSQL default of 8 connections (`portal_config.py`: default 8 for production+PostgreSQL).

No production data, configuration, secrets or service state were changed by this closeout verification.

## Closed implementation tails

### 1. PostgreSQL connection pool
The bounded pool introduced in 4.7 remains the runtime path for production PostgreSQL. It performs rollback/health validation and rebinds the company tenant context on every borrow. Adapter tests verify raw-connection reuse and tenant rebinding.

### 2. SQL-side filtering
The repository now provides:
- `list_by(...)` for equality filters;
- `list_range(...)` for half-open JSON text/date ranges;
- `list_recent(...)` for bounded newest-first reads.

Hot paths were moved away from whole-ledger reads where a bounded predicate exists: tariff versions, products, batch/task linkage, task work rows, user timers, payroll work ranges, payroll period lookups, invoice revisions/payments, request attachments/events, batch returns and recent notifications. Aggregate screens that genuinely need a company-wide snapshot still preload once and reuse it instead of doing N+1 reads.

### 3. Targeted cache invalidation
Android, Desktop/Web and iOS invalidate only cache keys affected by a successful mutation. Whole-company cache clearing is not used for normal working mutations.

### 4. Durable local working outbox
The encrypted durable outbox is expanded from only `/api/v3/work` to the safe idempotent production surface:
- `/api/v3/work`
- `/api/v3/links`
- `/api/v3/batches`
- `/api/v3/tasks`
- `/api/v3/shipments`
- `/api/v3/returns`

The same allowlist is enforced by shared JS, Android native bridge, Desktop/Web bridge and iOS bridge. Each mutation carries the same `request_id` on retry and relies on the existing server idempotency ledger.

Deliberately NOT queued offline: timers, invoices, payments, payroll, permissions, settings and tariffs. Timers have ordered/session dependencies; finance/admin mutations remain server-confirmed to avoid ambiguous money/rights conflicts.

Queue resilience was also corrected: a network failure stops replay until connectivity returns, while a server rejection for one retained local row no longer blocks later valid queue rows. The settings screen exposes pending count and sync errors.

## Performance evidence

### Tariffs screen request fan-out
The pre-optimization company #1 baseline had 78 operations and opened Tariffs with approximately 79 GET requests (1 catalog + 78 per-operation tariff-history calls).

The optimized contract is 2 GET requests (catalog + one bulk tariff-history request).

Reduction: 77 requests, about 97.5%.

This is enforced by the UI/server regression contract and is independent of network conditions.

### Live transport measurement
Eight real HTTPS `/api/ping` samples from the authorized Windows workstation to the current production sslip endpoint returned HTTP 200:
`1.444844, 1.329532, 1.447902, 1.325085, 1.337213, 1.397351, 1.309975, 1.404523 s`.

Mean: ~1.375 s. Median: ~1.367 s. Range: ~1.310–1.448 s.

These live values are materially slower than the earlier ~0.26–0.29 s warm transport observation, showing that WAN latency varies enough that a local-first cache is required rather than relying on a permanently fast VPS round-trip.

An exact historical wall-clock screen-opening time cannot be reconstructed under identical production network conditions without redeploying the old client/server path. The closeout therefore uses the reproducible I/O contract (79 → 2 requests), live current transport measurements, and stale-while-revalidate cache behavior as the acceptance evidence instead of inventing a non-comparable “before” time.

## Verification evidence

Local closeout checks:
- `server/test_portal_postgres.py`: 13/13 OK, including pool reuse/tenant rebind and SQL range/recent pushdown;
- `server/test_production.py`: 59/59 OK;
- targeted Node/native/Desktop cache tests: 7/7 OK;
- Android build-security + Desktop version/update tests: OK;
- Android/iOS parity: OK;
- `python -m compileall -q server`: OK;
- `node --check` shared assets: OK;
- `git diff --check`: OK.

Code-only candidate commit: `806cb93f78d2512d951ce13837004c68ca8e4bf8`.
GitHub CI on that commit: Server isolation, Web/PostgreSQL, Android UI, Android APK and Windows Desktop succeeded; master-control failed only because the required roadmap closeout entry was intentionally not yet present. The version/roadmap commit is the authoritative final CI gate.

## Release candidate

Next monotonic closeout versions:
- Android 4.8 / versionCode 48
- iOS 4.8 / build 48
- Server 4.8.0
- Desktop 5.6.0 / build 56

Publishing/deploying production remains a separate release operation. This closeout does not authorize or perform a production write/cutover beyond the read-only verification above.

[executed on device: Ernest-com (4fb1e780-e0f4-44fd-94a6-f543d0851c48)]