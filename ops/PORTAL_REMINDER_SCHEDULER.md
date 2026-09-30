# PORTAL internal reminder operator job

`server/reminder_operator.py` is a PostgreSQL-only, trusted operator entry point. It enumerates company IDs from the control registry, checks each company's active service/demo state, opens a company-bound repository, and runs only when that company has explicitly set `reminder_enabled=true`. Missing settings and the normal `false` default are skipped without creating periodic run rows. Candidate failures and tenant failures are reported as counts only; exception text, customer values, and credentials are never printed.

The job writes only idempotent internal attention-feed notifications. It does not send Telegram, email, push, or other external messages. The systemd service and hourly timer in `ops/systemd/*.example` are examples only: repository installation does not install or enable them. A deployment operator must explicitly review and install both files; production dispatch remains off until a company opts in through its own settings. Secrets and PostgreSQL connection values belong only in the protected `/etc/portal/portal.env` environment file.

Run a safe local syntax/test check with `python -m unittest test_reminder_operator -v` from `server/`. Run the PostgreSQL traversal test only through the disposable Web PostgreSQL fixture. Never point this operator at a production database as a test.
