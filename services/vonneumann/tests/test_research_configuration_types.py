"""Correctly rehashed adversarial configuration evidence, without authority."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from tests.security_support import OfflineTestMixin
from tests.test_provider_contract import OWNER, RUN, EPOCH, WALL, MONO, seed_bundle, source_inputs
from vonneumann.db.command_protocol import CommandValidationError
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import provider_ga_model as v1, partitioned_checkpoint as cp1
from vonneumann.research import provider_portable_ga_model as v2, portable_partitioned_checkpoint as cp2

ROOT = Path(__file__).resolve().parents[1]
MODEL_PAIRS = ((v1, cp1), (v2, cp2))


def leaves(value, path=()):
    if type(value) is dict:
        for key, item in value.items():
            yield from leaves(item, path + (key,))
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from leaves(item, path + (index,))
    else:
        yield path, value


def replace(value, path, following):
    for key in path[:-1]:
        value = value[key]
    value[path[-1]] = following


def fixture(model, checkpoint, **settings):
    ledger = model.SimulationLedger(OWNER, RUN)
    candidate = model.bootstrap(model.GAConfig('genetic_algorithm', OWNER, RUN,
        asset='SOL/USD', source_epoch=EPOCH, **settings), seed_bundle(), source_inputs(WALL), ledger=ledger)
    state = ledger.accept(candidate)
    return candidate, checkpoint.capture_owned_candidate(candidate), ledger, state


def rehashed_configuration(checkpoint, captured, altered):
    manifest = captured.to_dict()
    blocks = []
    for block in captured.components:
        value = block.to_dict()
        if value['kind'] == 'configuration':
            value['body'] = altered
            # Encode first so even a float alias has a real canonical wire/hash.
            wire = numbers.encode(value)
            reference = block.reference() | {'sha256': hashlib.sha256(wire).hexdigest()}
            manifest['components'] = [reference if ref['kind'] == 'configuration' else ref
                                      for ref in manifest['components']]
            block = checkpoint.TypedComponent(wire)
        blocks.append(block)
    return manifest, tuple(blocks)


class ResearchConfigurationTypeTests(OfflineTestMixin, unittest.TestCase):
    def test_unsupported_key_equality_is_never_invoked(self):
        calls = []

        class UnreviewedKey(str):
            __hash__ = str.__hash__

            def __eq__(self, other):
                calls.append(other)
                raise AssertionError('Unreviewed key equality invoked')

        for model, checkpoint in MODEL_PAIRS:
            candidate, _, _, _ = fixture(model, checkpoint)
            data = candidate.state.to_dict()
            original = data['engine']['config']
            data['engine']['config'] = {UnreviewedKey(key) if key == 'profile' else key: item
                                       for key, item in original.items()}
            with patch.object(model, 'GAConfig', side_effect=AssertionError('Untrusted constructor reached')):
                with self.assertRaises(model.ExactRehearsalError):
                    model._configuration(data)
        self.assertEqual(calls, [])

    def test_every_scalar_type_alias_fails_before_model_reconstruction(self):
        checked = 0
        for model, checkpoint in MODEL_PAIRS:
            candidate, _, _, _ = fixture(model, checkpoint)
            data = candidate.state.to_dict()
            for path, original in leaves(data['engine']['config']):
                alternatives = (False, 0, 0.0, '0')
                for replacement in alternatives:
                    if type(replacement) is type(original):
                        continue
                    altered = deepcopy(data)
                    replace(altered['engine']['config'], path, replacement)
                    with self.subTest(model=model.MODEL_FORMAT, path=path, kind=type(replacement).__name__):
                        with patch.object(model, 'GAConfig', side_effect=AssertionError('Untrusted constructor reached')):
                            with self.assertRaises(model.ExactRehearsalError):
                                model._configuration(altered)
                        checked += 1
        self.assertGreater(checked, 300)

    def test_rehashed_nested_types_and_unknown_missing_fields_are_refused(self):
        for model, checkpoint in MODEL_PAIRS:
            candidate, capture, _, _ = fixture(model, checkpoint)
            original = candidate.state.to_dict()['engine']['config']
            alterations = [
                ('bool_for_zero', lambda c: replace(c, ('lifecycle_policy', 'max_lifespan_seconds'), False)),
                ('float_for_zero', lambda c: replace(c, ('lifecycle_policy', 'max_lifespan_seconds'), 0.0)),
                ('string_for_zero', lambda c: replace(c, ('lifecycle_policy', 'max_lifespan_seconds'), '0')),
                ('bool_for_integer', lambda c: replace(c, ('execution', 'cash_scale'), True)),
                ('float_for_integer', lambda c: replace(c, ('execution', 'cash_scale'), 36.0)),
                ('integer_for_string', lambda c: replace(c, ('execution', 'config', 'fee_bps'), 0)),
                ('float_for_string', lambda c: replace(c, ('source_policy', 'epoch'), 0.0)),
                ('boolean_header', lambda c: c.update(profile=False)),
                ('unknown_top_field', lambda c: c.update(unreviewed_setting=0)),
                ('missing_top_field', lambda c: c.pop('code_version')),
                ('unknown_nested_field', lambda c: c['lifecycle_policy'].update(unreviewed_setting=0)),
                ('missing_nested_field', lambda c: c['execution']['config'].pop('fee_bps')),
            ]
            if model is v2:
                alterations.extend([
                    ('domain_boolean', lambda c: replace(c, ('mutation_policy', 'domains', 'ema_fast', 0), True)),
                    ('radius_string', lambda c: replace(c, ('mutation_policy', 'radii', 'ema_fast'), '3')),
                    ('gene_integer', lambda c: replace(c, ('mutation_policy', 'genes', 0), 0)),
                    ('extra_gene', lambda c: c['mutation_policy']['genes'].append('rsi_period')),
                    ('missing_domain', lambda c: c['mutation_policy']['domains'].pop('ema_slow')),
                ])
            for label, alter in alterations:
                changed = deepcopy(original)
                alter(changed)
                with self.subTest(model=model.MODEL_FORMAT, alteration=label):
                    with self.assertRaises(CommandValidationError):
                        manifest, components = rehashed_configuration(checkpoint, capture, changed)
                        checkpoint.resolve_manifest(manifest, components, owner_id=OWNER,
                            run_id=RUN, revision=candidate.state.revision)

    def test_original_wire_rejection_preserves_state_rng_ledger_and_reserved_stop(self):
        for model, checkpoint in MODEL_PAIRS:
            candidate, capture, ledger, state = fixture(model, checkpoint)
            before_data, before_strategy, _ = state._fork()
            before_wire = model.base._json(before_data)
            before_rng = before_strategy._rng.getstate()
            before_history = deepcopy(ledger.history)
            before_identities = set(ledger._identities)
            before_accepted = set(ledger._accepted)
            inputs = source_inputs(WALL + 1, mono=MONO + 1, serial=80)
            stop_before = model.prepare_control(state, 'stop', inputs, ledger=ledger)
            before_stop_capture = checkpoint.capture_owned_candidate(stop_before)
            before_stop_wire = checkpoint.prepare_transport(stop_before, before_stop_capture,
                command_id='00000000-0000-0000-0000-000000000080', previous=capture)
            control = model.prepare_control(state, 'pause', inputs, ledger=ledger)
            for original in (candidate, control):
                for side in ('before', 'after'):
                    payload = json.loads(original._wire)
                    if payload['transition'][side] is None:
                        continue
                    payload['transition'][side]['engine']['config']['lifecycle_policy']['max_lifespan_seconds'] = False
                    wire = model.base._json(payload)
                    expanded_size = len(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                        allow_nan=False, separators=(', ', ': ')).encode('utf-8'))
                    with self.subTest(model=model.MODEL_FORMAT, phase=payload['transition']['evidence']['kind'], side=side):
                        with self.assertRaises(model.ExactRehearsalError):
                            model.GACandidate(original.state, wire, expanded_size)
            altered = deepcopy(before_data['engine']['config'])
            altered['lifecycle_policy']['max_lifespan_seconds'] = False
            with self.assertRaises(CommandValidationError):
                manifest, components = rehashed_configuration(checkpoint, capture, altered)
                checkpoint.resolve_manifest(manifest, components, owner_id=OWNER, run_id=RUN, revision=state.revision)
            after_data, after_strategy, _ = state._fork()
            self.assertEqual(model.base._json(after_data), before_wire)
            self.assertEqual(after_strategy._rng.getstate(), before_rng)
            self.assertEqual(ledger.history, before_history)
            self.assertEqual(ledger._identities, before_identities)
            self.assertEqual(ledger._accepted, before_accepted)
            self.assertEqual(model.base._json(ledger._current), before_wire)
            stop_after = model.prepare_control(state, 'stop', inputs, ledger=ledger)
            after_stop_capture = checkpoint.capture_owned_candidate(stop_after)
            after_stop_wire = checkpoint.prepare_transport(stop_after, after_stop_capture,
                command_id='00000000-0000-0000-0000-000000000080', previous=capture)
            self.assertEqual(stop_after._wire, stop_before._wire)
            self.assertEqual(after_stop_wire, before_stop_wire)
            self.assertEqual(ledger.accept(stop_after).to_dict()['status'], 'stopped')

    def test_canonical_variable_settings_keep_versions_and_software_bindings(self):
        from vonneumann.core.decimal_execution import DecimalExecutionConfig
        for model, checkpoint in MODEL_PAIRS:
            candidate, capture, _, _ = fixture(model, checkpoint, search_seed='18446744073709551615',
                initial_cash='2000', seed_capital='200', account_loss_bps='9000',
                execution=DecimalExecutionConfig('25', '5', '10'))
            data = candidate.state.to_dict()
            rebuilt = model._configuration(data)
            self.assertEqual(model.base._json(rebuilt.to_dict()), model.base._json(data['engine']['config']))
            resolved = capture.resolve()
            self.assertEqual(resolved['source_model_version'], model.MODEL_FORMAT)
            self.assertEqual(resolved['engine']['optimizer']['software'], data['engine']['optimizer']['software'])
            self.assertEqual(json.loads(candidate._wire)['format'], model.COMMAND_FORMAT)
            self.assertEqual(resolved['engine']['config']['profile'], model.PROFILE)
            self.assertEqual(resolved['engine']['config']['execution']['version'], 'usd-reference-decimal-v2')

    def test_repair_provenance_keeps_historical_evidence_and_binds_current_sources(self):
        historical_path = ROOT / 'research/2026-10-12-config-type-review.json'
        historical = json.loads(historical_path.read_text())
        repair = json.loads((ROOT / 'research/configuration-type-repair-measurements.json').read_text())
        self.assertEqual(hashlib.sha256(historical_path.read_bytes()).hexdigest(), repair['historical_defect_artifact_sha256'])
        self.assertTrue(all(row['actual']['accepted'] for row in historical['results']))
        self.assertTrue(all(not row['actual']['accepted'] for row in repair['results']))
        for name, expected in repair['source_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
        for name in ('provider_ga_model.py', 'provider_portable_ga_model.py'):
            path = 'vonneumann/research/' + name
            self.assertEqual(repair['source_before'][path], historical['source_sha256'][path])
        self.assertFalse(repair['native_admission'])
        self.assertFalse(repair['restoration_authority'])
