"""Bind an offline migration transaction to a company under protected RLS.

The caller must use a dedicated migration role with key-table privileges,
never the API tenant role.
The company key stays inside PostgreSQL and is never returned to Python.
"""

from migration_validation import ValidationError


def bind_company(target, company_id, *, provision=False):
    if type(company_id) is not int or company_id < 1:
        raise ValidationError('Invalid company_id for migration context')
    if provision:
        # Only the dedicated migration role may write portal_company_keys.
        # portal_provision_company also inserts version rows and therefore must
        # not be called while importing historical migration records.
        target.execute('''INSERT INTO portal_company_keys(company_id,secret)
            VALUES(%s,encode(gen_random_bytes(32),'hex'))
            ON CONFLICT(company_id) DO NOTHING''', (company_id,))
    row = target.execute('''SELECT portal_bind_company(%s,secret)
        FROM portal_company_keys WHERE company_id=%s''',
                         (company_id, company_id)).fetchone()
    if row is None:
        raise ValidationError('Protected company context is unavailable')
