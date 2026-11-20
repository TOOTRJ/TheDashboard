"""Owned production paper orchestration for the maintained two-EMA model.

One durable control stream governs collection; one CAS journal governs simulated
economics.  Stop during warmup is still durable.  Replay, provider collection and
database replies are owned by background work, never by an HTTP request task.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from uuid import uuid4

from ..core.decimal_execution import CASH_SCALE, EntryPlan, _units, _text, mark_value
from ..core.prospective_artifacts import SourceRecipeStore
from ..core.prospective_runtime import ProspectiveRuntime, RuntimePending, RuntimeRefused, JournalRejected
from ..market import provider_acquisition_v3 as acquisition
from ..market import prospective_source_v3 as source
from ..research.prospective_ga_v3_policy import V3Config, V3Inputs, SourceBinding


@dataclass(frozen=True, slots=True)
class SourceBatch:
    mark: source.SourceMark | None
    history: source.SampledHistory | None = None
    series: source.SampledCloseSeries | None = None
    safe_error: str | None = None

    def __post_init__(self):
        if self.mark is None:
            if self.history is not None or self.series is not None or self.safe_error != 'provider_sample_unavailable':
                raise RuntimeRefused('invalid_source_batch')
            return
        if (type(self.mark) is not source.SourceMark or self.safe_error is not None or
            (self.history is None) != (self.series is None) or
            (self.history is not None and (type(self.history) is not source.SampledHistory
                or type(self.series) is not source.SampledCloseSeries))):
            raise RuntimeRefused('invalid_source_batch')


class ProspectivePaperService:
    def __init__(self, journal, feed, config: V3Config, *, interval=30,
                 clock=None, sleep=asyncio.sleep, artifacts=None):
        if type(config) is not V3Config or type(interval) not in (int, float) or not 5 <= interval <= 60:
            raise RuntimeRefused('invalid_prospective_configuration')
        config.__post_init__()
        self.owner_id, self.run_id = config.owner_id, config.run_id
        self._journal, self._feed, self._config = journal, feed, config
        self._interval, self._sleep = interval, sleep
        self._clock = self._real_clock if clock is None else clock
        self.artifacts = artifacts or SourceRecipeStore(journal, self.owner_id, self.run_id)
        self.runtime = ProspectiveRuntime(self.owner_id, self.run_id, journal, self.artifacts.reader)
        self._phase, self._last_failure = 'idle', None
        self._initialized, self._closing, self._stop_requested = False, False, False
        self._stop_latch = 0
        self._initialize_lock, self._control_lock = asyncio.Lock(), asyncio.Lock()
        self._task = None
        self._recovery_task = None
        self._last_control = None

    def _authorize(self, owner):
        if owner != self.owner_id:
            raise RuntimeRefused('run_unavailable')

    def _real_clock(self, binding):
        # A single process clock read supplies a narrow bound.  This is original
        # local clock evidence; it does not claim a trusted remote time oracle.
        lower = time.time_ns() // 1000
        monotonic = time.monotonic_ns() // 1000
        upper = time.time_ns() // 1000
        return acquisition.ClockBound(self.owner_id, self.run_id, binding.market_epoch,
            binding.acquisition_epoch, lower, max(lower, upper), monotonic)

    def _inputs(self, *, binding=None):
        if binding is None:
            binding = self._feed.current_binding
        clock = self._clock(binding)
        generation = 0 if self.runtime.state is None else self.runtime.state.to_dict()['engine']['generation']+1
        return V3Inputs(clock, clock.wall_upper_us,
            tuple(str(uuid4()) for _ in range(32)),
            tuple((generation, f'Paper-{generation}-{index+1}') for index in range(16)))

    async def _refresh_artifacts(self):
        await self.artifacts.restore()

    def _control(self, value):
        if value is not None:
            if ((value.get('owner_id'), value.get('run_id')) != (self.owner_id, self.run_id)
                or value.get('action') not in ('start', 'stop')):
                raise RuntimeRefused('invalid_durable_control')
            acquisition.uuid(value['request_id'])
        return value

    async def initialize(self):
        if self._recovery_task is None:
            self._phase = 'recovering'
            async def recover():
                try:
                    await self._recover()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._phase, self._last_failure = 'failed', 'paper_recovery_failed'
            self._recovery_task = asyncio.create_task(recover())
            self._recovery_task.add_done_callback(lambda task: None if task.cancelled() else task.exception())

    async def wait_ready(self):
        """Explicit test/operator wait; HTTP health and status never await replay."""
        await self.initialize()
        await asyncio.shield(self._recovery_task)
        if not self._initialized:
            raise RuntimeRefused('paper_recovery_unavailable')

    async def _recover(self):
        async with self._initialize_lock:
            if self._initialized:
                return
            self._phase = 'recovering'
            await self._refresh_artifacts()
            if hasattr(self._feed, 'restore'):
                await self._feed.restore()
            after = 0
            self.runtime.begin_restore()
            while True:
                rows = await self._journal.scan(after_sequence=after, limit=100)
                self.runtime.restore_page(rows)
                after += len(rows)
                if self._closing:
                    return
                if not rows:
                    break
            self.runtime.finish_restore()
            if hasattr(self._feed, 'set_consumed_history_sha256'):
                self._feed.set_consumed_history_sha256(None if self.runtime.state is None else
                    self.runtime.state.to_dict()['source']['history_sha256'])
            self._last_control = self._control(await self._journal.latest_control())
            self._initialized = True
            terminal = self.runtime.state is not None and self.runtime.state.to_dict()['status'] == 'stopped'
            self._phase = 'stopped' if terminal else 'idle'
            if self._last_control is not None:
                if self._last_control['action'] == 'start' and not terminal:
                    self._phase = 'warming_up' if self.runtime.state is None else 'running'
                    self._launch(self._run)
                elif self._last_control['action'] == 'stop':
                    self._stop_requested = True
                    self._phase = 'stopping'
                    self._launch(self._stop_model)

    def _launch(self, operation):
        if self._task is not None and not self._task.done():
            return
        async def owned():
            try:
                await operation()
            except JournalRejected:
                # Native storage retained an immutable rejection for the exact
                # prepared candidate because durable Stop won the run lock.
                # The candidate did not advance economics; complete that Stop.
                self._stop_requested = True
                try:
                    self._last_control = self._control(await self._journal.latest_control())
                    if self._last_control is None or self._last_control['action'] != 'stop':
                        raise RuntimeRefused('stop_rejection_control_mismatch')
                    await self._refresh_native_prefix()
                    await self._stop_model()
                except RuntimePending:
                    self._phase, self._last_failure = 'pending', 'original_transition_unresolved'
                except Exception:
                    self._phase, self._last_failure = 'failed', 'paper_stop_reconciliation_failed'
            except RuntimePending:
                self._phase = 'pending'
                self._last_failure = 'original_transition_unresolved'
            except asyncio.CancelledError:
                self._phase = 'pending' if self.runtime.pending else 'idle'
                raise
            except Exception:
                # Provider/SQL exception messages may contain private URLs.
                self._phase, self._last_failure = 'failed', 'paper_operation_failed'
        self._task = asyncio.create_task(owned())
        self._task.add_done_callback(lambda task: None if task.cancelled() else task.exception())

    async def _commit(self, candidate):
        state = await self.runtime.submit(candidate, command_id=str(uuid4()))
        return state

    async def _refresh_native_prefix(self):
        """A winning remote Stop may already include its economic Stop command.

        Independently replay that complete native prefix into a fresh owned
        runtime before choosing another control. Never import the remote JSON
        mirror or append a stale Stop against the old local head.
        """
        if not hasattr(self._journal, 'head'):
            return
        head = await self._journal.head()
        if head.get('sequence') == self.runtime.sequence:
            if head.get('sha256') != self.runtime.head_sha256:
                raise RuntimeRefused('native_head_digest_mismatch')
            return
        if type(head.get('sequence')) is not int or head['sequence'] < self.runtime.sequence:
            raise RuntimeRefused('native_head_regressed')
        self._phase, self._initialized = 'recovering', False
        await self._refresh_artifacts()
        following = ProspectiveRuntime(self.owner_id, self.run_id, self._journal, self.artifacts.reader)
        following.begin_restore()
        while True:
            rows = await self._journal.scan(after_sequence=following.sequence, limit=25)
            following.restore_page(rows)
            if rows:
                continue
            head = await self._journal.head()
            if head.get('sequence') == following.sequence and head.get('sha256') == following.head_sha256:
                break
            if type(head.get('sequence')) is not int or head['sequence'] <= following.sequence:
                raise RuntimeRefused('native_head_digest_mismatch')
        following.finish_restore()
        self.runtime = following
        if hasattr(self._feed, 'set_consumed_history_sha256'):
            self._feed.set_consumed_history_sha256(None if following.state is None else
                following.state.to_dict()['source']['history_sha256'])
        self._initialized = True

    async def _align_epoch(self):
        if self.runtime.state is None:
            return
        state = self.runtime.state.to_dict()
        binding = self._feed.current_binding
        current = SourceBinding(**state['source']['current_binding'])
        if binding != current:
            await self._commit(self.runtime.prepare_epoch_rollover(binding,
                self._inputs(binding=binding)))
        status = self.runtime.state.to_dict()['status']
        if status == 'paused':
            await self._commit(self.runtime.prepare_control('resume', self._inputs()))

    async def _run(self):
        if self._closing:
            return
        await self._align_epoch()
        self._phase = 'warming_up' if self.runtime.state is None else 'running'
        while not self._closing and not self._stop_requested:
            # Warmup has no economic append to reveal a winning remote Stop.
            # Read its original durable control before any history/provider I/O;
            # provider admission separately checks Stop races during collection.
            control = self._control(await self._journal.latest_control())
            if control is None:
                raise RuntimeRefused('paper_control_unavailable')
            if self._closing or self._stop_requested:
                break
            self._last_control = control
            if control['action'] == 'stop':
                self._stop_requested = True
                break
            batch = await self._feed.next_observation()
            if type(batch) is not SourceBatch:
                raise RuntimeRefused('invalid_source_batch')
            # A Stop acknowledged while a provider request was in flight bars
            # every subsequent mathematical/economic transition from that batch.
            if self._closing or self._stop_requested:
                break
            if batch.mark is None:
                self._phase = 'waiting_data'
                self._last_failure = batch.safe_error
                await self._sleep(self._interval)
                continue
            self._phase = 'warming_up' if self.runtime.state is None else 'running'
            self._last_failure = None
            # The collector and runtime share SourceRecipeStore. The collector
            # has already inserted/read back every returned recipe and populated
            # that cache; an extra inventory RPC would age the genuine mark.
            if self.runtime.state is None:
                if batch.history is not None:
                    await self._commit(self.runtime.prepare_bootstrap(self._config,
                        batch.history, batch.series, inputs=self._inputs()))
                    if hasattr(self._feed, 'ack_history'):
                        self._feed.ack_history(batch.history.sha256)
                    self._phase = 'running'
            else:
                if self.runtime.state.to_dict()['status'] == 'risk_halted':
                    self._phase = 'risk_halted'
                    return
                history, series = batch.history, batch.series
                if history is not None and history.sha256 == self.runtime.state.to_dict()['source']['history_sha256']:
                    history = series = None
                inputs = self._inputs()
                try:
                    # The archived mark can age during CPU work or scheduling.
                    # A known expired mark is an unavailable live opportunity,
                    # not an uncertain economic write. Only this pure preflight
                    # is caught; generic proof failures and any later dispatch
                    # uncertainty still fail closed with their original IDs.
                    source.validate_current_mark(batch.mark, inputs.clock,
                        expected_mark_sha256=batch.mark.sha256)
                except acquisition.SampleUnavailable:
                    self._phase, self._last_failure = 'waiting_data', 'current_mark_expired'
                    await self._sleep(self._interval)
                    continue
                # Collection may cross a completed-bar boundary after the feed
                # checked publication readiness. Protection still consumes this
                # genuine mark; decision waits for its exact completed history.
                # Never move a sealed decision clock or fabricate a missing bar.
                cutoff = (inputs.clock.wall_lower_us-source.COMPLETION_MARGIN_US) // (
                    source.BAR_SECONDS*1_000_000) * source.BAR_SECONDS
                history_end = (int(history.to_dict()['range']['end']) if history is not None else
                    self.runtime.state.to_dict()['source']['history_end'])
                if history_end != cutoff:
                    await self._commit(self.runtime.prepare_protective(batch.mark, inputs=inputs))
                    if self._stop_requested or self._closing:
                        break
                    if self.runtime.state.to_dict()['status'] == 'risk_halted':
                        self._phase = 'risk_halted'
                        return
                    self._phase, self._last_failure = 'waiting_data', 'completed_history_unavailable'
                    await self._sleep(self._interval)
                    continue
                protective, decision = self.runtime.prepare_observation(batch.mark,
                    inputs=inputs, history=history, series=series)
                await self._commit(protective)
                if self._stop_requested or self._closing:
                    break
                if decision is None:
                    self._phase = 'risk_halted'
                    return
                await self._commit(decision)
                if batch.history is not None and hasattr(self._feed, 'ack_history'):
                    self._feed.ack_history(batch.history.sha256)
            if not self._stop_requested and not self._closing:
                await self._sleep(self._interval)
        if self._stop_requested and not self._closing:
            await self._stop_model()

    async def _stop_model(self):
        self._phase = 'stopping'
        if self.runtime.pending:
            await self.runtime.reconcile()
        if self.runtime.state is not None and self.runtime.state.to_dict()['status'] != 'stopped':
            # Original current binding is needed when Stop arrives immediately
            # after a process restart and before any new acquisition epoch.
            binding = SourceBinding(**self.runtime.state.to_dict()['source']['current_binding'])
            if binding.acquisition_epoch != self._feed.current_binding.acquisition_epoch:
                await self._commit(self.runtime.prepare_epoch_rollover(self._feed.current_binding,
                    self._inputs()))
            await self._commit(self.runtime.prepare_control('stop', self._inputs()))
        self._phase = 'stopped'

    async def start(self, owner, request_id):
        self._authorize(owner); acquisition.uuid(request_id)
        await self.initialize()
        async with self._control_lock:
            if self._closing or self.runtime.pending:
                raise RuntimePending('paper_service_unavailable')
            if self._initialized and self.runtime.state is not None and self.runtime.state.to_dict()['status'] == 'stopped':
                raise RuntimeRefused('terminal_run_requires_new_run')
            stop_marker = self._stop_latch
            try:
                await self._journal.control(request_id, 'start')
                self._last_control = self._control(await self._journal.latest_control())
            except Exception:
                self._phase, self._last_failure = 'pending', 'start_control_unresolved'
                raise RuntimePending('original_control_unresolved') from None
            self._stop_requested = self._last_control['action'] == 'stop' or stop_marker != self._stop_latch
            if self._initialized and not self._stop_requested:
                self._phase = 'warming_up' if self.runtime.state is None else 'running'
                self._launch(self._run)
        return await self.status(owner)

    async def stop(self, owner, request_id):
        self._authorize(owner); acquisition.uuid(request_id)
        await self.initialize()
        # Latch admission synchronously before the durable control write.
        self._stop_latch += 1
        self._stop_requested = True
        if self._initialized:
            self._phase = 'stopping'
        async with self._control_lock:
            try:
                await self._journal.control(request_id, 'stop')
                self._last_control = self._control(await self._journal.latest_control())
            except Exception:
                self._phase, self._last_failure = 'pending', 'stop_control_unresolved'
                raise RuntimePending('original_control_unresolved') from None
            if self._initialized:
                self._launch(self._stop_model)
        return await self.status(owner)

    def _projection(self):
        if self.runtime.state is None:
            return None
        row = self.runtime.state.to_dict()
        accounts = {item['id']: item for item in row['accounts']}
        open_positions = [item for item in row['positions'] if not item['closed']]
        positions = {item['account_id']: item for item in open_positions}
        quote = row['source']['last_quote']
        price = None if quote is None else quote['price_decimal']
        total = _units(row['reserve'], CASH_SCALE)
        members = []
        for member in row['engine']['members']:
            account = accounts[member['id']]
            equity = _units(account['cash'], CASH_SCALE)
            position = positions.get(member['id'])
            if position is not None and price is not None:
                equity += _units(mark_value(EntryPlan.from_dict(position['entry']), price), CASH_SCALE)
            total += equity
            genome = member['genome']
            members.append({'id': member['id'], 'name': member['name'],
                'generation': genome['generation'], 'ema_fast': int(float.fromhex(genome['ema_fast'])),
                'ema_slow': int(float.fromhex(genome['ema_slow'])), 'cash': account['cash'],
                'initial_cash': account['initial_cash'], 'equity': _text(equity, CASH_SCALE),
                'num_trades': member['num_trades'], 'max_drawdown': member['max_drawdown'],
                'parent_ids': genome['parent_ids']})
        return {'status': row['status'], 'reserve_cash': row['reserve'],
            'total_equity': _text(total, CASH_SCALE), 'population': 8, 'asset': 'SOL/USD',
            'generation': row['engine']['generation'], 'members': members,
            'positions': open_positions, 'last_mark': quote,
            'risk': row['engine']['lifecycle']['risk'],
            'paper_fill': row['engine']['config']['paper_fill'],
            'valuation': 'reference_mark', 'real_money': False}

    async def status(self, owner):
        self._authorize(owner)
        await self.initialize()
        row = None if not self._initialized or self.runtime.state is None else self.runtime.state.to_dict()
        feed_status = self._feed.status() if hasattr(self._feed, 'status') else None
        return {'version': 6, 'owner_id': self.owner_id, 'run_id': self.run_id,
            'phase': self._phase, 'busy': (self._recovery_task is not None and not self._recovery_task.done())
                or (self._task is not None and not self._task.done()),
            'requires_reconciliation': self.runtime.pending or self._phase in {'pending', 'failed'},
            'sequence': self.runtime.sequence if self._initialized else 0,
            'latest_committed_sequence': self.runtime.sequence if self._initialized else 0,
            'recovery_sequence': self.runtime.sequence,
            'revision': None if row is None else row['revision'],
            'generation': 0 if row is None else row['engine']['generation'],
            'epoch': 0 if row is None else row['engine']['lifecycle']['search_epoch'],
            'last_request_id': None if self._last_control is None else self._last_control['request_id'],
            'last_failure': self._last_failure, 'warmup': feed_status,
            'projection': self._projection() if self._initialized else None,
            'profile': {'genes': ['ema_fast', 'ema_slow'], 'population': 8,
                'asset': 'SOL/USD', 'bar_seconds': 900, 'evaluation_seconds': 3600,
                'warmup_minutes': 915, 'interval_seconds': self._interval,
                'cost_assumptions': 'explicit_operator_uncalibrated_scenario',
                'stop_keeps_open_positions_recorded': True, 'real_money': False}}

    async def history(self, owner, after_sequence=0, limit=100):
        self._authorize(owner)
        await self.initialize()
        if not self._initialized:
            raise RuntimeRefused('paper_recovery_in_progress')
        if type(after_sequence) is not int or after_sequence < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise RuntimeRefused('invalid_history_page')
        if after_sequence > self.runtime.sequence:
            raise RuntimeRefused('invalid_history_page')
        rows = await self._journal.scan(after_sequence=after_sequence, limit=limit)
        records = []
        for entry in rows:
            envelope = entry.to_dict()
            if int(envelope['sequence']) > self.runtime.sequence:
                break
            if int(envelope['sequence']) != after_sequence+len(records)+1:
                raise RuntimeRefused('committed_history_gap')
            from ..research import numeric_wire
            candidate = numeric_wire.decode(envelope['candidate_wire'].encode('utf-8'))
            record = {'sequence': int(envelope['sequence']),
                'kind': candidate['transition']['evidence']['kind'], 'data': candidate['history']}
            if records and len(acquisition.canonical(records+[record])) > 192*1024:
                break
            records.append(record)
        next_sequence = after_sequence + len(records)
        return {'version': 6, 'owner_id': self.owner_id, 'run_id': self.run_id,
            'through_sequence': self.runtime.sequence, 'next_sequence': next_sequence,
            'has_more': next_sequence < self.runtime.sequence, 'records': records}

    async def close(self):
        self._closing = True
        if self._recovery_task is not None:
            await asyncio.gather(self._recovery_task, return_exceptions=True)
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
        await self._feed.close()
        if hasattr(self._journal, 'close'):
            await self._journal.close()
