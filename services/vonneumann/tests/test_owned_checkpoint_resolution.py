"""Factory ownership, full untrusted audits and pre-change exact wire continuity."""
from copy import deepcopy
import gc
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import weakref

from tests.security_support import deny_network
from tests.test_provider_contract import OWNER, RUN, WALL, EPOCH, seed_bundle, source_inputs
from tests.test_provider_ga_components import provider_trace
from vonneumann.db.command_protocol import CommandValidationError, canonical_json
from vonneumann.research import provider_portable_ga_model as ga
from vonneumann.research import provider_portable_checkpoint as legacy
from vonneumann.research import portable_partitioned_checkpoint as partitioned
from vonneumann.research import numeric_wire as numbers


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'tests/fixtures/owned-checkpoint-cache-wire-baseline.json'
MODULES = (legacy, partitioned)


def unowned_copy(module, owned):
    """A literal restored/foreign object is never registered by a successful audit."""
    result = object.__new__(module.ActiveCheckpoint)
    for name in ('wire', 'components', 'expected'):
        slot = '_ActiveCheckpoint__' + name
        object.__setattr__(result, slot, getattr(owned, slot))
    return result


def record(candidate, capture, wire):
    return {'phase': candidate.transition['evidence']['kind'], 'revision': candidate.state.revision,
        'candidate_sha256': hashlib.sha256(candidate._wire).hexdigest(),
        'compact_sha256': hashlib.sha256(wire).hexdigest(),
        'manifest_sha256': hashlib.sha256(numbers.encode(capture.to_dict(), maximum=partitioned.MAX_MANIFEST_BYTES)).hexdigest(),
        'component_sha256': [block.identity for block in capture.components]}


class OwnedCheckpointResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with deny_network():
            cls.ledger = ga.SimulationLedger(OWNER, RUN)
            cls.initial = ga.bootstrap(ga.GAConfig('genetic_algorithm', OWNER, RUN,
                asset='SOL/USD', source_epoch=EPOCH), seed_bundle(last_close='80'),
                source_inputs(WALL), ledger=cls.ledger)
            cls.state = cls.ledger.accept(cls.initial)
            cls.following = ga.prepare_control(cls.state, 'pause', source_inputs(WALL + 1, serial=910), ledger=cls.ledger)

    def setUp(self):
        guard = deny_network(); guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)

    def test_factory_validation_cannot_be_skipped_or_register_a_failed_capture(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                before = len(module._OWNED_RESOLUTIONS)
                with patch.object(module, 'resolve_manifest', side_effect=CommandValidationError('full factory refusal')):
                    with self.assertRaisesRegex(CommandValidationError, 'full factory refusal'):
                        module.capture_owned_candidate(self.initial)
                self.assertEqual(len(module._OWNED_RESOLUTIONS), before)

    def test_owned_resolution_is_detached_and_does_not_repeat_full_validator(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                capture = module.capture_owned_candidate(self.initial)
                original = capture.resolve()
                with patch.object(module, 'resolve_manifest', side_effect=AssertionError('unexpected repeat')):
                    view = capture.resolve()
                    view['engine']['config']['initial_cash'] = '0'
                    view['source']['bars'][0][1] = '999'
                    self.assertEqual(capture.resolve(), original)
                    self.assertIsNot(capture.resolve(), original)

    def test_unowned_same_bytes_hash_scope_and_revision_always_take_full_path(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                capture = module.capture_owned_candidate(self.initial)
                copied = unowned_copy(module, capture)
                self.assertIsNot(copied, capture)
                self.assertEqual(copied.to_dict(), capture.to_dict())
                self.assertNotIn(copied, module._OWNED_RESOLUTIONS)
                with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                    self.assertEqual(copied.resolve(), capture.resolve())
                    self.assertEqual(copied.resolve(), capture.resolve())
                    self.assertEqual(audit.call_count, 2)
                self.assertNotIn(copied, module._OWNED_RESOLUTIONS)

    def test_nonexact_capture_never_uses_custom_equality_or_hash_for_ownership(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                class ForeignCapture(module.ActiveCheckpoint):
                    def __eq__(self, other):
                        raise AssertionError('Foreign equality must not confer ownership')

                    def __hash__(self):
                        raise AssertionError('Foreign hash must not enter ownership lookup')

                owned = module.capture_owned_candidate(self.initial)
                foreign = object.__new__(ForeignCapture)
                for name in ('wire', 'components', 'expected'):
                    slot = '_ActiveCheckpoint__' + name
                    object.__setattr__(foreign, slot, getattr(owned, slot))
                with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                    self.assertEqual(foreign.resolve(), owned.resolve())
                    self.assertEqual(foreign.resolve(), owned.resolve())
                    self.assertEqual(audit.call_count, 2)

    def test_equal_bytes_replacement_invalidates_identity_proof_without_promotion(self):
        for module in MODULES:
            for field in ('wire', 'expected'):
                with self.subTest(module=module.__name__, field=field):
                    capture = module.capture_owned_candidate(self.initial)
                    expected = capture.resolve()
                    slot = '_ActiveCheckpoint__' + field
                    original = getattr(capture, slot)
                    replacement = memoryview(original).tobytes()
                    self.assertEqual(replacement, original); self.assertIsNot(replacement, original)
                    proof = module._OWNED_RESOLUTIONS[capture]
                    object.__setattr__(capture, slot, replacement)
                    with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                        self.assertEqual(capture.resolve(), expected)
                        self.assertEqual(capture.resolve(), expected)
                        self.assertEqual(audit.call_count, 2)
                    self.assertIs(module._OWNED_RESOLUTIONS[capture], proof)

    def test_changed_manifest_or_expected_refuses_under_full_audit(self):
        for module in MODULES:
            for field in ('wire', 'expected'):
                with self.subTest(module=module.__name__, field=field):
                    capture = module.capture_owned_candidate(self.initial)
                    if field == 'wire':
                        value = capture.to_dict(); value['reserve'] = '201'
                        changed = numbers.encode(value, maximum=module.MAX_MANIFEST_BYTES)
                    else:
                        value = capture.resolve(); value['reserve'] = '201'
                        changed = canonical_json(value)
                    object.__setattr__(capture, '_ActiveCheckpoint__' + field, changed)
                    with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                        with self.assertRaises(CommandValidationError): capture.resolve()
                        self.assertEqual(audit.call_count, 1)

    def test_component_tuple_identity_order_count_and_duplicate_changes_take_full_path(self):
        for module in MODULES:
            for change in ('equal_tuple', 'reorder', 'missing', 'duplicate'):
                with self.subTest(module=module.__name__, change=change):
                    capture = module.capture_owned_candidate(self.initial)
                    expected = capture.resolve(); original = capture.components
                    changed = list(original)
                    if change == 'reorder': changed[0], changed[1] = changed[1], changed[0]
                    elif change == 'missing': changed.pop()
                    elif change == 'duplicate': changed[1] = changed[0]
                    changed = tuple(changed); self.assertIsNot(changed, original)
                    object.__setattr__(capture, '_ActiveCheckpoint__components', changed)
                    with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                        if change in {'missing', 'duplicate'}:
                            with self.assertRaises(CommandValidationError): capture.resolve()
                        else:
                            # The existing full resolver treats a complete block
                            # tuple as a hash-addressed set; keep that meaning.
                            self.assertEqual(capture.resolve(), expected)
                        self.assertEqual(audit.call_count, 1)

    def test_changed_component_wire_invalidates_snapshot_and_refuses_stale_reference(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                capture = module.capture_owned_candidate(self.initial)
                block = capture.components[1]; value = block.to_dict()
                value['body']['cache-test-forgery'] = True
                object.__setattr__(block, '_wire', numbers.encode(value, maximum=module.MAX_COMPONENT_BYTES))
                with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                    with self.assertRaises(CommandValidationError): capture.resolve()
                    self.assertEqual(audit.call_count, 1)

    def test_self_rehashed_component_manifest_expected_mirror_cannot_skip_semantic_audit(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                capture = module.capture_owned_candidate(self.initial)
                expected = capture.resolve(); manifest = capture.to_dict()
                block = capture.components[1]; value = block.to_dict()
                value['body']['cache-test-forgery'] = True
                object.__setattr__(block, '_wire', numbers.encode(value, maximum=module.MAX_COMPONENT_BYTES))
                manifest['components'][1]['sha256'] = block.identity
                expected['engine']['optimizer'] = deepcopy(value['body'])
                object.__setattr__(capture, '_ActiveCheckpoint__wire', numbers.encode(manifest, maximum=module.MAX_MANIFEST_BYTES))
                object.__setattr__(capture, '_ActiveCheckpoint__expected', canonical_json(expected))
                with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                    with self.assertRaises(CommandValidationError): capture.resolve()
                    self.assertEqual(audit.call_count, 1)

    def test_replaced_equal_component_object_is_not_an_identity_cache_hit(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                capture = module.capture_owned_candidate(self.initial); expected = capture.resolve()
                components = list(capture.components)
                equal = module.TypedComponent(components[0]._wire)
                self.assertEqual(equal, components[0]); self.assertIsNot(equal, components[0])
                components[0] = equal
                object.__setattr__(capture, '_ActiveCheckpoint__components', tuple(components))
                with patch.object(module, 'resolve_manifest', wraps=module.resolve_manifest) as audit:
                    self.assertEqual(capture.resolve(), expected)
                    self.assertEqual(audit.call_count, 1)

    def test_weak_registry_value_cannot_retain_a_capture_after_last_reference(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                before = len(module._OWNED_RESOLUTIONS)
                capture = module.capture_owned_candidate(self.initial)
                observed = weakref.ref(capture)
                self.assertEqual(len(module._OWNED_RESOLUTIONS), before + 1)
                del capture; gc.collect()
                self.assertIsNone(observed())
                self.assertEqual(len(module._OWNED_RESOLUTIONS), before)

    def test_raw_manifest_resolution_still_checks_every_component(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                capture = module.capture_owned_candidate(self.initial)
                checked = module.TypedComponent._checked_value
                with patch.object(module.TypedComponent, '_checked_value', autospec=True, side_effect=checked) as audit:
                    result = module.resolve_manifest(capture.to_dict(), capture.components,
                        owner_id=OWNER, run_id=RUN, revision=capture.to_dict()['revision'])
                    self.assertEqual(result, capture.resolve())
                    self.assertGreaterEqual(audit.call_count, module.MAX_COMPONENTS)

    def test_full_and_compact_transport_equal_full_unowned_path_for_both_factories(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                previous = module.capture_owned_candidate(self.initial)
                following = module.capture_owned_candidate(self.following)
                original_candidate_wire = self.following._wire
                command_id = '44444444-4444-4444-8444-444444444444'
                owned = module.prepare_transport(self.following, following,
                    command_id=command_id, previous=previous)
                unowned = module.prepare_transport(self.following, unowned_copy(module, following),
                    command_id=command_id, previous=unowned_copy(module, previous))
                self.assertEqual(owned, unowned)
                self.assertIs(self.following._wire, original_candidate_wire)

    def test_70_pre_change_sparse_dense_full_compact_manifest_and_components_are_exact(self):
        baseline = json.loads(BASELINE.read_text())
        self.assertEqual(baseline['base_commit'], 'b1ab59f4e6d5ae9a134a21235ba9a7f4343332fd')
        self.assertEqual(baseline['source_before']['vonneumann/research/provider_portable_ga_model.py'],
            hashlib.sha256((ROOT/'vonneumann/research/provider_portable_ga_model.py').read_bytes()).hexdigest())
        total = 0
        for trace in baseline['traces']:
            rows = []
            provider_trace(trace['dense'], windows=trace['windows'], model=ga, checkpoint=partitioned,
                search_seed=trace['search_seed'], observer=lambda c, p, w: rows.append(record(c, p, w)))
            self.assertEqual(rows, trace['commands'])
            total += len(rows)
        self.assertEqual(total, 70)


if __name__ == '__main__': unittest.main()
