"""Bounded Stop dispatch with a held worker transport and exact bytes."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import unittest
from uuid import UUID

from vonneumann.research.native_stop_dispatch import StopDispatch, StopDispatchError, StopIntentPins


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode()


def identity(value):
    return str(UUID(int=value))


class NativeStopDispatchTests(unittest.TestCase):
    def setUp(self):
        self.scope = dict(owner_id=identity(1), run_id=identity(2), market_epoch=identity(3))
        self.pins = StopIntentPins(canonical(self.scope), identity(4), identity(5),
                                   'a' * 64, 'b' * 64, 'c' * 64, identity(6))
        self.command = dict(
            format='ga-jupiter-b2-allocation-command-research-v3-v1',
            native_policy_sha256='e5dca1d13839102fb1fdd261176393b73c770a95ab355eff74499169905bfba0',
            scope=self.scope, action_id=identity(4), action_kind='source_stop',
            expected_head=dict(native_sequence='4', native_head_sha256='e' * 64,
                               previous_seal_sha256=None),
            expected_fence_id=None, expected_fence_revision=None,
            body=dict(expected_control_sha256='d' * 64, expected_mode='open'),
        )
        self.command_wire = canonical(self.command)
        self.digest = hashlib.sha256(self.command_wire).hexdigest()
        self.intent = dict(
            format='ga-jupiter-b2-stop-intent-research-v3-v1', installation_id=identity(5),
            native_package_sha256='a' * 64, effective_catalog_sha256='b' * 64,
            handoff_sha256='c' * 64, control_binding_id=identity(6),
            original_command_wire=self.command_wire.decode(), original_command_sha256=self.digest,
        )
        self.observation = dict(
            format='ga-jupiter-b2-stop-intent-observation-research-v3-v1', scope=self.scope,
            action_id=identity(4), resolution='observed_committed_exact',
            intent_wire=canonical(self.intent).decode(),
        )
        self.committed_wire = canonical(self.observation)
        self.calls = []

    def guard(self):
        return StopDispatch(self.command_wire, self.pins)

    def read(self, query):
        self.calls.append(('read', query))
        return self.committed_wire

    def submit(self, command):
        self.calls.append(('submit', command))
        return {'pending_commit': True}

    def test_dispatches_exact_wire_only_after_one_positive_independent_read(self):
        guard = self.guard()
        self.assertIsNone(guard.dispatch(self.read, self.submit))
        query = canonical(dict(
            format='ga-jupiter-b2-original-query-research-v3-v1',
            native_policy_sha256=self.command['native_policy_sha256'], scope=self.scope,
            target_kind='source_stop', target_id=identity(4),
            expected_original_command_sha256=self.digest,
            correlation=dict(kind='original_action_id', id=identity(4)),
        ))
        self.assertEqual(self.calls, [('read', query), ('submit', self.command_wire)])
        with self.assertRaisesRegex(StopDispatchError, 'already used'):
            guard.dispatch(self.read, self.submit)
        self.assertEqual(len(self.calls), 2)

    def test_absence_provisional_or_changed_readback_never_dispatch(self):
        absent = dict(self.observation, resolution='observed_absent_unknown', intent_wire=None)
        other_scope = dict(self.scope, run_id=identity(8))
        variants = {
            'absent': canonical(absent),
            'provisional': canonical(dict(self.observation, pending_commit=True)),
            'wrong kind': canonical(dict(self.observation, format='other')),
            'wrong scope': canonical(dict(self.observation, scope=other_scope)),
            'wrong ID': canonical(dict(self.observation, action_id=identity(9))),
            'malformed': b'{"incomplete"',
            'duplicate': self.committed_wire[:-1] + b',"resolution":"observed_committed_exact"}',
            'noncanonical': self.committed_wire + b'\n',
            'wrong representation': self.committed_wire.decode(),
        }
        changed_command = deepcopy(self.command)
        changed_command['expected_head']['native_sequence'] = '5'
        for name, value in (
            ('installation_id', identity(11)), ('native_package_sha256', 'f' * 64),
            ('effective_catalog_sha256', 'f' * 64), ('handoff_sha256', 'f' * 64),
            ('control_binding_id', identity(12)), ('original_command_sha256', 'f' * 64),
            ('original_command_wire', canonical(changed_command).decode()),
        ):
            changed_intent = canonical(dict(self.intent, **{name: value})).decode()
            variants[name] = canonical(dict(self.observation, intent_wire=changed_intent))
        for name, result in variants.items():
            with self.subTest(name=name):
                guard = self.guard()
                with self.assertRaisesRegex(StopDispatchError, 'could not be verified'):
                    guard.dispatch(lambda query: result, self.submit)
                with self.assertRaisesRegex(StopDispatchError, 'already used'):
                    guard.dispatch(self.read, self.submit)
        self.assertEqual(self.calls, [])

    def test_refuses_malformed_originals_and_untrusted_identity_pins(self):
        for key, value in (
            ('action_kind', 'fence_renew'), ('action_id', identity(20)),
            ('scope', dict(self.scope, run_id=identity(21))),
            ('native_policy_sha256', '0' * 64), ('expected_fence_revision', '1'),
            ('body', dict(self.command['body'], expected_mode='paused')),
            ('expected_head', dict(self.command['expected_head'], native_sequence='16')),
        ):
            with self.subTest(key=key), self.assertRaisesRegex(StopDispatchError, 'pins are invalid'):
                StopDispatch(canonical(dict(self.command, **{key: value})), self.pins)
        for changed_wire, pins in (
            (self.command_wire + b'\n', self.pins),
            (self.command_wire, replace(self.pins, scope_wire=b'{}')),
            (self.command_wire, replace(self.pins, handoff_sha256='bad')),
            (self.command_wire, replace(self.pins, control_binding_id='bad')),
        ):
            with self.assertRaisesRegex(StopDispatchError, 'pins are invalid'):
                StopDispatch(changed_wire, pins)
        self.assertEqual(self.calls, [])

    def test_reader_failure_closes_dispatch_without_echoing_details(self):
        def failed_reader(query):
            raise TimeoutError('private transport detail')

        guard = self.guard()
        with self.assertRaisesRegex(StopDispatchError, '^Committed original Stop intent could not be read$'):
            guard.dispatch(failed_reader, self.submit)
        with self.assertRaisesRegex(StopDispatchError, 'already used'):
            guard.dispatch(self.read, self.submit)
        self.assertEqual(self.calls, [])

    def test_unknown_submit_requires_original_reconciliation_and_has_no_retry(self):
        def lost_submit(command):
            self.submit(command)
            raise ConnectionError('private transport detail')

        guard = self.guard()
        with self.assertRaisesRegex(StopDispatchError, 'requires independent reconciliation'):
            guard.dispatch(self.read, lost_submit)
        with self.assertRaisesRegex(StopDispatchError, 'already used'):
            guard.dispatch(self.read, self.submit)
        self.assertEqual([kind for kind, _ in self.calls], ['read', 'submit'])

    def test_reader_reentry_cannot_dispatch_a_second_attempt(self):
        guard = self.guard()

        def read_with_reentry(query):
            with self.assertRaisesRegex(StopDispatchError, 'already used'):
                guard.dispatch(self.read, self.submit)
            return self.read(query)

        guard.dispatch(read_with_reentry, self.submit)
        self.assertEqual([kind for kind, _ in self.calls], ['read', 'submit'])
