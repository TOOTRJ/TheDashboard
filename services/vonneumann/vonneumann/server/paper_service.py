"""One explicitly configured native-v5 paper pilot, with retained operations.

No legacy CRUD/EventPersister, restoration, signer or service-role fallback.
Resources are passed explicitly; cloud startup constructs them only in paper-v5.
"""
from __future__ import annotations
import asyncio
from dataclasses import asdict
from uuid import uuid4

from ..core.exact_lifecycle import ExactLifecycleConfig
from ..core.provider_lifecycle import ProviderLifecycleConfig
from ..core.provider_controller import CommandAllocation, ProviderPilotController
from ..core.operation_diagnostics import failure_labels
from ..core.provider_runner import ProviderPilotRunner
from ..core.provider_pilot import ProviderPilotLimits
from ..db.command_protocol import PreparedCommand, canonical_uuid
from ..db.command_repository import CommandRepository, UncertainCommand
from ..db.provider_pilot_owner import ProviderPilotOwner
from ..db.relay_acceptance import DurableRelayPublisher
from ..db.transition_coordinator import PublicationError


class ServiceRefused(RuntimeError):
    pass


class PaperService:
    """Exclusive resources for one supervised pilot; start and stop IDs retained.

    The HTTP caller never owns the execution task. Losing/cancelling its reply
    cannot create a second run. Explicit settlement continues the original
    controller/runner stage only. Shutdown latches drain before awaiting work.
    """
    def __init__(self, economic, relay, feed, *, owner_id, run_id, epoch_id,
                 start_id, stop_id, strategy='genetic_algorithm', interval=5,
                 max_ticks=12):
        self.owner_id = canonical_uuid(owner_id)
        self.run_id = canonical_uuid(run_id)
        self.start_id, self.stop_id = canonical_uuid(start_id), canonical_uuid(stop_id)
        if self.start_id == self.stop_id:
            raise ServiceRefused('distinct_control_ids_required')
        self.config = ProviderLifecycleConfig(ExactLifecycleConfig(strategy,
            self.owner_id, self.run_id, asset='SOL/USD'), canonical_uuid(epoch_id))
        if type(max_ticks) is not int or not 1 <= max_ticks <= 3601:
            raise ServiceRefused('invalid_tick_budget')
        if (type(interval) is not int or not 1 <= interval <= 30
                or interval * max_ticks > ProviderPilotLimits.MAX_ELAPSED_QUOTE_SECONDS):
            raise ServiceRefused('invalid_pilot_duration')
        self._economic, self._relay, self._feed = economic, relay, feed
        # A restart gets a new worker identity and cannot adopt a prior receipt.
        self.repository = CommandRepository(economic, self.owner_id, self.run_id, str(uuid4()))
        self.controller = self.runner = None
        self._interval, self._ticks = interval, max_ticks
        self._task = None
        self._phase = 'fresh'
        self._last_operation_failure = None
        self._result = None
        self._stop_requested = self._closing = False
        self._command = None
        self._cleanup = None

    def _authorize(self, owner):
        if owner != self.owner_id:
            raise ServiceRefused('run_unavailable')

    def status(self, owner):
        self._authorize(owner)
        report = None if self.runner is None else self.runner.last_report
        native_phases = getattr(self._economic, 'last_failure_phases', None)
        allowed_phases = (None, 'connect', 'begin', 'role', 'execute', 'decode', 'commit', 'cleanup')
        transport_phases = None if type(native_phases) is not dict else {
            key: native_phases.get(key) if native_phases.get(key) in allowed_phases else None
            for key in ('economic', 'relay')}
        return {'version': 1, 'owner_id': self.owner_id, 'run_id': self.run_id,
            'request_id': self.start_id, 'phase': self._phase,
            'busy': self._task is not None and not self._task.done(),
            'stop_requested': self._stop_requested, 'revision': self.repository.revision,
            'requires_reconciliation': self._phase in ('pending', 'failed', 'drained'),
            'last_transport_failure_phases': transport_phases,
            'last_controller_failure': None if self.controller is None else self.controller.last_failure,
            'last_operation_failure': None if self._last_operation_failure is None else self._last_operation_failure.to_dict(),
            'admission': None if self.controller is None else {
                'controller_reason': self.controller.closed_reason,
                'owner_reason': self.controller._owner.closed_reason,
                'pending_stage': self.controller.pending_stage},
            'report': None if report is None else {
                'status': report.status, 'ticks_completed': report.ticks_completed,
                'stop_requested': report.stop_requested,
                'idle_renewals': report.idle_renewals,
                'last_tick': None if not report.reports else asdict(report.reports[-1])},
            'profile': {'genes': ['ema_fast', 'ema_slow'], 'population': 8,
                'asset': 'SOL/USD', 'interval_seconds': self._interval,
                'max_ticks': self._ticks, 'max_replacements': 1,
                'evaluation_seconds': 3600,
                'completion_grace_seconds': ProviderPilotLimits.COMPLETION_GRACE_SECONDS,
                'cost_assumptions': 'uncalibrated_scenario', 'restoration': False}}

    def _owned(self, operation):
        if self._task is not None and not self._task.done():
            raise ServiceRefused('original_operation_busy')
        async def run():
            try:
                await operation()
            except (UncertainCommand, PublicationError):
                self._phase = 'pending'
            except asyncio.CancelledError:
                self._phase = 'drained'
                if self.runner is not None: self.runner.close_admission()
                raise
            except Exception as error:
                # Driver/provider exception text may include URLs or secrets.
                if self._last_operation_failure is None:
                    self._last_operation_failure = failure_labels('service_operation', error)
                self._phase = 'failed'
                if self.runner is not None: self.runner.close_admission()
        self._task = asyncio.create_task(run())
        self._task.add_done_callback(lambda t: None if t.cancelled() else t.exception())

    def _allocate(self, kind, generation):
        return CommandAllocation(str(uuid4()), tuple(str(uuid4()) for _ in range(9)),
            tuple((generation, f'Paper-{generation}-{index}') for index in range(8)))

    async def _after_create(self):
        if self.runner is None:
            owner = ProviderPilotOwner(self.repository, self._relay, self.config,
                                       stop_command_id=self.stop_id)
            publisher = DurableRelayPublisher(self._relay, self.owner_id, self.run_id)
            self.controller = ProviderPilotController(owner, self._feed, publisher,
                                                     self._allocate, lease_seconds=120)
            self.runner = ProviderPilotRunner(self.controller,
                interval_seconds=self._interval, max_ticks=self._ticks)
        if self._closing:
            self.runner.close_admission(); self._phase = 'drained'; return
        if self._stop_requested:
            # A create without bootstrap has only reserve. Do not acquire
            # provider history just to manufacture a terminal checkpoint.
            self.runner.close_admission(); self._phase = 'drained'; return
        self._phase = 'running'
        await self._finish(await self.runner.run())

    async def _finish(self, report):
        if report is None or report.status == 'pending':
            self._phase = 'pending'; return
        if report.status == 'complete':
            # Finite budget exhaustion is a real reserved stop, never a
            # liquidation or success inferred from a timer.
            self._stop_requested = True
            self.runner.request_stop()
            report = await self.runner.settle()
        self._phase = 'stopped' if report.status == 'stopped' else (
            'pending' if report.status == 'pending' else 'drained')

    async def _start(self):
        # The native readback contract requires an existing run. A fresh create
        # is admitted exactly once under its configured original ID; SQL rejects
        # an old run/replay whose worker identity differs after process restart.
        # No negative read is interpreted as rollback or permission for retry.
        self._command = PreparedCommand.create(self.owner_id, self.run_id,
            self.repository.worker_id, self.config.run_configuration(), self.config.initial_cash,
            command_id=self.start_id, lease_seconds=120)
        await self.repository.submit(self._command)
        await self._after_create()

    def start(self, owner, request_id):
        self._authorize(owner)
        if request_id != self.start_id: raise ServiceRefused('original_start_id_required')
        if self._phase != 'fresh': return self.status(owner)
        if self._closing: raise ServiceRefused('admission_closed')
        # Latch before scheduling/first await; retries can only read this task.
        self._phase = 'starting'
        self._owned(self._start)
        return self.status(owner)

    def stop(self, owner, request_id):
        self._authorize(owner)
        if request_id != self.stop_id: raise ServiceRefused('original_stop_id_required')
        self._stop_requested = True
        if self._phase == 'fresh': self._phase = 'drained'
        if self.runner is not None:
            self.runner.request_stop()
            if self._task is None or self._task.done():
                self._owned(self._settle)
        # A request is acknowledged as a latch, not a persisted stopped state.
        return self.status(owner)

    async def _settle(self):
        if self.runner is None:
            if self.repository.pending is None: raise ServiceRefused('no_original_command')
            receipt = await self.repository.resolve_pending()
            if receipt is None: self._phase = 'pending'; return
            await self._after_create()
        else:
            await self._finish(await self.runner.settle())

    def settle(self, owner, request_id):
        self._authorize(owner)
        if request_id != self.start_id: raise ServiceRefused('original_start_id_required')
        if self._phase not in ('pending', 'drained'):
            raise ServiceRefused('settlement_unavailable')
        if self._closing: raise ServiceRefused('admission_closed')
        self._owned(self._settle)
        return self.status(owner)

    async def close(self):
        self._closing = True
        if self.runner is not None: self.runner.close_admission()
        # Cleanup stays owned after the caller's deadline. Never close a feed
        # under retained controller work or abandon its eventual resource close.
        if self._cleanup is None:
            async def cleanup():
                if self._task is not None:
                    await asyncio.gather(self._task, return_exceptions=True)
                await self._feed.close()
                await self._economic.aclose()
                if self._relay is not self._economic: await self._relay.aclose()
            self._cleanup = asyncio.create_task(cleanup())
            self._cleanup.add_done_callback(lambda t: None if t.cancelled() else t.exception())
        try: await asyncio.wait_for(asyncio.shield(self._cleanup), 12)
        except TimeoutError: self._phase = 'drained'
        return self.status(self.owner_id)
