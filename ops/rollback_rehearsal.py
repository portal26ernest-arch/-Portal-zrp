#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path
from urllib.parse import urlparse

SHA256=re.compile(r"^[0-9a-f]{64}$")
REQUIRED_FLAGS=("backup_restore_rehearsed","restore_cleanup_verified","migration_dry_run","reconciliation","tenant_isolation","financial_invariants","production_untouched")
class RollbackEvidenceError(ValueError): pass

def truthy(v): return v is True or v=="pass" or v=="green"

def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def load_json(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict):raise RollbackEvidenceError("JSON root must be an object")
    return data

def verify_backup(manifest_path):
    p=Path(manifest_path).expanduser().resolve(strict=True);m=load_json(p)
    name=m.get("file");expected=m.get("sha256")
    if not isinstance(name,str) or Path(name).name!=name:raise RollbackEvidenceError("unsafe backup filename")
    if not isinstance(expected,str) or not SHA256.fullmatch(expected):raise RollbackEvidenceError("invalid backup sha256")
    backup=p.parent/name
    if not backup.is_file():raise RollbackEvidenceError("backup file missing")
    if sha256_file(backup)!=expected:raise RollbackEvidenceError("backup sha256 mismatch")
    if m.get("verified_pg_restore_list") is not True:raise RollbackEvidenceError("backup lacks pg_restore-list verification")
    sidecar=p.with_suffix(".sha256")
    if not sidecar.is_file():raise RollbackEvidenceError("backup checksum sidecar missing")
    parts=sidecar.read_text(encoding="utf-8").strip().split()
    if len(parts)<2 or parts[0]!=expected or Path(parts[-1]).name!=name:raise RollbackEvidenceError("backup checksum sidecar mismatch")
    return {"manifest":p.name,"file":name,"sha256":expected,"encrypted":bool(m.get("encrypted")),"verified_pg_restore_list":True,"bytes":backup.stat().st_size}

def validate_https(value):
    if value is None:return None
    if not isinstance(value,str) or value.strip()!=value:raise RollbackEvidenceError("endpoint must be a clean HTTPS URL")
    u=urlparse(value)
    if u.scheme.lower()!="https" or not u.hostname or u.username or u.password or u.query or u.fragment:raise RollbackEvidenceError("endpoint must be credential-free HTTPS")
    if u.port not in (None,443):raise RollbackEvidenceError("endpoint must use standard HTTPS port")
    return value.rstrip("/")

def build(manifest_path,evidence_path,previous_endpoint=None,candidate_endpoint=None):
    backup=verify_backup(manifest_path);e=load_json(evidence_path)
    previous=validate_https(previous_endpoint);candidate=validate_https(candidate_endpoint)
    if previous and candidate and previous==candidate:raise RollbackEvidenceError("previous and candidate endpoints must differ")
    blockers=["missing_or_failed:"+k for k in REQUIRED_FLAGS if not truthy(e.get(k))]
    if backup["encrypted"] and not truthy(e.get("backup_decryption_rehearsed")):blockers.append("missing_or_failed:backup_decryption_rehearsed")
    if e.get("production_untouched") is not True:blockers.append("production_must_remain_untouched_during_rehearsal")
    plan=[
      "Freeze candidate traffic and writes only after explicit owner rollback authorization.",
      "Preserve incident logs and failed candidate state before restoration.",
      "Use the verified pre-cutover backup through the guarded disposable restore path first.",
      "Reconcile tenant boundaries, financial invariants, counts and checksums before reopening writes.",
      "Restore the previous approved client endpoint only under the named rollback decision owner.",
      "Do not reverse financial history manually and do not dual-write."
    ]
    if not previous:plan.append("Previous production endpoint is not recorded; endpoint rollback remains an external owner gate.")
    if not candidate:plan.append("Candidate production endpoint is not recorded; endpoint cutover remains an external owner gate.")
    return {"schema_version":1,"mode":"read_only_rehearsal","production_mutation_performed":False,"backup":backup,
      "evidence_flags":{k:truthy(e.get(k)) for k in REQUIRED_FLAGS},
      "backup_decryption_rehearsed":truthy(e.get("backup_decryption_rehearsed")),
      "previous_endpoint":previous,"candidate_endpoint":candidate,"blockers":sorted(set(blockers)),"ready":not blockers,"rollback_plan":plan}

def markdown(r):
    lines=["# PORTAL rollback rehearsal evidence","",
      "This is a read-only rehearsal record. It is not authorization to mutate production.","",
      "- backup SHA-256: "+r["backup"]["sha256"],
      "- backup encrypted: "+str(r["backup"]["encrypted"]).lower(),
      "- production mutation performed: false",
      "- result: "+("READY" if r["ready"] else "NO-GO"),
      "- blockers: "+str(len(r["blockers"])),"","## Required evidence",""]
    for k,v in r["evidence_flags"].items():lines.append("- "+k+": "+("PASS" if v else "MISSING/FAIL"))
    if r["backup"]["encrypted"]:lines.append("- backup_decryption_rehearsed: "+("PASS" if r["backup_decryption_rehearsed"] else "MISSING/FAIL"))
    if r["blockers"]:lines+=["","## Blockers",""]+["- "+x for x in r["blockers"]]
    lines+=["","## Rollback plan",""]+[str(i+1)+". "+x for i,x in enumerate(r["rollback_plan"])]
    return "\n".join(lines)+"\n"

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--backup-manifest",required=True);ap.add_argument("--evidence",required=True)
    ap.add_argument("--previous-endpoint");ap.add_argument("--candidate-endpoint");ap.add_argument("--json");ap.add_argument("--markdown");ap.add_argument("--fail-on-blocker",action="store_true")
    a=ap.parse_args();r=build(a.backup_manifest,a.evidence,a.previous_endpoint,a.candidate_endpoint)
    if a.json:Path(a.json).write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if a.markdown:Path(a.markdown).write_text(markdown(r),encoding="utf-8")
    print(json.dumps({"ready":r["ready"],"blockers":len(r["blockers"]),"production_mutation_performed":False,"backup_sha256":r["backup"]["sha256"]},sort_keys=True))
    return 3 if a.fail_on_blocker and r["blockers"] else 0

if __name__=="__main__":raise SystemExit(main())
