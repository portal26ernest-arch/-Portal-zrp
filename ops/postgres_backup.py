#!/usr/bin/env python3
"""PORTAL PostgreSQL backup helper.

Creates a pg_dump custom-format backup, verifies it with pg_restore --list,
computes SHA-256, optionally encrypts with age using a recipient file, writes
a JSON manifest, and applies retention only after a successful backup.

Credentials are intentionally NOT accepted as CLI arguments. Use PostgreSQL
environment variables, PGSERVICE/PGPASSFILE, or another protected runtime
mechanism.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_checked(argv: list[str]) -> None:
    subprocess.run(argv, check=True)


def prune_old(directory: Path, prefix: str, retention_days: int, keep: set[Path]) -> list[str]:
    if retention_days < 1:
        raise ValueError("retention_days must be >= 1")
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retention_days)
    removed: list[str] = []
    for p in directory.glob(prefix + "*"):
        if p in keep or not p.is_file():
            continue
        try:
            mtime = dt.datetime.fromtimestamp(p.stat().st_mtime, tz=dt.timezone.utc)
        except OSError:
            continue
        if mtime < cutoff and (p.suffix in {".dump", ".age", ".json", ".sha256"} or ".dump." in p.name):
            p.unlink()
            removed.append(p.name)
    return removed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", required=True, help="Database name only; credentials come from protected PG env/service")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--prefix", default="portal-pg-")
    ap.add_argument("--retention-days", type=int, default=14)
    ap.add_argument("--age-recipient-file", help="Optional age recipient file containing public recipient(s)")
    ap.add_argument("--pg-dump", default="pg_dump")
    ap.add_argument("--pg-restore", default="pg_restore")
    ap.add_argument("--age", default="age")
    args = ap.parse_args()

    if any(x in args.database for x in ("://", "@", "password=", " ")):
        raise SystemExit("--database must be a plain DB name, not a credential-bearing DSN")
    if args.retention_days < 1:
        raise SystemExit("--retention-days must be >= 1")

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{args.prefix}{stamp}"
    final_dump = out_dir / f"{stem}.dump"
    manifest = out_dir / f"{stem}.json"
    checksum_file = out_dir / f"{stem}.sha256"

    with tempfile.TemporaryDirectory(prefix="portal-backup-", dir=str(out_dir)) as td:
        tmp_dump = Path(td) / "backup.dump"
        run_checked([args.pg_dump, "--format=custom", "--no-owner", "--no-acl",
                     "--file", str(tmp_dump), args.database])
        run_checked([args.pg_restore, "--list", str(tmp_dump)])

        tmp_hash = sha256_file(tmp_dump)
        encrypted = bool(args.age_recipient_file)

        if encrypted:
            recipient_file = Path(args.age_recipient_file).expanduser().resolve()
            if not recipient_file.is_file():
                raise SystemExit("age recipient file not found")
            encrypted_path = out_dir / f"{stem}.dump.age"
            run_checked([args.age, "-R", str(recipient_file), "-o", str(encrypted_path), str(tmp_dump)])
            final_path = encrypted_path
            final_hash = sha256_file(final_path)
        else:
            shutil.move(str(tmp_dump), str(final_dump))
            final_path = final_dump
            final_hash = tmp_hash

    checksum_file.write_text(f"{final_hash}  {final_path.name}\n", encoding="utf-8")
    data = {
        "schema_version": 1,
        "created_at_utc": stamp,
        "database": args.database,
        "file": final_path.name,
        "bytes": final_path.stat().st_size,
        "sha256": final_hash,
        "verified_pg_restore_list": True,
        "encrypted": encrypted,
        "plaintext_sha256_before_encryption": tmp_hash if encrypted else None,
        "retention_days": args.retention_days,
    }
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    keep = {final_path, manifest, checksum_file}
    removed = prune_old(out_dir, args.prefix, args.retention_days, keep)

    print(json.dumps({
        "backup": final_path.name,
        "manifest": manifest.name,
        "checksum": checksum_file.name,
        "sha256": final_hash,
        "verified": True,
        "encrypted": encrypted,
        "pruned": removed,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
