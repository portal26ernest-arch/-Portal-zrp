#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

IDENT=re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MONEY_FIELDS={
"portal_client_operations":("employee_rate","client_rate"),
"work_log":("rate","salary","client_rate","revenue","direct_cost","unit_direct_cost"),
"payroll_transactions":("amount",),
"client_invoices":("amount_due",),
"client_payments":("amount",),
"materials":("unit_cost",),
"material_movements":("unit_cost",),
"work_material_consumption":("unit_cost",),
"production_jobs":("internal_cost",),
"products":("material_cost_per_unit","other_cost_per_unit"),
"tariff_versions":("employee_rate","client_rate"),
"portal_manager_service_rates":("price",),
"client_invoice_items":("unit_price","amount"),
"expense_requests":("amount",),
"payroll_closure_batches":("amount_paid",),
"payroll_payments":("amount_snapshot",),
}
MINOR_FIELDS={"payroll_settlement_entries":("amount_minor",)}

class ReconciliationError(ValueError): pass

def ident(v):
    if not isinstance(v,str) or not IDENT.fullmatch(v): raise ReconciliationError("unsafe SQL identifier")
    return '"'+v+'"'

def open_readonly(path):
    p=Path(path).expanduser().resolve(strict=True)
    if not p.is_file(): raise ReconciliationError("database path is not a file")
    c=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True);c.row_factory=sqlite3.Row
    if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
        c.close();raise ReconciliationError("SQLite integrity_check failed")
    return c

def columns(c,t):
    return {r[1]:(r[2] or "").upper() for r in c.execute("PRAGMA table_info("+ident(t)+")").fetchall()}

def tables(c):
    return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

def dec(v):
    if v is None or isinstance(v,bool): raise ReconciliationError("invalid money value")
    try: x=Decimal(str(v))
    except (InvalidOperation,ValueError) as e: raise ReconciliationError("invalid money value") from e
    if not x.is_finite(): raise ReconciliationError("invalid money value")
    return x

def expected_minor(v):
    x=dec(v)*Decimal("100");i=x.to_integral_value()
    if x!=i: raise ReconciliationError("money value is not exactly representable in kopecks")
    return int(i)

def select(c,t,fields,company_id):
    cs=columns(c,t)
    for f in fields:
        if f not in cs: raise ReconciliationError("missing field "+t+"."+f)
    q="SELECT "+",".join(ident(x) for x in fields)+" FROM "+ident(t);args=()
    if "company_id" in cs: q+=" WHERE company_id=?";args=(company_id,)
    elif company_id!=1: raise ReconciliationError("unscoped legacy table may only represent company 1: "+t)
    return c.execute(q,args),cs

def fp(values):
    hs=[hashlib.sha256(x.encode()).digest() for x in values]
    return hashlib.sha256(b"".join(sorted(hs))).hexdigest()

def inspect_money(c,t,f,company_id):
    cur,cs=select(c,t,(f,),company_id);rows=nulls=invalid=non_cent=0;norm=[]
    for r in cur:
        rows+=1;v=r[0]
        if v is None: nulls+=1;continue
        try: norm.append(str(dec(v).normalize())+"="+str(expected_minor(v)))
        except ReconciliationError as e:
            invalid+=1
            if "representable in kopecks" in str(e): non_cent+=1
    return {"table":t,"field":f,"sqlite_type":cs[f],"rows":rows,"nulls":nulls,
            "invalid_values":invalid,"non_cent_values":non_cent,"fingerprint_sha256":fp(norm)}

def inspect_minor(c,t,f,company_id):
    cur,cs=select(c,t,(f,),company_id);rows=nulls=invalid=0;norm=[]
    for r in cur:
        rows+=1;v=r[0]
        if v is None: nulls+=1
        elif type(v) is not int: invalid+=1
        else: norm.append(str(v))
    return {"table":t,"field":f,"sqlite_type":cs[f],"rows":rows,"nulls":nulls,
            "invalid_values":invalid,"fingerprint_sha256":fp(norm)}

def parse_pair(v):
    left,sep,minor=v.partition("=");parts=left.split(".",1)
    if not sep or len(parts)!=2: raise ReconciliationError("pair must be table.legacy=minor")
    t,legacy=parts
    if t not in MONEY_FIELDS or legacy not in MONEY_FIELDS[t]: raise ReconciliationError("legacy pair field is not in money allowlist")
    if not IDENT.fullmatch(minor): raise ReconciliationError("unsafe minor-unit field")
    return t,legacy,minor

def reconcile_pair(c,t,legacy,minor,company_id):
    cur,_=select(c,t,(legacy,minor),company_id)
    rows=mismatches=null_mismatch=invalid_legacy=invalid_minor=non_cent=0
    for r in cur:
        rows+=1;old,new=r[0],r[1]
        if old is None or new is None:
            if old is not None or new is not None:null_mismatch+=1
            continue
        try: exp=expected_minor(old)
        except ReconciliationError as e:
            invalid_legacy+=1
            if "representable in kopecks" in str(e):non_cent+=1
            continue
        if type(new) is not int: invalid_minor+=1
        elif exp!=new:mismatches+=1
    ok=not any((mismatches,null_mismatch,invalid_legacy,invalid_minor))
    return {"table":t,"legacy_field":legacy,"minor_field":minor,"rows":rows,"mismatches":mismatches,
            "null_mismatches":null_mismatch,"invalid_legacy":invalid_legacy,"non_cent_legacy":non_cent,
            "invalid_minor":invalid_minor,"ok":ok}

def build_report(c,company_id,pairs):
    if type(company_id) is not int or company_id<1: raise ReconciliationError("company_id must be positive")
    present=tables(c);money=[];minor=[]
    for t,names in MONEY_FIELDS.items():
        if t not in present:continue
        cs=columns(c,t)
        for f in names:
            if f in cs:money.append(inspect_money(c,t,f,company_id))
    for t,names in MINOR_FIELDS.items():
        if t not in present:continue
        cs=columns(c,t)
        for f in names:
            if f in cs:minor.append(inspect_minor(c,t,f,company_id))
    prs=[reconcile_pair(c,*p,company_id) for p in pairs];blockers=[]
    for x in money:
        if x["invalid_values"]:blockers.append(x["table"]+"."+x["field"]+": invalid/non-cent values")
    for x in minor:
        if x["invalid_values"]:blockers.append(x["table"]+"."+x["field"]+": non-integer minor units")
    for x in prs:
        if not x["ok"]:blockers.append(x["table"]+"."+x["legacy_field"]+"->"+x["minor_field"]+": mismatch")
    return {"schema_version":1,"read_only":True,"company_id":company_id,"money_fields":money,
            "minor_unit_fields":minor,"dual_read_pairs":prs,"blockers":blockers,
            "ready_for_additive_minor_unit_migration":not blockers}

def markdown(r):
    out=["# PORTAL legacy money reconciliation","",
         "Read-only evidence. No values are changed and no business totals are printed.","",
         "- company_id: **"+str(r["company_id"])+"**",
         "- money fields present: **"+str(len(r["money_fields"]))+"**",
         "- minor-unit fields present: **"+str(len(r["minor_unit_fields"]))+"**",
         "- dual-read pairs checked: **"+str(len(r["dual_read_pairs"]))+"**",
         "- blockers: **"+str(len(r["blockers"]))+"**",
         "- additive migration preflight: **"+("PASS" if r["ready_for_additive_minor_unit_migration"] else "BLOCKED")+"**","",
         "## Money fields","",
         "| Field | SQL type | Rows | Null | Invalid | Non-cent | Fingerprint |",
         "|---|---|---:|---:|---:|---:|---|"]
    for x in r["money_fields"]:
        out.append("| "+x["table"]+"."+x["field"]+" | "+x["sqlite_type"]+" | "+str(x["rows"])+" | "+str(x["nulls"])+" | "+str(x["invalid_values"])+" | "+str(x["non_cent_values"])+" | "+x["fingerprint_sha256"][:16]+"... |")
    if r["blockers"]:out+=["","## Blockers",""]+["- "+x for x in r["blockers"]]
    return "\n".join(out)+"\n"

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--database",required=True);ap.add_argument("--company-id",type=int,default=1)
    ap.add_argument("--pair",action="append",default=[]);ap.add_argument("--json");ap.add_argument("--markdown");ap.add_argument("--fail-on-blocker",action="store_true")
    a=ap.parse_args();pairs=[parse_pair(x) for x in a.pair]
    with open_readonly(a.database) as c:r=build_report(c,a.company_id,pairs)
    if a.json:Path(a.json).write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if a.markdown:Path(a.markdown).write_text(markdown(r),encoding="utf-8")
    print(json.dumps({"read_only":True,"money_fields":len(r["money_fields"]),"minor_unit_fields":len(r["minor_unit_fields"]),"dual_read_pairs":len(r["dual_read_pairs"]),"blockers":len(r["blockers"])},sort_keys=True))
    return 2 if a.fail_on_blocker and r["blockers"] else 0

if __name__=="__main__":raise SystemExit(main())
