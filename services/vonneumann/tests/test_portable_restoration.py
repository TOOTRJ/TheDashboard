"""Original-v2 offline restoration: exact next commands and refused authority.

Synthetic accepted-head bindings exercise decoding, never authenticate a server.
The independent native actor/catalog/COMMIT join is a separate acceptance gate.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import deny_network
from tests.test_provider_contract import OWNER, RUN, WORKER, source_inputs, WALL
from tests.test_provider_ga_components import provider_trace
from tests.postgres.portable_sql_fixture import extra_sequence, recovery_sequence, frozen_completion_sequence
from vonneumann.core.decision_inputs import DecisionInputs
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import provider_portable_ga_model as ga, portable_partitioned_checkpoint as cp
from vonneumann.research import portable_restoration as restore
from vonneumann.research import portable_restoration_wire as wire


def fixture_readback(row):
    """Literal test reader response plus separate synthetic operator bindings."""
    candidate, capture, command_wire = row
    manifest_wire = numbers.encode(capture.to_dict(), maximum=wire.MAX_MANIFEST_BYTES)
    command = numbers.decode(command_wire)
    expected = wire.ExpectedHead(OWNER, RUN, candidate.state.revision,
        hashlib.sha256(manifest_wire).hexdigest(), command['command_id'],
        hashlib.sha256(command_wire).hexdigest(), 'a' * 64, 'b' * 64)
    receipt = {'format': wire.RECEIPT_FORMAT, 'owner_id': OWNER, 'run_id': RUN,
        'command_id': expected.command_id, 'command_sha256': expected.command_sha256,
        'revision': str(expected.revision), 'manifest_sha256': expected.manifest_sha256,
        'model_format': ga.MODEL_FORMAT, 'assessment_format': ga.ASSESSMENT_FORMAT,
        'semantic_validator_sha256': expected.semantic_validator_sha256,
        'native_package_sha256': expected.native_package_sha256,
        'record_observed': True, 'pending_until_commit': False,
        'guard_observed_at': '2026-10-12T18:14:15.000123+00:00',
        'final_visible_instant_freshness': False, 'restoration_authority': False, 'hosted_authority': False}
    response = {'format': wire.FORMAT, 'manifest_wire': manifest_wire.decode('utf-8'),
        'component_wires': [block._wire.decode('utf-8') for block in capture.components],
        'receipt': receipt, 'current_revision': str(expected.revision),
        'current_status': candidate.state.to_dict()['status'], 'pending_command_authority': False,
        'restoration_authority': False, 'hosted_authority': False}
    return response, expected


def response_wire(response):
    # Deliberate PostgreSQL-compatible noncanonical outer order and whitespace.
    return json.dumps(response, ensure_ascii=False, indent=1).encode('utf-8')


def inputs_of(candidate):
    supplied = candidate.transition['evidence']['inputs']
    return DecisionInputs(datetime.fromisoformat(supplied['event_at']),
        datetime.fromisoformat(supplied['wall_at']), float.fromhex(supplied['monotonic_at']),
        tuple(supplied['ids']), tuple(tuple(item) for item in supplied['names']))


def oracle_response(expected, asked, original_ledger):
    # This oracle is held by the uninterrupted fixture, including retired IDs.
    # It is not reconstructed from active checkpoint accounts/positions.
    return {'format': restore.IDENTITY_FORMAT, 'owner_id': OWNER, 'run_id': RUN,
        'revision': str(expected.revision), 'manifest_sha256': expected.manifest_sha256,
        'native_package_sha256': expected.native_package_sha256,
        'identities': {identifier: ({'used': True, 'kind': 'account', 'born_revision': '2'}
                         if original_ledger.used(identifier) else {'used': False}) for identifier in asked},
        'restoration_authority': False, 'hosted_authority': False}


def prepare_original_next(state, candidate, inputs, ledger):
    evidence = candidate.transition['evidence']
    provider = evidence['inputs']['provider']
    if evidence['kind'] == 'protective':
        return ga.prepare_protective(state, provider['frame'], inputs, ledger=ledger)
    if evidence['kind'] == 'decision':
        return ga.prepare_decision(state, provider['frame'], provider['history'], inputs, ledger=ledger)
    control = evidence['control']
    return ga.prepare_control(state, control['action'], inputs, frame=provider['frame'],
        history=provider['history'], trip_id=control['trip_id'], ledger=ledger)


def prepare_restored_next(restored, candidate, inputs, identities):
    evidence = candidate.transition['evidence']
    provider = evidence['inputs']['provider']
    control = evidence['control']
    return restore.prepare_restored_candidate(restored, inputs, identities,
        phase=evidence['kind'], frame=provider['frame'], history=provider['history'],
        action=None if control is None else control['action'],
        trip_id=None if control is None else control['trip_id'])


class PortableRestorationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.multigeneration = []
        cls.metrics, _, _, _ = provider_trace(True, windows=2, model=ga, checkpoint=cp,
            search_seed='18446744073709551615',
            observer=lambda c, p, w: cls.multigeneration.append((c, p, w)))
        cls.controls = extra_sequence(controls=True)
        cls.recovery = recovery_sequence()
        cls.terminal = frozen_completion_sequence()
        # Stop at the first original accepted eight-position state. Existing
        # recovery/restart fixtures may have legitimately closed them later.
        ledger = ga.SimulationLedger(OWNER, RUN); cls.retained_stop = []
        for row in cls.controls:
            ledger.accept(row[0]); cls.retained_stop.append(row)
            if len(row[0].state.to_dict()['positions']) == 8: break
        state = row[0].state.to_dict(); at = state['engine']['last_quote']['timestamp'] + 1
        stopped = ga.prepare_control(row[0].state, 'stop', source_inputs(at, serial=5000), ledger=ledger)
        capture = cp.capture_owned_candidate(stopped)
        cls.retained_stop.append((stopped, capture, cp.prepare_transport(stopped, capture,
            previous=row[1], command_id=str(UUID(int=110000000 + stopped.state.revision)))))

    def setUp(self):
        context = deny_network(); context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def restore(self, row):
        response, expected = fixture_readback(row)
        return restore.restore_readback(response_wire(response), expected)

    def test_all_original_next_full_and_compact_wires_are_exact(self):
        comparisons = 0
        statuses, generations, held, risks, restarted, source_sequences = set(), set(), 0, 0, 0, set()
        selections = []
        for label, rows in [('two_generations', self.multigeneration), ('pause_resume', self.controls),
                            ('risk_recovery', self.recovery), ('terminal_completion', self.terminal),
                            ('stop_retained_positions', self.retained_stop)]:
            ledger = ga.SimulationLedger(OWNER, RUN)
            ledger.accept(rows[0][0])
            for previous, following in zip(rows, rows[1:]):
                with self.subTest(trace=label, revision=previous[0].state.revision):
                    restored = self.restore(previous)
                    self.assertEqual(restored.state.to_dict(), previous[0].state.to_dict())
                    inputs = inputs_of(following[0])
                    oracle = oracle_response(restored.checkpoint.expected, inputs.ids, ledger)
                    identities = restore.decode_identity_lookup(response_wire(oracle), restored.checkpoint.expected, inputs.ids)
                    prepared = prepare_restored_next(restored, following[0], inputs, identities)
                    self.assertEqual(prepared._wire, following[0]._wire)
                    self.assertEqual(prepared.state.to_dict(), following[0].state.to_dict())
                    compact = restore.prepare_restored_transport(restored, prepared,
                        command_id=numbers.decode(following[2])['command_id'])
                    self.assertEqual(compact, following[2])
                    state = restored.state.to_dict()
                    statuses.add(state['status']); generations.add(state['engine']['generation'])
                    held += len(state['positions']) == 8
                    risks += state['engine']['lifecycle']['risk']['active']
                    restarted += state['engine']['lifecycle']['search_epoch'] > 0
                    source_sequences.add(state['source']['quote_sequence'])
                    if following[0].history['selection'] is not None:
                        selections.append(following[0].history['selection'])
                    ledger.accept(following[0]); comparisons += 1
            stopped = self.restore(rows[-1])
            self.assertEqual(stopped.state.to_dict(), rows[-1][0].state.to_dict())
            statuses.add(stopped.state.to_dict()['status'])
            generations.add(stopped.state.to_dict()['engine']['generation'])
        self.assertEqual(comparisons, sum(len(rows) - 1 for rows in
            [self.multigeneration, self.controls, self.recovery, self.terminal, self.retained_stop]))
        self.assertGreaterEqual(comparisons, 60)
        self.assertGreaterEqual(max(generations), 2)
        self.assertTrue({'running', 'paused', 'risk_halted', 'stopped'} <= statuses)
        self.assertGreater(held, 0); self.assertGreater(risks, 0); self.assertGreater(restarted, 0)
        self.assertGreater(len(source_sequences), 8)
        self.assertTrue(selections)
        self.assertTrue({'clone_mutation', 'crossover_mutation'} <=
            {child['operation'] for selection in selections for child in selection['offspring']})

    def test_decoded_checkpoint_must_come_from_the_bound_decoder(self):
        response, expected = fixture_readback(self.controls[0])
        with self.assertRaises(wire.RestorationError):
            wire.DecodedCheckpoint(expected, response['manifest_wire'].encode(), (), 2, 'running', '')

    def test_readback_aggregate_cap_is_charged_before_component_decoding(self):
        response, expected = fixture_readback(self.controls[0])
        response['component_wires'][1] = 'x' * 140000
        response['component_wires'][2] = 'x' * 140000
        raw = response_wire(response)
        self.assertLessEqual(len(raw), wire.MAX_ENVELOPE_BYTES)
        self.assertGreater(sum(len(value.encode()) for value in response['component_wires'])
            + len(response['manifest_wire'].encode()), wire.MAX_AGGREGATE_BYTES)
        with self.assertRaisesRegex(wire.RestorationError, 'aggregate'):
            wire.decode_readback(raw, expected)

    def test_decode_never_bootstraps_seeds_allocates_or_evolves(self):
        row = self.multigeneration[-1]
        response, expected = fixture_readback(row)
        from contextlib import ExitStack
        from vonneumann.core.search_random import SearchRandomStreams
        from vonneumann.core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
        with ExitStack() as stack:
            for target in ['random.Random.seed', 'uuid.uuid4']:
                stack.enter_context(patch(target, side_effect=AssertionError('Decoder cannot allocate or seed')))
            stack.enter_context(patch.object(ga, 'bootstrap', side_effect=AssertionError('No bootstrap')))
            stack.enter_context(patch.object(SearchRandomStreams, '__init__', side_effect=AssertionError('No RNG namespace init')))
            stack.enter_context(patch.object(GeneticAlgorithmStrategy, 'evolve', side_effect=AssertionError('No evolution during restore')))
            restored = restore.restore_readback(response_wire(response), expected)
        self.assertEqual(restored.state.to_dict(), row[0].state.to_dict())
        self.assertEqual(restored.clock_epoch, row[0].state.to_dict()['source']['epoch'])
        self.assertFalse(restored.restoration_authority); self.assertFalse(restored.hosted_authority)
        self.assertFalse(restored.lease_restored); self.assertFalse(restored.identity_ledger_restored)

    def test_inner_original_wires_and_thirteen_ordered_dependencies_are_retained(self):
        row = self.recovery[-1]
        response, expected = fixture_readback(row)
        decoded = wire.decode_readback(response_wire(response), expected)
        self.assertEqual(decoded.manifest_wire, numbers.encode(row[1].to_dict()))
        self.assertEqual(decoded.component_wires, tuple(block._wire for block in row[1].components))
        self.assertEqual(len(decoded.component_wires), 13)
        self.assertLessEqual(len(decoded.manifest_wire) + sum(map(len, decoded.component_wires)), 262144)
        self.assertFalse(decoded.restoration_authority); self.assertFalse(decoded.pending_command_authority)
        self.assertFalse(decoded.hosted_authority)

    def test_bound_receipt_refuses_scope_hash_semantics_pending_and_claimed_authority(self):
        response, expected = fixture_readback(self.controls[3])
        for key, value in [('owner_id', WORKER), ('run_id', WORKER), ('command_id', WORKER),
                ('revision', '1'), ('manifest_sha256', 'c' * 64), ('command_sha256', 'c' * 64),
                ('semantic_validator_sha256', 'c' * 64), ('native_package_sha256', 'c' * 64),
                ('model_format', 'unknown-v3'), ('assessment_format', 'unknown-v3'),
                ('record_observed', False), ('record_observed', 1), ('pending_until_commit', True),
                ('guard_observed_at', None), ('guard_observed_at', '2026-10-12T18:14:15+00:00'),
                ('guard_observed_at', '2026-10-12T18:14:15.000123+01:00'),
                ('final_visible_instant_freshness', True), ('restoration_authority', True), ('hosted_authority', True)]:
            with self.subTest(field=key, value=value):
                changed = deepcopy(response); changed['receipt'][key] = value
                with self.assertRaises(wire.RestorationError): wire.decode_readback(response_wire(changed), expected)
        changed = deepcopy(response); changed['receipt']['seeded_semantic_prior'] = True
        with self.assertRaises(wire.RestorationError): wire.decode_readback(response_wire(changed), expected)

    def test_readback_refuses_unknown_duplicate_truncated_noncanonical_missing_and_reordered(self):
        response, expected = fixture_readback(self.controls[3])
        variants = []
        value = deepcopy(response); value['unknown'] = None; variants.append(response_wire(value))
        variants += [b'{"format":"x","format":"x"}', b'{"x":', b'\xff', b' ' * (589824 + 1)]
        value = deepcopy(response); value['current_revision'] = 2; variants.append(response_wire(value))
        value = deepcopy(response); value['current_revision'] = '02'; variants.append(response_wire(value))
        value = deepcopy(response); value['component_wires'].pop(); variants.append(response_wire(value))
        value = deepcopy(response); value['component_wires'][0], value['component_wires'][1] = value['component_wires'][1], value['component_wires'][0]; variants.append(response_wire(value))
        value = deepcopy(response); value['component_wires'][1] = value['component_wires'][0]; variants.append(response_wire(value))
        value = deepcopy(response); value['component_wires'][0] += ' '; variants.append(response_wire(value))
        value = deepcopy(response); value['manifest_wire'] += ' '; variants.append(response_wire(value))
        value = deepcopy(response); value['component_wires'][0] = 'x' * 196609; variants.append(response_wire(value))
        for key in ['pending_command_authority', 'restoration_authority', 'hosted_authority']:
            value = deepcopy(response); value[key] = True; variants.append(response_wire(value))
        for index, value in enumerate(variants):
            with self.subTest(case=index), self.assertRaises(wire.RestorationError): wire.decode_readback(value, expected)

    def test_numeric_types_never_round_or_use_boolean_integer_aliases(self):
        original = {'large': 2**63 - 1, 'negative': -(2**200), 'float': -0.0, 'bool': True}
        decoded = wire.decode_numeric(numbers.encode(original), maximum=262144)
        self.assertEqual(decoded['large'], 2**63 - 1); self.assertEqual(decoded['negative'], -(2**200))
        self.assertEqual(decoded['float'].hex(), '-0x0.0p+0'); self.assertIs(decoded['bool'], True)
        for raw in [b'{"x":9007199254740992}', b'{"x":{"$integer":"01"}}', b'{"x":{"$integer":"-0"}}',
                b'{"x":{"$float64":"nan"}}', b'{"x":{"$float64":"0.1"}}', b'{"x":{"$integer":"1","other":false}}',
                b'{"x":{"$integer":"1"},"x":false}', b'{"x":true} ', b'[' * 65 + b']' * 65]:
            with self.subTest(raw=raw[:100]), self.assertRaises(wire.RestorationError): wire.decode_numeric(raw, maximum=262144)

    def test_historical_inspection_cannot_prepare_continuation(self):
        response, expected = fixture_readback(self.controls[2])
        response['current_revision'] = str(expected.revision + 1)
        with self.assertRaises(wire.RestorationError): wire.decode_readback(response_wire(response), expected)
        historical = wire.decode_readback(response_wire(response), replace(expected, allow_historical=True))
        self.assertFalse(historical.is_current)
        with self.assertRaises(wire.RestorationError): restore.reconstruct_checkpoint(historical)

    def test_rehashed_graph_forgery_cannot_change_genome_rng_layout_or_runtime(self):
        row = self.multigeneration[-1]
        response, original_expected = fixture_readback(row)
        optimizer = numbers.decode(response['component_wires'][1].encode('utf-8'))
        variants = []
        altered = deepcopy(optimizer); altered['body']['software']['python'] = '3.12.13'; variants.append(altered)
        altered = deepcopy(optimizer); altered['body']['strategy']['class'] = 'ArbitraryClass'; variants.append(altered)
        altered = deepcopy(optimizer); altered['body']['strategy']['fields']['_rng']['index'] = 625; variants.append(altered)
        altered = deepcopy(optimizer); altered['body']['strategy']['fields']['_rng']['words'][0] = True; variants.append(altered)
        altered = deepcopy(optimizer); altered['body']['strategy']['fields']['_search_streams'] = {'ref': 999}; variants.append(altered)
        altered = deepcopy(optimizer); altered['body']['strategy']['fields']['_search_epoch'] = {'type': 'integer', 'decimal': '10'}; variants.append(altered)
        for index, altered in enumerate(variants):
            # Rehashed fixture operator binding still cannot bypass structural
            # graph/mirror checks; this is not authentic historical acceptance.
            value = deepcopy(response); manifest = numbers.decode(value['manifest_wire'].encode('utf-8'))
            component_wire = numbers.encode(altered)
            value['component_wires'][1] = component_wire.decode('utf-8')
            manifest['components'][1]['sha256'] = hashlib.sha256(component_wire).hexdigest()
            value['manifest_wire'] = numbers.encode(manifest).decode('utf-8')
            digest = hashlib.sha256(value['manifest_wire'].encode('utf-8')).hexdigest()
            value['receipt']['manifest_sha256'] = digest
            expected = replace(original_expected, manifest_sha256=digest)
            with self.subTest(case=index), self.assertRaises(ValueError): restore.restore_readback(response_wire(value), expected)

    def test_head_bound_identity_oracle_never_defaults_missing_or_foreign_ids_to_unused(self):
        restored = self.restore(self.multigeneration[0])
        inputs = inputs_of(self.multigeneration[1][0]); ledger = ga.SimulationLedger(OWNER, RUN)
        ledger.accept(self.multigeneration[0][0])
        response = oracle_response(restored.checkpoint.expected, inputs.ids, ledger)
        oracle = restore.decode_identity_lookup(response_wire(response), restored.checkpoint.expected, inputs.ids)
        with self.assertRaises(wire.RestorationError): oracle.used(WORKER)
        empty = oracle_response(restored.checkpoint.expected, (), ledger)
        checked_empty = restore.decode_identity_lookup(response_wire(empty), restored.checkpoint.expected, ())
        with self.assertRaises(wire.RestorationError): checked_empty.used(inputs.ids[0])
        with self.assertRaises(wire.RestorationError):
            restore.prepare_restored_candidate(restored, inputs, checked_empty, phase='control', action='stop')
        variants = []
        for key, value in [('owner_id', WORKER), ('run_id', WORKER), ('revision', str(restored.state.revision + 1)),
                ('manifest_sha256', 'c' * 64), ('native_package_sha256', 'c' * 64), ('restoration_authority', True)]:
            altered = deepcopy(response); altered[key] = value; variants.append(altered)
        altered = deepcopy(response); altered['identities'].pop(inputs.ids[0]); variants.append(altered)
        altered = deepcopy(response); altered['identities'][WORKER] = {'used': False}; variants.append(altered)
        altered = deepcopy(response); altered['identities'][inputs.ids[0]] = {'used': 0}; variants.append(altered)
        altered = deepcopy(response); altered['identities'][inputs.ids[0]] = {'used': True, 'kind': 'unknown', 'born_revision': '2'}; variants.append(altered)
        altered = deepcopy(response); altered['identities'][inputs.ids[0]] = {'used': True, 'kind': 'risk', 'born_revision': str(restored.state.revision + 1)}; variants.append(altered)
        for index, altered in enumerate(variants):
            with self.subTest(case=index), self.assertRaises(wire.RestorationError):
                restore.decode_identity_lookup(response_wire(altered), restored.checkpoint.expected, inputs.ids)

    def test_retired_original_identity_still_refuses_allocation_after_restore(self):
        rows = self.multigeneration
        ledger = ga.SimulationLedger(OWNER, RUN)
        for index, row in enumerate(rows):
            before = row[0].transition['before']
            if before is not None and any(op['kind'] == 'birth' for op in row[0].operations) and before['engine']['generation'] >= 1:
                previous = rows[index - 1]; following = row; break
            ledger.accept(row[0])
        else:
            self.fail('Fixture needs second-generation allocation')
        old_id = rows[0][0].state.to_dict()['accounts'][0]['id']
        self.assertTrue(ledger.used(old_id))
        self.assertNotIn(old_id, {account['id'] for account in previous[0].state.to_dict()['accounts']})
        original_inputs = inputs_of(following[0])
        changed_inputs = replace(original_inputs, ids=(old_id,) + original_inputs.ids[1:])
        restored = self.restore(previous)
        oracle = restore.decode_identity_lookup(response_wire(oracle_response(restored.checkpoint.expected, changed_inputs.ids, ledger)),
            restored.checkpoint.expected, changed_inputs.ids)
        self.assertTrue(oracle.used(old_id))
        with self.assertRaises(ga.ExactRehearsalError):
            prepare_restored_next(restored, following[0], changed_inputs, oracle)

    def test_stopped_retained_positions_never_restore_running_or_lease(self):
        row = self.retained_stop[-1]; restored = self.restore(row)
        self.assertEqual(restored.state.to_dict()['status'], 'stopped')
        self.assertEqual(len(restored.state.to_dict()['positions']), 8)
        inputs = source_inputs(WALL + 10000, serial=3000)
        ledger = ga.SimulationLedger(OWNER, RUN)
        for item in self.retained_stop: ledger.accept(item[0])
        oracle = restore.decode_identity_lookup(response_wire(oracle_response(restored.checkpoint.expected, inputs.ids, ledger)), restored.checkpoint.expected, inputs.ids)
        with self.assertRaises(ga.ExactRehearsalError) as original:
            ga.prepare_control(row[0].state, 'stop', inputs, ledger=ledger)
        with self.assertRaises(ga.ExactRehearsalError) as reconstructed:
            restore.prepare_restored_candidate(restored, inputs, oracle, phase='control', action='stop')
        self.assertEqual(str(original.exception), str(reconstructed.exception))
        self.assertFalse(restored.lease_restored)

    def test_original_uncertain_request_is_only_reconciled_by_original_id_hash_and_wire(self):
        row = self.recovery[-1]; response, expected = fixture_readback(row)
        pending = restore.PendingOriginalRequest.capture(row[2])
        absent = response_wire({'format': restore.COMMAND_READBACK_FORMAT, 'found': False})
        unresolved = restore.reconcile_original_request(pending, absent, expected)
        self.assertEqual(unresolved.outcome, 'not_observed_uncertain')
        self.assertFalse(unresolved.retry_authority)
        observed = {'format': restore.COMMAND_READBACK_FORMAT, 'found': True,
            'receipt': response['receipt'], 'original_command_wire': row[2].decode('utf-8')}
        accepted = restore.reconcile_original_request(pending, response_wire(observed), expected)
        self.assertEqual(accepted.original.command_id, pending.command_id)
        self.assertEqual(accepted.original.wire, row[2]); self.assertFalse(accepted.retry_authority)
        self.assertEqual(accepted.outcome, 'observed_original_commit')
        for key, value in [('command_id', WORKER), ('command_sha256', 'c' * 64), ('owner_id', WORKER),
                ('native_package_sha256', 'c' * 64), ('record_observed', False), ('pending_until_commit', True)]:
            altered = deepcopy(observed); altered['receipt'][key] = value
            with self.subTest(field=key), self.assertRaises(wire.RestorationError):
                restore.reconcile_original_request(pending, response_wire(altered), expected)
        altered = deepcopy(observed); altered['original_command_wire'] += ' '
        with self.assertRaises(wire.RestorationError): restore.reconcile_original_request(pending, response_wire(altered), expected)

    def test_pure_import_boundary_denies_environment_provider_database_and_network(self):
        project = Path(__file__).resolve().parents[1]
        code = '''
import builtins, importlib.abc, os, socket, sys
blocked = ('dotenv', 'supabase', 'httpx', 'requests', 'vonneumann.config', 'vonneumann.db.repository',
           'vonneumann.market.jupiter', 'vonneumann.market.birdeye', 'vonneumann.market.price_feed')
class Boundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == item or fullname.startswith(item + '.') for item in blocked):
            raise AssertionError('Forbidden restoration import: ' + fullname)
sys.meta_path.insert(0, Boundary())
original_open = builtins.open
def guarded_open(file, *args, **kwargs):
    path = os.fspath(file) if isinstance(file, (str, bytes, os.PathLike)) else ''
    if isinstance(path, str) and ('.env' in path.split('/')[-1] or '/ssl/' in path):
        raise AssertionError('Restoration must not read private configuration')
    return original_open(file, *args, **kwargs)
builtins.open = guarded_open
def denied(*args, **kwargs): raise AssertionError('Restoration network is forbidden')
socket.getaddrinfo = socket.create_connection = denied
socket.socket.connect = socket.socket.connect_ex = denied
from vonneumann.research import portable_restoration
print('pure-import-boundary-pass')
'''
        env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(project),
            'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        result = subprocess.run([sys.executable, '-c', code],
            cwd=project, env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'pure-import-boundary-pass')


class PortablePendingRequestShapeTests(unittest.TestCase):
    def test_malformed_nested_pending_evidence_has_controlled_refusal(self):
        value = {'format': cp.TRANSPORT_FORMAT, 'command_id': WORKER, 'owner_id': OWNER, 'run_id': RUN,
            'prior': None, 'checkpoint': {'format': cp.FORMAT, 'source_model_version': ga.MODEL_FORMAT,
                'owner_id': OWNER, 'run_id': RUN, 'revision': 2},
            'components': [], 'operations': [], 'history': {}, 'evidence': None, 'events': []}
        for evidence in (None, [], '', False):
            value['evidence'] = evidence
            with self.subTest(evidence=evidence), self.assertRaisesRegex(wire.RestorationError, 'evidence'):
                restore.PendingOriginalRequest.capture(numbers.encode(value))


if __name__ == '__main__': unittest.main()
