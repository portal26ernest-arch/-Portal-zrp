# PORTAL production cutover follow-up — 2026-10-02

## 1. Legacy account discrepancy resolved

Previous reconciliation treated `portal_production.app_users(company_id=1)=5`
versus `portal_prod_company_1.app_users=4` as an unresolved blocker.

Preserved phone/source snapshots contain exactly four operational Company 1 accounts:
- `Ernest` — admin
- `V.Belov` — admin
- `E.Miroshnichenko` — manager
- `N.Asafova` — manager

The old server candidate contained those operational identities plus
a separate legacy `admin` account.

The current split tenant contains the four operational accounts.
The control database contains the separate Platform Owner/God identity
and it must not be counted as a Company 1 tenant user.

Historic setup code defaulted the first bootstrap username to `admin`.

Conclusion: the 5→4 difference is not evidence of a lost employee/user record.
The extra old `admin` row is a legacy bootstrap/server account and must not
be blindly copied into the split tenant.

## 2. Live verification performed 2026-10-02

Live VPS checks confirmed:
- `portal-production.service`: active, enabled, NRestarts=0
- PostgreSQL: active
- `portal-central-backup.timer`: active and enabled
- control: 1 company, 1 Platform Owner, 1 company key
- tenant: 4 employees, 4 app users
- 39 clients, 78 operations, 403 tariff versions
- 8 work rows, 47 products
- 48 FORCE RLS tables
- materials, material movements, invoices, generated documents and Excel imports: 0
- old Company 1 business counts match the split tenant for core business entities
- central snapshot and supplement SHA-256 manifests verify successfully
- daily backup completed with `BACKUP_SUCCESS=1 RETENTION_DAYS=14`

## 3. Remaining cutover gates

The legacy `admin` discrepancy is no longer a data-loss blocker.
Final production cutover is still NOT approved until the remaining gates close.

Remaining gates:
1. Establish a fresh authoritative source/write-freeze checkpoint and prove lineage.
2. Sync the central VPS Git mirror to the current repository state.
3. Configure and verify an independent off-server backup copy.
4. Rotate Stage 7 DB roles out of production and use production-only roles.
5. Configure an owned production HTTPS hostname.
6. Build and verify the protected signed Android production release.
7. Perform final authenticated read/write smoke and post-restart checks.

Do not delete the old database, phone/source snapshots, or local recovery copies
before the final cutover declaration and off-server restore test.
