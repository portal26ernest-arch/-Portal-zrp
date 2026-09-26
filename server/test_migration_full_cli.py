"""Opt-in, one-shot end-to-end validation of the synthetic Stage 4B VPS.

Run as postgres after test_migration_full_vps.py. Existing target data is never
cleared. Failure artifacts, rollback DB and restored DB remain for inspection.
Only the three explicitly named test databases below may be used.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from migration_context import bind_company
from migration_import import open_copy, prepared_source, summary, identity_maxima
from test_migration_full_vps import ROOT, DB, ROLES, TENANT_TABLES, CONTROL_TABLES

ROLLBACK_DB = DB + '_rollback'
RESTORE_DB = DB + '_restore'
HERE = Path(__file__).resolve().parent


@unittest.skipUnless(os.environ.get('PORTAL_FULL_CLI_INTEGRATION') == '1',
                     'requires dedicated synthetic full-CLI VPS databases')
class FullMigrationCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        cls.pg, cls.sql = psycopg, sql
        if DB != 'portal_test_migration_full_20260926' or os.geteuid() == 0:
            raise RuntimeError('Use the postgres OS user and fixed isolated test DB')
        cls.secrets = json.loads((ROOT / 'secrets.json').read_text())
        cls.dsn = cls.secrets['migration_dsn']
        for kind in ('migration', 'tenant', 'control'):
            details = conninfo_to_dict(cls.secrets[kind + '_dsn'])
            if (details.get('dbname') != DB or details.get('host') != '127.0.0.1'
                    or details.get('user') != ROLES[kind]):
                raise RuntimeError('Unexpected test DSN destination')
        cls.rollback_dsn = make_conninfo(cls.dsn, dbname=ROLLBACK_DB)
        cls.restore_dsn = make_conninfo(cls.dsn, dbname=RESTORE_DB)
        cls.results = ROOT / ('results-' + str(time.time_ns()))
        cls.results.mkdir(mode=0o700)
        cls.copies = [ROOT/'platform-synthetic.db'] + [ROOT/f'tenant-{n}-synthetic.db' for n in (1,2)]
        cls.hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in cls.copies}
        cls.facts = {}
        for cid in (1,2):
            with open_copy(ROOT/f'tenant-{cid}-synthetic.db') as source:
                cls.facts[cid] = summary(source, prepared_source(source,cid),cid)
        with psycopg.connect('dbname=' + DB + ' user=postgres', autocommit=True) as admin:
            if admin.execute('SELECT count(*) FROM companies').fetchone()[0]:
                raise RuntimeError('Test database is not empty; never reset it')
        with psycopg.connect('dbname=postgres user=postgres', autocommit=True) as admin:
            for name in (ROLLBACK_DB,RESTORE_DB):
                if admin.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
                    raise RuntimeError('Preserving existing test database: ' + name)
            admin.execute(sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(
                sql.Identifier(ROLLBACK_DB),sql.Identifier(DB)))
        cls.report = {'database':DB,'source_sha256':cls.hashes,'checks':{}}

    @classmethod
    def tearDownClass(cls):
        cls.report['source_unchanged'] = all(
            hashlib.sha256(p.read_bytes()).hexdigest()==cls.hashes[p.name] for p in cls.copies)
        (cls.results/'checks.json').write_text(json.dumps(cls.report,indent=2)+'\n')

    def cli(self, script, args, dsn=None, expected=0):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        env.pop('PORTAL_MIGRATION_DSN',None)
        if dsn:
            env['PORTAL_MIGRATION_DSN'] = dsn
        result = subprocess.run([sys.executable,'-B',str(HERE/script),*args],
                                env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,expected,
                         script + ': ' + result.stdout + result.stderr)
        return result

    def import_args(self, report, tenant2=None):
        return ['--tenant-copy','1:'+str(self.copies[1]),
                '--tenant-copy','2:'+str(tenant2 or self.copies[2]),
                '--platform-copy',str(self.copies[0]),'--report',str(report)]

    def check_sources(self):
        for p in self.copies:
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),self.hashes[p.name])

    def test_01_cli_dry_run_and_atomic_failure(self):
        path=self.results/'dry-run.json'
        self.cli('migrate_sqlite_to_pg.py',self.import_args(path))
        self.assertEqual(json.loads(path.read_text())['status'],'DRY_RUN')
        # The artificial bad second tenant passes source preflight but violates
        # a PostgreSQL NOT NULL constraint after control and tenant A import.
        bad=self.results/'tenant-2-bad.db'
        shutil.copyfile(self.copies[2],bad)
        with sqlite3.connect(bad) as c:
            c.execute('UPDATE app_users SET created_at=NULL')
        self.cli('migrate_sqlite_to_pg.py',self.import_args(self.results/'bad-dry.json',bad))
        path=self.results/'rollback.json'
        self.cli('migrate_sqlite_to_pg.py',self.import_args(path,bad)+['--apply'],self.rollback_dsn,1)
        failure=json.loads(path.read_text())
        self.assertEqual(failure['status'],'FAILED')
        self.assertEqual(failure['reason'],'NotNullViolation')
        with self.pg.connect('dbname='+ROLLBACK_DB+' user=postgres') as c:
            for table in (*CONTROL_TABLES,*TENANT_TABLES,'portal_company_keys'):
                count=c.execute(self.sql.SQL('SELECT count(*) FROM {}').format(self.sql.Identifier(table))).fetchone()[0]
                self.assertEqual(count,0,table)
        self.check_sources()
        self.report['checks']['cli_rollback_all_tables']=True

    def test_02_cli_apply(self):
        path=self.results/'apply.json'
        self.cli('migrate_sqlite_to_pg.py',self.import_args(path)+['--apply'],self.dsn)
        result=json.loads(path.read_text())
        self.assertEqual(result['status'],'IMPORTED_AND_VERIFIED')
        self.assertEqual(result['company_count'],2)
        self.assertGreater(result['identity_sequences_checked'],0)
        for company in result['companies']:
            facts=self.facts[company['company_id']]
            self.assertEqual(company['counts'],facts['counts'])
            self.assertEqual(company['money'],facts['money'])
        self.check_sources()
        self.report['checks']['cli_apply']=result

    def test_03_cli_validator_and_mismatch(self):
        for cid in (1,2):
            self.cli('validate_pg_migration.py',['--sqlite-copy',str(self.copies[cid]),
                     '--company-id',str(cid)],self.dsn)
        bad=self.results/'tenant-money-mismatch.db'
        shutil.copyfile(self.copies[1],bad)
        with sqlite3.connect(bad) as c:
            c.execute('UPDATE work_log SET salary=999')
        self.cli('validate_pg_migration.py',['--sqlite-copy',str(bad),'--company-id','1'],self.dsn,1)
        self.check_sources()
        self.report['checks']['validator_and_mismatch']=True

    def test_04_login_roles_and_identity_sequences(self):
        for kind in ('migration','tenant','control'):
            with self.pg.connect(self.secrets[kind+'_dsn']) as c:
                role=c.execute('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
                self.assertEqual(role,(ROLES[kind],False,False))
                self.assertEqual(c.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner=current_user").fetchone()[0],0)
        connections=[open_copy(self.copies[n]) for n in (1,2)]
        control=open_copy(self.copies[0])
        try:
            maxima=identity_maxima(list(zip((1,2),connections)),control)
        finally:
            for c in [*connections,control]: c.close()
        checked=0
        with self.pg.connect(self.dsn) as c:
            for table,maximum in maxima.items():
                seq=c.execute("SELECT pg_get_serial_sequence(%s,'id')",('public.'+table,)).fetchone()[0]
                if seq:
                    self.assertGreater(c.execute('SELECT nextval(%s::regclass)',(seq,)).fetchone()[0],maximum)
                    checked+=1
        self.assertGreater(checked,5)
        self.report['checks']['login_roles_and_sequences']=checked

    def test_05_forced_rls_and_history(self):
        with self.pg.connect(self.secrets['control_dsn']) as control:
            keys=dict(control.execute('SELECT company_id,secret FROM portal_company_keys').fetchall())
        with self.pg.connect(self.secrets['tenant_dsn'],autocommit=True) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM work_log').fetchone()[0],0)
            self.assertTrue(c.execute("SELECT row_security_active('portal_production')").fetchone()[0])
            for cid in (1,2):
                with c.transaction():
                    c.execute('SELECT portal_bind_company(%s,%s)',(cid,keys[cid]))
                    self.assertEqual(c.execute('SELECT DISTINCT company_id FROM work_log').fetchall(),[(cid,)])
                    self.assertEqual(c.execute('UPDATE portal_clients SET name=name WHERE company_id=%s',(3-cid,)).rowcount,0)
                    c.execute("SELECT set_config('portal.company_id',%s,true)",(str(3-cid),))
                    self.assertEqual(c.execute('SELECT count(*) FROM work_log').fetchone()[0],0)
                with self.assertRaises(self.pg.Error):
                    with c.transaction():
                        c.execute('SELECT portal_bind_company(%s,%s)',(cid,keys[cid]))
                        c.execute("INSERT INTO portal_clients(company_id,name,created_at,updated_at) VALUES(%s,'Forged','x','x')",(3-cid,))
            with self.assertRaises(self.pg.Error): c.execute('SELECT secret FROM portal_company_keys')
            with self.assertRaises(self.pg.Error): c.execute('SELECT * FROM platform_owners')
            with self.assertRaises(self.pg.Error):
                with c.transaction():
                    c.execute('SELECT portal_bind_company(%s,%s)',(1,keys[1]))
                    c.execute('DELETE FROM work_log')
            with self.assertRaises(self.pg.Error):
                with c.transaction():
                    c.execute('SELECT portal_bind_company(%s,%s)',(1,keys[1]))
                    c.execute("UPDATE portal_production SET payload=jsonb_set(payload::jsonb,'{salary}','999')::text WHERE kind='works'")
            with self.assertRaisesRegex(RuntimeError,'rollback probe'):
                with c.transaction():
                    c.execute('SELECT portal_bind_company(%s,%s)',(1,keys[1]))
                    c.execute("INSERT INTO portal_clients(name,created_at,updated_at) VALUES('Rollback probe','x','x')")
                    raise RuntimeError('rollback probe')
        self.verify_sources_in_target()
        self.report['checks']['rls_and_history_and_rollback']=True

    def verify_sources_in_target(self):
        for cid in (1,2):
            self.cli('validate_pg_migration.py',['--sqlite-copy',str(self.copies[cid]),
                     '--company-id',str(cid)],self.dsn)

    def test_06_backup_restore(self):
        backup=self.results/'synthetic.dump'
        subprocess.run(['pg_dump','-Fc','-d',DB,'-f',str(backup)],check=True,capture_output=True)
        with self.pg.connect('dbname='+DB+' user=postgres',autocommit=True) as c:
            c.execute(self.sql.SQL('CREATE DATABASE {}').format(self.sql.Identifier(RESTORE_DB)))
        result=subprocess.run(['pg_restore','--exit-on-error','-d',RESTORE_DB,str(backup)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,'pg_restore failed')
        for cid in (1,2):
            self.cli('validate_pg_migration.py',['--sqlite-copy',str(self.copies[cid]),
                     '--company-id',str(cid)],self.restore_dsn)
        self.report['checks']['backup_restore']=True

    def test_07_imported_api_and_restart(self):
        # A dedicated temporary process; the existing 8766 service is untouched.
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',8767))
        env=dict(os.environ,PORTAL_ENV='test',PORTAL_DB_BACKEND='postgresql',
                 PORTAL_DATABASE_URL=self.secrets['tenant_dsn'],
                 PORTAL_CONTROL_DATABASE_URL=self.secrets['control_dsn'],
                 PORTAL_APP_HOST='127.0.0.1',PORTAL_APP_PORT='8767',
                 PORTAL_PUBLIC_API_URL='http://127.0.0.1:8767',PYTHONDONTWRITEBYTECODE='1')
        def api(path,body=None,token=None):
            headers={'Content-Type':'application/json'}
            if token: headers['Authorization']='Bearer '+token
            request=Request('http://127.0.0.1:8767'+path,
                            data=json.dumps(body).encode() if body is not None else None,headers=headers)
            try:
                with urlopen(request,timeout=5) as r: return r.status,json.load(r)
            except HTTPError as e:
                return e.code,json.load(e)
        def start():
            p=subprocess.Popen([sys.executable,'-B',str(HERE/'portal_app_server.py')],env=env,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(50):
                if p.poll() is not None: self.fail('Isolated imported API failed startup')
                try:
                    if api('/api/ping')[0]==200: return p
                except OSError: pass
                time.sleep(.1)
            p.terminate(); p.wait(timeout=5)
            self.fail('Isolated imported API startup timeout')
        process=start()
        try:
            tokens={}
            for cid,label in ((1,'a'),(2,'b')):
                status,login=api('/api/login',{'company_id':cid,'username':'admin_'+label,
                                             'pin':self.secrets['synthetic_pin']})
                self.assertEqual(status,200,'Imported login failed')
                tokens[cid]=login['token']
                status,listed=api('/api/clients',token=tokens[cid])
                self.assertEqual(status,200)
                self.assertEqual(len(listed['clients']),1)
            self.assertEqual(api('/api/clients?company_id=2',token=tokens[1])[0],403)
            status,created=api('/api/admin/clients',{'name':'Post migration API client'},tokens[1])
            self.assertEqual(status,200)
            self.assertGreater(created['id'],1)
            process.terminate(); process.wait(timeout=10)
            process=start()
            status,listed=api('/api/clients',token=tokens[1])
            self.assertEqual(status,200)
            self.assertTrue(any(r['id']==created['id'] for r in listed['clients']))
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=10)
        with self.pg.connect(self.dsn) as c:
            for cid in (1,2):
                bind_company(c,cid)
                row=c.execute("SELECT payload FROM portal_production WHERE kind='works'").fetchone()
                self.assertEqual(json.loads(row[0])['salary'],705)
                self.assertEqual(c.execute('SELECT salary::text FROM work_log').fetchone()[0],'7.05')
        self.check_sources()
        self.report['checks']['imported_api_and_restart']=True


if __name__=='__main__':
    unittest.main(verbosity=2)
