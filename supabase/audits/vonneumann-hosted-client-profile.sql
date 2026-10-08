-- Exact The Dashboard / fxpxsciltakyypunglzr only; verify provider IDs outside SQL.
-- Read-only bounded metadata, no application rows/passwords/role verifiers or persistent DDL.
-- Exact Dashboard only; metadata, never application rows/credentials.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL lock_timeout='1s';
SET LOCAL statement_timeout='15s';
SELECT jsonb_build_object(
 'session',jsonb_build_object('read_only',current_setting('transaction_read_only'),
  'isolation',current_setting('transaction_isolation'),'statement_timeout',current_setting('statement_timeout'),
  'lock_timeout',current_setting('lock_timeout'),'postgres_version',current_setting('server_version'),
  'role',current_user,'session_role',session_user,'authentication',system_user,
  'tcp',inet_client_addr() IS NOT NULL,
  'ssl',(SELECT jsonb_build_object('enabled',ssl,'protocol',version,'cipher',cipher,'bits',bits)
   FROM pg_stat_ssl WHERE pid=pg_backend_pid())),
 'settings',(SELECT jsonb_object_agg(name,setting) FROM pg_settings
  WHERE name IN ('ssl','ssl_min_protocol_version','ssl_max_protocol_version','password_encryption',
   'max_connections','superuser_reserved_connections','reserved_connections')),
 'candidate_state',jsonb_build_object(
  'durability_schema',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='vn_durability'),
  'read_schema',EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='vn_read'),
  'private_owner',EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_contract_owner'),
  'economic_role',EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_economic'),
  'relay_role',EXISTS(SELECT 1 FROM pg_roles WHERE rolname='vn_relay'),
  'native_role_count',(SELECT count(*) FROM pg_roles WHERE rolname ~ '^vn_native_[a-f0-9]{32}$')),
 'client_inventory',(SELECT coalesce(jsonb_agg(to_jsonb(grouped)),'[]'::jsonb) FROM (
  SELECT CASE WHEN a.usename IN ('postgres','authenticator','supabase_auth_admin','supabase_storage_admin','supabase_admin','pgbouncer') THEN a.usename ELSE 'other_role' END AS role_category,
   CASE WHEN a.application_name ILIKE '%postgrest%' THEN 'postgrest'
    WHEN a.application_name ILIKE '%supavisor%' THEN 'supavisor'
    WHEN a.application_name ILIKE '%pgbouncer%' THEN 'pgbouncer'
    WHEN a.application_name='' THEN 'unnamed' ELSE 'other_application' END AS application_category,
   CASE WHEN a.client_addr IS NULL THEN 'local_or_hidden' WHEN s.ssl IS TRUE THEN 'tls' WHEN s.ssl IS FALSE THEN 'plaintext' ELSE 'unknown' END AS transport,
   count(*)::integer AS connections
  FROM pg_stat_activity a LEFT JOIN pg_stat_ssl s ON s.pid=a.pid
  WHERE a.backend_type='client backend'
  GROUP BY 1,2,3 ORDER BY 1,2,3) grouped),
 'migration_versions',(SELECT coalesce(jsonb_agg(version ORDER BY version),'[]'::jsonb)
   FROM supabase_migrations.schema_migrations)
) AS inventory;
ROLLBACK;
