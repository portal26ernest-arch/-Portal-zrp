"""Opt-in disposable PostgreSQL fixture: never accepts a production DSN.

Run as the postgres OS user, or set PORTAL_TEST_POSTGRES_ADMIN_DSN to an
explicit isolated test cluster with PORTAL_DOCUMENTS_PG_INTEGRATION=1 (or
PORTAL_WEB_PG_E2E=1 for the same disposable fixture under the Web gate).
Creates a fresh randomly named portal_test_documents_* database, two restricted
roles, synthetic companies and an in-process HTTP handler. Removes only resources
created by this fixture. Normal regression runs skip this isolated live gate.
"""
import base64
import hashlib
import importlib.util
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
 'postgresql_stage4c.sql','postgresql_stage8_documents_excel.sql','postgresql_stage9_invoice_revisions.sql',
 'postgresql_stage10_access_invites.sql')

_WEB_E2E=os.environ.get('PORTAL_WEB_PG_E2E')=='1'
_DOCS_E2E=os.environ.get('PORTAL_DOCUMENTS_PG_INTEGRATION')=='1'
_REAL_PDF=os.environ.get('PORTAL_DOCUMENTS_PG_REAL_PDF')=='1'
@unittest.skipUnless(_DOCS_E2E or _WEB_E2E,'requires disposable local PostgreSQL fixture')
class DocumentsPostgreSQLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        admin_dsn=os.environ.get('PORTAL_TEST_POSTGRES_ADMIN_DSN')
        if not admin_dsn:
            import pwd
            if os.name!='posix' or os.getuid()!=pwd.getpwnam('postgres').pw_uid:
                raise RuntimeError('Set PORTAL_TEST_POSTGRES_ADMIN_DSN for an isolated disposable test cluster')
        else:
            admin_options=conninfo_to_dict(admin_dsn)
            if admin_options.get('user')!='postgres' or admin_options.get('host') not in ('127.0.0.1','localhost','::1') or admin_options.get('hostaddr') not in (None,'127.0.0.1','::1') or admin_options.get('dbname') not in (None,'','postgres'):
                raise RuntimeError('Disposable PostgreSQL admin DSN must target local postgres only')
        cls.make_conninfo=make_conninfo
        cls.pg,cls.sql=psycopg,sql;cls.created_db=False;cls.created_roles=[]
        suffix=secrets.token_hex(6)
        db_prefix='portal_test_web_' if _WEB_E2E else 'portal_test_documents_'
        role_prefix='portal_web_' if _WEB_E2E else 'portal_docs_'
        cls.database=db_prefix+suffix
        cls.roles={'tenant':role_prefix+'t_'+suffix,'control':role_prefix+'c_'+suffix}
        cls.admin_dsn=make_conninfo(admin_dsn,dbname='postgres') if admin_dsn else 'dbname=postgres user=postgres host=/var/run/postgresql'
        cls.super_connection=psycopg.connect(cls.admin_dsn,autocommit=True)
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
            cls.migration('postgresql_stage9_invoice_revisions.sql')
            cls.migration('postgresql_stage10_access_invites.sql')
            with psycopg.connect(make_conninfo(cls.admin_dsn,dbname=cls.database),autocommit=True) as admin:
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
                admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON portal_access_invites TO {}').format(tenant))
                admin.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(tenant))
                admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_bind_company(BIGINT,TEXT) TO {}').format(tenant))
                for table in ('companies','platform_owners','platform_sessions','platform_audit'):
                    admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON {} TO {}').format(sql.Identifier(table),control))
                admin.execute(sql.SQL('GRANT SELECT ON portal_company_keys TO {}').format(control))
                admin.execute(sql.SQL('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}').format(control))
                admin.execute(sql.SQL('GRANT EXECUTE ON FUNCTION portal_provision_company(BIGINT) TO {}').format(control))
                for cid in (1,2):
                    limit=None if cid==1 else 15
                    admin.execute("INSERT INTO companies(id,name,user_limit,created_at,updated_at) VALUES(%s,%s,%s,CURRENT_TIMESTAMP::text,CURRENT_TIMESTAMP::text)",(cid,'Synthetic company '+str(cid),limit))
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
            cls.synthetic_pin=secrets.token_urlsafe(20)
            salt,pin_hash=cls.portal.hash_pin(cls.synthetic_pin)
            for cid in (1,2):
                with cls.portal.tenants.company_scope(cid),cls.portal.db() as conn:
                    r=Repository(conn,cid)
                    r.sql('INSERT INTO employees(company_id,telegram_id,full_name,username) VALUES(?,101,?,?)',(cid,'Synthetic person '+str(cid),'profile'))
                    if cid==2:r.sql("INSERT INTO employees(company_id,telegram_id,full_name,username) VALUES(2,103,'Synthetic existing employee','existing-employee')")
                    r.sql('''INSERT INTO app_users(company_id,id,username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at)
                         VALUES(?,1,'admin','Synthetic admin','admin',101,1,?,?,?,?)''',(cid,salt,pin_hash,utcnow(),utcnow()))
                    r.sql('INSERT INTO employees(company_id,telegram_id,full_name,username) VALUES(?,102,?,?)',(cid,'Synthetic packer '+str(cid),'packer'))
                    r.sql('''INSERT INTO app_users(company_id,id,username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at)
                         VALUES(?,2,'packer','Synthetic packer','packer',102,1,?,?,?,?)''',(cid,salt,pin_hash,utcnow(),utcnow()))
                    r.sql("INSERT INTO portal_clients(company_id,id,name,active,created_at,updated_at) VALUES(?,1,'Synthetic client',1,?,?)",(cid,utcnow(),utcnow()))
                    r.sql("INSERT INTO portal_client_operations(company_id,id,client_id,name,employee_rate,client_rate,created_at,updated_at) VALUES(?,1,1,'Packing',2,5,?,?)",(cid,utcnow(),utcnow()))
                    r.insert('tariffs',dict(client_id=1,operation_id=1,employee_rate=200,client_rate=500,effective_from=utcnow()))
                    cls.tokens[cid]=cls.portal.create_session(conn,1)
                    if cid==1:cls.tokens['company_1_packer']=cls.portal.create_session(conn,2)
                with cls.portal.tenants.company_scope(cid),cls.portal.db() as conn:migrate(conn,cid)
            # A second, independent account/session in company 1 proves that
            # documents are server truth shared across clients, not session state.
            with cls.portal.tenants.company_scope(1),cls.portal.db() as conn:
                r=Repository(conn,1)
                r.sql('INSERT INTO employees(company_id,telegram_id,full_name,username) VALUES(?,103,?,?)',(1,'Synthetic second director','second'))
                r.sql('''INSERT INTO app_users(company_id,id,username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at)
                     VALUES(?,3,'second-director','Synthetic second director','director',103,1,?,?,?,?)''',(1,salt,pin_hash,utcnow(),utcnow()))
                cls.tokens['same_company_second_session']=cls.portal.create_session(conn,3)
            # Only the fixture administrator adjusts sequences after explicit IDs.
            with psycopg.connect(make_conninfo(cls.admin_dsn,dbname=cls.database),autocommit=True) as admin:
                for table in ('app_users','portal_clients','portal_client_operations'):
                    admin.execute(sql.SQL("SELECT setval(pg_get_serial_sequence(%s,'id'),GREATEST((SELECT MAX(id) FROM {}),1),true)").format(sql.Identifier(table)),(table,))
            cls.http=cls.portal.ThreadingHTTPServer(('127.0.0.1',0),legacy.QuietHandler)
            cls.http_thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.http_thread.start()
        except Exception:
            cls.cleanup();raise

    @classmethod
    def migration(cls,name):
        migration_dsn=cls.make_conninfo(cls.admin_dsn,dbname=cls.database)
        result=subprocess.run(['psql','-X','-v','ON_ERROR_STOP=1','-q','--dbname',migration_dsn],
            input=(Path(__file__).parent/'migrations'/name).read_text(encoding='utf-8'),text=True,capture_output=True)
        if result.returncode:raise RuntimeError('Disposable migration failed: '+name)

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
                expected='portal_test_web_' if _WEB_E2E else 'portal_test_documents_'
                if not cls.database.startswith(expected):raise RuntimeError('Unexpected disposable database name')
                cls.super_connection.execute(cls.sql.SQL('DROP DATABASE {}').format(cls.sql.Identifier(cls.database)))
            for role in cls.created_roles:cls.super_connection.execute(cls.sql.SQL('DROP ROLE {}').format(cls.sql.Identifier(role)))
            if cls.created_db and cls.super_connection.execute('SELECT 1 FROM pg_database WHERE datname=%s',(cls.database,)).fetchone():
                raise RuntimeError('Disposable PostgreSQL database cleanup failed')
            for role in cls.created_roles:
                if cls.super_connection.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                    raise RuntimeError('Disposable PostgreSQL role cleanup failed')
            cls.super_connection.close()
        if hasattr(cls,'tmp'):
            temp_path=cls.tmp.name;cls.tmp.cleanup()
            if os.path.exists(temp_path):raise RuntimeError('Disposable PostgreSQL fixture files were not cleaned')
        if hasattr(cls,'admin_dsn'):
            print('Disposable PostgreSQL cleanup verified: db=0 roles=0 temp=0')

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

    def test_document_is_shared_between_independent_same_company_sessions(self):
        """Create/list/download/archive must resolve through the company server ledger."""
        first=self.tokens[1]
        second=self.tokens['same_company_second_session']
        doc=self.upload(first)
        listed=self.get('documents',second)['data']
        self.assertIn(doc['id'],[row['id'] for row in listed])
        metadata=self.get('document-metadata?id='+doc['id'],second)['data']
        self.assertEqual(metadata['company_id'],1)
        file_data=self.get('document-file?id='+doc['id'],second)['data']
        self.assertEqual(base64.b64decode(file_data['file_b64']),b'%PDF-1.4\nSynthetic\n%%EOF\n')
        archived=self.post('documents',dict(action='archive',id=doc['id']),second)['data']
        self.assertEqual(archived['status'],'archived')
        refreshed=self.get('documents?include_archived=true',first)['data']['items']
        self.assertEqual(next(row for row in refreshed if row['id']==doc['id'])['status'],'archived')
        self.get('document-metadata?id='+doc['id'],first)

    def test_secure_invitation_lifecycle_uses_hash_and_tenant_scope(self):
        """Stage 10 invitations remain hash-only, one-time and tenant-scoped on PostgreSQL."""
        body={'action':'create','role':'packer','username':'pg-invite-candidate',
              'display_name':'PG Invite Candidate','request_id':'pg-invite-once'}
        created=self.request('/api/v3/invitations',self.admin,body,method='POST')['data']
        token=created['token'];invite_id=created['invite']['id']
        self.assertTrue(token.startswith('1.'))
        replay=self.request('/api/v3/invitations',self.admin,body,method='POST')['data']
        self.assertEqual(replay['invite']['id'],invite_id)
        self.assertIsNone(replay['token'])
        self.assertTrue(replay['replay'])

        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            digest=hashlib.sha256(token.encode()).hexdigest()
            stored=conn.execute('SELECT token_hash,status FROM portal_access_invites WHERE id=?',(invite_id,)).fetchone()
            self.assertEqual((stored['token_hash'],stored['status']),(digest,'pending'))
            audit=' '.join(row['payload'] for row in conn.execute("SELECT payload FROM portal_production WHERE kind='audit'"))
            self.assertNotIn(token,audit)

        # A separately authenticated tenant cannot see this invite, nor can a
        # forged company header make the first session cross its RLS boundary.
        company_two=self.request('/api/v3/invitations?status=pending',self.tokens[2])['data']['items']
        self.assertNotIn(invite_id,[row['id'] for row in company_two])
        self.request('/api/v3/invitations',self.tokens['company_1_packer'],
                     {'action':'create','role':'packer','username':'forbidden-invite',
                      'display_name':'Forbidden','request_id':'pg-invite-forbidden'},method='POST',status=403)
        self.request('/api/v3/invitations',self.admin,extra_headers={'X-Portal-Company':'2'},status=403)
        self.request('/api/access-invites/accept',body={'token':token,'pin':'6789'},method='POST',
                     extra_headers={'X-Portal-Company':'2'},status=403)

        accepted=self.request('/api/access-invites/accept',body={'token':token,'pin':'6789'},method='POST')['data']
        self.assertEqual(accepted['status'],'pending_approval')
        repeated=self.request('/api/access-invites/accept',body={'token':token,'pin':'9999'},method='POST')['data']
        self.assertEqual(repeated['status'],'pending_approval')
        self.request('/api/v3/invitations',self.tokens[1],{'action':'approve','invite_id':invite_id},method='POST')
        self.request('/api/login',body={'company_id':1,'username':'pg-invite-candidate','pin':'6789'})
        self.request('/api/access-invites/accept',body={'token':token,'pin':'6789'},method='POST',status=403)

        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            self.assertEqual(conn.execute('SELECT status FROM portal_access_invites WHERE id=?',(invite_id,)).fetchone()[0],'approved')
            events=[json.loads(row['payload']) for row in conn.execute(
                "SELECT payload FROM portal_production WHERE kind='audit' AND payload LIKE '%access_invite.%'")]
            self.assertGreaterEqual(len(events),3)
            self.assertTrue(all(token not in json.dumps(event) for event in events))

    def test_invitation_links_existing_employee_without_creating_duplicate_employee(self):
        body={'action':'create','role':'packer','username':'existing-employee-invite',
              'display_name':'Synthetic existing employee','employee_id':103,'request_id':'existing-employee-invite-once'}
        created=self.request('/api/v3/invitations',self.tokens[2],body,method='POST')['data']
        self.assertEqual(created['invite']['employee_id'],103)
        accepted=self.request('/api/access-invites/accept',body={'token':created['token'],'pin':'6789'},method='POST')['data']
        self.assertEqual(accepted['status'],'pending_approval')
        self.request('/api/v3/invitations',self.tokens[2],{'action':'approve','invite_id':created['invite']['id']},method='POST')
        self.request('/api/login',body={'company_id':2,'username':'existing-employee-invite','pin':'6789'})
        with self.portal.tenants.company_scope(2),self.portal.db() as conn:
            users=conn.execute('SELECT telegram_id,active FROM app_users WHERE username=?',('existing-employee-invite',)).fetchone()
            employees=conn.execute("SELECT COUNT(*) FROM employees WHERE company_id=2 AND telegram_id=103").fetchone()[0]
            self.assertEqual(tuple(users),(103,1))
            self.assertEqual(employees,1)

    def test_platform_owner_audit_is_separate_filtered_and_role_gated(self):
        pin=secrets.token_urlsafe(24)
        salt,digest=self.portal.hash_pin(pin)
        with self.pg.connect(type(self).make_conninfo(self.admin_dsn,dbname=self.database),autocommit=True) as admin:
            admin.execute('INSERT INTO platform_owners(id,username,display_name,pin_salt,pin_hash) VALUES(1,%s,%s,%s,%s)',
                          ('synthetic-owner','Synthetic Owner',salt,digest))
        owner=self.request('/api/platform/login',body={'username':'synthetic-owner','pin':pin})['token']
        filtered=self.request('/api/platform/audit?company_id=1&actor_id=1&event=owner_login&page=1&limit=10',owner)
        self.assertEqual(filtered['total'],1)
        self.assertEqual(filtered['rows'][0]['event'],'owner_login')
        self.assertEqual(filtered['rows'][0]['outcome'],'success')
        self.assertNotIn(pin,json.dumps(filtered))
        self.request('/api/platform/audit',self.admin,status=403)
        self.request('/api/platform/audit',self.tokens['company_1_packer'],status=403)
        invite_body={'action':'create','role':'packer','username':'owner-scoped-invite',
                     'display_name':'Owner Scoped Invite','request_id':'owner-scoped-invite-once'}
        self.request('/api/v3/invitations',owner,invite_body,method='POST',status=403)
        selected=self.request('/api/v3/invitations',owner,invite_body,method='POST',
                              extra_headers={'X-Portal-Company':'2'})['data']
        self.assertTrue(selected['token'].startswith('2.'))
        self.assertEqual(selected['invite']['company_id'],2)

    def test_postgresql_api_enforces_standard_active_user_limit(self):
        """The standard company limit is enforced by the server, not just the UI."""
        access=self.request('/api/v3/company-access',self.tokens[2])['data']
        active=access['active_users']
        self.assertGreaterEqual(active,2)
        self.assertEqual((access['user_limit'],access['unlimited']),(15,False))
        with self.pg.connect(type(self).make_conninfo(self.admin_dsn,dbname=self.database),autocommit=True) as admin:
            admin.execute('UPDATE companies SET user_limit=%s WHERE id=2',(active,))
        self.request('/api/users',self.tokens[2],{'username':'over-seat','display_name':'Over Seat',
                     'role':'packer','pin':'5678'},method='POST',status=400)
        self.assertEqual(self.request('/api/v3/company-access',self.tokens[2])['data']['active_users'],active)
        self.request('/api/v3/company-access',self.tokens[1],extra_headers={'X-Portal-Company':'2'},status=403)

    def test_payroll_settlement_role_scope_and_closed_snapshot_over_postgresql(self):
        """Only an authorized same-company actor can append a payout; close snapshots stay immutable."""
        from datetime import date, timedelta
        from production_repository import Repository

        work=self.post('work',dict(client_id=1,operation_id=1,quantity=2),self.tokens[1])['data']
        anchor=date.today()-timedelta(days=180)
        start=anchor.replace(day=1);end=anchor.replace(day=15)
        historical=dict(work,id='pg-settlement-'+work['id'],
                        completed_at=end.isoformat()+'T12:00:00.000000',
                        created_at=end.isoformat()+'T12:00:00.000000')
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            Repository(conn,1).insert('works',{k:v for k,v in historical.items() if k not in {'id','company_id'}},historical['id'])
            conn.commit()
        period=self.post('payroll-periods',dict(period_start=start.isoformat(),period_end=end.isoformat()),self.tokens[1])['data']
        employee_id=period['snapshot']['employees'][0]['employee_id']
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            repo=Repository(conn,1)
            employee_id=repo.payroll_employee(employee_id,legacy=True)['employee_id']
            snapshot_before=repo.get('payroll_periods',period['id'])['snapshot']

        payout_body=dict(payroll_period_id=period['id'],employee_id=employee_id,
                         entry_type='payout',amount='1.00',reason='Disposable PostgreSQL role-flow',
                         request_id='pg-settlement-payout-once')
        self.request('/api/v3/payroll-settlements',self.tokens['company_1_packer'],payout_body,method='POST',status=403)
        payout=self.request('/api/v3/payroll-settlements',self.tokens[1],payout_body,method='POST')['data']
        retry=self.request('/api/v3/payroll-settlements',self.tokens[1],payout_body,method='POST')['data']
        self.assertEqual(payout['id'],retry['id'])
        totals=self.request('/api/v3/payroll-settlements?payroll_period_id='+period['id'],self.tokens[1])['data']['totals']
        self.assertEqual((totals['accrued'],totals['paid'],totals['balance']),(400,100,300))
        self.request('/api/v3/payroll-settlements?payroll_period_id='+period['id'],self.tokens['company_1_packer'],status=403)
        self.request('/api/v3/payroll-settlements?payroll_period_id='+period['id'],self.tokens[2],status=400)
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            repo=Repository(conn,1)
            self.assertEqual(repo.get('payroll_periods',period['id'])['snapshot'],snapshot_before)
            self.assertEqual(conn.execute('SELECT COUNT(*),SUM(amount_minor),typeof(SUM(amount_minor)) FROM payroll_settlement_entries WHERE payroll_period_id=?',(period['id'],)).fetchone()[:],(1,100,'integer'))

    @unittest.skipUnless(_WEB_E2E,'Web browser gate only')
    def test_real_web_static_login_meta_and_company_scope_in_browser(self):
        """Use Chromium against this fixture's real loopback API; no API routes are mocked."""
        import shutil
        node=shutil.which('node')
        if not node:self.skipTest('Node.js is unavailable')
        script=Path(__file__).resolve().parents[1]/'android_src'/'tests'/'web-postgresql.playwright.cjs'
        env=os.environ.copy()
        env.update(PORTAL_WEB_E2E_ORIGIN='http://127.0.0.1:%d'%self.http.server_address[1],
                   PORTAL_WEB_E2E_PIN=self.synthetic_pin,
                   PORTAL_WEB_E2E_COMPANY_A='1',PORTAL_WEB_E2E_COMPANY_B='2')
        result=subprocess.run([node,str(script)],cwd=script.parent,env=env,text=True,capture_output=True,timeout=90)
        self.assertEqual(result.returncode,0,'Browser E2E failed: '+result.stdout+'\n'+result.stderr)

    @unittest.skipUnless(_REAL_PDF and importlib.util.find_spec('reportlab'),
                         'requires ReportLab real PDF PostgreSQL gate')
    def test_real_pdf_renderer_on_postgresql_documents(self):
        from datetime import date,timedelta
        from production_repository import Repository
        from reportlab.pdfbase import pdfmetrics
        work=self.post('work',dict(client_id=1,operation_id=1,quantity=2),self.tokens[1])['data']
        invoice=self.post('invoices',dict(work_ids=[work['id']]),self.tokens[1])['data']
        work_before=self.get('works',self.tokens[1])['data'];invoice_before=self.get('invoices',self.tokens[1])['data']
        invoice_body=dict(document_type='invoice_pdf',invoice_id=invoice['id'])
        invoice_doc=self.post('document-generate',invoice_body,self.tokens[1])['data']
        self.assertEqual(self.post('document-generate',invoice_body,self.tokens[1])['data']['id'],invoice_doc['id'])
        invoice_pdf=base64.b64decode(self.get('document-file?id='+invoice_doc['id'],self.tokens[1])['data']['file_b64'])
        self.assertTrue(invoice_pdf.startswith(b'%PDF-'));self.assertIn(b'%%EOF',invoice_pdf[-2048:]);self.assertIn(b'/MediaBox',invoice_pdf)
        self.assertEqual(self.get('document-metadata?id='+invoice_doc['id'],self.tokens[1])['data']['company_id'],1)
        self.get('document-file?id='+invoice_doc['id'],self.tokens[2],status=400)
        self.assertEqual(self.get('works',self.tokens[1])['data'],work_before);self.assertEqual(self.get('invoices',self.tokens[1])['data'],invoice_before)

        anchor=date.today()-timedelta(days=180)
        start=anchor.replace(day=1);end=anchor.replace(day=15)
        historical=dict(work,id='pg-real-pdf-'+work['id'],completed_at=end.isoformat()+'T12:00:00.000000',created_at=end.isoformat()+'T12:00:00.000000')
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            Repository(conn,1).insert('works',{k:v for k,v in historical.items() if k not in {'id','company_id'}},historical['id']);conn.commit()
        works_for_payroll=self.get('works',self.tokens[1])['data']
        period=self.post('payroll-periods',dict(period_start=start.isoformat(),period_end=end.isoformat()),self.tokens[1])['data']
        employee_id=period['snapshot']['employees'][0]['employee_id']
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            repo=Repository(conn,1);employee_id=repo.payroll_employee(employee_id,legacy=True)['employee_id']
            snapshot_before=repo.get('payroll_periods',period['id'])['snapshot'];settlements_before=repo.payroll_settlements(period['id'],employee_id)
        payroll_body=dict(document_type='payroll_slip_pdf',payroll_period_id=period['id'],employee_id=employee_id)
        payroll_doc=self.post('document-generate',payroll_body,self.tokens[1])['data']
        self.assertEqual(self.post('document-generate',payroll_body,self.tokens[1])['data']['id'],payroll_doc['id'])
        payroll_pdf=base64.b64decode(self.get('document-file?id='+payroll_doc['id'],self.tokens[1])['data']['file_b64'])
        self.assertTrue(payroll_pdf.startswith(b'%PDF-'));self.assertIn(b'%%EOF',payroll_pdf[-2048:]);self.assertIn(b'/MediaBox',payroll_pdf)
        self.assertIn(ord('\u0420'),pdfmetrics.getFont('PortalUnicode').face.charToGlyph)
        self.get('document-file?id='+payroll_doc['id'],self.tokens[2],status=400)
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            repo=Repository(conn,1)
            self.assertEqual(repo.get('payroll_periods',period['id'])['snapshot'],snapshot_before)
            self.assertEqual(repo.payroll_settlements(period['id'],employee_id),settlements_before)
        self.assertEqual(self.get('works',self.tokens[1])['data'],works_for_payroll);self.assertEqual(self.get('invoices',self.tokens[1])['data'],invoice_before)

    def test_generated_invoice_and_payroll_documents_are_company_scoped_and_financially_read_only(self):
        from datetime import date,timedelta
        from production_repository import Repository
        from unittest.mock import patch
        pdf=b'%PDF-1.4\nDisposable PostgreSQL PDF route fixture\n%%EOF\n'
        work=self.post('work',dict(client_id=1,operation_id=1,quantity=2),self.tokens[1])['data']
        invoice=self.post('invoices',dict(work_ids=[work['id']]),self.tokens[1])['data']
        def fake_invoice(*args):return pdf
        def fake_payroll(*args):return pdf
        work_before=self.get('works',self.tokens[1])['data']
        invoice_before=self.get('invoices',self.tokens[1])['data']
        with patch.dict('sys.modules',{'pdf_documents':type('FakePdfRenderer',(),{'invoice_pdf':staticmethod(fake_invoice),'payroll_slip_pdf':staticmethod(fake_payroll)})()}):
            invoice_doc=self.post('document-generate',dict(document_type='invoice_pdf',invoice_id=invoice['id']),self.tokens[1])['data']
            invoice_doc_retry=self.post('document-generate',dict(document_type='invoice_pdf',invoice_id=invoice['id']),self.tokens[1])['data']
            self.assertEqual(invoice_doc['id'],invoice_doc_retry['id'])
            self.assertEqual(base64.b64decode(self.get('document-file?id='+invoice_doc['id'],self.tokens[1])['data']['file_b64']),pdf)
            for document_id in (invoice_doc['id'],invoice_doc_retry['id']):
                self.get('document-file?id='+document_id,self.tokens[2],status=400)
                self.get('document-metadata?id='+document_id,self.tokens[2],status=400)
            self.assertEqual(self.get('works',self.tokens[1])['data'],work_before)
            self.assertEqual(self.get('invoices',self.tokens[1])['data'],invoice_before)

            today=date.today()
            if today.day>15:
                start=today.replace(day=1);end=today.replace(day=15)
            else:
                previous=today.replace(day=1)-timedelta(days=1)
                start=previous.replace(day=16);end=previous
            historical=dict(work,id='pg-pdf-'+work['id'],completed_at=end.isoformat()+'T12:00:00.000000',created_at=end.isoformat()+'T12:00:00.000000')
            with self.portal.tenants.company_scope(1),self.portal.db() as conn:
                Repository(conn,1).insert('works',{k:v for k,v in historical.items() if k not in {'id','company_id'}},historical['id'])
                conn.commit()
            works_for_payroll=self.get('works',self.tokens[1])['data']
            period=self.post('payroll-periods',dict(period_start=start.isoformat(),period_end=end.isoformat()),self.tokens[1])['data']
            employee_id=period['snapshot']['employees'][0]['employee_id']
            with self.portal.tenants.company_scope(1),self.portal.db() as conn:
                repo=Repository(conn,1);employee_id=repo.payroll_employee(employee_id,legacy=True)['employee_id']
                snapshot_before=repo.get('payroll_periods',period['id'])['snapshot']
                settlements_before=repo.payroll_settlements(period['id'],employee_id)
            payroll_body=dict(document_type='payroll_slip_pdf',payroll_period_id=period['id'],employee_id=employee_id)
            payroll_doc=self.post('document-generate',payroll_body,self.tokens[1])['data']
            payroll_retry=self.post('document-generate',payroll_body,self.tokens[1])['data']
            self.assertEqual(payroll_doc['id'],payroll_retry['id'])
            self.assertEqual(base64.b64decode(self.get('document-file?id='+payroll_doc['id'],self.tokens[1])['data']['file_b64']),pdf)
            for document_id in (payroll_doc['id'],payroll_retry['id']):
                self.get('document-file?id='+document_id,self.tokens[2],status=400)
                self.get('document-metadata?id='+document_id,self.tokens[2],status=400)
        with self.portal.tenants.company_scope(1),self.portal.db() as conn:
            repo=Repository(conn,1)
            self.assertEqual(repo.get('payroll_periods',period['id'])['snapshot'],snapshot_before)
            self.assertEqual(repo.payroll_settlements(period['id'],employee_id),settlements_before)
            rows=conn.execute("SELECT document_type,category,company_id,invoice_id,client_id,employee_id,payroll_period_id,metadata,storage_key FROM portal_documents WHERE id IN (?,?,?,?) ORDER BY document_type",(invoice_doc['id'],invoice_doc_retry['id'],payroll_doc['id'],payroll_retry['id'])).fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual({row['company_id'] for row in rows},{1})
            self.assertTrue(all(row['metadata'] and row['storage_key'] for row in rows))
            self.assertEqual(sum(row['document_type']=='invoice_pdf' and row['invoice_id']==invoice['id'] and row['client_id']==invoice['client_id'] for row in rows),1)
            self.assertEqual(sum(row['document_type']=='payroll_slip_pdf' and row['employee_id']==employee_id and row['payroll_period_id']==period['id'] for row in rows),1)
        self.assertEqual(self.get('works',self.tokens[1])['data'],works_for_payroll)
        self.assertEqual(self.get('invoices',self.tokens[1])['data'],invoice_before)

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
