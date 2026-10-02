#!/usr/bin/env python3
"""Verify a PORTAL backup bundle and export it to an off-server target.

Supported transports:
- filesystem: mounted/network/off-server path, copied atomically and verified locally.
- rclone: any configured rclone remote. Credentials stay in protected rclone config.

This tool never accepts passwords, tokens, access keys or secret URLs.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

SECRETISH=re.compile(r"(password=|token=|secret=|access_key=|://[^/@\s]+:[^/@\s]+@)",re.I)

def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def load_bundle(manifest_path: Path):
    data=json.loads(manifest_path.read_text(encoding="utf-8"))
    filename=data.get("file")
    expected=data.get("sha256")
    if not isinstance(filename,str) or Path(filename).name!=filename:
        raise ValueError("manifest contains unsafe backup filename")
    if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{64}",expected):
        raise ValueError("manifest contains invalid sha256")
    backup=manifest_path.parent/filename
    if not backup.is_file():
        raise FileNotFoundError("backup file from manifest is missing")
    actual=sha256_file(backup)
    if actual!=expected:
        raise ValueError("backup sha256 mismatch")
    checksum=manifest_path.parent/(manifest_path.stem+".sha256")
    if not checksum.is_file():
        raise FileNotFoundError("checksum sidecar is missing")
    first=checksum.read_text(encoding="utf-8").strip().split()
    if len(first)<2 or first[0]!=expected or Path(first[-1]).name!=filename:
        raise ValueError("checksum sidecar does not match manifest")
    return data,backup,checksum

def validate_target(target: str):
    if not isinstance(target,str) or not target.strip() or target!=target.strip():
        raise ValueError("target is required")
    if SECRETISH.search(target):
        raise ValueError("credentials/secrets must not be embedded in target")
    return target

def filesystem_export(manifest: Path,target: Path):
    data,backup,checksum=load_bundle(manifest)
    target=target.expanduser().resolve()
    target.mkdir(parents=True,exist_ok=True)
    copied=[]
    for src in (backup,manifest,checksum):
        with tempfile.NamedTemporaryFile(prefix=src.name+".",suffix=".tmp",dir=target,delete=False) as tmp:
            tmp_path=Path(tmp.name)
        try:
            shutil.copy2(src,tmp_path)
            final=target/src.name
            tmp_path.replace(final)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        if sha256_file(final)!=sha256_file(src):
            raise ValueError("offsite filesystem verification failed: "+src.name)
        copied.append(final.name)
    return {"transport":"filesystem","target":str(target),"files":copied,"backup_sha256":data["sha256"],"verified":True}

def rclone_export(manifest: Path,target: str,rclone="rclone"):
    data,backup,checksum=load_bundle(manifest)
    target=validate_target(target).rstrip("/")
    files=(backup,manifest,checksum)
    for src in files:
        subprocess.run([rclone,"copyto",str(src),target+"/"+src.name,"--immutable"],check=True)
    # rclone check compares local source directory subset to remote destination.
    # Verify exact uploaded files with one-file check commands so unrelated remote files are ignored.
    for src in files:
        subprocess.run([rclone,"check",str(src),target+"/"+src.name,"--one-way"],check=True)
    return {"transport":"rclone","target":target,"files":[x.name for x in files],"backup_sha256":data["sha256"],"verified":True}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--transport",choices=("filesystem","rclone"),required=True)
    ap.add_argument("--target",required=True)
    ap.add_argument("--rclone",default="rclone")
    args=ap.parse_args()
    manifest=Path(args.manifest).expanduser().resolve()
    if args.transport=="filesystem":
        result=filesystem_export(manifest,Path(validate_target(args.target)))
    else:
        result=rclone_export(manifest,args.target,args.rclone)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
