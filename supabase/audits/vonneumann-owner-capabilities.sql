-- Read-only metadata for the future dedicated v5 owner/credential design.
-- Verify The Dashboard/fxpxsciltakyypunglzr/cqfnnaunmupdyobkyqfo first.
-- No credentials, row identities, function bodies or unrestricted settings.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='15s';
SELECT jsonb_build_object(
 'session',jsonb_build_object('read_only',current_setting('transaction_read_only'),
   'isolation',current_setting('transaction_isolation'),'statement_timeout',current_setting('statement_timeout'),
   'lock_timeout',current_setting('lock_timeout'),'postgres_version',current_setting('server_version'),
   'executor_role',current_user,'executor_session_role',session_user),
 'installation_roles',(SELECT jsonb_agg(jsonb_build_object('name',rolname,'superuser',rolsuper,
   'create_role',rolcreaterole,'create_db',rolcreatedb,'bypass_rls',rolbypassrls,'inherit',rolinherit,
   'auth_schema_usage',has_schema_privilege(oid,'auth','USAGE'),
   'auth_schema_usage_grantable',has_schema_privilege(oid,'auth','USAGE WITH GRANT OPTION'),
   'uid_execute',has_function_privilege(oid,'auth.uid()','EXECUTE'),
   'uid_execute_grantable',has_function_privilege(oid,'auth.uid()','EXECUTE WITH GRANT OPTION'),
   'auth_user_id_references_grantable',has_column_privilege(oid,'auth.users','id','REFERENCES WITH GRANT OPTION'),
   'auth_user_id_references',has_column_privilege(oid,'auth.users','id','REFERENCES'),
   'set_postgres',pg_has_role(oid,'postgres','SET')) ORDER BY rolname)
   FROM pg_roles WHERE rolname IN ('postgres','supabase_admin','vn_contract_owner')),
 'private_owner_present',EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_contract_owner'),
 'api_role_admin_or_create',(SELECT jsonb_agg(jsonb_build_object('name',r.rolname,
   'create_role',r.rolcreaterole,'create_db',r.rolcreatedb,'replication',r.rolreplication,
   'admin_memberships', (SELECT count(*) FROM pg_auth_members m WHERE m.member=r.oid AND m.admin_option))
   ORDER BY r.rolname) FROM pg_roles r WHERE r.rolname IN ('anon','authenticated','service_role','authenticator'))
) AS inventory;
ROLLBACK;
