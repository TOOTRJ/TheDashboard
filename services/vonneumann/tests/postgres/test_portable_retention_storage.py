"""Measure retained original-v2 rows in one owned, non-pruning native trace.

This test borrows only native fixture construction and command helpers. It never
calls that fixture's per-test reset, copies a semantic head, or deletes a row.
The measured trace is synthetic bootstrap plus 32 data-free controls; it is not
a price-volume, provider, hosted load, restoration, or pruning acceptance test.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
OPT_IN = 'DASHBOARD_ISOLATED_POSTGRES_TESTS'
TABLES = (
    'vn_portable_native_research.actor_bindings',
    'vn_portable_native_research.package_manifest',
    'vn_portable_native_research.runs',
    'vn_portable_native_research.commands',
    'vn_portable_native_research.dependency_pins',
    'vn_portable_native_research.active_projection',
    'vn_portable_native_research.history_projection',
    'vn_portable_native_research.events',
    'vn_portable_semantic_research.accepted_heads',
    'vn_portable_semantic_research.accepted_commands',
    'vn_portable_economic_research.allocated',
    'vn_portable_dependency_research.components',
    'vn_portable_dependency_research.checkpoints',
)
WIRE_COLUMNS = (
    ('vn_portable_semantic_research.accepted_commands', 'command_wire'),
    ('vn_portable_dependency_research.components', 'wire'),
    ('vn_portable_dependency_research.checkpoints', 'manifest_wire'),
    ('vn_portable_native_research.active_projection', 'resolved_wire'),
    ('vn_portable_native_research.history_projection', 'history_wire'),
    ('vn_portable_native_research.events', 'event_wire'),
)


@unittest.skipUnless(os.environ.get(OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class PortableRetentionStorageTests(unittest.TestCase):
    measurement = None

    @classmethod
    def setUpClass(cls):
        # Import inside opted-in setup. No module-level TestCase alias causes
        # unittest discovery to rerun the complete native suite.
        from tests.postgres import test_portable_native as native
        cls.native = native
        native.PortableNativeSqlTests.setUpClass()
        cls.fixture = native.PortableNativeSqlTests(methodName='runTest')

    @classmethod
    def tearDownClass(cls):
        cls.native.PortableNativeSqlTests.tearDownClass()

    def measure_storage(self):
        """Operator-only, read-only query restricted to 13 owned fixture tables."""
        literal = self.native.literal
        table_rows = []
        for table in TABLES:
            table_rows.append(
                "SELECT jsonb_build_object('table'," + literal(table) + ","
                "'rows',(SELECT count(*) FROM " + table + "),"
                "'heap_main_bytes',pg_catalog.pg_relation_size(c.oid,'main'),"
                "'heap_fsm_bytes',pg_catalog.pg_relation_size(c.oid,'fsm'),"
                "'heap_vm_bytes',pg_catalog.pg_relation_size(c.oid,'vm'),"
                "'indexes_bytes',pg_catalog.pg_indexes_size(c.oid),"
                "'toast_total_bytes',CASE WHEN c.reltoastrelid=0 THEN 0 ELSE "
                "pg_catalog.pg_total_relation_size(c.reltoastrelid) END,"
                "'table_including_toast_auxiliary_bytes',pg_catalog.pg_table_size(c.oid),"
                "'total_relation_bytes',pg_catalog.pg_total_relation_size(c.oid)) value "
                "FROM pg_catalog.pg_class c WHERE c.oid=" + literal(table) + "::regclass"
            )
        wire_rows = [
            "SELECT jsonb_build_object('table'," + literal(table) + ", 'column'," + literal(column) +
            ", 'wire_bytes',coalesce(sum(octet_length(" + column + ")),0)) value FROM " + table
            for table, column in WIRE_COLUMNS
        ]
        sql = """BEGIN READ ONLY;
          SELECT jsonb_build_object(
          'tables',(SELECT jsonb_agg(value ORDER BY value->>'table') FROM (""" + \
            ' UNION ALL '.join(table_rows) + """ ) t),
          'selected_text_columns',(SELECT jsonb_agg(value ORDER BY value->>'table') FROM (""" + \
            ' UNION ALL '.join(wire_rows) + """ ) t),
          'native_run',(SELECT jsonb_build_object('revision',revision,'status',status,
            'commands',commands,'logical_charge_bytes',used_bytes)
            FROM vn_portable_native_research.runs),
          'missing_pin_rows',(SELECT count(*) FROM vn_portable_native_research.dependency_pins p
            LEFT JOIN vn_portable_dependency_research.components c
              ON c.owner_id=p.owner_id AND c.run_id=p.run_id AND c.sha256=p.sha256
            WHERE c.sha256 IS NULL)); COMMIT;"""
        result = json.loads(self.fixture.db.scalar(sql))
        self.assertEqual(len(result['tables']), len(TABLES))
        for row in result['tables']:
            self.assertEqual(row['total_relation_bytes'], row['table_including_toast_auxiliary_bytes'] + row['indexes_bytes'])
            self.assertGreaterEqual(row['table_including_toast_auxiliary_bytes'], row['heap_main_bytes'] + row['toast_total_bytes'])
        self.assertEqual(result['missing_pin_rows'], 0)
        result['totals'] = {
            key: sum(row[key] for row in result['tables'])
            for key in ('heap_main_bytes', 'heap_fsm_bytes', 'heap_vm_bytes', 'indexes_bytes',
                        'toast_total_bytes', 'table_including_toast_auxiliary_bytes', 'total_relation_bytes')
        }
        result['totals']['selected_text_column_wire_bytes'] = sum(row['wire_bytes'] for row in result['selected_text_columns'])
        return result

    def heartbeat(self, expected_revision):
        n = self.native
        reply = json.loads(self.fixture.db.scalar(
            'SELECT vn_portable_native_research.heartbeat(' + ','.join((
                n.literal(n.OWNER), n.literal(n.RUN), n.literal(n.WORKER), '1', '60')) + ');', role=n.ACTOR))
        self.assertEqual(reply['revision'], str(expected_revision))
        self.assertEqual(reply['fence'], '1')
        self.assertFalse(reply['hosted_authority'])

    def verify_retained(self, rows, expected_current_revision):
        """Read every accepted original ID and its 13 exact immutable pins."""
        result = []
        for row in rows:
            observed = self.fixture.read(row)
            self.assertTrue(observed['found'])
            self.assertEqual(observed['original_command_wire'].encode(), row[2])
            receipt = observed['receipt']
            self.assertTrue(receipt['record_observed'])
            self.assertFalse(receipt['pending_until_commit'])
            self.assertIsNotNone(receipt['guard_observed_at'])
            for flag in ('hosted_authority', 'restoration_authority', 'final_visible_instant_freshness'):
                self.assertFalse(receipt[flag])
            envelope = self.fixture.checkpoint(row)
            self.assertEqual(envelope['receipt'], receipt)
            self.assertEqual(envelope['current_revision'], str(expected_current_revision))
            self.assertEqual(envelope['manifest_wire'].encode(), self.native.numbers.encode(row[1].to_dict()))
            self.assertEqual([value.encode() for value in envelope['component_wires']],
                             [block._wire for block in row[1].components])
            self.assertEqual(len(envelope['component_wires']), 13)
            self.assertFalse(envelope['pending_command_authority'])
            self.assertFalse(envelope['restoration_authority'])
            self.assertFalse(envelope['hosted_authority'])
            result.append({'revision': row[0].state.revision,
                           'command_sha256': hashlib.sha256(row[2]).hexdigest(),
                           'manifest_sha256': self.fixture.manifest_sha(row),
                           'pins': 13,
                           'native_package_sha256': receipt['native_package_sha256'],
                           'semantic_validator_sha256': receipt['semantic_validator_sha256']})
        return result

    def test_retains_exact_originals_and_pins_while_measuring_actual_storage(self):
        started = time.monotonic()
        model_contract_path = ROOT / 'research/portable-sql-source-contract.json'
        # This source contract records the pre-cache measurement. Keep it exact;
        # bind the two implementation changes through the separately reviewed
        # lineage rather than rewriting that historical receipt.
        self.assertEqual(hashlib.sha256(model_contract_path.read_bytes()).hexdigest(),
                         '7dff960f6c0c88b5aa7b1cb9f80438d3662fab188eeda9ab485d6b046c08944c')
        historical_sources = json.loads(model_contract_path.read_text())['portable_model_sources_sha256']
        lineage_path = ROOT / 'research/owned-checkpoint-cache-source-lineage.json'
        self.assertEqual(hashlib.sha256(lineage_path.read_bytes()).hexdigest(),
                         'af0a494726b242fb110b591366e933ad6cfe2dfee68dc8c70934f353498f3869')
        lineage = json.loads(lineage_path.read_text())
        changed = {'vonneumann/research/portable_partitioned_checkpoint.py',
                   'vonneumann/research/provider_portable_checkpoint.py'}
        self.assertEqual(len(historical_sources), 10)
        self.assertTrue(changed <= set(historical_sources))
        model_sources = dict(historical_sources)
        for path in changed:
            self.assertEqual(historical_sources[path], lineage['source_before'][path])
            self.assertNotEqual(lineage['source_before'][path], lineage['source_after'][path])
            model_sources[path] = lineage['source_after'][path]
        for path, digest in model_sources.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        baseline = self.measure_storage()
        self.assertTrue(all(row['rows'] == (2 if row['table'].endswith('.actor_bindings') else
                                            1 if row['table'].endswith('.package_manifest') else 0)
                            for row in baseline['tables']))
        self.fixture.create()
        row = self.fixture.bootstrap()
        # No measurement, journal copying, or expensive work consumes the real
        # five-second receipt window between bootstrap construction and COMMIT.
        self.fixture.commit(row[2])
        rows = [row]
        selected = []
        immutable_blocks = {}
        original_events = 0
        allocations = self.native.numbers.decode(row[2])['history']['allocated_ids']
        identity_before = json.loads(self.fixture.db.scalar(
            "BEGIN READ ONLY; SELECT jsonb_agg(to_jsonb(a) ORDER BY id) "
            "FROM vn_portable_economic_research.allocated a; COMMIT;"))

        def check_trace(control_count):
            current = rows[-1]
            checked = self.verify_retained(rows, current[0].state.revision)
            storage = self.measure_storage()
            counts = {item['table']: item['rows'] for item in storage['tables']}
            accepted = len(rows)
            for table in ('vn_portable_native_research.commands',
                          'vn_portable_semantic_research.accepted_commands',
                          'vn_portable_native_research.history_projection'):
                self.assertEqual(counts[table], accepted)
            self.assertEqual(counts['vn_portable_native_research.dependency_pins'], 13 * accepted)
            self.assertEqual(counts['vn_portable_native_research.active_projection'], 1)
            self.assertEqual(counts['vn_portable_dependency_research.checkpoints'], 1)
            self.assertEqual(counts['vn_portable_semantic_research.accepted_heads'], 1)
            self.assertEqual(counts['vn_portable_dependency_research.components'], len(immutable_blocks))
            self.assertEqual(counts['vn_portable_native_research.events'], original_events)
            self.assertEqual(storage['native_run']['commands'], accepted)
            self.assertEqual(storage['native_run']['revision'], current[0].state.revision)
            wire_sums = {(item['table'], item['column']): item['wire_bytes'] for item in storage['selected_text_columns']}
            self.assertEqual(wire_sums[WIRE_COLUMNS[0]], sum(len(item[2]) for item in rows))
            self.assertEqual(wire_sums[WIRE_COLUMNS[1]], sum(len(value) for value in immutable_blocks.values()))
            identities = json.loads(self.fixture.db.scalar(
                "BEGIN READ ONLY; SELECT jsonb_agg(to_jsonb(a) ORDER BY id) "
                "FROM vn_portable_economic_research.allocated a; COMMIT;"))
            self.assertEqual(identities, identity_before)
            lookup = json.loads(self.fixture.db.scalar(self.fixture.lookup(current, [item['id'] for item in identities]), role=self.native.ACTOR))
            self.assertTrue(all(value['used'] for value in lookup['identities'].values()))
            self.assertEqual(len(lookup['identities']), len(identities))
            self.assertFalse(lookup['restoration_authority'])
            self.assertFalse(lookup['hosted_authority'])
            for identity in identities:
                self.assertEqual(lookup['identities'][identity['id']],
                                 {'used': True, 'kind': identity['kind'],
                                  'born_revision': str(identity['born_revision'])})
            selected.append({'controls': control_count, 'readbacks': checked, 'storage': storage})

        def record_original(current):
            nonlocal original_events
            document = self.native.numbers.decode(current[2])
            original_events += len(document['events'])
            self.assertFalse(current[0].state.to_dict()['positions'])
            for component in current[1].components:
                digest = hashlib.sha256(component._wire).hexdigest()
                if digest in immutable_blocks:
                    self.assertEqual(immutable_blocks[digest], component._wire)
                immutable_blocks[digest] = component._wire

        record_original(row)
        check_trace(0)
        for index in range(1, 33):
            if index in (1, 9, 17, 25):
                self.heartbeat(row[0].state.revision)
            action = 'stop' if index == 32 else 'pause' if index % 2 else 'resume'
            row = self.fixture.control(row, action, serial=100 + index)
            self.assertEqual(self.native.numbers.decode(row[2])['evidence']['kind'], 'control')
            self.fixture.commit(row[2])
            rows.append(row)
            record_original(row)
            if index in (8, 16, 32):
                check_trace(index)
        self.assertEqual(row[0].state.to_dict()['status'], 'stopped')
        self.assertEqual(len(identity_before), len(allocations))
        self.assertLess(selected[-1]['storage']['native_run']['logical_charge_bytes'], 8388608)
        source_paths = ['tests/postgres/test_portable_retention_storage.py',
                        'tests/postgres/test_portable_native.py', 'tests/postgres/harness.py',
                        'db-contract/research/portable_native.sql',
                        'research/portable-sql-source-contract.json',
                        'research/owned-checkpoint-cache-source-lineage.json'] + list(model_sources) + [
                            'db-contract/research/' + filename for filename, _, _ in self.native.FILES]
        type(self).measurement = {
            'format': 'ga-portable-retained-storage-measurement-lab-v1',
            'accepted': True, 'date_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'one genuine native accepted synthetic-bootstrap trace plus 32 data-free controls; final Stop while flat',
            'fixture': dict(self.fixture.db.identity), 'python': platform.python_version(),
            'controls': 32, 'accepted_commands': 33, 'selected_checkpoints': [0, 8, 16, 32],
            'original_id_and_13_pin_readbacks': sum(len(item['readbacks']) for item in selected),
            'identity_allocations_retained': len(identity_before),
            'baseline_storage': baseline, 'selected': selected,
            'seconds': round(time.monotonic() - started, 6),
            'source_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in source_paths},
            'limits': {'ordinary_commands': 127, 'ordinary_logical_charge_bytes': 8388608,
                       'reserved_stop_command': 128, 'reserved_stop_total_logical_charge_bytes': 9707520},
            'authority': {flag: False for flag in ('retention_deletion', 'pruning', 'hosted',
                          'native_production_admission', 'restoration', 'real_provider',
                          'representative_load', 'physical_crash_durability', 'profitability')},
            'notes': [
                'Historical source contract stays exact; the current two checkpoint implementation hashes are bound by the reviewed cache lineage.',
                'No per-test reset, DELETE, pruning, semantic-head copy, source-window relaxation, or original-ID conflict retry.',
                'Storage is measured for these 13 owned tables only; selected exact TEXT column bytes are not full row/storage bytes.',
                'pg_table_size includes TOAST and auxiliary forks; total equals that value plus pg_indexes_size. Do not add TOAST twice.',
                'Relations include page allocation and dead tuples from ordinary projection/head/run UPDATEs; no VACUUM was issued.',
                'Native logical charge is a bounded accounting policy, not physical heap/index/TOAST/WAL storage.',
                'WAL, replicas, backups, physical crash behavior, cloud billing, market-load growth and a deletion transaction remain unmeasured.',
                'Elapsed time is a contended local mechanics observation, not a throughput, latency, or hosted-load benchmark.',
            ],
        }


if __name__ == '__main__':
    unittest.main()
