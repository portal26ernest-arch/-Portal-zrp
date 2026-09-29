#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONEY = re.compile(r"(amount|price|rate|salary|revenue|cost|paid|balance|profit|margin|fee|total|due)",re.I)
MINOR = re.compile(r"(_cents|_minor|minor_units|amount_minor)",re.I)
DECL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+(REAL|FLOAT|DOUBLE(?:\s+PRECISION)?|NUMERIC|DECIMAL(?:\([^)]*\))?|BIGINT|INTEGER)\b",re.I)

def files(root):
    cp=subprocess.run(["git","ls-files"],cwd=root,check=True,text=True,capture_output=True)
    return [x.strip().replace("\\","/") for x in cp.stdout.splitlines() if x.strip()]

def scan(root: Path):
    fields=[]
    for rel in files(root):
        if not rel.endswith((".sql",".py")):
            continue
        try:
            text=(root/rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for no,line in enumerate(text.splitlines(),1):
            for m in DECL.finditer(line):
                name,typ=m.group(1),m.group(2).upper()
                if not MONEY.search(name):
                    continue
                float_like=typ.startswith(("REAL","FLOAT","DOUBLE","NUMERIC","DECIMAL")) and not MINOR.search(name)
                fields.append({"path":rel,"line":no,"field":name,"sql_type":typ,"legacy_float_like":bool(float_like),"minor_unit":bool(MINOR.search(name)),"text":line.strip()[:260]})
    cent_hits=[]
    p=re.compile(r"settlement_cents|_cents\b|_minor\b|amount_minor\b")
    for rel in files(root):
        if not rel.endswith((".py",".sql",".js",".cjs")):
            continue
        try:
            text=(root/rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for no,line in enumerate(text.splitlines(),1):
            if p.search(line):
                cent_hits.append({"path":rel,"line":no,"text":line.strip()[:260]})
    return {
        "fields":fields,
        "legacy_float_like_count":sum(1 for x in fields if x["legacy_float_like"]),
        "minor_unit_declared_count":sum(1 for x in fields if x["minor_unit"]),
        "cent_source_hits":cent_hits
    }

def report(data):
    out=[
        "# PORTAL money field inventory","",
        "Generated inventory for roadmap item 105. No schema or values are changed.","",
        "## Summary","",
        f"- legacy float-like money declarations: {data['legacy_float_like_count']}",
        f"- explicit minor-unit money declarations: {data['minor_unit_declared_count']}",
        f"- source references to cents/minor-unit conversion: {len(data['cent_source_hits'])}","",
        "## Migration policy","",
        "- New monetary storage/calculation should use integer minor units.",
        "- Legacy REAL/NUMERIC money must not be dropped or silently rewritten.",
        "- Migration must be additive, deterministic, reconciled and rehearsed on disposable PostgreSQL.",
        "- Quantity/weight fields are intentionally excluded from money classification.","",
        "## Legacy float-like money declarations","",
        "| File | Line | Field | SQL type | Evidence |","|---|---:|---|---|---|"
    ]
    for x in data["fields"]:
        if x["legacy_float_like"]:
            out.append(f"| {x['path']} | {x['line']} | {x['field']} | {x['sql_type']} | {x['text'].replace('|','\\|')} |")
    return "\n".join(out)+"\n"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",default=str(ROOT))
    ap.add_argument("--markdown")
    ap.add_argument("--json")
    a=ap.parse_args()
    data=scan(Path(a.root).resolve())
    if a.markdown:
        Path(a.markdown).write_text(report(data),encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"legacy_float_like_count":data["legacy_float_like_count"],"minor_unit_declared_count":data["minor_unit_declared_count"],"cent_source_hits":len(data["cent_source_hits"])},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
