# PORTAL production cutover runbook (prepared; not executed)

This is a controlled checklist. It is not authorization to mutate production. Require an explicit owner go/no-go before any production write, import, DNS switch, or client cutover.

## Preconditions

- Confirm the approved production hostname, DNS owner, firewall path, TLS certificate and HTTPS API URL.
- Confirm production DB/service identity and that a separate disposable `portal_test_*` rehearsal completed with zero leftover test databases and roles.
- Confirm protected GitHub production secrets are configured by an authorized owner. Never print or copy their values into logs, reports, APKs, or this repository.
- Confirm an off-server encrypted backup target, retention, checksum, and a successful restore verification.
- Approve a maintenance window, named operator, independent verifier, and rollback decision owner.
- Confirm the candidate commit, migration checksums, staging artifact checksums, security gates, and unresolved roadmap items.

## Preflight (read-only)

1. Record code SHA, schema/migration checksums, source and target versions, row counts, and financial totals by company/client/employee/work/payroll/invoice/material.
2. Verify runtime DB roles are non-superuser, lack `BYPASSRLS`, and RLS/FORCE RLS applies to the intended tenant tables.
3. Verify health and HTTPS certificate for the approved endpoint; verify the setup endpoint is closed and no debug service is exposed.
4. Verify a fresh source snapshot can be restored to an isolated database and reconciled before scheduling cutover.
5. Abort if any count, checksum, money total, tenant boundary, backup, or health check differs from the approved baseline.

## Owner-authorized cutover sequence

1. Announce and begin write freeze on the legacy source. Record freeze time and prevent further writes there.
2. Take a final immutable SQLite snapshot; checksum it and preserve the original read-only.
3. Run the import in dry-run mode against the approved target; reconcile counts and integer-cent totals independently.
4. Obtain explicit operator and independent-verifier sign-off on reconciliation output.
5. Apply only the approved additive migrations and final import to production. Do not drop legacy columns or rewrite historical financial facts.
6. Verify counts/checksums, representative document downloads, employee identity mapping, closed payroll snapshots, invoices/payments, and company isolation.
7. Switch the approved client endpoint only after verification. Smoke login and critical read/write journeys with authorized synthetic/controlled checks.
8. Keep legacy source frozen and recoverable through the agreed observation period. Never dual-write.

## Rollback

- Stop traffic/writes to the candidate immediately on failed health, authorization, tenant-isolation, reconciliation, or financial invariants.
- Restore the previous client endpoint/configuration only under the approved rollback decision; preserve logs and the failed candidate state for investigation.
- Restore DB state from the verified pre-cutover snapshot if writes occurred and the incident plan requires it. Do not improvise reverse financial updates.
- Reconcile restored counts/checksums and confirm tenant isolation before reopening writes.

## Post-cutover evidence

Record approvals, operators, timestamps, exact commits and migration checksums, source snapshot checksum, reconciliation outputs, smoke results, backup/restore evidence, and rollback decision. Store evidence in the approved protected operations location; do not put production data or secrets in Git.

**Current status:** no production freeze, import, migration, DNS change, service/config mutation, or cutover has been performed by Part 12.
