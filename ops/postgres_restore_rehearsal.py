#!/usr/bin/env python3
"""Restore a PORTAL PostgreSQL dump into a disposable test database only.

Hard guard: target DB name must start with portal_test_restore_.
The database is always dropped in finally unless --keep-for-debug is used.
No production database name can be supplied directly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import subprocess


PREFIX = "portal_test_restore_"


def run(argv: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=True, text=True, capture_output=capture)


def safe_db_name(name: str) -> str:
    if not name.startswith(PREFIX):
        raise ValueError(f"restore rehearsal DB must start with {PREFIX}")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    if any(c not in allowed for c in name):
        raise ValueError("unsafe database name")
    return name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--createdb", default="createdb")
    ap.add_argument("--dropdb", default="dropdb")
    ap.add_argument("--pg-restore", default="pg_restore")
    ap.add_argument("--psql", default="psql")
    ap.add_argument("--validation-sql", help="Optional read-only SQL file run after restore")
    ap.add_argument("--keep-for-debug", action="store_true")
    args = ap.parse_args()

    dump = Path(args.dump).expanduser().resolve()
    if dump.suffix == ".age":
        raise SystemExit("decrypt encrypted backup to a protected temporary path before rehearsal")
    if not dump.is_file():
        raise SystemExit("dump not found")

    db = safe_db_name(PREFIX + secrets.token_hex(6))
    created = False
    validation_output = ""
    try:
        run([args.createdb, db])
        created = True
        run([args.pg_restore, "--exit-on-error", "--no-owner", "--no-acl", "--dbname", db, str(dump)])
        if args.validation_sql:
            sql = Path(args.validation_sql).expanduser().resolve()
            if not sql.is_file():
                raise SystemExit("validation SQL not found")
            cp = run([args.psql, "--set", "ON_ERROR_STOP=1", "--dbname", db, "--file", str(sql)], capture=True)
            validation_output = cp.stdout[-4000:]
        print(json.dumps({
            "database": db,
            "restored": True,
            "validation_ran": bool(args.validation_sql),
            "validation_output_tail": validation_output,
            "cleanup_planned": not args.keep_for_debug,
        }, ensure_ascii=False))
        return 0
    finally:
        if created and not args.keep_for_debug:
            run([args.dropdb, "--if-exists", db])


if __name__ == "__main__":
    raise SystemExit(main())
