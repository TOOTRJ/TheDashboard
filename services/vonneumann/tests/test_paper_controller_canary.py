"""No-network boundaries for the explicitly selected finite hosted assessment."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tests.security_support import OfflineTestMixin, deny_network
with deny_network():
    from tools import paper_controller_canary as module


class CanaryTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def configuration(self, **changes):
        return {'VN_SERVICE_MODE': 'closed', 'VN_PAPER_ACCEPTANCE': 'finite-controller-v1',
                'VN_JUPITER_SOLE_CONSUMER': '1', **changes}

    def test_closed_explicit_scope_and_sole_consumer_are_required_before_construction(self):
        for change in ({'VN_SERVICE_MODE': 'paper-v5'}, {'VN_PAPER_ACCEPTANCE': ''},
                       {'VN_JUPITER_SOLE_CONSUMER': '0'}):
            with patch.object(module, 'configured_service') as factory:
                with self.assertRaises(ValueError): module.configuration(self.configuration(**change))
                factory.assert_not_called()

    def test_budget_is_finite_and_selection_does_not_change_environment(self):
        environment = self.configuration()
        original = environment.copy()
        for interval, ticks in ((4, 12), (5, 31), (5, 0)):
            with patch.object(module, 'configured_service', return_value=SimpleNamespace(_ticks=ticks, _interval=interval)):
                with self.assertRaises(ValueError): module.configuration(environment)
        service = SimpleNamespace(_ticks=30, _interval=5)
        with patch.object(module, 'configured_service', return_value=service) as factory:
            self.assertIs(module.configuration(environment), service)
            self.assertEqual(factory.call_args.args[0]['VN_SERVICE_MODE'], 'paper-v5')
        self.assertEqual(environment, original)

    async def test_instrumentation_keeps_identity_payload_result_and_single_owned_call(self):
        class Transport:
            def __init__(self): self.calls = []; self.closed = False
            async def rpc(self, name, arguments):
                self.calls.append((name, arguments))
                return arguments
            async def aclose(self): self.closed = True
        original = Transport(); measured = module.MeasuredTransport(original)
        arguments = {'private_body': 'never-retained-in-metrics'}
        self.assertIs(await measured.accept_event(arguments), arguments)
        self.assertEqual(original.calls, [('accept_event', arguments)])
        self.assertEqual(measured.calls, 1)
        self.assertEqual(set(measured.samples), {'accept_event'})
        self.assertEqual(len(measured.samples['accept_event']), 1)
        await measured.aclose(); self.assertTrue(original.closed)
        with self.assertRaises(ValueError): await measured.rpc('unreviewed_function', {})
        self.assertEqual(len(original.calls), 1)

    async def test_failure_and_cancellation_are_counted_once_and_never_retried(self):
        for error in (OSError('private diagnostics'), asyncio.CancelledError()):
            calls = []
            async def rpc(name, arguments):
                calls.append(name)
                raise error
            measured = module.MeasuredTransport(SimpleNamespace(rpc=rpc))
            with self.assertRaises(type(error)): await measured.rpc('commit_command', {})
            self.assertEqual(calls, ['commit_command'])
            self.assertEqual(dict(measured.errors), {'commit_command': 1})
            self.assertEqual(len(measured.samples['commit_command']), 1)
