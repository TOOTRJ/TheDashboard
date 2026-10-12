"""Literal-provider offline model, component and complete-command acceptance."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from uuid import UUID

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_provider_contract import (
    OWNER, RUN, WORKER, WALL, MONO, END, EPOCH, raw_capture, raw_minutes,
    seed_bundle, source_inputs, source as old_source,
)
from vonneumann.db.command_protocol import CommandValidationError, canonical_json
from vonneumann.research import provider_ga_model as ga
from vonneumann.research import provider_checkpoint as cp
from vonneumann.research import numeric_wire as numbers


def provider_trace(dense, windows=32, observer=None, *, model=ga, checkpoint=cp, search_seed='0'):
    # Explicit trusted test modules; no monkeypatch or shared model globals.
    ga, cp = model, checkpoint
    ledger = ga.SimulationLedger(OWNER, RUN)
    metrics = {'windows': windows, 'dense': dense, 'candidates': 0,
        'max_resolved_bytes': 0, 'max_manifest_bytes': 0, 'max_compact_command_bytes': 0,
        'max_full_candidate_bytes': 0, 'changes_by_kind': {}, 'changes_by_phase': {},
        'total_full_candidate_bytes': 0, 'total_compact_command_bytes': 0,
        'unique_component_bytes': 0, 'component_body_maxima': {}}
    previous, last, seen = None, None, set()

    def accept(candidate):
        nonlocal previous, last
        capture = cp.capture_owned_candidate(candidate)
        resolved = capture.resolve()
        original = candidate.state.to_dict()
        expected = dict(original); expected.pop('version')
        expected.update(format=cp.FORMAT, source_model_version=ga.MODEL_FORMAT)
        if resolved != expected:
            raise AssertionError('Capture omitted original model evidence')
        wire = cp.prepare_transport(candidate, capture, previous=previous,
            command_id=str(UUID(int=40_000_000 + original['revision'])))
        retained = set() if previous is None else {block.identity for block in previous.components}
        changes = tuple(block for block in capture.components if block.identity not in retained)
        phase = candidate.transition['evidence']['kind']
        metrics['changes_by_phase'].setdefault(phase, []).append(len(changes))
        for block in changes:
            kind = block.to_dict()['kind']
            metrics['changes_by_kind'][kind] = metrics['changes_by_kind'].get(kind, 0) + 1
        for block in capture.components:
            kind = block.to_dict()['kind']
            metrics['component_body_maxima'][kind] = max(metrics['component_body_maxima'].get(kind, 0),
                                                        len(numbers.encode(block.to_dict()['body'])))
            if block.identity not in seen:
                seen.add(block.identity); metrics['unique_component_bytes'] += len(block._wire)
        metrics['candidates'] += 1
        for key, value in (('resolved', capture.resolved_bytes), ('manifest', capture.manifest_bytes),
                           ('compact_command', len(wire)), ('full_candidate', candidate.payload_bytes)):
            metrics['max_' + key + '_bytes'] = max(metrics['max_' + key + '_bytes'], value)
        metrics['total_full_candidate_bytes'] += candidate.payload_bytes
        metrics['total_compact_command_bytes'] += len(wire)
        state = ledger.accept(candidate)
        if observer is not None:
            observer(candidate, capture, wire)
        previous, last = capture, candidate
        return state

    with deny_network():
        state = accept(ga.bootstrap(ga.GAConfig('genetic_algorithm', OWNER, RUN,
            asset='SOL/USD', source_epoch=EPOCH, search_seed=search_seed), seed_bundle(last_close='80'),
            source_inputs(WALL), ledger=ledger))
        offsets = [1] + [offset for bar in range(1, 4 * windows + 1)
                         for offset in (bar * 900, bar * 900 + 1)]
        for serial, offset in enumerate(offsets, 1):
            wall, mono = WALL + offset, MONO + offset
            generation = state.to_dict()['engine']['generation']
            frame = ga.source.make_frame(raw_capture(block=100 + serial,
                source_second=wall - 2, wall=wall - 1, mono=mono - 1),
                prior_source=state.to_dict()['source'], epoch=EPOCH,
                wall_now=wall, monotonic_now=mono)
            state = accept(ga.prepare_protective(state, frame,
                source_inputs(wall, mono=mono, generation=generation + 1, serial=serial * 2), ledger=ledger))
            history = None
            if offset % 900 == 0:
                bar = offset // 900
                high = bar % 2 == 1 if dense else bar % 4 == 1
                history = ga.source.build_history(raw_minutes(end=END + offset, count=15,
                    close='120' if high else '80', wall=wall - 1, mono=mono - 1),
                    prior_bars=state.to_dict()['source']['bars'], seed=False,
                    wall_us=wall * 1_000_000, monotonic_us=int(mono * 1_000_000))
            state = accept(ga.prepare_decision(state, frame, history,
                source_inputs(wall, mono=mono, generation=generation + 1, serial=serial * 2 + 1), ledger=ledger))
    metrics['final_generation'] = state.to_dict()['engine']['generation']
    metrics['assessments'] = sum(len(row['assessments']) for row in ledger.history)
    metrics['closed_positions'] = sum(len(row['closed_positions']) for row in ledger.history)
    metrics['source_sequence'] = state.to_dict()['source']['quote_sequence']
    metrics['ema_count'] = state.to_dict()['engine']['ema']['count']
    metrics['unique_components'] = len(seen)
    for phase, counts in metrics['changes_by_phase'].items():
        metrics['changes_by_phase'][phase] = {str(count): counts.count(count) for count in sorted(set(counts))}
    return metrics, last, previous, ledger


class ProviderGAComponentTests(OfflineTestMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = []
        cls.traces = {dense: provider_trace(dense, observer=lambda c, p, w:
            cls.samples.append((c, p, w)) if len(cls.samples) < 5 else None) for dense in (False, True)}
        if os.environ.get('DASHBOARD_PROVIDER_GA_MEASURE') == '1':
            artifact = Path(__file__).resolve().parents[1] / 'research/provider-ga-capacity.json'
            artifact.write_text(json.dumps({'model': ga.MODEL_FORMAT, 'format': cp.FORMAT,
                'scope': 'literal synthetic provider responses; complete offline candidates and compact requests',
                'excluded': ['durable admission', 'restore', 'real-provider workload', 'hosted latency/cost', 'profitability'],
                'traces': [row[0] for row in cls.traces.values()]}, indent=2, sort_keys=True) + '\n')

    def test_32_sparse_dense_windows_are_bounded_and_complete(self):
        for metrics, last, capture, ledger in self.traces.values():
            self.assertEqual(metrics['final_generation'], 32)
            self.assertEqual(metrics['assessments'], 256)
            self.assertEqual(metrics['candidates'], 515)
            self.assertEqual(metrics['source_sequence'], 257)
            self.assertEqual(metrics['ema_count'], 189)
            self.assertLess(metrics['max_compact_command_bytes'], cp.ORDINARY_COMMAND_BYTES)
            self.assertLess(metrics['max_resolved_bytes'], cp.MAX_RESOLVED_BYTES)
            self.assertEqual(len(capture.resolve()['accounts']), 8)
            self.assertLessEqual(len(capture.resolve()['positions']), 8)
            for history in ledger.history:
                for record in history['assessments']:
                    self.assertEqual(record['window_source_start']['policy'], ga.source.SOURCE_VERSION)
                    self.assertIsNotNone(record['window_source_start']['frame']['quote']['document']['response_sha256'])
                    self.assertEqual(record['window_source_end']['epoch'], EPOCH)
                    self.assertEqual(record['metrics']['source']['epoch'], EPOCH)

    def test_quote_only_reuses_all_blocks_but_diff_is_not_readback(self):
        old, following = self.samples[0][1], self.samples[1][1]
        self.assertEqual(cp.component_updates(old, following), ())
        self.assertEqual(cp.resolve_manifest(following.to_dict(), old.components,
            owner_id=OWNER, run_id=RUN, revision=following.to_dict()['revision']), following.resolve())
        with self.assertRaises(CommandValidationError):
            cp.resolve_manifest(following.to_dict(), (), owner_id=OWNER, run_id=RUN,
                                revision=following.to_dict()['revision'])

    def test_missing_foreign_duplicate_stale_components_are_rejected(self):
        capture = self.samples[2][1]
        manifest, blocks = capture.to_dict(), capture.components
        foreign = cp.TypedComponent.make(WORKER, RUN, 'configuration', 'configuration', 0, blocks[0].to_dict()['body'])
        for changed in (blocks[:-1], blocks + (blocks[0],), (blocks[0],) * 11, (foreign,) + blocks[1:]):
            with self.assertRaises(CommandValidationError):
                cp.resolve_manifest(manifest, changed, owner_id=OWNER, run_id=RUN, revision=manifest['revision'])

    def test_rehashed_genotype_cannot_disagree_with_optimizer(self):
        capture = self.samples[2][1]
        manifest, blocks = capture.to_dict(), list(capture.components)
        body = blocks[3].to_dict()['body']
        body['ema_fast'] = float(2 if float.fromhex(body['ema_fast']) != 2 else 3).hex()
        blocks[3] = cp.TypedComponent.make(OWNER, RUN, 'genome', manifest['engine']['members'][0]['id'], 0, body)
        manifest['components'][3] = blocks[3].reference()
        with self.assertRaises(CommandValidationError):
            cp.resolve_manifest(manifest, tuple(blocks), owner_id=OWNER, run_id=RUN, revision=manifest['revision'])

    def test_reference_scope_revision_hash_and_source_are_bound(self):
        capture = self.samples[2][1]
        for field, value in (('owner_id', WORKER), ('run_id', WORKER), ('revision', True),
                             ('source_model_version', 5), ('format', 'native-v6')):
            manifest = capture.to_dict(); manifest[field] = value
            with self.assertRaises(CommandValidationError):
                cp.resolve_manifest(manifest, capture.components, owner_id=OWNER, run_id=RUN, revision=capture.to_dict()['revision'])
        manifest = capture.to_dict(); manifest['source']['epoch'] = WORKER
        with self.assertRaises(CommandValidationError):
            cp.resolve_manifest(manifest, capture.components, owner_id=OWNER, run_id=RUN, revision=manifest['revision'])

    def test_transport_original_identity_prior_and_whole_budget(self):
        candidate, capture, wire = self.samples[1]
        value = numbers.decode(wire)
        self.assertEqual(value['command_id'], str(UUID(int=40_000_000 + candidate.state.revision)))
        self.assertEqual(value['history'], candidate.history)
        self.assertEqual(value['evidence'], candidate.transition['evidence'])
        with self.assertRaises(CommandValidationError):
            cp.prepare_transport(candidate, capture, command_id=str(UUID(int=4)))
        with self.assertRaises(CommandValidationError):
            cp.prepare_transport(candidate, self.samples[0][1], previous=self.samples[0][1], command_id=str(UUID(int=4)))
        with self.assertRaises(CommandValidationError):
            numbers.encode({'a': ['x' * 16000] * 20})

    def test_research_wire_cannot_enter_existing_runtime_versions(self):
        from vonneumann.db.command_protocol import PreparedCommand
        candidate = self.samples[0][0]
        for version in (5, 6):
            with self.assertRaises(ValueError):
                PreparedCommand.batch(OWNER, RUN, WORKER, 1, 1, candidate.operations,
                                      version=version, transition=candidate.transition)

    def test_repeated_preparation_keeps_original_wire_and_rng(self):
        ledger = ga.SimulationLedger(OWNER, RUN)
        candidate = ga.bootstrap(ga.GAConfig('genetic_algorithm', OWNER, RUN, asset='SOL/USD', source_epoch=EPOCH),
            seed_bundle(), source_inputs(WALL), ledger=ledger)
        state = ledger.accept(candidate); before = state.to_dict()
        frame = ga.source.make_frame(raw_capture(), prior_source=before['source'], epoch=EPOCH,
            wall_now=WALL, monotonic_now=MONO)
        inputs = source_inputs(WALL, serial=98)
        first = ga.prepare_protective(state, frame, inputs, ledger=ledger)
        repeated = ga.prepare_protective(state, frame, inputs, ledger=ledger)
        self.assertEqual(first._wire, repeated._wire)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(ledger._owned_current.to_dict(), before)
        self.assertEqual(ledger.history, [candidate.history])

    def test_counter_wire_exceeds_javascript_safe_integer_without_rounding(self):
        evidence = {'revision': 2**63 - 1, 'slot': 2**64 - 1, 'negative': -(2**200),
                    'yes': True, 'float': 0.1, 'negative_zero': -0.0}
        wire = numbers.encode(evidence)
        self.assertEqual(numbers.decode(wire), evidence)
        self.assertIn(b'9223372036854775807', wire)
        self.assertEqual(numbers.decode(wire)['negative_zero'].hex(), '-0x0.0p+0')
        node = shutil.which('node')
        self.assertIsNotNone(node, 'The existing local Node runtime is required for the wire acceptance test')
        copied = subprocess.run([node, '-e', "process.stdout.write(JSON.stringify(JSON.parse(require('fs').readFileSync(0,'utf8'))))"],
            input=wire, capture_output=True, check=True, timeout=10).stdout
        self.assertEqual(copied, wire)
        for value in ({'x': 9007199254740992}, {'x': {'$integer': '01'}}, {'x': {'$integer': '-0'}},
                      {'x': {'$float64': 'nan'}}, {'x': {'$integer': '1', 'other': 'x'}}):
            with self.assertRaises(CommandValidationError): numbers.decode(canonical_json(value))
        for value in ({'$integer': '1'}, {'x': float('nan')}, {'x': 2**256}):
            with self.assertRaises(CommandValidationError): numbers.encode(value)
        with self.assertRaises(CommandValidationError): numbers.decode(b'{"x":true,"x":false}')

    def test_early_death_freezes_provider_metrics_and_rejects_tampered_history(self):
        ledger = ga.SimulationLedger(OWNER, RUN)
        candidate = ga.bootstrap(ga.GAConfig('genetic_algorithm', OWNER, RUN, asset='SOL/USD',
            source_epoch=EPOCH, account_loss_bps='9000'),
            seed_bundle(last_close='80'), source_inputs(WALL), ledger=ledger)
        state = ledger.accept(candidate)
        for serial, offset in enumerate((1, 900, 901), 1):
            wall, mono = WALL + offset, MONO + offset
            frame = ga.source.make_frame(raw_capture(block=100 + serial, source_second=wall - 2,
                wall=wall - 1, mono=mono - 1), prior_source=state.to_dict()['source'],
                epoch=EPOCH, wall_now=wall, monotonic_now=mono)
            state = ledger.accept(ga.prepare_protective(state, frame, source_inputs(wall, mono=mono, serial=serial * 2), ledger=ledger))
            history = None if offset != 900 else ga.source.build_history(raw_minutes(end=END + 900, count=15,
                close='120', wall=wall - 1, mono=mono - 1), prior_bars=state.to_dict()['source']['bars'], seed=False,
                wall_us=wall * 1_000_000, monotonic_us=int(mono * 1_000_000))
            state = ledger.accept(ga.prepare_decision(state, frame, history, source_inputs(wall, mono=mono, serial=serial * 2 + 1), ledger=ledger))
        self.assertTrue(state.to_dict()['positions'])
        wall, mono = WALL + 902, MONO + 902
        frame = ga.source.make_frame(raw_capture(price='0.1', block=105, source_second=wall - 2,
            wall=wall - 1, mono=mono - 1), prior_source=state.to_dict()['source'], epoch=EPOCH,
            wall_now=wall, monotonic_now=mono)
        candidate = ga.prepare_protective(state, frame, source_inputs(wall, mono=mono, serial=80), ledger=ledger)
        capture = cp.capture_owned_candidate(candidate)
        terminals = [m for m in capture.resolve()['engine']['members'] if m['terminal']]
        self.assertTrue(terminals)
        self.assertTrue(all(m['assessment']['source']['frame'] == frame for m in terminals))
        altered = json.loads(candidate._wire); altered['history']['closed_positions'] = []
        forged = ga.GACandidate(candidate.state, ga.base._json(altered),
            len(json.dumps(altered, sort_keys=True, separators=(', ', ': ')).encode()))
        with self.assertRaises(ga.ExactRehearsalError): ledger.accept(forged)
        state = ledger.accept(candidate)
        stopped = ga.prepare_control(state, 'stop', source_inputs(wall + 1, mono=mono + 1, serial=81), ledger=ledger)
        cp.capture_owned_candidate(stopped).resolve()
        frozen = [r for r in stopped.history['assessments'] if r['early_terminal_frozen']]
        self.assertEqual(len(frozen), len(terminals))
        self.assertTrue(all(r['metrics']['source']['frame'] == frame and r['fitness_float64'] is None for r in frozen))

    def test_final_reserved_revision_stop_and_source_overflow_are_explicit(self):
        ledger = ga.SimulationLedger(OWNER, RUN)
        candidate = ga.bootstrap(ga.GAConfig('genetic_algorithm', OWNER, RUN, asset='SOL/USD', source_epoch=EPOCH),
            seed_bundle(), source_inputs(WALL), ledger=ledger)
        state = ledger.accept(candidate)
        data, strategy, cohort = state._fork()
        data['revision'] = 2**63 - 2
        state = ga.GAState._seal(data, strategy, cohort)
        # Controlled counter fixture, not restoration or a database admission.
        ledger._current, ledger._owned_current = deepcopy(data), state
        with self.assertRaises(ga.base.ExactCapacityError):
            ga.prepare_control(state, 'pause', source_inputs(WALL + 1, serial=60), ledger=ledger)
        stopped = ga.prepare_control(state, 'stop', source_inputs(WALL + 1, serial=61), ledger=ledger)
        self.assertEqual(cp.capture_owned_candidate(stopped).resolve()['revision'], 2**63 - 1)

    def test_provider_freshness_history_revision_and_epoch_fail_before_acceptance(self):
        ledger = ga.SimulationLedger(OWNER, RUN)
        candidate = ga.bootstrap(ga.GAConfig('genetic_algorithm', OWNER, RUN, asset='SOL/USD', source_epoch=EPOCH),
            seed_bundle(), source_inputs(WALL), ledger=ledger)
        state = ledger.accept(candidate)
        frame = ga.source.make_frame(raw_capture(), prior_source=state.to_dict()['source'], epoch=EPOCH,
            wall_now=WALL, monotonic_now=MONO)
        for changed in ('stale', 'epoch', 'sequence'):
            altered = deepcopy(frame)
            if changed == 'stale': altered['quote']['document']['received_wall_us'] -= 6_000_000
            elif changed == 'epoch':
                data = state.to_dict()['source']; data['epoch'] = WORKER
                with self.assertRaises(ga.source.ProviderSourceError):
                    ga.source.validate_frame(altered, prior_source=data, epoch=EPOCH)
                continue
            else: altered['sequence'] = 0
            with self.assertRaises(ga.source.ProviderSourceError):
                ga.prepare_protective(state, altered, source_inputs(WALL, serial=95), ledger=ledger)
        history = seed_bundle(); history['documents'][0]['response_sha256'] = 'a' * 64
        with self.assertRaises(ga.source.ProviderSourceError):
            ga.source.validate_history(history, prior_bars=state.to_dict()['source']['bars'], seed=False,
                wall_us=WALL * 1_000_000, monotonic_us=int(MONO * 1_000_000))
        self.assertEqual(ledger._owned_current.to_dict(), state.to_dict())

    def test_new_source_sequence_does_not_relax_v5_or_accept_reset(self):
        _, last, capture, ledger = self.traces[False]
        prior = last.state.to_dict()['source']; prior['quote_sequence'] = 4096
        prior['last_quote']['sequence'] = 4096
        wall = prior['last_quote']['decision_second'] + 1
        mono = prior['last_quote']['decision_monotonic_us'] / 1_000_000 + 1
        frame = ga.source.make_frame(raw_capture(block=prior['last_quote']['quote']['block_ref'] + 1,
            source_second=wall - 2, wall=wall - 1, mono=mono - 1), prior_source=prior,
            epoch=EPOCH, wall_now=wall, monotonic_now=mono)
        self.assertEqual(frame['sequence'], 4097)
        legacy = deepcopy(prior); legacy['version'] = 1
        with self.assertRaises(old_source.ProviderSourceError):
            old_source.make_frame(raw_capture(), prior_source=legacy, epoch=EPOCH, wall_now=wall, monotonic_now=mono)
        frame['sequence'] = 1
        with self.assertRaises(ga.source.ProviderSourceError): ga.source.validate_frame(frame, prior_source=prior, epoch=EPOCH)

    def test_stop_needs_no_provider_fetch_and_aborted_records_withhold_scores(self):
        _, last, capture, ledger = self.traces[False]
        data = last.state.to_dict(); at = data['engine']['last_quote']['timestamp'] + 1
        candidate = ga.prepare_control(last.state, 'stop', source_inputs(at, mono=MONO + at - WALL, serial=9999), ledger=ledger)
        stopped = cp.capture_owned_candidate(candidate)
        wire = cp.prepare_transport(candidate, stopped, previous=capture, command_id=str(UUID(int=99111)))
        self.assertLess(len(wire), cp.MAX_RESOLVED_BYTES)
        self.assertIsNone(numbers.decode(wire)['evidence']['inputs']['provider']['frame'])
        self.assertTrue(all(row['fitness_float64'] is None and row['metrics']['roi_ratio'] is None
                            for row in candidate.history['assessments']))
        self.assertEqual(ledger.accept(candidate).to_dict()['status'], 'stopped')
        self.assertEqual(ledger.accept(candidate).to_dict()['revision'], candidate.state.revision)


class ProviderSourceOverflowTests(OfflineTestMixin, unittest.TestCase):
    def test_last_source_sequence_rejects_without_wrap_or_mutation(self):
        bars = ga.source.derive_bars(seed_bundle())
        prior = ga.source.source_state(EPOCH, None, bars)
        frame = ga.source.make_frame(raw_capture(), prior_source=prior, epoch=EPOCH,
            wall_now=WALL, monotonic_now=MONO)
        frame['sequence'] = ga.source.MAX_SEQUENCE
        prior = ga.source.source_state(EPOCH, frame, bars)
        before = deepcopy(prior)
        with self.assertRaises(ga.source.ProviderSourceError):
            ga.source.make_frame(raw_capture(block=101, source_second=WALL - 1, wall=WALL, mono=MONO),
                prior_source=prior, epoch=EPOCH, wall_now=WALL + 1, monotonic_now=MONO + 1)
        self.assertEqual(prior, before)


if __name__ == '__main__':
    unittest.main()
