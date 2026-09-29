#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"api\.telegram\.org|BOT_TOKEN|OWNER_TELEGRAM_ID|com\.termux|/storage/emulated/0/PORTAL-BOT|data/data/com\.termux", re.I)
TG = re.compile(r"\btelegram_id\b")
EMP = re.compile(r"\bemployee_id\b")
RUNTIME_PREFIXES = ("server/", "android_src/app/src/main/")
EXCLUDE = ("/test_", "/tests/", "/migrations/", "/docs/")

def files(root: Path):
    cp = subprocess.run(["git","ls-files"], cwd=root, check=True, text=True, capture_output=True)
    return [x.strip().replace("\\","/") for x in cp.stdout.splitlines() if x.strip()]

def runtime(path: str) -> bool:
    return path.startswith(RUNTIME_PREFIXES) and not any(x in ("/"+path) for x in EXCLUDE)

def classify(path: str, line: str) -> str:
    if FORBIDDEN.search(line):
        return "forbidden_external_runtime" if runtime(path) else "schema_test_or_legacy"
    if runtime(path) and TG.search(line):
        return "runtime_bridge" if EMP.search(line) else "runtime_direct_telegram_id"
    if TG.search(line):
        return "schema_test_or_legacy"
    return "other"

def scan(root: Path):
    rows=[]
    for rel in files(root):
        if not rel.endswith((".py",".js",".cjs",".java",".kt",".sql",".sh",".ps1",".txt")):
            continue
        try:
            text=(root/rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for no,line in enumerate(text.splitlines(),1):
            if TG.search(line) or FORBIDDEN.search(line):
                rows.append({"path":rel,"line":no,"kind":classify(rel,line),"text":line.strip()[:260]})
    counts={}
    for row in rows:
        counts[row["kind"]]=counts.get(row["kind"],0)+1
    return {"counts":counts,"findings":rows}

def report(data):
    c=data["counts"]
    out=[
        "# PORTAL legacy runtime identity audit","",
        "Generated evidence only; this tool does not modify schemas or data.","",
        "## Summary","",
        f"- forbidden external Telegram/Termux runtime references: {c.get('forbidden_external_runtime',0)}",
        f"- active runtime direct telegram_id references: {c.get('runtime_direct_telegram_id',0)}",
        f"- active runtime compatibility bridges: {c.get('runtime_bridge',0)}",
        f"- schema/test/legacy references: {c.get('schema_test_or_legacy',0)}","",
        "## Release interpretation","",
        "- External Telegram/Termux runtime count must remain zero.",
        "- employee_id is the target canonical identity.",
        "- Direct active-runtime telegram_id references mean roadmap item 102 is not yet fully complete.",
        "- Historical columns may remain until an additive rehearsed migration proves safe.","",
        "## Active runtime findings","",
        "| Kind | File | Line | Evidence |","|---|---|---:|---|"
    ]
    for x in data["findings"]:
        if x["kind"] in {"runtime_direct_telegram_id","runtime_bridge","forbidden_external_runtime"}:
            out.append(f"| {x['kind']} | {x['path']} | {x['line']} | {x['text'].replace('|','\\|')} |")
    return "\n".join(out)+"\n"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default=str(ROOT))
    ap.add_argument("--markdown")
    ap.add_argument("--json")
    ap.add_argument("--fail-on-direct-runtime-telegram-id",action="store_true")
    a=ap.parse_args()
    data=scan(Path(a.root).resolve())
    if a.markdown:
        Path(a.markdown).write_text(report(data),encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(data["counts"],ensure_ascii=False,sort_keys=True))
    if data["counts"].get("forbidden_external_runtime",0):
        return 2
    if a.fail_on_direct_runtime_telegram_id and data["counts"].get("runtime_direct_telegram_id",0):
        return 3
    return 0

if __name__=="__main__":
    raise SystemExit(main())
