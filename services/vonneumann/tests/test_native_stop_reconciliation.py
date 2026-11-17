"""Exercise exact original Stop readback without a control transport."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import unittest

from tests.test_native_stop_dispatch import canonical, identity
from vonneumann.market.provider_acquisition_v3 import AcquisitionError
from vonneumann.research.native_stop_dispatch import NATIVE_POLICY_SHA256, StopIntentPins
from vonneumann.research.native_stop_reconciliation import StopReconciliation


def digest(raw):
    return sha256(raw).hexdigest()


def native_format(record):
    return f'ga-jupiter-b2-{record}-research-v3-v1'


def pin(kind, original_id, value):
    raw = canonical(value)
    return dict(semantic_kind=kind, original_id=original_id, original_wire=raw.decode(),
                wire_sha256=digest(raw), wire_bytes=str(len(raw)))


class NativeStopReconciliationTests(unittest.TestCase):
    def setUp(self):
        scope = dict(owner_id=identity(1), run_id=identity(2), market_epoch=identity(3))
        stop_id = identity(4)
        self.pins = StopIntentPins(canonical(scope), stop_id, identity(5),
                                   'a' * 64, 'b' * 64, 'c' * 64, identity(6))
        self.common = dict(native_policy_sha256=NATIVE_POLICY_SHA256, scope=scope)
        control = pin('native_command', identity(7), dict(**self.common,
            action_kind='source_resume', action_id=identity(7)))
        fence = pin('native_fence_record', identity(8), dict(scope=scope, fence_id=identity(8), revision='2'))
        self.previous_head = 'e' * 64
        self.command = dict(format=native_format('allocation-command'), **self.common,
            action_id=stop_id, action_kind='source_stop',
            expected_head=dict(native_sequence='5', native_head_sha256=self.previous_head, previous_seal_sha256=None),
            expected_fence_id=None, expected_fence_revision=None,
            body=dict(expected_control_sha256=control['wire_sha256'], expected_mode='open'))
        self.command_wire = canonical(self.command)
        self.action = dict(action_id=stop_id, action_kind='source_stop',
                           original_command_sha256=digest(self.command_wire))
        self.limits = dict.fromkeys(('provider_attested', 'calibrated_clock', 'hosted_authority',
                                    'running_authority', 'live_trading_authority', 'model_native_join'), False)
        self.target = dict(target_kind='source_stop', target_id=stop_id)
        self.query = canonical(dict(format=native_format('original-query'), **self.common, **self.target,
            expected_original_command_sha256=self.action['original_command_sha256'],
            correlation=dict(kind='original_action_id', id=stop_id)))
        self.result = dict(format=native_format('allocation-result'), **self.common, **self.action,
            native_sequence='6', dependencies=[control, fence], limits=self.limits,
            result_body=dict(previous_mode='open', resulting_mode='stopped',
                             previous_control_sha256=control['wire_sha256'], resulting_fence_revision='3'))
        result_wire = canonical(self.result)
        self.receipt = dict(format=native_format('allocation-receipt'), **self.common, **self.action,
            native_sequence='6', result_sha256=digest(result_wire), previous_native_head_sha256=self.previous_head,
            admission_observation=None, native_package_sha256='a' * 64, catalog_manifest_sha256='b' * 64,
            final_function_observation=dict.fromkeys(('observed_at_us', 'wall_lower_us', 'wall_upper_us'), '22'),
            commit_processing_observation=dict.fromkeys(('observed_at_us', 'wall_lower_us', 'wall_upper_us'), '23'),
            limits=self.limits)
        receipt_wire = canonical(self.receipt)
        self.receipt_sha = digest(receipt_wire)
        self.stop_head = digest(canonical(dict(native_sequence='6', **self.action,
            original_result_sha256=digest(result_wire), original_receipt_sha256=self.receipt_sha,
            previous_native_head_sha256=self.previous_head)))
        self.reply = dict(format=native_format('original-reply'), **self.common, **self.target,
            original_command_wire=self.command_wire.decode(), original_result_wire=result_wire.decode(),
            original_receipt_wire=receipt_wire.decode(), dependencies=[control, fence], limits=self.limits,
            observed_head=dict(native_sequence='6', native_head_sha256=self.stop_head, previous_seal_sha256=None))
        self.adapter = StopReconciliation(self.command_wire, self.pins)
        self.reads = []

    def read(self, response):
        def getter(raw):
            self.reads.append(raw)
            return response
        return self.adapter.read(getter)

    def test_reconciles_exact_current_stop_and_retains_hashes_after_later_capture(self):
        current = self.read(canonical(self.reply))
        self.assertEqual(current.resolution, 'observed_committed_exact')
        self.assertEqual(current.receipt_sha256, self.receipt_sha)
        self.assertEqual(current.stop_head_sha256, self.stop_head)
        later = deepcopy(self.reply)
        later['observed_head'].update(native_sequence='7', native_head_sha256='f' * 64)
        self.assertEqual(self.read(canonical(later)), current)
        self.assertEqual(self.reads, [self.query, self.query])

    def test_missing_provisional_malformed_and_transport_failure_are_unknown(self):
        absent = canonical(dict(format=native_format('query-observation'), **self.common, **self.target,
            correlation=dict(kind='original_action_id', id=self.pins.reserved_stop_id),
            resolution='observed_absent_unknown', observed_head=self.command['expected_head'],
            original_operation_pin=None, limits=self.limits))
        def disconnected(query):
            self.assertEqual(query, self.query)
            raise ConnectionError('private transport diagnostic')
        for response in (absent, canonical({'pending_commit': True}), b'{broken', canonical(self.reply) + b'\n'):
            with self.subTest(response=response[:32]):
                outcome = self.read(response)
                self.assertEqual(outcome.resolution, 'unknown')
                self.assertIsNone(outcome.receipt_sha256)
                self.assertIsNone(outcome.stop_head_sha256)
        self.assertEqual(self.adapter.read(disconnected).resolution, 'unknown')

    def test_refuses_mismatched_original_result_receipt_and_dependencies(self):
        variants = [dict(self.reply, target_id=identity(12)), dict(self.reply, target_kind='source_resume'),
                    dict(self.reply, scope=dict(self.common['scope'], run_id=identity(12))),
                    dict(self.reply, native_policy_sha256='f' * 64),
                    dict(self.reply, original_command_wire=canonical(dict(self.command, action_id=identity(12))).decode())]
        for field, value in (('action_id', identity(12)), ('native_policy_sha256', 'f' * 64),
                             ('original_command_sha256', 'f' * 64), ('native_sequence', '7')):
            variants.append(dict(self.reply, original_result_wire=canonical(dict(self.result, **{field: value})).decode()))
        for field, value in (('result_sha256', 'f' * 64), ('native_package_sha256', 'f' * 64),
                             ('catalog_manifest_sha256', 'f' * 64), ('previous_native_head_sha256', 'f' * 64),
                             ('commit_processing_observation', self.receipt['final_function_observation'])):
            variants.append(dict(self.reply, original_receipt_wire=canonical(dict(self.receipt, **{field: value})).decode()))
        for field, value in (('native_head_sha256', 'f' * 64), ('native_sequence', '5')):
            variants.append(dict(self.reply, observed_head=dict(self.reply['observed_head'], **{field: value})))
        damaged_pin = deepcopy(self.reply)
        damaged_pin['dependencies'][0]['wire_sha256'] = 'f' * 64
        variants.append(damaged_pin)
        variants.append(dict(self.reply, dependencies=self.reply['dependencies'][1:]))
        for index, response in enumerate(variants):
            with self.subTest(index=index):
                self.assertEqual(self.read(canonical(response)).resolution, 'unknown')

    def test_invalid_reserved_id_never_constructs_a_reader(self):
        with self.assertRaises(AcquisitionError):
            StopReconciliation(self.command_wire, replace(self.pins, reserved_stop_id=identity(10)))
        with self.assertRaises(AcquisitionError):
            StopReconciliation(self.command_wire + b'\n', self.pins)
        self.assertEqual(self.reads, [])
