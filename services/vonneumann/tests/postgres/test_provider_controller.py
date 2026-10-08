"""Whole provider paper operations through real, isolated PostgreSQL commands.

Raw Jupiter, Solana RPC and Birdeye replies are fabricated locally and parsed by
the actual adapters. Process/server clocks are real; no configured database,
provider credential, network endpoint or application environment file is read.
This verifies the executable controller against the existing laboratory SQL,
not Supabase/PostgREST authentication or production migration readiness.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from decimal import Decimal
import json
import time
import unittest

from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import FixtureRpcTransport, identity, literal
from tests.security_support import deny_network
from tests.test_birdeye_candles import body, row
from tests.test_feed_reliability import Response
from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig
from vonneumann.core.provider_controller import CommandAllocation, ProviderPilotController
from vonneumann.core.provider_runner import ProviderPilotRunner
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandBusy, CommandRepository, UncertainCommand
from vonneumann.db.provider_pilot_owner import ProviderPilotOwner
from vonneumann.db.transition_coordinator import PublicationError
from vonneumann.market import provider_contract as source
with deny_network():
    from vonneumann.market.jupiter_feed import JupiterFeed
    from vonneumann.market.solana_time import MAINNET_GENESIS_HASH


class LiteralProviderSession:
    """Fake HTTP transport only; production adapter parsing is not replaced."""

    def __init__(self, *, candles=False):
        self.candles = candles
        self.closed = False
        self.calls = []
        self.raw_documents = []
        self._block = 345_678_900

    def get(self, url, **options):
        # Retain approved request metadata only, never the dummy auth header.
        self.calls.append(('GET', url, deepcopy(options['params'])))
        if self.candles:
            if url != 'https://public-api.birdeye.so/defi/v3/ohlcv':
                raise AssertionError('Unexpected literal candle endpoint')
            params = options['params']
            raw = json.dumps(body(*(row(stamp, o=100, h=102, l=99, c=100)
                for stamp in range(params['time_from'], params['time_to'], 60))),
                separators=(',', ':')).encode()
        else:
            if url != 'https://api.jup.ag/price/v3':
                raise AssertionError('Unexpected literal price endpoint')
            self._block += 1
            raw = ('{"'+source.MINT+'":{"usdPrice":100.000000000000000001,'
                   '"blockId":'+str(self._block)+',"decimals":9}}').encode()
        self.raw_documents.append(raw)
        return Response(raw)

    def post(self, url, **options):
        if url != 'https://controller-fixture.invalid/rpc':
            raise AssertionError('Unexpected literal RPC endpoint')
        request = options['json']
        self.calls.append(('POST', url, deepcopy(request)))
        if request['method'] == 'getGenesisHash':
            result = MAINNET_GENESIS_HASH
        elif request['method'] == 'getBlockTime':
            result = int(time.time()) - 1
        else:
            raise AssertionError('Unexpected literal source-time method')
        # Preserve the literal response wire for the bounded RPC stream parser.
        raw = json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result},
                         separators=(',', ':')).encode()
        self.raw_documents.append(raw)
        return Response(json.loads(raw))

    async def close(self):
        self.closed = True


class HeldCommitReplyTransport(FixtureRpcTransport):
    """Hold one acknowledged transaction's reply, leaving no DB lock held."""

    def __init__(self, database):
        super().__init__(database)
        self.hold_next_commit = False
        self.committed = asyncio.Event()
        self.release = asyncio.Event()

    async def rpc(self, name, args):
        result = await super().rpc(name, args)
        if name == 'commit_command' and self.hold_next_commit:
            self.hold_next_commit = False
            self.committed.set()
            await self.release.wait()
        return result


class ProviderControllerSqlTests(PostgresContractTestCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        guard = deny_network()
        guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)
        self.owner_id, self.run_id, self.worker_id = identity(), identity(), identity()
        self.stop_id = identity()
        self.db.sql('INSERT INTO auth.users(id) VALUES ('+literal(self.owner_id)+');')
        self.config = ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',
            self.owner_id, self.run_id, asset='SOL/USD'), identity())
        self.transport = HeldCommitReplyTransport(self.db)
        self.repository = CommandRepository(self.transport, self.owner_id,
                                            self.run_id, self.worker_id)
        self.feed = JupiterFeed(api_key='controller-fixture-key',
            rpc_url='https://controller-fixture.invalid/rpc',
            birdeye_api_key='controller-fixture-key')
        self.price_session = LiteralProviderSession()
        self.candle_session = LiteralProviderSession(candles=True)
        self.feed._session = self.price_session
        self.feed._candles._session = self.candle_session
        self.events, self.allocations, self.tasks = [], [], []
        self.owner = self.controller = None

    async def asyncTearDown(self):
        self.transport.release.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks, return_exceptions=True), 5)
        if self.controller is not None:
            self.controller.close_admission()
            try:
                await asyncio.wait_for(self.controller.settle(), 5)
            except (UncertainCommand, PublicationError):
                # Tests assert the retained stage before cleanup. A fixture
                # failure must not accidentally dispatch a replacement command.
                pass
        await self.feed.close()

    def allocate(self, kind, generation):
        value = CommandAllocation(identity(), tuple(identity() for _ in range(9)),
            tuple((generation, f'SqlController-{generation}-{index}') for index in range(8)))
        self.allocations.append((kind, generation, value))
        return value

    async def publish(self, event):
        # Every publication must see its already installed authoritative state.
        self.assertIsNotNone(self.owner.installed_state)
        self.assertLessEqual(event['revision'], self.owner.installed_state.to_dict()['revision'])
        self.events.append(deepcopy(event))

    async def ready(self, *, heartbeat=True):
        await self.repository.submit(PreparedCommand.create(self.owner_id, self.run_id,
            self.worker_id, self.config.run_configuration(), self.config.initial_cash,
            command_id=identity(), lease_seconds=120))
        self.owner = ProviderPilotOwner(self.repository, self.transport, self.config,
                                       stop_command_id=self.stop_id)
        self.controller = ProviderPilotController(self.owner, self.feed, self.publish,
                                                 self.allocate, lease_seconds=120)
        if heartbeat:
            await self.controller.heartbeat()

    async def first_complete_tick(self):
        # Literal receipt fractions must wait for an actual next whole second;
        # no timestamp is rewritten or test clock advanced to bypass admission.
        end = time.monotonic() + 8
        while time.monotonic() < end:
            report = await self.controller.tick()
            if report.status == 'complete':
                return report
            self.assertEqual(report.status, 'deferred')
            await asyncio.sleep(.05)
        self.fail('Literal current-clock quote never completed its original tick')

    def commit_calls(self):
        return [deepcopy(args) for name, args in self.transport.calls if name == 'commit_command']

    def provider_calls(self):
        return deepcopy((self.price_session.calls, self.candle_session.calls))

    def sql_state(self):
        value = self.db.scalar('SELECT engine_state FROM vn_durability.runs WHERE id='
                               +literal(self.run_id)+';')
        return json.loads(value)

    def assert_projection(self):
        state = self.owner.installed_state.to_dict()
        self.assertEqual(self.sql_state(), state)
        self.assertEqual(Decimal(self.db.scalar('SELECT reserve::text FROM vn_durability.runs WHERE id='
                                       +literal(self.run_id)+';')), Decimal(state['reserve']))
        self.assertEqual(self.db.scalar('SELECT command_version FROM vn_durability.runs WHERE id='
                                       +literal(self.run_id)+';'), '5')
        self.assertEqual(len(self.events), len({event['event_id'] for event in self.events}))
        return state

    async def assert_no_pending_outbox(self):
        page = await self.transport.rpc('read_outbox', {'owner_id': self.owner_id,
            'run': self.run_id, 'through_revision': self.owner.installed_state.to_dict()['revision'],
            'max_events': 50, 'max_bytes': 65536})
        self.assertEqual(page['events'], [])
        self.assertFalse(page['has_more'])

    async def test_literal_bootstrap_first_tick_pause_and_reserved_stop_match_sql(self):
        await self.ready()
        boot = await self.controller.bootstrap()
        self.assertEqual((boot.status, boot.revision, boot.quote_sequence), ('complete', 2, 0))
        self.assertEqual(len(self.candle_session.calls), 1)
        self.assertEqual(len(self.sql_state()['source']['bars']), 61)
        report = await self.first_complete_tick()
        self.assertEqual(report.quote_sequence, 1)
        self.assertGreaterEqual(report.elapsed_seconds, 0)
        self.assertTrue(report.phase_seconds)
        before = self.assert_projection()
        self.assertEqual(before['source']['last_quote']['quote']['price'], '100.000000000000000001')
        calls = self.provider_calls()
        paused = await self.controller.control('pause')
        self.assertEqual(paused.status, 'complete')
        pause_state = self.assert_projection()
        self.assertEqual(pause_state['status'], 'paused')
        stopped = await self.controller.stop()
        self.assertEqual(stopped.status, 'complete')
        after = self.assert_projection()
        self.assertEqual(after['status'], 'stopped')
        for field in ('positions', 'accounts', 'reserve'):
            self.assertEqual(after[field], before[field])
        self.assertEqual(self.provider_calls(), calls, 'controls must not acquire providers')
        self.assertEqual(self.commit_calls()[-1]['command_id'], self.stop_id)
        await self.assert_no_pending_outbox()

    async def test_lost_bootstrap_reply_installs_original_without_refetch_or_duplicate(self):
        await self.ready()
        self.transport.drop_reply_once = 'commit_command'
        with self.assertRaises(UncertainCommand):
            await self.controller.bootstrap()
        self.assertIsNone(self.owner.installed_state)
        self.assertIsNotNone(self.sql_state())
        commits, calls = self.commit_calls(), self.provider_calls()
        original = self.owner.pending_command
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(self.commit_calls(), commits)
        self.assertEqual(self.provider_calls(), calls)
        self.assertEqual(self.repository.last_receipt.command.command_id, original.command_id)
        self.assert_projection()
        await self.assert_no_pending_outbox()

    async def test_lost_protection_reply_resolves_then_decides_same_original_quote(self):
        await self.ready()
        await self.controller.bootstrap()
        previous = self.owner.installed_state
        prior_calls = len(self.commit_calls())
        self.transport.drop_reply_once = 'commit_command'
        with self.assertRaises(UncertainCommand):
            await self.first_complete_tick()
        self.assertIs(self.owner.installed_state, previous)
        self.assertEqual(self.sql_state()['source']['quote_sequence'], 1)
        submitted, providers = self.commit_calls(), self.provider_calls()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(report.quote_sequence, 1)
        self.assertEqual(self.provider_calls(), providers)
        # A recovered protection may admit the still-fresh first decision, but
        # can never resubmit or refetch the protection already in the journal.
        commits = self.commit_calls()
        self.assertEqual(commits[:len(submitted)], submitted)
        self.assertEqual(len(commits), prior_calls + 1 + int(report.decision_committed))
        self.assertEqual(len({args['command_id'] for args in commits}), len(commits))
        rpc_names = [name for name, _ in self.transport.calls]
        readback = rpc_names.index('get_command')
        if report.decision_committed:
            self.assertIn('heartbeat', rpc_names[readback + 1:])
            heartbeat = rpc_names.index('heartbeat', readback + 1)
            self.assertLess(heartbeat, rpc_names.index('commit_command', readback + 1))
        self.assert_projection()
        await self.assert_no_pending_outbox()

    async def test_lost_delivery_ack_resumes_stable_event_without_second_commit(self):
        await self.ready()
        self.transport.drop_reply_once = 'acknowledge_event'
        with self.assertRaises(PublicationError):
            await self.controller.bootstrap()
        self.assertIsNotNone(self.owner.installed_state)
        self.assertEqual(len(self.events), 1)
        first = deepcopy(self.events[0])
        commits, providers = self.commit_calls(), self.provider_calls()
        report = await self.controller.settle()
        self.assertEqual(report.status, 'complete')
        self.assertEqual(self.commit_calls(), commits)
        self.assertEqual(self.provider_calls(), providers)
        self.assertEqual(self.events[0], first)
        self.assertEqual(len(self.events), 9)
        self.assert_projection()
        await self.assert_no_pending_outbox()

    async def test_cancelled_tick_caller_retains_entire_committed_operation_until_settlement(self):
        await self.ready()
        await self.controller.bootstrap()
        prior_calls = len(self.commit_calls())
        self.transport.hold_next_commit = True
        # A first fractional quote may normally defer before it owns a commit.
        end = time.monotonic() + 8
        while time.monotonic() < end:
            caller = asyncio.create_task(self.controller.tick())
            self.tasks.append(caller)
            barrier = asyncio.create_task(self.transport.committed.wait())
            try:
                done, _ = await asyncio.wait((caller, barrier), timeout=2,
                                             return_when=asyncio.FIRST_COMPLETED)
            finally:
                if not barrier.done():
                    barrier.cancel()
                await asyncio.gather(barrier, return_exceptions=True)
            if self.transport.committed.is_set():
                break
            self.assertIn(caller, done)
            self.assertEqual(caller.result().status, 'deferred')
            await asyncio.sleep(.05)
        else:
            self.fail('Literal quote never reached the held real SQL commit')
        self.assertEqual(self.sql_state()['source']['quote_sequence'], 1)
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await caller
        with self.assertRaises(CommandBusy):
            await self.controller.tick()
        # A stop request intentionally latches drain even when its terminal
        # command cannot start yet. Finish publication of the admitted
        # protection, then omit the unsubmitted decision until explicit stop.
        with self.assertRaises(CommandBusy):
            await self.controller.stop()
        providers = self.provider_calls()
        self.transport.release.set()
        report = await asyncio.wait_for(self.controller.settle(), 5)
        self.assertEqual(report.status, 'drained')
        self.assertEqual(report.quote_sequence, 1)
        self.assertFalse(report.decision_committed)
        self.assertEqual(self.provider_calls(), providers)
        commits = self.commit_calls()
        self.assertEqual(len(commits), prior_calls + 1)
        self.assertEqual(len({args['command_id'] for args in commits}), len(commits))
        self.assert_projection()
        await self.assert_no_pending_outbox()
        stopped = await self.controller.stop()
        self.assertEqual(stopped.status, 'complete')
        self.assertEqual(self.commit_calls()[-1]['command_id'], self.stop_id)
        self.assertEqual(self.assert_projection()['status'], 'stopped')
        await self.assert_no_pending_outbox()

    async def test_finite_literal_runner_completes_without_auto_stop_then_explicitly_stops(self):
        # The runner owns a controller with no previous operations/reports.
        # Its bootstrap renews the creation lease before provider acquisition.
        await self.ready(heartbeat=False)
        runner = ProviderPilotRunner(self.controller, interval_seconds=.1, max_ticks=20)
        actual_rpc = self.transport.rpc
        active_rpc = peak_rpc = 0

        async def tracked_rpc(name, args):
            nonlocal active_rpc, peak_rpc
            active_rpc += 1
            peak_rpc = max(peak_rpc, active_rpc)
            try:
                return await actual_rpc(name, args)
            finally:
                active_rpc -= 1

        self.transport.rpc = tracked_rpc
        # Twenty paced attempts span actual seconds even when their original
        # fractional receipts defer. No test clock or provider timestamp moves.
        report = await asyncio.wait_for(runner.run(), 12)
        self.assertEqual((report.status, report.ticks_completed, report.stop_requested),
                         ('complete', 20, False))
        self.assertEqual(len(report.reports), 21)
        self.assertEqual(report.reports[0].kind, 'bootstrap')
        state = self.assert_projection()
        self.assertEqual(state['status'], 'running')
        self.assertGreaterEqual(state['source']['quote_sequence'], 1)
        self.assertEqual(peak_rpc, 1, 'paced runner overlapped SQL transport operations')
        self.assertEqual(active_rpc, 0)
        commands = self.commit_calls()
        self.assertEqual(len(commands), len({args['command_id'] for args in commands}))
        self.assertNotIn(self.stop_id, {args['command_id'] for args in commands},
                         'natural finite completion must not spend the reserved stop')
        completed = [item for item in report.reports if item.kind == 'tick' and item.status == 'complete']
        self.assertEqual([item.quote_sequence for item in completed],
                         list(range(1, state['source']['quote_sequence'] + 1)))
        await self.assert_no_pending_outbox()
        before = {field: deepcopy(state[field]) for field in ('positions', 'accounts', 'reserve')}
        runner.request_stop()
        stopped = await asyncio.wait_for(runner.settle(), 5)
        self.assertEqual((stopped.status, stopped.ticks_completed, stopped.stop_requested),
                         ('stopped', 20, True))
        self.assertEqual(len(stopped.reports), 22)
        self.assertEqual(self.commit_calls()[-1]['command_id'], self.stop_id)
        after = self.assert_projection()
        self.assertEqual(after['status'], 'stopped')
        for field, value in before.items():
            self.assertEqual(after[field], value)
        self.assertEqual(peak_rpc, 1)
        self.assertEqual(active_rpc, 0)
        await self.assert_no_pending_outbox()
