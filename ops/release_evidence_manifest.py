#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, subprocess
from pathlib import Path

REQUIRED_EVIDENCE=(
    'PORTAL_RELEASE_READINESS_MATRIX.md',
    'PORTAL_FINALIZATION_PART12_REPORT.md',
    'PORTAL_WINDOWS_DESKTOP_REPORT.md',
    'PORTAL_EMPLOYEE_ID_MIGRATION_MAP.md',
    'PORTAL_LEGACY_RUNTIME_AUDIT.md',
    'PORTAL_MONEY_FIELD_INVENTORY.md',
    'ops/PORTAL_INFRA_READINESS.md',
    'ops/PORTAL_MONEY_RECONCILIATION.md',
)
REQUIRED_WORKFLOWS=(
    '.github/workflows/infra-readiness.yml',
    '.github/workflows/windows-desktop-build.yml',
)
RELEASE_KEYS=('versionName','versionCode','buildNumber','buildDate','channel')
BUILD_RE=re.compile(r'^\d+\.\d+$')

class EvidenceError(ValueError):pass

def run_git(root,*args):
    cp=subprocess.run(['git',*args],cwd=root,text=True,capture_output=True,check=True)
    return cp.stdout.strip()
def parse_properties(path):
    data={}
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if not sep:raise EvidenceError('invalid release.properties line')
        data[key.strip()]=value.strip()
    missing=[k for k in RELEASE_KEYS if not data.get(k)]
    if missing:raise EvidenceError('missing release metadata: '+','.join(missing))
    if not data['versionCode'].isdigit() or int(data['versionCode'])<1:
        raise EvidenceError('invalid versionCode')
    if not BUILD_RE.fullmatch(data['buildNumber']):
        raise EvidenceError('invalid buildNumber')
    if not data['versionName'].startswith(data['buildNumber']):
        raise EvidenceError('versionName/buildNumber mismatch')
    if data['channel'] not in {'development','staging','production'}:
        raise EvidenceError('unsupported release channel')
    return data

def fingerprint(path):
    p=Path(path);h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return {'size':p.stat().st_size,'sha256':h.hexdigest()}
def build_manifest(root):
    root=Path(root).resolve()
    props=parse_properties(root/'android_src/release.properties')
    required=REQUIRED_EVIDENCE+REQUIRED_WORKFLOWS+('android_src/release.properties',)
    missing=[rel for rel in required if not (root/rel).is_file()]
    if missing:raise EvidenceError('missing evidence: '+','.join(missing))
    head=run_git(root,'rev-parse','HEAD');branch=run_git(root,'branch','--show-current')
    dirty=bool(run_git(root,'status','--porcelain'))
    evidence={rel:fingerprint(root/rel) for rel in required}
    return {
        'schema_version':1,'branch':branch,'head':head,'dirty':dirty,
        'release':props,'evidence':evidence,
    }

def markdown(data):
    r=data['release'];out=[
        '# PORTAL release evidence manifest','',
        'Generated from the current checkout; it is not a production approval.','',
        '- branch: '+data['branch'],
        '- head: '+data['head'],
        '- working tree: '+('DIRTY' if data['dirty'] else 'CLEAN'),
        '- version: '+r['versionName']+' / code '+r['versionCode']+' / build '+r['buildNumber'],
        '- channel: '+r['channel'],'',
        '## Evidence fingerprints','',
        '| Path | Bytes | SHA-256 |','|---|---:|---|']
    for path,item in sorted(data['evidence'].items()):
        out.append('| '+path+' | '+str(item['size'])+' | '+item['sha256']+' |')
    return '\n'.join(out)+'\n'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument('--json');ap.add_argument('--markdown');ap.add_argument('--require-clean',action='store_true')
    a=ap.parse_args();data=build_manifest(a.root)
    if a.require_clean and data['dirty']:raise EvidenceError('working tree is dirty')
    if a.json:Path(a.json).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if a.markdown:Path(a.markdown).write_text(markdown(data),encoding='utf-8')
    print(json.dumps({'branch':data['branch'],'head':data['head'],'dirty':data['dirty'],
                      'versionName':data['release']['versionName'],'versionCode':data['release']['versionCode'],
                      'evidence_files':len(data['evidence'])},sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
