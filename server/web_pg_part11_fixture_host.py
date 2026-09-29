"""Disposable PostgreSQL fixture for Part 11 Web template downloads."""
import json
import os
import time
from pathlib import Path

if os.environ.get("PORTAL_WEB_PG_E2E") != "1":
    raise SystemExit("PORTAL_WEB_PG_E2E=1 is required")

READY = Path(os.environ["PORTAL_WEB_PG_READY_FILE"])
STOP = Path(os.environ["PORTAL_WEB_PG_STOP_FILE"])
RESULT = Path(os.environ["PORTAL_WEB_PG_RESULT_FILE"])
for path in (READY, STOP, RESULT):
    if not str(path).startswith("/tmp/portal-web-part11-"):
        raise SystemExit("unsafe fixture coordination path")

import test_documents_postgresql as fixture

cls = fixture.DocumentsPostgreSQLTest
started = False

def counts():
    with cls.portal.tenants.company_scope(1), cls.portal.db() as conn:
        return {
            "clients": conn.execute("SELECT COUNT(*) FROM portal_clients").fetchone()[0],
            "operations": conn.execute("SELECT COUNT(*) FROM portal_client_operations").fetchone()[0],
            "employees": conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0],
            "documents": conn.execute("SELECT COUNT(*) FROM portal_documents").fetchone()[0],
        }
try:
    cls.setUpClass()
    started = True
    with cls.portal.tenants.company_scope(1):
        cls.portal.save_user({
            "username": "director",
            "display_name": "Synthetic director",
            "role": "director",
            "pin": cls.synthetic_pin,
        })

    before = counts()
    ready = {
        "port": cls.http.server_address[1],
        "company_a": 1,
        "company_b": 2,
        "pin": cls.synthetic_pin,
        "director_username": "director",
        "database_prefix": "portal_test_web_",
        "role_prefix": "portal_web_",
    }
    READY.write_text(json.dumps(ready), encoding="utf-8")
    os.chmod(READY, 0o600)

    deadline = time.time() + 300
    while time.time() < deadline and not STOP.exists():
        time.sleep(0.25)
    if not STOP.exists():
        raise TimeoutError("external browser did not signal completion")

    after = counts()
    verified = before == after
    RESULT.write_text(json.dumps({
        "browser_stop_received": True,
        "before_counts": before,
        "after_counts": after,
        "fixture_verified": verified,
    }), encoding="utf-8")
    os.chmod(RESULT, 0o600)
    if not verified:
        raise RuntimeError("template downloads mutated database state")
finally:
    if started:
        cls.cleanup()
    clean = RESULT.with_suffix(".clean.json")
    clean.write_text(json.dumps({"cleanup_complete": True}), encoding="utf-8")
    os.chmod(clean, 0o600)
