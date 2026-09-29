# PORTAL minor-unit reconciliation

legacy_money_reconcile.py is a read-only release/cutover helper for roadmap item 105.

It opens an SQLite backup copy with mode=ro, inspects only an explicit allowlist of monetary fields, and checks whether every legacy value is exactly representable in integer kopecks. Quantity, weight, stock and other non-money numerics are excluded on purpose.

During an additive migration, a dual-read pair can be checked with --pair work_log.salary=salary_minor. The report exposes counts and fingerprints, not business totals or row values.

The tool does not create minor-unit columns, perform updates, run production migration, or approve cutover. Schema changes remain separately reviewed and must be rehearsed on disposable PostgreSQL.
