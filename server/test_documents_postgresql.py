"""Opt-in disposable PostgreSQL fixture: never accepts a production DSN.

Run as the postgres OS user with PORTAL_DOCUMENTS_PG_INTEGRATION=1.
Creates a fresh randomly named portal_test_documents_* database, two restricted
roles, synthetic companies and an in-process HTTP handler. Removes only resources
created by this fixture. Normal regression runs skip this isolated live gate.
"""
import base64
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

MIGRATIONS=('postgresql_core_stage4b.sql','postgresql_stage3.sql','postgresql_runtime.sql',
 'postgresql_rls_context.sql','postgresql_stage5_chat_retention.sql','postgresql_stage6_payroll_settlement.sql',
 'postgresql_stage4c.sql','postgresql_stage8_documents_excel.sql')

@unittest.skipUnless(os.environ.get('PORTAL_DOCUMENTS_PG_INTEGRATION')=='1','requires disposable local PostgreSQL fixture')
class DocumentsPostgreSQLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pwd
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        if os.getuid()!=pwd.getpwnam('postgres').pw_uid:raise RuntimeError('Run disposable fixture as postgres OS user')
        cls.pg,cls.sql=psycopg,sql;cls.created_db=False;cls.created_roles=[]
        suffix=secrets.token_hex(6);cls.database='portal_test_documents_'+suffix
        cls.roles={'tenant':'portal_docs_t_'+suffix,'control':'portal_docs_c_'+suffix}
        cls.super_connection=psycopg.connect('dbname=postgres user=postgres host=/var/run/postgresql',autocommit=True)
        cls.tmp=tempfile.TemporaryDirectory(prefix='portal-documents-pg-')
        try:
            passwords={kind:secrets.token_urlsafe(32) for kind in cls.roles}
            if cls.super_connection.execute('SELECT 1 FROM pg_database WHERE datname=%s',(cls.database,)).fetchone():raise RuntimeError('Disposable target already exists')
            for kind,role in cls.roles.items():
                if cls.super_connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():raise RuntimeError('Disposable role already exists')
                cls.super_connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}').format(sql.Identifier(role),sql.Literal(passwords[kind])))
                cls.created_roles.append(role)
            cls.super_connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.database)));cls.created_db=True
            for name in MIGRATIONS:cls.migration(name)
            # Verify reapplication without modifying earlier migration history.
            cls.migration('postgresql_stage8_documents_excel.sql')
            with psycopg.connect('dbname='+cls.database+' user=postgres host=/var/run/postgresql',autocommit=True) as admin:
                tenant=sql.Identifier(cls.roles['tenant']);control=sql.Identifier(cls.roles['control'])
                for role in (tenant,control):
                    admin.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(cls.database),role))
                    admin.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(role))
                    admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_current_company() TO {}').format(role))
                tables=('employees','app_users','app_sessions','portal_clients','portal_client_operations','manager_client_assignments',
                        'portal_production','portal_production_migrations','payroll_employee_identities','payroll_settlement_entries',
                        'portal_company_requisites','portal_client_requisites','work_log','payroll_payments','payroll_transactions',
                        'client_invoices','client_payments','materials','operation_material_norms','portal_runtime_schema','portal_rls_context_schema')
                for table in tables:admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON {} TO {}').format(sql.Identifier(table),tenant))
                for table in ('portal_documents','portal_excel_imports'):
                    admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON {} TO {}').format(sql.Identifier(table),tenant))
                admin.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(tenant))
                admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_bind_company(BIGINT,TEXT) TO {}').format(tenant))
                for table in ('companies','platform_owners','platform_sessions','platform_audit'):
                    admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON {} TO {}').format(sql.Identifier(table),control))
                admin.execute(sql.SQL('GRANT SELECT ON portal_company_keys TO {}').format(control))
                admin.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(control))
                admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_provision_company(BIGINT) TO {}').format(control))
                for cid in (1,2):
                    admin.execute("INSERT INTO companies(id,name,user_limit,created_at,updated_at) VALUES(%s,%s,NULL,CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text)",(cid,'Synthetic company '+str(cid)))
                    admin.execute('SELECT portal_provision_company(%s)',(cid,))
            import test_portal_app_server as legacy
            import test_production as production
            from portal_config import load_config
            cls.legacy,cls.production,cls.portal=legacy,production,legacy.portal
            cls.old_config,cls.old_db=cls.portal.CONFIG,cls.portal.DB_PATH
            cls.old_http=os.environ.get('PORTAL_TEST_HTTP');os.environ['PORTAL_TEST_HTTP']='0'
            cls.old_root=os.environ.get('PORTAL_DOCUMENT_ROOT');os.environ['PORTAL_DOCUMENT_ROOT']=cls.tmp.name+'/blobs'
            tenant_dsn=make_conninfo(dbname=cls.database,user=cls.roles['tenant'],password=passwords['tenant'],host='127.0.0.1')
            control_dsn=make_conninfo(dbname=cls.database,user=cls.roles['control'],password=passwords['control'],host='127.0.0.1')
            cls.portal.CONFIG=load_config({'PORTAL_ENV':'test','PORTAL_DB_BACKEND':'postgresql',
              'PORTAL_DATABASE_URL':tenant_dsn,'PORTAL_CONTROL_DATABASE_URL':control_dsn,'PORTAL_APP_HOST':'127.0.0.1','PORTAL_APP_PORT':'18770'})
            cls.portal.tenants.configure(cls.portal.CONFIG);cls.portal.DB_PATH=cls.tmp.name+'/unused.db'
            from production_repository import Repository,utcnow
            from production_migrations import migrate
            cls.tokens={}
            salt,pin_hash=cls.portal.hash_pin(secrets.token_urlsafe(20))
            for cid in (1,2):
                with cls.portal.tenants.company_scope(cid),cls.portal.db() as conn:
                    r=Repository(conn,cid)
                    r.sql('INSERT INTO employees(company_id,telegram_id,full_name,username) VALUES(?,101,?,?)',(cid,'Synthetic person '+str(cid),'profile'))
                    r.sql('''INSERT INTO app_users(company_id,id,username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at)
                         VALUES(?,1,'admin','Synthetic admin','admin',101,1,?,?,?,?)''',(cid,salt,pin_hash,utcnow(),utcnow()))
                    r.sql("INSERT INTO portal_clients(company_id,id,name,active,created_at,updated_at) VALUES(?,1,'Synthetic client',1,?,?)",(cid,utcnow(),utcnow()))
                    r.sql("INSERT INTO portal_client_operations(company_id,id,client_id,name,employee_rate,client_rate,created_at,updated_at) VALUES(?,1,1,'Packing',2,5,?,?)",(cid,utcnow(),utcnow()))
                    r.insert('tariffs',dict(client_id=1,operation_id=1,employee_rate=200,client_rate=500,effective_from=utcnow()))
                    cls.tokens[cid]=cls.portal.create_session(conn,1)
                with cls.portal.tenants.company_scope(cid),cls.portal.db() as conn:migrate(conn,cid)
            # Only the fixture administrator adjusts sequences after explicit IDs.
            with psycopg.connect('dbname='+cls.database+' user=postgres host=/var/run/postgresql',autocommit=True) as admin:
                for table in ('app_users','portal_clients','portal_client_operations'):
                    admin.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,'id'),GREATEST((SELECT MAX(id) FROM {}),1),true)").format(sql.Identifier(table)),(table,))
            cls.http=cls.portal.ThreadingHTTPServer(('127.0.0.1',0),legacy.QuietHandler)
            cls.http_thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.http_thread.start()
        except Exception:
            cls.cleanup();raise

    @classmethod
    def migration(cls,name):
        result=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-q','-d',cls.database],
            input=(Path(__file__).parent/'migrations'/name).read_text(encoding='utf-8'),text=True,capture_output=True)
        if result.returncode:raise RuntimeError('Disposable migration failed: '+name+'\n'+result.stderr)

    @classmethod
    def cleanup(cls):
        if getattr(cls,'http',None):
            cls.http.shutdown();cls.http.server_close();cls.http_thread.join(timeout=3);cls.http=None
        if hasattr(cls,'old_config'):
            cls.portal.CONFIG,cls.portal.DB_PATH=cls.old_config,cls.old_db;cls.portal.tenants.configure(cls.old_config)
            for key,value in (('PORTAL_TEST_HTTP',cls.old_http),('PORTAL_DOCUMENT_ROOT',cls.old_root)):
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
        if hasattr(cls,'super_connection'):
            if cls.created_db:
                if not cls.database.startswith('portal_test_documents_'):raise RuntimeError('Unexpected disposable database name')
                cls.super_connection.execute(cls.sql.SQL('DROP DATABASE {}').format(cls.sql.Identifier(cls.database)))
            for role in cls.created_roles:cls.super_connection.execute(cls.sql.SQL('DROP ROLE {}').format(cls.sql.Identifier(role)))
            cls.super_connection.close()
        if hasattr(cls,'tmp'):cls.tmp.cleanup()

    @classmethod
    def tearDownClass(cls):cls.cleanup()
    def request(self,*args,**kwargs):return self.legacy.PortalAPITest.request(self,*args,**kwargs)
    def post(self,*args,**kwargs):return self.production.ProductionTest.post(self,*args,**kwargs)
    def get(self,*args,**kwargs):return self.production.ProductionTest.get(self,*args,**kwargs)
    @property
    def admin(self):return self.tokens[1]

    def upload(self,token):
        data=b'%PDF-1.4\nSynthetic\n%%EOF\n'
        return self.post('documents',dict(action='upload',document_type='report_pdf',original_filename='test.pdf',mime_type='application/pdf',file_b64=base64.b64encode(data).decode(),title='Live PG test '+secrets.token_hex(4)),token)['data']

    def test_catalog_rls_grants_and_database_reference_guards(self):
        doc=self.upload(self.tokens[1])
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            roles=conn.execute('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user').fetchone()
            self.assertEqual(tuple(roles),(False,False))
            for table in ('portal_documents','portal_excel_imports'):
                self.assertEqual(tuple(conn.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=?::regclass',(table,)).fetchone()),(True,True))
                self.assertEqual(conn.execute("SELECT has_table_privilege(current_user,?,'DELETE')",(table,)).fetchone()[0],False)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_documents WHERE company_id=2').fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT jsonb_typeof(metadata) FROM portal_documents WHERE id=?",(doc['id'],)).fetchone()[0],'object')
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            from document_domain import COLUMNS
            copied=list(conn.execute('SELECT '+','.join(COLUMNS)+' FROM portal_documents WHERE id=?',(doc['id'],)).fetchone())
            copied[0]=2;copied[1]=secrets.token_hex(16);copied[COLUMNS.index('request_id')]=secrets.token_hex(16)
            copied[COLUMNS.index('metadata')]=json.dumps(copied[COLUMNS.index('metadata')])
            with self.assertRaises(self.pg.errors.InsufficientPrivilege):
                conn.execute('INSERT INTO portal_documents('+','.join(COLUMNS)+') VALUES('+','.join('?' for _ in COLUMNS)+')',tuple(copied))
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            with self.assertRaises(self.pg.errors.RaiseException):conn.execute("UPDATE portal_documents SET title='forged' WHERE id=?",(doc['id'],))
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            conn.execute("SELECT set_config('portal.company_id','2',true)")
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_documents').fetchone()[0],0)

    def test_http_cross_company_metadata_download_archive_and_template(self):
        doc=self.upload(self.tokens[2])
        for action in ('document-metadata','document-file'):self.get(action+'?id='+doc['id'],self.tokens[1],status=400)
        self.post('documents',dict(action='archive',id=doc['id']),self.tokens[1],status=400)
        self.request('/api/v3/documents',self.tokens[1],status=403,extra_headers={'X-Portal-Company':'2'})
        self.assertNotIn(doc['id'],[d['id'] for d in self.get('documents',self.tokens[1])['data']])
        self.assertEqual(self.get('document-metadata?id='+doc['id'],self.tokens[2])['data']['company_id'],2)

    def test_pg_preview_apply_retry_failure_rollback_and_job_immutability(self):
        from excel_template import workbook
        from excel_apply import _apply_row
        payload=workbook({'Клиенты':[dict(client_ref='pg',name='Import '+secrets.token_hex(6),active=1)],
                          'Сотрудники':[dict(employee_ref='pg',full_name='Person '+secrets.token_hex(6))],
                          'Операции_Тарифы':[dict(client_ref='pg',name='New operation',employee_rate='1.25',client_rate='2.50',active=1)]})
        body=dict(file_b64=base64.b64encode(payload).decode())
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            before=conn.execute('SELECT COUNT(*) FROM portal_clients').fetchone()[0]
            jobs=conn.execute('SELECT COUNT(*) FROM portal_excel_imports').fetchone()[0]
        preview=self.request('/api/v3/excel-import-preview',self.tokens[1],body)['data']
        self.assertTrue(preview['can_apply'])
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_clients').fetchone()[0],before)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_excel_imports').fetchone()[0],jobs)
        apply_body=dict(body,import_id=preview['import_id'],preview_token=preview['preview_token'])
        counter=[]
        def fail(importer,row,refs):
            value=_apply_row(importer,row,refs);counter.append(row)
            if len(counter)==2:raise RuntimeError('synthetic failure')
            return value
        with patch('excel_apply._apply_row',side_effect=fail):
            failed=self.request('/api/v3/excel-import-apply',self.tokens[1],apply_body,status=409)['data']
        self.assertEqual(failed['status'],'failed')
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_clients').fetchone()[0],before)
        applied=self.request('/api/v3/excel-import-apply',self.tokens[1],apply_body)['data']
        self.assertEqual(applied['status'],'applied')
        retry=self.request('/api/v3/excel-import-apply',self.tokens[1],apply_body)['data'];self.assertEqual(applied,retry)
        self.get('excel-import-result?id='+applied['import_id'],self.tokens[2],status=400)
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            with self.assertRaises(self.pg.errors.RaiseException):conn.execute("UPDATE portal_excel_imports SET status='failed',applied_at=NULL WHERE import_id=?",(applied['import_id'],))
