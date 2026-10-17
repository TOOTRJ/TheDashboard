import hashlib
import random
import unittest

from vonneumann.research.retention_manifest import (
    KINDS, MAX_ARTIFACT_BYTES, RetainedArtifact, RetentionReport, RetentionReportError, build_retention_report,
)

OWNER = '10000000-0000-4000-8000-000000000001'
RUN = '20000000-0000-4000-8000-000000000002'


class RetentionManifestTests(unittest.TestCase):
    def report(self, artifacts):
        return build_retention_report(OWNER, RUN, tuple(artifacts))

    def test_every_required_class_is_protected_even_with_no_incoming_reference(self):
        report = self.report([RetainedArtifact(kind, kind.encode()) for kind in KINDS])
        data = report.to_dict()
        self.assertEqual(data['missing_artifact_classes'], [])
        self.assertFalse(data['inventory_complete'])
        self.assertFalse(report.deletion_authority)
        self.assertTrue(all(row['disposition'] == 'retain' and not row['eligible_for_deletion']
                            for row in data['artifacts']))
        self.assertIsNone(data['actual_table_toast_index_wal_bytes'])

    def test_exact_shared_wire_is_counted_as_descriptors_and_unique_blobs_separately(self):
        wire = b'original request bytes'
        data = self.report([RetainedArtifact('original_command', wire),
                            RetainedArtifact('pending_request', wire)]).to_dict()
        self.assertEqual(data['supplied_wire_bytes'], len(wire) * 2)
        self.assertEqual(data['unique_blob_wire_bytes'], len(wire))
        self.assertEqual(data['unique_blob_count'], 1)
        self.assertFalse(data['wire_bytes_are_database_storage'])

    def test_references_protect_dependencies_and_missing_links_are_explicit(self):
        block = RetainedArtifact('dependency_component', b'full immutable component')
        missing = hashlib.sha256(b'not supplied').hexdigest()
        manifest = RetainedArtifact('checkpoint_manifest', b'full original manifest', (block.sha256, missing))
        data = self.report([manifest, block]).to_dict()
        self.assertEqual(data['missing_referenced_digests'], [missing])
        component = next(row for row in data['artifacts'] if row['kind'] == 'dependency_component')
        self.assertIn('referenced_retained_artifact', component['protected_reasons'])
        self.assertFalse(data['eligible_for_deletion'])

    def test_input_order_and_reference_order_do_not_change_the_report_identity(self):
        a, b = RetainedArtifact('receipt', b'full receipt'), RetainedArtifact('identity_ledger', b'identity snapshot')
        manifest = RetainedArtifact('checkpoint_manifest', b'original manifest', (a.sha256, b.sha256))
        reversed_refs = RetainedArtifact(manifest.kind, manifest.wire, tuple(reversed(manifest.references)))
        self.assertEqual(self.report([a, b, manifest]).report_id,
                         self.report([reversed_refs, b, a]).report_id)
        self.assertNotEqual(self.report([a]).report_id, self.report([RetainedArtifact(a.kind, a.wire+b'changed')]).report_id)

    def test_report_values_do_not_mutate_retained_bytes_or_later_reports(self):
        item = RetainedArtifact('worker_control_identity', b'original Start and Stop IDs')
        report = self.report([item]); first = report.to_dict()
        first['artifacts'][0]['eligible_for_deletion'] = True
        self.assertFalse(report.to_dict()['artifacts'][0]['eligible_for_deletion'])
        self.assertEqual(item.wire, b'original Start and Stop IDs')

    def test_refuses_unknown_mutable_duplicate_or_oversized_inputs(self):
        for args in [('future-kind', b'x'), ('receipt', bytearray(b'x')),
                     ('receipt', b''), ('receipt', b'x' * (MAX_ARTIFACT_BYTES+1)),
                     ('receipt', b'x', ['a'*64]), ('receipt', b'x', ('bad',)),
                     ('receipt', b'x', ('a'*64, 'a'*64))]:
            with self.assertRaises(RetentionReportError): RetainedArtifact(*args)
        item = RetainedArtifact('receipt', b'x')
        for inventory in ([], (), [item], (item, item)):
            with self.assertRaises(RetentionReportError): build_retention_report(OWNER, RUN, inventory)
        with self.assertRaises(RetentionReportError): build_retention_report(OWNER.replace('-', ''), RUN, (item,))
        with self.assertRaises(RetentionReportError): RetentionReport(b'{"deletion_authority":true}')
        with self.assertRaises(TypeError): KINDS['future-kind'] = 'future reason'

    def test_seeded_inventory_properties_always_retain_all_exact_supplied_bytes(self):
        rng = random.Random(20261013)
        for count in range(1, 65):
            items = tuple(RetainedArtifact(rng.choice(tuple(KINDS)), rng.randbytes(rng.randint(1, 128)))
                          for _ in range(count))
            report = self.report(items); data = report.to_dict()
            self.assertEqual(data['supplied_wire_bytes'], sum(len(item.wire) for item in items))
            self.assertEqual({row['sha256'] for row in data['artifacts']}, {item.sha256 for item in items})
            self.assertFalse(data['eligible_for_deletion'])
            self.assertFalse(data['restoration_authority'])
            self.assertFalse(data['hosted_authority'])
            self.assertTrue(all(not row['eligible_for_deletion'] for row in data['artifacts']))


if __name__ == '__main__': unittest.main()
