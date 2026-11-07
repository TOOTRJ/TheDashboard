-- Owned synthetic V18 fixture, exact success hook only. No production use.
BEGIN READ ONLY;
SET LOCAL search_path = pg_catalog, pg_temp;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '3000ms';
SET LOCAL transaction_timeout = '4000ms';

WITH relation_manifest(relation_name, relation_oid) AS MATERIALIZED (VALUES
  ('package_inputs', 'vn_jupiter_b2_fixture_anchor.package_inputs'::pg_catalog.regclass),
  ('actor_bindings', 'vn_jupiter_b2_fixture_anchor.actor_bindings'::pg_catalog.regclass),
  ('scope_state', 'vn_jupiter_b2_allocation_research_v3.scope_state'::pg_catalog.regclass),
  ('original_operations', 'vn_jupiter_b2_allocation_research_v3.original_operations'::pg_catalog.regclass),
  ('journal_entries', 'vn_jupiter_b2_allocation_research_v3.journal_entries'::pg_catalog.regclass),
  ('identities', 'vn_jupiter_b2_allocation_research_v3.identities'::pg_catalog.regclass),
  ('domain_facts', 'vn_jupiter_b2_allocation_research_v3.domain_facts'::pg_catalog.regclass),
  ('dependency_associations', 'vn_jupiter_b2_allocation_research_v3.dependency_associations'::pg_catalog.regclass)
),
measured_scope AS MATERIALIZED (
  SELECT scope_wire, head_wire::pg_catalog.jsonb AS head,
         accounting_wire::pg_catalog.jsonb AS accounting
  FROM vn_jupiter_b2_allocation_research_v3.scope_state
  WHERE head_wire::pg_catalog.jsonb->>'source_mode' = 'stopped'
    AND head_wire::pg_catalog.jsonb->>'native_sequence' = '16'
    AND head_wire::pg_catalog.jsonb->'active_fence_id' = 'null'::pg_catalog.jsonb
    AND head_wire::pg_catalog.jsonb->>'fence_revision' = '14'
),
physical AS MATERIALIZED (
  SELECT r.relation_name,
    pg_catalog.pg_relation_size(r.relation_oid, 'main') AS heap_main_bytes,
    pg_catalog.pg_relation_size(r.relation_oid, 'fsm') AS heap_fsm_bytes,
    pg_catalog.pg_relation_size(r.relation_oid, 'vm') AS heap_vm_bytes,
    pg_catalog.pg_relation_size(r.relation_oid, 'init') AS heap_init_bytes,
    pg_catalog.pg_indexes_size(r.relation_oid) AS base_indexes_bytes,
    CASE WHEN c.reltoastrelid = 0::pg_catalog.oid THEN 0::pg_catalog.int8
      ELSE pg_catalog.pg_total_relation_size(c.reltoastrelid::pg_catalog.regclass)
    END AS toast_all_forks_and_indexes_bytes,
    pg_catalog.pg_table_size(r.relation_oid) AS table_including_toast_bytes,
    pg_catalog.pg_total_relation_size(r.relation_oid) AS relation_total_bytes
  FROM relation_manifest r
  JOIN pg_catalog.pg_class c ON c.oid = r.relation_oid
  WHERE c.relkind = 'r' AND c.relpersistence = 'p'
),
logical(relation_name, whole_visible_rows, stopped_scope_rows, stopped_scope_stored_canonical_text_bytes) AS MATERIALIZED (
  SELECT 'package_inputs', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0) + COALESCE(pg_catalog.octet_length(package_wire), 0) + COALESCE(pg_catalog.octet_length(actor_manifest_wire), 0) + COALESCE(pg_catalog.octet_length(genesis_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_fixture_anchor.package_inputs
  UNION ALL
  SELECT 'actor_bindings', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0) + COALESCE(pg_catalog.octet_length(binding_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_fixture_anchor.actor_bindings
  UNION ALL
  SELECT 'scope_state', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0) + COALESCE(pg_catalog.octet_length(head_wire), 0) + COALESCE(pg_catalog.octet_length(accounting_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_allocation_research_v3.scope_state
  UNION ALL
  SELECT 'original_operations', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0) + COALESCE(pg_catalog.octet_length(command_wire), 0) + COALESCE(pg_catalog.octet_length(result_wire), 0) + COALESCE(pg_catalog.octet_length(receipt_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_allocation_research_v3.original_operations
  UNION ALL
  SELECT 'journal_entries', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0) + COALESCE(pg_catalog.octet_length(journal_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_allocation_research_v3.journal_entries
  UNION ALL
  SELECT 'identities', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0) + COALESCE(pg_catalog.octet_length(record_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_allocation_research_v3.identities
  UNION ALL
  SELECT 'domain_facts', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0) + COALESCE(pg_catalog.octet_length(original_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_allocation_research_v3.domain_facts
  UNION ALL
  SELECT 'dependency_associations', pg_catalog.count(*),
    pg_catalog.count(*) FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)),
    COALESCE(pg_catalog.sum(COALESCE(pg_catalog.octet_length(scope_wire), 0))
      FILTER (WHERE scope_wire = (SELECT scope_wire FROM measured_scope)), 0)
  FROM vn_jupiter_b2_allocation_research_v3.dependency_associations
),
combined AS (
  SELECT p.*, l.whole_visible_rows, l.stopped_scope_rows,
    l.stopped_scope_stored_canonical_text_bytes
  FROM physical p JOIN logical l USING (relation_name)
)
SELECT pg_catalog.jsonb_build_object(
  'format', 'dashboard-v18-owned-fixture-storage-v1',
  'physical_extent', 'eight whole relations, both synthetic scopes',
  'logical_extent', 'unique stopped scope at position 16',
  'measured_scope_count', (SELECT pg_catalog.count(*) FROM measured_scope),
  'server_version_num', pg_catalog.current_setting('server_version_num')::pg_catalog.int4,
  'block_size_bytes', pg_catalog.current_setting('block_size')::pg_catalog.int4,
  'server_encoding', pg_catalog.current_setting('server_encoding'),
  'scope_head', (SELECT pg_catalog.jsonb_build_object(
    'status', head->>'source_mode', 'native_sequence', head->>'native_sequence',
    'fence_revision', head->>'fence_revision') FROM measured_scope),
  'contract_accounting', (SELECT pg_catalog.jsonb_build_object(
    'committed_positions', accounting->>'committed_positions',
    'retained_rows', accounting->>'retained_rows',
    'logical_UTF8_bytes', accounting->>'logical_UTF8_bytes',
    'identity_rows', accounting->>'identity_rows', 'domain_rows', accounting->>'domain_rows',
    'dependency_rows', accounting->>'dependency_rows', 'row_writes', accounting->>'row_writes',
    'index_entries', accounting->>'index_entries',
    'Stop_reserve_consumed', accounting->'Stop_reserve_consumed') FROM measured_scope),
  'tables', (SELECT pg_catalog.jsonb_agg(pg_catalog.to_jsonb(t)
      ORDER BY t.relation_name COLLATE "C") FROM combined t)
);
ROLLBACK;
