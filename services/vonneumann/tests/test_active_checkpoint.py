"""Actual admitted GA captures; no database, restoration or network authority."""
from copy import deepcopy
import json
import unittest

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_checkpoint_reference import pair
from tests.test_provider_capacity import capacity_trace
from tests.test_provider_contract import (
    OWNER, RUN, WORKER, WALL, MONO, EPOCH, life, kernel, seed_bundle,
    source_inputs, raw_capture, source,
)
from vonneumann.core import exact_rehearsal as base
from vonneumann.db.command_protocol import CommandValidationError, PreparedCommand, canonical_json
from vonneumann.research.active_checkpoint import (
    ActiveCheckpoint, TypedComponent, capture_owned_candidate, component_updates,
    resolve_manifest, MAX_RESOLVED_BYTES, MAX_COMPONENTS,
)


def ga_trace(dense):
    records = []
    result = capacity_trace('genetic_algorithm', dense=dense,
                            observer=lambda candidate, command: records.append(candidate))
    return result, records


class ActiveCheckpointTests(OfflineTestMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with deny_network():
            cls.traces = {dense: ga_trace(dense) for dense in (False, True)}
            cls.pair = pair()

    def resolve(self, manifest, components):
        return resolve_manifest(manifest, components, owner_id=OWNER,
                                run_id=RUN, revision=manifest.get('revision', 3))

    def test_real_sparse_dense_replacements_keep_exact_current_evidence(self):
        for dense, (result, records) in self.traces.items():
            for candidate in records:
                with self.subTest(dense=dense, revision=candidate.state.revision):
                    original_wire = candidate._wire
                    original = candidate.state.to_dict()
                    capture = capture_owned_candidate(candidate)
                    resolved = capture.resolve()
                    ids = {m['id'] for m in original['engine']['members']}
                    self.assertEqual(resolved['accounts'], [a for a in original['accounts'] if a['id'] in ids])
                    self.assertEqual(resolved['positions'], [p for p in original['positions'] if not p['closed']])
                    self.assertEqual(resolved['engine']['members'], original['engine']['members'])
                    for key in ('config', 'optimizer', 'cohort', 'ema', 'lifecycle', 'last_quote', 'decision_timestamp'):
                        self.assertEqual(resolved['engine'][key], original['engine'][key])
                    self.assertEqual(resolved['reserve'], original['reserve'])
                    self.assertEqual(resolved['source'], original['source'])
                    self.assertEqual(len(resolved['accounts']), 8)
                    self.assertLessEqual(len(resolved['positions']), 8)
                    self.assertEqual(len(capture.components), MAX_COMPONENTS)
                    self.assertNotIn('used_ids', resolved['engine'])
                    self.assertNotIn('last_evaluation', resolved['engine'])
                    self.assertNotIn('distribution_id', resolved['engine'])
                    self.assertEqual(candidate._wire, original_wire)
                    self.assertEqual(candidate.state.to_dict(), original)
                    self.assertLess(capture.resolved_bytes, MAX_RESOLVED_BYTES)
            self.assertEqual(result['completed_generation'], 3)
            self.assertIsNone(result['rejection'])
            final = records[-1].state.to_dict()
            self.assertEqual(len(final['accounts']), 32)
            self.assertEqual(len(final['positions']), 48 if dense else 13)

    def test_price_only_capture_reuses_all_components_but_requires_full_readback(self):
        old, new = [capture_owned_candidate(candidate) for candidate in self.pair]
        self.assertEqual(component_updates(old, new), ())
        self.assertEqual({b.identity for b in old.components}, {b.identity for b in new.components})
        self.assertEqual(self.resolve(new.to_dict(), old.components), new.resolve())
        # A pure diff is not a server ACK or permission to discard dependencies.
        with self.assertRaises(CommandValidationError):
            self.resolve(new.to_dict(), component_updates(old, new))

    def test_generation_replacement_reuses_configuration_only(self):
        records = self.traces[True][1]
        index = next(i for i, c in enumerate(records) if c.state.to_dict()['engine']['generation'] == 1)
        previous = capture_owned_candidate(records[index - 1])
        following = capture_owned_candidate(records[index])
        changed = component_updates(previous, following)
        self.assertEqual(len(changed), 10)
        self.assertNotIn('configuration', [c.to_dict()['kind'] for c in changed])
        self.assertEqual(following.resolve()['engine']['generation'], 1)

    def test_retired_early_terminal_members_survive_until_deadline_and_abort(self):
        candidate = next(c for c in self.traces[True][1]
                         if any(not p['closed'] for p in c.state.to_dict()['positions']))
        before = candidate.state.to_dict()
        quote = before['source']['last_quote']
        wall = quote['decision_wall_us'] // 1_000_000 + 1
        mono = quote['decision_monotonic_us'] / 1_000_000 + 1
        frame = source.make_frame(raw_capture(price='0.1', block=quote['quote']['block_ref'] + 1,
            source_second=wall - 2, wall=wall - 1, mono=mono - 1),
            prior_source=before['source'], epoch=EPOCH, wall_now=wall, monotonic_now=mono)
        terminal = life.prepare_protective(candidate.state, frame,
            source_inputs(wall, mono=mono, serial=9000))
        original = terminal.state.to_dict()
        self.assertTrue(any(m['terminal'] is not None for m in original['engine']['members']))
        capture = capture_owned_candidate(terminal)
        active = capture.resolve()
        self.assertEqual(active['engine']['members'], original['engine']['members'])
        self.assertEqual(len(active['accounts']), 8)
        self.assertTrue(any(a['retired'] for a in active['accounts']))
        self.assertEqual(active['engine']['cohort']['phase'], 'evaluating')
        self.assertEqual(active['positions'], [])
        stopped = life.prepare_control(terminal.state, 'stop', source_inputs(wall + 1, mono=mono + 1, serial=9001))
        aborted = capture_owned_candidate(stopped).resolve()
        self.assertEqual(aborted['engine']['cohort']['phase'], 'aborted')
        self.assertEqual(len(aborted['engine']['cohort']['evaluations']), 8)
        self.assertTrue(all(not row['cohort_complete'] for row in aborted['engine']['cohort']['evaluations']))
        self.assertEqual(aborted['engine']['members'], stopped.state.to_dict()['engine']['members'])

    def test_capture_and_component_output_is_detached_and_immutable(self):
        candidate = self.pair[1]
        capture = capture_owned_candidate(candidate)
        manifest = capture.to_dict(); manifest['reserve'] = '0'
        decoded = capture.resolve(); decoded['engine']['members'][0]['genome']['ema_fast'] = 'bad'
        block = capture.components[0]
        body = block.to_dict(); body['body']['initial_cash'] = '0'
        self.assertEqual(capture.resolve()['reserve'], candidate.state.to_dict()['reserve'])
        self.assertNotEqual(block.to_dict()['body']['initial_cash'], '0')
        with self.assertRaises(AttributeError): capture._ActiveCheckpoint__wire = b'changed'
        with self.assertRaises(AttributeError): block._wire = b'changed'
        with self.assertRaises(CommandValidationError): ActiveCheckpoint()

    def test_only_owned_admitted_ga_candidates_can_enter(self):
        for value in (self.pair[0].state, self.pair[0]._wire, self.pair[0].state.to_dict(), None):
            with self.subTest(value=type(value)), self.assertRaises(CommandValidationError):
                capture_owned_candidate(value)
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            'differential_evolution', OWNER, RUN, asset='SOL/USD'), EPOCH)
        different = life.bootstrap(config, seed_bundle(), source_inputs(WALL))
        with self.assertRaisesRegex(CommandValidationError, 'GA-only'):
            capture_owned_candidate(different)

    def test_component_bytes_require_exact_canonical_types_and_slot(self):
        capture = capture_owned_candidate(self.pair[0])
        block = capture.components[0]
        value = block.to_dict()
        variants = [json.dumps(value, indent=2).encode(), b'{"format":1,"format":2}', b'not json']
        for wire in variants:
            with self.subTest(wire=wire[:30]), self.assertRaises(CommandValidationError): TypedComponent(wire)
        for patch in ({'generation': True}, {'hash_policy': 'postgres-jsonb'}, {'kind': 'patch'},
                      {'body': None}, {'extra': 1}, {'owner_id': 'bad'}, {'entity_id': 'other'},
                      {'format': 'ga-typed-component-v2'}):
            with self.subTest(patch=patch), self.assertRaises(CommandValidationError):
                TypedComponent(canonical_json({**value, **patch}))

    def test_wrong_scope_revision_and_model_version_fail_closed(self):
        capture = capture_owned_candidate(self.pair[1])
        manifest = capture.to_dict()
        for patch in ({'owner_id': WORKER}, {'run_id': WORKER}, {'revision': True},
                      {'revision': manifest['revision'] + 1}, {'source_model_version': True},
                      {'source_model_version': 6}, {'format': 'ga-active-checkpoint-v2'}, {'extra': 1}):
            with self.subTest(patch=patch), self.assertRaises(CommandValidationError):
                resolve_manifest({**manifest, **patch}, capture.components, owner_id=OWNER,
                                 run_id=RUN, revision=manifest['revision'])

    def test_missing_extra_duplicate_foreign_and_changed_blocks_fail_closed(self):
        capture = capture_owned_candidate(self.pair[1])
        blocks = capture.components
        value = blocks[0].to_dict()
        foreign = TypedComponent.make(WORKER, RUN, 'configuration', 'configuration', 0, value['body'])
        changed_body = deepcopy(value['body']); changed_body['initial_cash'] = '1001'
        changed = TypedComponent.make(OWNER, RUN, 'configuration', 'configuration', 0, changed_body)
        for altered in (blocks[:-1], blocks + (blocks[0],), (blocks[0],) * 11,
                        (foreign,) + blocks[1:], (changed,) + blocks[1:], list(blocks)):
            with self.subTest(size=len(altered)), self.assertRaises(CommandValidationError):
                self.resolve(capture.to_dict(), altered)

    def test_reference_shape_hash_kind_entity_generation_and_duplicates_are_bound(self):
        capture = capture_owned_candidate(self.pair[1])
        for field, value in (('sha256', 'a' * 64), ('sha256', 'A' * 64), ('kind', 'patch'),
                             ('entity_id', WORKER), ('generation', True), ('generation', 1), ('extra', 1)):
            manifest = capture.to_dict(); manifest['components'][0][field] = value
            with self.subTest(field=field), self.assertRaises(CommandValidationError):
                self.resolve(manifest, capture.components)
        manifest = capture.to_dict(); manifest['components'][1] = manifest['components'][0]
        with self.assertRaises(CommandValidationError): self.resolve(manifest, capture.components)

    def test_valid_rehashed_genome_substitution_disagrees_with_frozen_optimizer(self):
        capture = capture_owned_candidate(self.pair[1])
        manifest = capture.to_dict(); blocks = list(capture.components)
        first, second = blocks[3].to_dict(), blocks[4].to_dict()
        body = deepcopy(second['body']); body['parent_ids'] = first['body']['parent_ids']
        # Choose an actual valid different phenotype so the integrity check is
        # against the frozen optimizer/cohort, not only a malformed hex string.
        body['ema_fast'] = float(3 if float.fromhex(first['body']['ema_fast']) != 3 else 4).hex()
        replaced = TypedComponent.make(OWNER, RUN, 'genome', first['entity_id'], 0, body)
        blocks[3] = replaced; manifest['components'][3] = replaced.reference()
        with self.assertRaises(CommandValidationError): self.resolve(manifest, tuple(blocks))

    def test_missing_member_account_and_historical_fields_are_rejected(self):
        capture = capture_owned_candidate(self.pair[1])
        for change in ('member', 'account', 'terminal', 'used_ids', 'last_evaluation'):
            manifest = capture.to_dict()
            if change == 'member': manifest['engine']['members'].pop()
            elif change == 'account': manifest['accounts'].pop()
            elif change == 'terminal': manifest['accounts'][0]['retired'] = True
            else: manifest['engine'][change] = []
            with self.subTest(change=change), self.assertRaises(CommandValidationError):
                self.resolve(manifest, capture.components)

    def test_corrupt_capture_cannot_omit_a_live_holding_from_admitted_source(self):
        candidate = next(c for c in self.traces[True][1]
                         if any(not p['closed'] for p in c.state.to_dict()['positions']))
        capture = capture_owned_candidate(candidate)
        altered = capture.to_dict(); altered['positions'].pop()
        # Even bypassing Python's immutability does not change the independently
        # captured expected projection of the admitted source checkpoint.
        object.__setattr__(capture, '_ActiveCheckpoint__wire', canonical_json(altered))
        with self.assertRaises(CommandValidationError): capture.resolve()

    def test_flat_components_reject_recursive_configuration_patch(self):
        capture = capture_owned_candidate(self.pair[1])
        manifest = capture.to_dict(); blocks = list(capture.components)
        body = blocks[0].to_dict()['body']; body['component_reference'] = manifest['components'][1]
        replacement = TypedComponent.make(OWNER, RUN, 'configuration', 'configuration', 0, body)
        blocks[0] = replacement; manifest['components'][0] = replacement.reference()
        with self.assertRaises(CommandValidationError): self.resolve(manifest, tuple(blocks))

    def test_component_aggregate_budget_is_checked_before_resolution(self):
        capture = capture_owned_candidate(self.pair[1])
        manifest = capture.to_dict(); blocks = list(capture.components)
        # Each block individually fits. The combined dependency set must fail
        # before an attacker gets eleven full blocks expanded/validated.
        for index in (3, 4):
            value = blocks[index].to_dict()
            body = {'padding': ['x' * 16000] * 8}
            replacement = TypedComponent.make(OWNER, RUN, 'genome', value['entity_id'], 0, body)
            blocks[index] = replacement; manifest['components'][index] = replacement.reference()
        with self.assertRaisesRegex(CommandValidationError, 'aggregate exceeds capacity before resolution'):
            self.resolve(manifest, tuple(blocks))

    def test_structural_work_string_depth_cycle_and_float_limits_fail_early(self):
        capture = capture_owned_candidate(self.pair[1])
        manifest = capture.to_dict()
        for bad in ('x' * 17000, list(range(4097)), [None] * 20001, 2**257, 1.5):
            altered = deepcopy(manifest); altered['padding'] = bad
            with self.subTest(kind=type(bad)), self.assertRaises(CommandValidationError):
                self.resolve(altered, capture.components)
        cyclic = {}; cyclic['cycle'] = cyclic
        with self.assertRaises(CommandValidationError): self.resolve(cyclic, capture.components)
        nested = {}
        for _ in range(66): nested = {'child': nested}
        with self.assertRaises(CommandValidationError): self.resolve(nested, capture.components)

    def test_generation_watermark_and_original_runtime_caps_are_not_lifted(self):
        capture = capture_owned_candidate(self.pair[1])
        manifest = capture.to_dict(); manifest['engine']['generation'] = 4
        with self.assertRaises(CommandValidationError): self.resolve(manifest, capture.components)
        manifest = capture.to_dict(); manifest['source']['quote_sequence'] = 4097
        with self.assertRaises(CommandValidationError): self.resolve(manifest, capture.components)
        manifest = capture.to_dict(); manifest['source']['quote_sequence'] = 0
        with self.assertRaises(CommandValidationError): self.resolve(manifest, capture.components)
        self.assertEqual(base.MAX_GENERATIONS, 3)
        self.assertEqual(base.MAX_PAYLOAD_BYTES, 262144)
        self.assertEqual(base.MAX_POSITIONS, 64)

    def test_current_metric_indicator_and_pending_shapes_remain_strict(self):
        capture = capture_owned_candidate(self.pair[1])
        for change in ('name', 'trade_count', 'drawdown', 'peak', 'pending', 'ema_count', 'ema_period', 'ema_value', 'status'):
            manifest = capture.to_dict(); member = manifest['engine']['members'][0]
            if change == 'name': member['name'] = ' padded '
            elif change == 'trade_count': member['num_trades'] = True
            elif change == 'drawdown': member['max_drawdown']['denominator'] = '0'
            elif change == 'peak': member['peak_equity'] = '100.0'
            elif change == 'pending': member['pending'] = {'action': 'entry', 'signal_at': WALL, 'position_id': None}
            elif change == 'ema_count': manifest['engine']['ema']['count'] = 4097
            elif change == 'ema_period': manifest['engine']['ema']['values'].pop('2')
            elif change == 'ema_value': manifest['engine']['ema']['values']['2'] = 'nan'
            else: manifest['status'] = 'live'
            with self.subTest(change=change), self.assertRaises(CommandValidationError):
                self.resolve(manifest, capture.components)

    def test_component_diff_rejects_same_revision_and_foreign_run(self):
        capture = capture_owned_candidate(self.pair[0])
        with self.assertRaises(CommandValidationError): component_updates(capture, capture)
        old, new = [capture_owned_candidate(c) for c in self.pair]
        with self.assertRaises(CommandValidationError): component_updates(new, old)
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            'genetic_algorithm', OWNER, WORKER, asset='SOL/USD'), EPOCH)
        foreign = capture_owned_candidate(life.bootstrap(config, seed_bundle(), source_inputs(WALL)))
        with self.assertRaises(CommandValidationError): component_updates(foreign, new)

    def test_capture_never_becomes_a_v5_or_v6_runtime_command(self):
        candidate = self.pair[1]
        manifest = capture_owned_candidate(candidate).to_dict()
        for version in (5, 6):
            with self.subTest(version=version), self.assertRaises(CommandValidationError):
                PreparedCommand.batch(OWNER, RUN, WORKER, 1, candidate.state.revision - 1,
                    candidate.operations, version=version, transition=manifest)


if __name__ == '__main__':
    unittest.main()
