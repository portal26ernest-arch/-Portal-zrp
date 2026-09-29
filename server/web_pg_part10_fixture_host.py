"""External-browser Part 10 fixture for invoice revisions and role scopes.

Creates only disposable portal_test_web_* PostgreSQL resources by reusing the
Part 8 fixture. Production services/databases are never used.
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
    if not str(path).startswith("/tmp/portal-web-part10-"):
        raise SystemExit("unsafe fixture coordination path")

import test_documents_postgresql as fixture

cls = fixture.DocumentsPostgreSQLTest
case = cls(methodName="test_catalog_rls_grants_and_database_reference_guards")
started = False
owner_username = "owner_" + secrets.token_hex(4)
owner_pin = "Owner-" + secrets.token_urlsafe(18)
try:
    cls.setUpClass()
    started = True
    with cls.portal.tenants.company_scope(1):
        director_id = cls.portal.save_user({
            "username": "director", "display_name": "Synthetic director",
            "role": "director", "pin": cls.synthetic_pin})
        manager_id = cls.portal.save_user({
            "username": "manager", "display_name": "Synthetic manager",
            "role": "manager", "pin": cls.synthetic_pin})
        with cls.portal.db() as conn:
            manager = conn.execute(
                "SELECT telegram_id FROM app_users WHERE id=?", (manager_id,)).fetchone()
            conn.execute(
                "INSERT INTO manager_client_assignments"
                "(telegram_id,client_id,active,company_id) VALUES(?,1,1,1)",
                (manager["telegram_id"],))
            conn.execute(
                "INSERT INTO portal_company_requisites"
                "(company_id,id,legal_name,inn,kpp,ogrn,legal_address,"
                "settlement_account,bank_name,bik,correspondent_account,updated_at)"
                " VALUES(1,1,?,?,?,?,?,?,?,?,?,?)",
                ("Synthetic PORTAL LLC","7700000000","770001001","1000000000000",
                 "Synthetic address","40702810000000000001","Synthetic Bank",
                 "044525000","30101810000000000002","2026-09-29"))
            conn.execute(
                "INSERT INTO portal_client_requisites"
                "(company_id,client_id,legal_name,inn,kpp,ogrn,legal_address,"
                "settlement_account,bank_name,bik,correspondent_account,updated_at)"
                " VALUES(1,1,?,?,?,?,?,?,?,?,?,?)",
                ("Synthetic Client LLC","7700000001","770001002","1000000000001",
                 "Synthetic client address","40702810000000000003","Client Bank",
                 "044525001","30101810000000000004","2026-09-29"))
            conn.commit()

    owner_id = cls.portal.create_platform_owner(
        owner_username, owner_pin, "Synthetic Platform Owner")
    work = case.post("work", {
        "client_id": 1, "operation_id": 1, "quantity": 2}, cls.tokens[1])["data"]
    invoice = case.post("invoices", {
        "work_ids": [work["id"]]}, cls.tokens[1])["data"]

    ready = {
        "port": cls.http.server_address[1],
        "company_a": 1, "company_b": 2,
        "pin": cls.synthetic_pin,
        "director_username": "director",
        "manager_username": "manager",
        "packer_username": "packer",
        "owner_username": owner_username,
        "owner_pin": owner_pin,
        "owner_id": owner_id,
        "invoice_id": invoice["id"],
        "invoice_revision": invoice.get("revision", 1),
        "database_prefix": "portal_test_web_",
        "role_prefix": "portal_web_",
    }
    READY.write_text(json.dumps(ready, ensure_ascii=False), encoding="utf-8")
    os.chmod(READY, 0o600)

    deadline = time.time() + 360
    while time.time() < deadline and not STOP.exists():
        time.sleep(0.25)
    if not STOP.exists():
        raise TimeoutError("external browser did not signal completion")

    invoice_after = next(
        row for row in case.get("invoices", cls.tokens[1])["data"]
        if str(row["id"]) == str(invoice["id"]))
    company_b_invoices = case.get("invoices", cls.tokens[2])["data"]
    document_data = case.get(
        "documents?status=all&include_archived=true", cls.tokens[1])["data"]
    documents = document_data.get("items", []) if isinstance(document_data, dict) else document_data
    invoice_xlsx = [
        row for row in documents
        if row.get("document_type") == "invoice_xlsx"
        and str(row.get("invoice_id")) == str(invoice["id"])
    ]
    with cls.portal.tenants.control(cls.portal.DB_PATH) as control:
        owner_audit = control.execute(
            "SELECT COUNT(*) FROM platform_audit WHERE actor_id=?",
            (owner_id,)).fetchone()[0]

    verified = (
        invoice_after.get("state") == "finalized"
        and int(invoice_after.get("revision", 0)) == 2
        and len(company_b_invoices) == 0
        and len(invoice_xlsx) >= 1
        and int(owner_audit) >= 1
    )
    RESULT.write_text(json.dumps({
        "browser_stop_received": True,
        "invoice_state": invoice_after.get("state"),
        "invoice_revision": invoice_after.get("revision"),
        "invoice_xlsx_documents": len(invoice_xlsx),
        "company_b_invoice_count": len(company_b_invoices),
        "owner_audit_rows": int(owner_audit),
        "fixture_verified": verified,
    }), encoding="utf-8")
    os.chmod(RESULT, 0o600)
    if not verified:
        raise RuntimeError("Part 10 fixture postconditions failed")
finally:
    if started:
        cls.cleanup()
    clean = RESULT.with_suffix(".clean.json")
    clean.write_text(json.dumps({"cleanup_complete": True}), encoding="utf-8")
    os.chmod(clean, 0o600)
