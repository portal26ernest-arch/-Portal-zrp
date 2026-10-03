#!/usr/bin/env python3
"""PORTAL release/cutover evidence gate.

Reads a JSON evidence manifest and returns:
0 = staging/release-readiness evidence satisfies the requested profile
2 = invalid manifest
3 = NO-GO due to failed/missing evidence
4 = production profile requested without explicit owner authorization marker

This tool NEVER performs deployment, migration, DNS, service or database changes.
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

SHA256=re.compile(r"^[0-9a-f]{64}$")
GIT_SHA=re.compile(r"^[0-9a-f]{7,40}$")
HTTPS=re.compile(r"^https://[^/?#]+(?::\d+)?(?:/[^?#]*)?$",re.I)

COMMON_REQUIRED=(
    "git_sha","worktree_clean",
    "ci_server","ci_web","ci_android_ui","ci_android_build",
    "tenant_isolation","rls_force","secrets_scan","financial_invariants",
    "backup_created","backup_restore_rehearsed","migration_dry_run",
    "reconciliation","production_untouched",
    "release_payload_complete","api_smoke","web_smoke","runtime_release_verified",
)
COMMON_PASS_FLAGS=tuple(x for x in COMMON_REQUIRED if x!="git_sha")
STAGING_REQUIRED=COMMON_REQUIRED+(
    "staging_apk_sha256","staging_version_name","staging_version_code",
)
PRODUCTION_REQUIRED=STAGING_REQUIRED+(
    "production_https_url","tls_valid","production_signing",
    "offsite_backup_verified","owner_authorized_cutover",
    "write_freeze_confirmed","independent_verifier",
)

def truthy(v):
    return v is True or v=="pass" or v=="green"

def validate(data: dict, profile: str):
    errors=[]; failures=[]
    required=STAGING_REQUIRED if profile=="staging" else PRODUCTION_REQUIRED
    for key in required:
        if key not in data:
            errors.append("missing:"+key)
    if errors:
        return errors,failures

    if not GIT_SHA.fullmatch(str(data["git_sha"])):
        errors.append("invalid:git_sha")
    if not SHA256.fullmatch(str(data["staging_apk_sha256"])):
        errors.append("invalid:staging_apk_sha256")
    try:
        if int(data["staging_version_code"]) < 1:
            errors.append("invalid:staging_version_code")
    except Exception:
        errors.append("invalid:staging_version_code")
    if "-dev" not in str(data["staging_version_name"]) and profile=="staging":
        errors.append("staging_version_name_must_be_dev")

    for key in COMMON_PASS_FLAGS:
        if not truthy(data[key]):
            failures.append(key)

    if profile=="production":
        if "-dev" in str(data["staging_version_name"]):
            failures.append("production_version_is_dev")
        if not HTTPS.fullmatch(str(data["production_https_url"])):
            failures.append("production_https_url")
        for key in (
            "tls_valid","production_signing","offsite_backup_verified",
            "owner_authorized_cutover","write_freeze_confirmed","independent_verifier",
        ):
            if not truthy(data[key]):
                failures.append(key)
    return errors,sorted(set(failures))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",required=True)
    ap.add_argument("--profile",choices=("staging","production"),default="staging")
    a=ap.parse_args()
    try:
        data=json.loads(Path(a.evidence).read_text(encoding="utf-8"))
        if not isinstance(data,dict):
            raise ValueError("manifest root must be object")
    except Exception as e:
        print(json.dumps({"go":False,"kind":"invalid_manifest","error":str(e)},ensure_ascii=False))
        return 2
    errors,failures=validate(data,a.profile)
    if errors:
        print(json.dumps({"go":False,"kind":"invalid_manifest","errors":errors},ensure_ascii=False,sort_keys=True))
        return 2
    if a.profile=="production" and not truthy(data.get("owner_authorized_cutover")):
        print(json.dumps({"go":False,"kind":"owner_authorization_required","failures":failures},ensure_ascii=False,sort_keys=True))
        return 4
    go=not failures
    print(json.dumps({"go":go,"profile":a.profile,"failures":failures,"git_sha":data.get("git_sha")},ensure_ascii=False,sort_keys=True))
    return 0 if go else 3

if __name__=="__main__":
    raise SystemExit(main())
