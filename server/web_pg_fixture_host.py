"""External-browser host for the disposable Part 8 PostgreSQL fixture.

This is test-only. It creates only portal_test_web_* resources through the
existing fixture, exposes the loopback HTTP port via a mode-0600 ready file,
waits for a stop file, verifies the synthetic Excel mutation, then always
cleans up the disposable database/roles/temp blobs.
"""
import json
import os
import secrets
import time
from pathlib import Path

if os.environ.get("PORTAL_WEB_PG_E2E") != "1":
    raise SystemExit("PORTAL_WEB_PG_E2E=1 is required")

READY = Path(os.environ["PORTAL_WEB_PG_READY_FILE"])
STOP = Path(os.environ["PORTAL_WEB_PG_STOP_FILE"])
RESULT = Path(os.environ["PORTAL_WEB_PG_RESULT_FILE"])
for path in (READY, STOP, RESULT):
    if not str(path).startswith("/tmp/portal-web-part8-"):
        raise SystemExit("unsafe fixture coordination path")

import test_documents_postgresql as fixture

cls = fixture.DocumentsPostgreSQLTest
case = cls(methodName="test_catalog_rls_grants_and_database_reference_guards")
started = False
client_name = "Web E2E " + secrets.token_hex(6)
try:
    cls.setUpClass()
    started = True
    doc = case.upload(cls.tokens[1])
    listed = case.get("documents", cls.tokens[1])["data"]
    if doc["id"] not in [row["id"] for row in listed]:
        raise RuntimeError("fixture document is not visible through real Documents API")
    from excel_template import workbook
    payload = workbook({"Клиенты": [dict(client_ref="web-e2e", name=client_name, active=1)]})
    xlsx = Path(cls.tmp.name) / "PORTAL_web_e2e.xlsx"
    xlsx.write_bytes(payload)
    ready = {
        "port": cls.http.server_address[1],
        "pin": cls.synthetic_pin,
        "company_a": 1,
        "company_b": 2,
        "document_id": doc["id"],
        "document_title": doc["title"],
        "document_visible_preflight": True,
        "xlsx_path": str(xlsx),
        "client_name": client_name,
        "database_prefix": "portal_test_web_",
        "role_prefix": "portal_web_",
    }
    READY.write_text(json.dumps(ready, ensure_ascii=False), encoding="utf-8")
    os.chmod(READY, 0o600)

    deadline = time.time() + 300
    while time.time() < deadline and not STOP.exists():
        time.sleep(0.25)
    if not STOP.exists():
        raise TimeoutError("external browser did not signal completion")

    with cls.portal.tenants.company_scope(1), cls.portal.db() as conn:
        count_a = conn.execute("SELECT COUNT(*) FROM portal_clients WHERE name=?", (client_name,)).fetchone()[0]
    with cls.portal.tenants.company_scope(2), cls.portal.db() as conn:
        count_b = conn.execute("SELECT COUNT(*) FROM portal_clients WHERE name=?", (client_name,)).fetchone()[0]
    RESULT.write_text(json.dumps({
        "browser_stop_received": True,
        "company_a_new_client": int(count_a),
        "company_b_new_client": int(count_b),
        "fixture_verified": count_a == 1 and count_b == 0,
    }), encoding="utf-8")
    os.chmod(RESULT, 0o600)
finally:
    if started:
        cls.cleanup()
    clean = RESULT.with_suffix(".clean.json")
    clean.write_text(json.dumps({"cleanup_complete": True}), encoding="utf-8")
    os.chmod(clean, 0o600)
