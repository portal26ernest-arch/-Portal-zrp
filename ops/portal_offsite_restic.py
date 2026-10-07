#!/usr/bin/env python3
"""Fail-closed encrypted off-site backup and disposable restore verification."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile
try:
    import fcntl
except ImportError:  # Windows static/unit-test hosts; production systemd uses flock.
    fcntl = None
    import msvcrt
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SOURCE = Path("/srv/portal/central/backups")
MARKER = "central-backup-success.json"
HOST = "portal-central"
TAG = "portal-central"
EXIT_CONFIG = 20
EXIT_STALE = 21
EXIT_VERIFY = 22
EXIT_LOCKED = 23

def log(message: str) -> None:
    print(f"portal-offsite: {message}", file=sys.stderr, flush=True)

def run(args: list[str], *, capture=False) -> str:
    try:
        p = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE)
    except FileNotFoundError:
        log("required executable is unavailable")
        raise SystemExit(EXIT_CONFIG)
    except subprocess.CalledProcessError as e:
        # Never echo child output: provider tools can include repository/config details.
        log(f"command failed ({Path(args[0]).name}, exit {e.returncode})")
        raise SystemExit(EXIT_VERIFY)
    return p.stdout if capture else ""

def require_configuration() -> None:
    repo=os.environ.get("RESTIC_REPOSITORY", "")
    password=os.environ.get("RESTIC_PASSWORD_FILE", "")
    keys=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
    if not repo.startswith("s3:https://") or not re.fullmatch(r"s3:https://[^\s@]+/.+", repo):
        log("RESTIC_REPOSITORY must be an explicit HTTPS S3 repository")
        raise SystemExit(EXIT_CONFIG)
    if not password or not Path(password).is_file() or not os.access(password, os.R_OK) or Path(password).stat().st_size == 0:
        log("RESTIC_PASSWORD_FILE must name a readable non-empty file")
        raise SystemExit(EXIT_CONFIG)
    if any(not os.environ.get(k) for k in keys):
        log("AWS credential environment is incomplete")
        raise SystemExit(EXIT_CONFIG)
    if not os.environ.get("AWS_DEFAULT_REGION"):
        log("AWS_DEFAULT_REGION is required")
        raise SystemExit(EXIT_CONFIG)

def verified_inventory(max_age_hours: int) -> tuple[dict, list[Path]]:
    marker=SOURCE / MARKER
    try:
        data=json.loads(marker.read_text(encoding="utf-8"))
        completed=datetime.strptime(data["completed_at_utc"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        log("local central backup success marker is absent or invalid")
        raise SystemExit(EXIT_STALE)
    age=(datetime.now(timezone.utc)-completed).total_seconds()
    if age < -300 or age > max_age_hours*3600 or marker.stat().st_mtime < completed.timestamp()-300:
        log("local central backup is stale or has an invalid completion time")
        raise SystemExit(EXIT_STALE)
    entries=data.get("files")
    if data.get("schema") != 1 or not isinstance(entries,list) or not entries:
        log("local central backup inventory is invalid")
        raise SystemExit(EXIT_VERIFY)
    paths=[]; by_rel={}; found_control=False; found_tenant=False; found_storage=False
    for item in entries:
        rel=item.get("path") if isinstance(item,dict) else None
        if not isinstance(rel,str) or PurePosixPath(rel).is_absolute() or ".." in PurePosixPath(rel).parts:
            log("local inventory contains unsafe path")
            raise SystemExit(EXIT_VERIFY)
        path=(SOURCE / rel).resolve()
        if not path.is_relative_to(SOURCE.resolve()) or not path.is_file():
            log("a file from the local central backup inventory is missing")
            raise SystemExit(EXIT_VERIFY)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item.get("sha256") or path.stat().st_size != item.get("size"):
            log("local central backup file failed SHA/size validation")
            raise SystemExit(EXIT_VERIFY)
        if path.name.endswith(".dump"):
            run(["pg_restore", "--list", str(path)])
            found_control |= path.name.startswith("portal_prod_control-")
            found_tenant |= path.name.startswith("portal_prod_company_1-")
        if path.name.endswith(".tar.gz"):
            run(["tar", "-tzf", str(path)])
            found_storage |= path.name.startswith("central-storage-")
        paths.append(path); by_rel[rel]=path
    for rel,path in by_rel.items():
        if path.name.endswith(".sha256"):
            try: fields=path.read_text(encoding="ascii").strip().split()
            except (OSError, UnicodeError): fields=[]
            target_name=path.name[:-7]
            target=by_rel.get(str(PurePosixPath(rel).with_name(target_name)))
            if target is None or len(fields)<2 or fields[0]!=hashlib.sha256(target.read_bytes()).hexdigest() or Path(fields[-1]).name!=target.name:
                log("local central backup checksum sidecar is invalid")
                raise SystemExit(EXIT_VERIFY)
    if not (found_control and found_tenant and found_storage):
        log("inventory must include verified control DB, production tenant DB, and central storage")
        raise SystemExit(EXIT_VERIFY)
    return data, paths

def staged_payload(max_age_hours: int):
    data, files=verified_inventory(max_age_hours)
    td=tempfile.TemporaryDirectory(prefix="portal-offsite-stage-")
    root=Path(td.name)
    for src in files:
        dest=root/src.relative_to(SOURCE)
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dest)
    (root/MARKER).write_text(json.dumps(data,sort_keys=True)+"\n",encoding="utf-8")
    return td,root

def bootstrap(args) -> int:
    require_configuration()
    run(["restic", "snapshots"],capture=True)  # prove repository connectivity; never init implicitly
    log("repository is reachable and initialized")
    return 0

def backup(args) -> int:
    require_configuration()
    td,root=staged_payload(args.max_age_hours)
    try:
        run(["restic","backup","--host",HOST,"--tag",TAG,"--tag","central","--one-file-system",str(root)])
        run(["restic","forget","--host",HOST,"--tag",TAG,"--keep-daily","14","--keep-weekly","8","--keep-monthly","12","--prune"])
        run(["restic","check","--read-data-subset=5%"])
    finally:
        td.cleanup()
    log("encrypted backup, retention, and repository check completed")
    return 0

def restore_test(args) -> int:
    require_configuration()
    # TemporaryDirectory is disposable; this command has no production destination option.
    with tempfile.TemporaryDirectory(prefix="portal-restore-test-") as td:
        target=Path(td)/"restored"
        run(["restic","restore","latest","--host",HOST,"--tag",TAG,"--target",str(target)])
        restored=target
        candidates=list(restored.rglob(MARKER))
        if len(candidates)!=1:
            log("restore test did not yield exactly one inventory")
            return EXIT_VERIFY
        data=json.loads(candidates[0].read_text(encoding="utf-8"))
        base=candidates[0].parent
        for item in data.get("files",[]):
            rel=PurePosixPath(item["path"])
            path=base.joinpath(*rel.parts)
            if not path.is_file() or path.stat().st_size!=item["size"] or hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
                log("restored file failed inventory/SHA validation")
                return EXIT_VERIFY
            if path.name.endswith(".dump"): run(["pg_restore","--list",str(path)])
            if path.name.endswith(".tar.gz"): run(["tar","-tzf",str(path)])
    log("disposable restore test passed SHA, inventory, dump, and archive checks")
    return 0

def initialize(args) -> int:
    require_configuration()
    if not args.init:
        log("repository initialization requires explicit --init")
        return EXIT_CONFIG
    # init is opt-in; bucket provisioning is never attempted.
    run(["restic","init"])
    log("repository initialized; no bucket was created")
    return 0

def main() -> int:
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    for name,func in (("preflight",bootstrap),("init",initialize),("backup",backup),("restore-test",restore_test)):
        q=sub.add_parser(name); q.set_defaults(func=func)
        if name in ("backup",): q.add_argument("--max-age-hours",type=int,default=30)
        if name=="init": q.add_argument("--init",action="store_true")
    args=p.parse_args()
    try:
        lock_path=Path("/var/lib/portal-offsite/operation.lock")
        lock_path.parent.mkdir(parents=True,exist_ok=True)
        lock=lock_path.open("a")
        try:
            if fcntl is not None:
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            else:
                lock.seek(0); lock.write("0"); lock.flush(); lock.seek(0)
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except (BlockingIOError, OSError):
            log("another off-site operation is already running")
            return EXIT_LOCKED
        return args.func(args)
    except SystemExit: raise
    except Exception:
        log("operation failed safely; details withheld to avoid leaking configuration")
        return EXIT_VERIFY
if __name__=="__main__": raise SystemExit(main())
