#!/usr/bin/env python3
"""Build a read-only PORTAL cutover dry-run evidence file.

The collector intentionally inspects only repository artifacts and operator-
provided evidence JSON. It never connects to production or mutates services.
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def sha256_file(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def git(args):
    cp=subprocess.run(["git",*args],cwd=ROOT,check=True,text=True,capture_output=True)
    return cp.stdout.strip()

def tracked_clean():
    return git(["status","--porcelain"])==""

def migration_checksums():
    out={}
    for p in sorted((ROOT/"server"/"migrations").glob("*.sql")):
        out[p.name]=sha256_file(p)
    return out

def load_optional(path):
    if not path:return {}
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict):raise ValueError("operator evidence must be a JSON object")
    return data

def collect(operator):
    data={
        "schema_version":1,
        "git_sha":git(["rev-parse","HEAD"]),
        "git_branch":git(["branch","--show-current"]),
        "worktree_clean":tracked_clean(),
        "migration_checksums":migration_checksums(),
        "production_untouched":True,
        "collector_mode":"read_only_repository",
    }
    protected={"git_sha","git_branch","worktree_clean","migration_checksums","production_untouched","collector_mode","schema_version"}
    for k,v in operator.items():
        if k not in protected:
            data[k]=v
    return data

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--operator-evidence")
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    data=collect(load_optional(a.operator_evidence))
    Path(a.output).write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"output":a.output,"git_sha":data["git_sha"],"worktree_clean":data["worktree_clean"],"migrations":len(data["migration_checksums"]),"production_untouched":True},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
