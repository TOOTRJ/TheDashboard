"""Provider retrieval ownership over real v5 admission and literal price bytes.

The feed and transport are offline fakes. Acquisition races must preserve the
same capture and owner-issued ticket without inventing clocks or issuing an
economic command merely because a provider response arrived.
"""
from __future__ import annotations

import asyncio
from collections import deque
import time
from unittest.mock import patch
import unittest
from uuid import UUID

from tests.security_support import deny_network
from tests.test_exact_rehearsal import OWNER, RUN, WORKER
from tests.test_provider_contract import EPOCH, WALL, MONO, raw_capture, raw_minutes
from tests.test_transition_coordinator import Clock, CommittingTransport
from vonneumann.core import exact_lifecycle as kernel
from vonneumann.core import provider_lifecycle as life
from vonneumann.core import provider_acquisition as module
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandAdmissionError, CommandBusy, CommandRepository
from vonneumann.db.provider_owner import ProviderAdmissionOwner, ProviderQuote
from vonneumann.market.provider_contract import ProviderSourceError


class FeedGate:
    """Wait before returning a feed response, with visible cancellation."""
    def __init__(self, result):
        self.result = result
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    async def __call__(self):
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result


class ExactFeed:
    """Return only previously parsed immutable captures; forbid legacy views."""
    def __init__(self, *responses):
        self.responses = deque(responses)
        self.calls = []

    async def get_price_captures(self, assets):
        self.calls.append(tuple(assets))
        if not self.responses:
            raise AssertionError('Acquisition unexpectedly refetched the provider')
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return await response()
        return response

    async def get_ticks(self, *_args, **_kwargs):
        raise AssertionError('Acquisition must not use the floating-point tick path')


class ProviderAcquisitionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.wall, self.mono = Clock(), Clock()
        self.wall.value, self.mono.value = float(WALL), MONO
        self.transport = CommittingTransport()
        self.repo = CommandRepository(self.transport, OWNER, RUN, WORKER, monotonic=self.mono)
        self.owner = None
        self.acquisition = None
        self.identities = 18_000_000
        self.tasks, self.gates = [], []

    async def asyncTearDown(self):
        for gate in self.gates:
            gate.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 3)
        if self.acquisition is not None:
            try:
                await asyncio.wait_for(self.acquisition.settle(), 3)
            except (CommandAdmissionError, ProviderSourceError, TimeoutError):
                pass

    def identity(self):
        self.identities += 1
        return str(UUID(int=self.identities))

    def allocation(self, generation=1):
        return {'ids': tuple(self.identity() for _ in range(9)),
                'names': tuple((generation, f'Acquisition-{generation}-{i}') for i in range(8)),
                'command_id': self.identity()}

    def age(self, delta):
        self.wall.value += delta
        self.mono.value += delta

    def capture(self, *, block=100, price='100', wall=None, mono=None, source_second=None):
        return raw_capture(block=block, price=price,
            wall=self.wall.value - 1 if wall is None else wall,
            mono=self.mono.value - 1 if mono is None else mono,
            source_second=int(self.wall.value) - 2 if source_second is None else source_second)

    def response(self, capture):
        return {'SOL/USDC': capture}

    def spawn(self, awaitable):
        task = asyncio.create_task(awaitable)
        self.tasks.append(task)
        return task

    def gate(self, capture):
        gate = FeedGate(self.response(capture))
        self.gates.append(gate)
        return gate

    async def ready(self, *responses):
        config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
            'genetic_algorithm', OWNER, RUN, asset='SOL/USD'), EPOCH)
        await self.repo.submit(PreparedCommand.create(OWNER, RUN, WORKER,
            config.run_configuration(), config.initial_cash, command_id=self.identity()))
        self.owner = ProviderAdmissionOwner(self.repo, self.transport, config,
            wall_clock=self.wall, monotonic=self.mono)
        await self.owner.heartbeat()
        await self.owner.bootstrap(raw_minutes(), **self.allocation(0))
        await self.owner.publish_pending(self.sink)
        self.feed = ExactFeed(*responses)
        self.acquisition = module.ProviderPriceAcquisition(self.feed, self.owner)
        return self.acquisition

    async def sink(self, _event):
        return None

    async def accept(self, ticket):
        await self.owner.protect(ticket, **self.allocation())
        await self.owner.decide(ticket, **self.allocation())
        await self.owner.publish_pending(self.sink)

    def assert_closed(self):
        self.assertFalse(self.acquisition.accepting)
        self.assertFalse(self.owner.accepting)
        self.assertIsNotNone(self.owner.closed_reason)

    async def test_exact_capture_returns_owner_ticket_without_commands_or_legacy_float_path(self):
        capture = self.capture(price='1.000000000000000001')
        await self.ready(self.response(capture))
        previous = self.owner.installed_state
        count = self.transport.count('commit_command')
        ticket = await self.acquisition.capture_quote()
        self.assertIs(type(ticket), ProviderQuote)
        self.assertEqual(ticket.frame['quote']['price'], '1.000000000000000001')
        self.assertEqual(ticket.frame['quote']['document']['response_sha256'],
                         capture.record.document.response_sha256)
        self.assertEqual(self.feed.calls, [('SOL/USDC',)])
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.assertTrue(self.acquisition.accepting)

    async def test_fractional_capture_waits_for_actual_next_second_and_does_not_refetch(self):
        await self.ready()
        self.age(.25)
        capture = self.capture(wall=self.wall.value, mono=self.mono.value)
        self.feed.responses.append(self.response(capture))
        previous = self.owner.installed_state
        self.assertIsNone(await self.acquisition.capture_quote())
        self.assertTrue(self.acquisition.has_deferred_capture)
        self.assertEqual(self.feed.calls, [('SOL/USDC',)])
        self.assertIs(self.owner.installed_state, previous)
        self.assertTrue(self.owner.accepting)
        self.age(.5)
        self.assertIsNone(await self.acquisition.capture_quote())
        self.age(.25)
        ticket = await self.acquisition.capture_quote()
        self.assertFalse(self.acquisition.has_deferred_capture)
        self.assertEqual(len(self.feed.calls), 1)
        self.assertEqual(ticket.frame['decision_second'], WALL + 1)
        self.assertEqual(ticket.frame['quote']['document']['received_wall_us'],
                         capture.record.document.manifest()['received_at'] * 1_000_000)
        self.assertEqual(ticket.frame['quote']['document']['response_sha256'],
                         capture.record.document.response_sha256)

    async def test_unchanged_source_is_dropped_for_later_poll_without_refreshing_accepted_anchor(self):
        await self.ready(self.response(self.capture()))
        first = await self.acquisition.capture_quote()
        await self.accept(first)
        source = self.owner.installed_state.to_dict()['source']
        self.age(1)
        duplicate = self.capture(source_second=first.frame['quote']['estimated_source_second'])
        newer = self.capture(block=101)
        self.feed.responses.extend((self.response(duplicate), self.response(newer)))
        count = self.transport.count('commit_command')
        self.assertIsNone(await self.acquisition.capture_quote())
        self.assertFalse(self.acquisition.has_deferred_capture)
        self.assertEqual(self.owner.installed_state.to_dict()['source'], source)
        self.assertEqual(self.transport.count('commit_command'), count)
        second = await self.acquisition.capture_quote()
        self.assertEqual(second.frame['quote']['block_ref'], 101)
        self.assertEqual(second.frame['sequence'], 2)
        self.assertEqual(len(self.feed.calls), 3)

    async def test_repeated_unchanged_provider_receipts_cannot_extend_source_age(self):
        await self.ready(self.response(self.capture()))
        first = await self.acquisition.capture_quote()
        await self.accept(first)
        original = self.owner.installed_state.to_dict()['source']
        for _ in range(4):
            self.age(7)
            self.feed.responses.append(self.response(self.capture(
                source_second=first.frame['quote']['estimated_source_second'])))
            self.assertIsNone(await self.acquisition.capture_quote())
            self.assertEqual(self.owner.installed_state.to_dict()['source'], original)
            self.assertFalse(self.acquisition.has_deferred_capture)
        self.age(.001)
        self.feed.responses.append(self.response(self.capture(
            source_second=first.frame['quote']['estimated_source_second'])))
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assert_closed()
        self.assertEqual(self.owner.installed_state.to_dict()['source'], original)

    async def test_new_block_in_same_actual_second_retains_its_original_fractional_capture(self):
        await self.ready(self.response(self.capture()))
        first = await self.acquisition.capture_quote()
        await self.accept(first)
        self.age(.25)
        newer = self.capture(block=101, wall=self.wall.value, mono=self.mono.value)
        self.feed.responses.append(self.response(newer))
        self.assertIsNone(await self.acquisition.capture_quote())
        self.assertTrue(self.acquisition.has_deferred_capture)
        self.age(.75)
        second = await self.acquisition.capture_quote()
        self.assertEqual(second.frame['quote']['block_ref'], 101)
        self.assertEqual(second.frame['decision_second'], first.frame['decision_second'] + 1)
        self.assertEqual(second.frame['quote']['document']['response_sha256'],
                         newer.record.document.response_sha256)
        self.assertEqual(len(self.feed.calls), 2)

    async def test_overlap_is_rejected_before_another_feed_call(self):
        gate = self.gate(self.capture())
        await self.ready(gate)
        waiting = self.spawn(self.acquisition.capture_quote())
        await asyncio.wait_for(gate.entered.wait(), 2)
        with self.assertRaises(CommandBusy):
            await self.acquisition.capture_quote()
        self.assertEqual(len(self.feed.calls), 1)
        self.assertFalse(gate.cancelled)
        gate.release.set()
        self.assertIs(type(await waiting), ProviderQuote)

    async def test_cancelled_caller_retains_same_completed_ticket_for_next_caller(self):
        gate = self.gate(self.capture())
        await self.ready(gate)
        waiting = self.spawn(self.acquisition.capture_quote())
        await asyncio.wait_for(gate.entered.wait(), 2)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.assertFalse(gate.cancelled)
        with self.assertRaises(CommandBusy):
            await self.acquisition.capture_quote()
        issued = []
        capture_quote = self.owner.capture_quote
        def track(capture):
            ticket = capture_quote(capture)
            issued.append(ticket)
            return ticket
        with patch.object(self.owner, 'capture_quote', side_effect=track):
            gate.release.set()
            await self.acquisition.settle()
            self.assertEqual(len(issued), 1)
            self.assertTrue(self.acquisition.busy)
            self.assertFalse(self.acquisition.accepting)
            ticket = await self.acquisition.capture_quote()
        self.assertIs(ticket, issued[0])
        self.assertEqual(len(self.feed.calls), 1)
        self.assertFalse(self.acquisition.busy)
        self.assertTrue(self.acquisition.accepting)

    async def test_settle_does_not_consume_the_cancelled_callers_ticket(self):
        gate = self.gate(self.capture())
        await self.ready(gate)
        waiting = self.spawn(self.acquisition.capture_quote())
        await asyncio.wait_for(gate.entered.wait(), 2)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        gate.release.set()
        await self.acquisition.settle()
        await self.acquisition.settle()
        self.assertIs(type(await self.acquisition.capture_quote()), ProviderQuote)
        self.assertEqual(len(self.feed.calls), 1)

    async def test_cancelled_settle_cannot_cancel_the_owned_provider_request(self):
        gate = self.gate(self.capture())
        await self.ready(gate)
        waiting = self.spawn(self.acquisition.capture_quote())
        await asyncio.wait_for(gate.entered.wait(), 2)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        settling = self.spawn(self.acquisition.settle())
        await asyncio.sleep(0)
        settling.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await settling
        self.assertFalse(gate.cancelled)
        gate.release.set()
        await self.acquisition.settle()
        self.assertIs(type(await self.acquisition.capture_quote()), ProviderQuote)

    async def test_source_retrieval_failure_closes_both_admissions_without_commands(self):
        await self.ready(RuntimeError('offline fake retrieval failed'))
        count = self.transport.count('commit_command')
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assert_closed()
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assertEqual(len(self.feed.calls), 1)
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_missing_capture_closes_both_admissions(self):
        await self.ready({})
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assert_closed()
        self.assertEqual(self.acquisition.last_failure['stage'], 'invalid_capture')

    async def test_provider_failure_retains_fixed_code_without_message_or_repeat(self):
        from vonneumann.market.feed import MarketFeedError
        await self.ready(MarketFeedError('price_stale'))
        count = self.transport.count('commit_command')
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        expected = {'stage': 'provider_capture', 'category': 'market_feed_error',
                    'provider_code': 'price_stale'}
        self.assertEqual(self.acquisition.last_failure, expected)
        self.assert_closed()
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(self.acquisition.last_failure, expected)
        self.assertEqual(len(self.feed.calls), 1)
        self.assertEqual(self.transport.count('commit_command'), count)
        self.acquisition.last_failure['provider_code'] = 'changed'
        self.assertEqual(self.acquisition.last_failure, expected)

    async def test_untrusted_error_code_and_text_cannot_enter_failure_labels(self):
        from vonneumann.market.feed import MarketFeedError
        await self.ready(MarketFeedError('https://private.invalid/?key=must-not-leak'))
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(self.acquisition.last_failure, {
            'stage': 'provider_capture', 'category': 'market_feed_error',
            'provider_code': 'unclassified_provider_error'})
        self.assertNotIn('private.invalid', str(self.acquisition.last_failure))

    async def test_owner_quote_validation_retains_its_admission_stage(self):
        await self.ready(self.response(raw_capture(mint='JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN')))
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assertEqual(self.acquisition.last_failure['stage'], 'quote_admission')
        self.assertEqual(self.acquisition.last_failure['category'], 'operational_admission_failed')

    async def test_non_dict_provider_result_is_rejected_without_iterating_it(self):
        consumed = []
        def response_generator():
            consumed.append(True)
            yield ('SOL/USDC', self.capture())
        await self.ready(response_generator())
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(consumed, [])
        self.assert_closed()

    async def test_unrequested_capture_cannot_expand_the_single_asset_acquisition(self):
        capture = self.capture()
        await self.ready({'SOL/USDC': capture, 'OTHER/USDC': capture})
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assert_closed()

    async def test_non_capture_value_closes_both_admissions(self):
        await self.ready({'SOL/USDC': {'price': '100'}})
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assert_closed()

    async def test_mismatched_mint_capture_closes_both_admissions(self):
        await self.ready(self.response(raw_capture(mint='JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN')))
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assert_closed()

    async def test_stale_response_after_slow_fetch_closes_without_issuing_a_ticket(self):
        capture = self.capture()
        async def slow_fetch():
            self.age(5)
            return self.response(capture)
        await self.ready(slow_fetch)
        previous = self.owner.installed_state
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assert_closed()
        self.assertIs(self.owner.installed_state, previous)

    async def test_clock_rollback_during_fetch_closes_before_ticket_issuance(self):
        capture = self.capture()
        async def clock_regression():
            self.wall.value -= 1
            return self.response(capture)
        await self.ready(clock_regression)
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assert_closed()

    async def test_expired_retained_fractional_capture_is_not_refetched_or_reanchored(self):
        await self.ready()
        self.age(.25)
        capture = self.capture(wall=self.wall.value, mono=self.mono.value)
        self.feed.responses.append(self.response(capture))
        self.assertIsNone(await self.acquisition.capture_quote())
        self.age(5)
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        self.assert_closed()
        self.assertEqual(len(self.feed.calls), 1)

    async def test_close_prevents_new_fetch_and_is_permanent(self):
        await self.ready(self.response(self.capture()))
        self.acquisition.close_admission()
        self.assertFalse(self.acquisition.accepting)
        self.assertTrue(self.owner.accepting)
        with self.assertRaises((CommandAdmissionError, ProviderSourceError)):
            await self.acquisition.capture_quote()
        await self.acquisition.settle()
        self.assertEqual(self.feed.calls, [])
        self.assertFalse(self.acquisition.accepting)
        self.assertTrue(self.owner.accepting)

    async def test_close_during_cancelled_fetch_preserves_original_result_for_explicit_retrieval(self):
        gate = self.gate(self.capture())
        await self.ready(gate)
        waiting = self.spawn(self.acquisition.capture_quote())
        await asyncio.wait_for(gate.entered.wait(), 2)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        self.acquisition.close_admission()
        self.assertFalse(self.acquisition.accepting)
        self.assertTrue(self.owner.accepting)
        gate.release.set()
        retained = await self.acquisition.settle()
        self.assertIs(type(retained), ProviderQuote)
        self.assertIs(await self.acquisition.capture_quote(), retained)
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(len(self.feed.calls), 1)
        self.assertFalse(gate.cancelled)

    async def test_timeout_bounds_the_whole_owned_fetch_and_permanently_closes_admission(self):
        gate = self.gate(self.capture())
        await self.ready(gate)
        count = self.transport.count('commit_command')
        with patch.object(module, 'ACQUISITION_TIMEOUT_SECONDS', .01):
            with self.assertRaises(CommandAdmissionError):
                await self.acquisition.capture_quote()
        self.assertTrue(gate.entered.is_set())
        self.assertTrue(gate.cancelled)
        self.assert_closed()
        self.assertFalse(self.acquisition.busy)
        self.assertEqual(self.transport.count('commit_command'), count)
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(len(self.feed.calls), 1)

    async def test_feed_suppressing_timeout_cancellation_cannot_return_a_fresh_ticket(self):
        await self.ready()
        cancelled = []
        async def cancellation_suppressing_feed():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(True)
                # Receipt and source age remain valid under the owner's clocks.
                # Provider freshness must not override the acquisition deadline.
                return self.response(self.capture())
        self.feed.responses.append(cancellation_suppressing_feed)
        previous = self.owner.installed_state
        count = self.transport.count('commit_command')
        with patch.object(module, 'ACQUISITION_TIMEOUT_SECONDS', .01), \
                patch.object(self.owner, 'capture_quote', wraps=self.owner.capture_quote) as issue:
            with self.assertRaises(CommandAdmissionError):
                await self.acquisition.capture_quote()
        self.assertEqual(cancelled, [True])
        self.assertEqual(issue.call_count, 0)
        self.assert_closed()
        self.assertFalse(self.acquisition.busy)
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.transport.count('commit_command'), count)
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(len(self.feed.calls), 1)

    async def test_synchronous_quote_parsing_overrun_is_rejected_before_returning_the_ticket(self):
        await self.ready(self.response(self.capture()))
        original = self.owner.capture_quote
        issued = []
        def slow_quote(capture):
            ticket = original(capture)
            issued.append(ticket)
            # A timeout callback cannot run while synchronous provider parsing
            # occupies the loop, so the explicit deadline check is essential.
            time.sleep(.025)
            return ticket
        previous = self.owner.installed_state
        count = self.transport.count('commit_command')
        with patch.object(module, 'ACQUISITION_TIMEOUT_SECONDS', .01), \
                patch.object(self.owner, 'capture_quote', side_effect=slow_quote):
            with self.assertRaises(CommandAdmissionError):
                await self.acquisition.capture_quote()
        self.assertEqual(len(issued), 1)
        self.assert_closed()
        self.assertFalse(self.acquisition.busy)
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.transport.count('commit_command'), count)

    async def test_synchronous_deferral_overrun_is_failure_rather_than_a_normal_retry(self):
        await self.ready()
        self.age(.25)
        self.feed.responses.append(self.response(self.capture(
            wall=self.wall.value, mono=self.mono.value)))
        original = self.owner.capture_quote
        def slow_deferral(capture):
            try:
                return original(capture)
            finally:
                time.sleep(.025)
        count = self.transport.count('commit_command')
        with patch.object(module, 'ACQUISITION_TIMEOUT_SECONDS', .01), \
                patch.object(self.owner, 'capture_quote', side_effect=slow_deferral):
            with self.assertRaises(CommandAdmissionError):
                await self.acquisition.capture_quote()
        self.assert_closed()
        self.assertFalse(self.acquisition.busy)
        self.assertEqual(self.transport.count('commit_command'), count)
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(len(self.feed.calls), 1)

    async def test_cancelled_waiters_failed_result_is_retained_without_a_replacement_fetch(self):
        gate = self.gate({'not': 'a capture'})
        # Gate already holds a normal response wrapper; replacing its value
        # makes the retained provider operation independently malformed.
        gate.result = {'SOL/USDC': None}
        await self.ready(gate)
        waiting = self.spawn(self.acquisition.capture_quote())
        await asyncio.wait_for(gate.entered.wait(), 2)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        gate.release.set()
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.settle()
        self.assertTrue(self.acquisition.busy)
        self.assert_closed()
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertFalse(self.acquisition.busy)
        self.assertEqual(len(self.feed.calls), 1)

    async def test_closed_owner_is_rejected_before_a_provider_fetch(self):
        await self.ready(self.response(self.capture()))
        self.owner.close_admission()
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(self.feed.calls, [])
        self.assertFalse(self.acquisition.accepting)

    async def test_busy_owner_is_rejected_before_a_provider_fetch(self):
        await self.ready(self.response(self.capture()))
        ticket = self.owner.capture_quote(self.capture())
        entered, release = asyncio.Event(), asyncio.Event()
        async def delay_reply(response, _arguments):
            entered.set()
            await release.wait()
            return response
        self.transport.fault('commit_command', delay_reply)
        waiting = self.spawn(self.owner.protect(ticket, **self.allocation()))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            with self.assertRaises(CommandBusy):
                await self.acquisition.capture_quote()
            self.assertEqual(self.feed.calls, [])
        finally:
            release.set()
        await waiting
        await self.owner.publish_pending(self.sink)

    async def test_constructor_rejects_a_legacy_owner_and_a_feed_without_exact_captures(self):
        await self.ready()
        with self.assertRaises(CommandAdmissionError):
            module.ProviderPriceAcquisition(self.feed, object())
        with self.assertRaises(CommandAdmissionError):
            module.ProviderPriceAcquisition(object(), self.owner)
        self.assertTrue(self.owner.accepting)
        self.assertEqual(self.feed.calls, [])

    async def test_second_event_loop_is_rejected_without_network_or_owner_changes(self):
        await self.ready(self.response(self.capture()))
        await self.acquisition.capture_quote()
        previous = self.owner.installed_state
        def other_loop():
            return asyncio.run(self.acquisition.capture_quote())
        with self.assertRaises(CommandAdmissionError):
            await asyncio.to_thread(other_loop)
        self.assertEqual(len(self.feed.calls), 1)
        self.assertIs(self.owner.installed_state, previous)
        self.assertTrue(self.acquisition.accepting)

    async def test_scheduling_failure_closes_owner_before_fetch_and_leaves_no_owned_coroutine(self):
        await self.ready(self.response(self.capture()))
        with patch.object(module.asyncio, 'create_task', side_effect=RuntimeError('fake scheduler failure')):
            with self.assertRaises(CommandAdmissionError):
                await self.acquisition.capture_quote()
        self.assert_closed()
        self.assertFalse(self.acquisition.busy)
        self.assertEqual(self.feed.calls, [])

    async def test_owned_task_cancelled_before_first_instruction_closes_both_admissions(self):
        await self.ready(self.response(self.capture()))
        previous = self.owner.installed_state
        count = self.transport.count('commit_command')
        cancelled = []
        def cancelling_factory(coroutine):
            task = asyncio.Task(coroutine)
            task.cancel()
            cancelled.append(task)
            return task
        with patch.object(module.asyncio, 'create_task', side_effect=cancelling_factory):
            with self.assertRaises(CommandAdmissionError):
                await self.acquisition.capture_quote()
        self.assertEqual(len(cancelled), 1)
        self.assertTrue(cancelled[0].cancelled())
        self.assert_closed()
        self.assertFalse(self.acquisition.busy)
        self.assertEqual(self.feed.calls, [])
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.transport.count('commit_command'), count)
        await self.acquisition.settle()
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(self.feed.calls, [])

    async def test_cancelled_before_start_task_is_closed_and_retained_through_settlement(self):
        await self.ready(self.response(self.capture()))
        previous = self.owner.installed_state
        count = self.transport.count('commit_command')
        cancelled = []
        def cancelling_factory(coroutine):
            task = asyncio.Task(coroutine)
            task.cancel()
            cancelled.append(task)
            return task
        # Force caller cancellation at the shielding boundary before the owned
        # task has received its first instruction. Its independent cancellation
        # must still latch admission after the caller has already disappeared.
        with patch.object(module.asyncio, 'create_task', side_effect=cancelling_factory), \
                patch.object(module.asyncio, 'shield', side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await self.acquisition.capture_quote()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertTrue(cancelled[0].cancelled())
        self.assertTrue(self.acquisition.busy)
        self.assert_closed()
        for _ in range(2):
            with self.assertRaises(CommandAdmissionError):
                await self.acquisition.settle()
            self.assertTrue(self.acquisition.busy)
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertFalse(self.acquisition.busy)
        self.assert_closed()
        self.assertEqual(self.feed.calls, [])
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.transport.count('commit_command'), count)
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(self.feed.calls, [])

    async def test_owned_task_interrupted_during_fetch_closes_without_an_economic_command(self):
        gate = self.gate(self.capture())
        await self.ready(gate)
        previous = self.owner.installed_state
        count = self.transport.count('commit_command')
        waiting = self.spawn(self.acquisition.capture_quote())
        await asyncio.wait_for(gate.entered.wait(), 2)
        # This is cancellation of the owned task, rather than its caller. It
        # models shutdown/interruption and must never be treated as a retry.
        self.acquisition._task.cancel()
        with self.assertRaises(CommandAdmissionError):
            await waiting
        self.assertTrue(gate.cancelled)
        self.assert_closed()
        self.assertFalse(self.acquisition.busy)
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.transport.count('commit_command'), count)
        with self.assertRaises(CommandAdmissionError):
            await self.acquisition.capture_quote()
        self.assertEqual(len(self.feed.calls), 1)
