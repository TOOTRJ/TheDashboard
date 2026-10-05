"""Explicitly paced, finite execution of an exclusively owned paper pilot.

No cadence is selected here. A caller must supply an interval and tick budget.
Only an explicit stop request spends the pilot's reserved terminal command.
Unknown commands and delivery failures require explicit settlement; the runner
does not retry them in a loop or start another economic operation behind them.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import time

from .provider_controller import ProviderPilotController, TickReport
from .provider_pilot import ProviderPilotLimits
from ..db.command_repository import CommandBusy
from ..db.rehearsal_owner import OperationalAdmissionError


@dataclass(frozen=True, slots=True)
class RunnerReport:
    status: str
    ticks_completed: int
    stop_requested: bool
    reports: tuple[TickReport, ...]


class ProviderPilotRunner:
    """Own one bounded run, including its wait and cancelled caller's result.

    ``controller`` must be fresh, and must have no other callers after being
    handed to this runner. Every next tick is scheduled after the previous
    operation completes plus ``interval_seconds``. Delays never create a queue
    of missed ticks. Deferred snapshots still count against the tick budget.
    """

    def __init__(self, controller, *, interval_seconds, max_ticks,
                 monotonic=time.monotonic):
        if (type(controller) is not ProviderPilotController or controller.busy
                or controller.pending_stage is not None or controller.last_report is not None
                or not callable(monotonic)):
            raise OperationalAdmissionError('runner requires an exclusive fresh pilot controller')
        if (type(interval_seconds) not in (int, float) or not math.isfinite(interval_seconds)
                or not 0 < interval_seconds < controller.lease_seconds
                or interval_seconds > ProviderPilotLimits.MAX_ELAPSED_QUOTE_SECONDS):
            raise OperationalAdmissionError('an explicit finite positive pilot interval is required')
        limits = controller.pilot_limits
        limits.__post_init__()
        if type(max_ticks) is not int or not 1 <= max_ticks <= limits.max_quotes:
            raise OperationalAdmissionError('tick budget must fit the pilot quote budget')
        self._controller = controller
        self._interval, self._max_ticks = float(interval_seconds), max_ticks
        self._monotonic, self._last_mono = monotonic, None
        self._loop = self._task = None
        self._waiter = False
        self._wake = asyncio.Event()
        self._started = self._finished = self._bootstrapped = False
        self._draining = self._stop_requested = self._stop_done = False
        self._stage = None
        self._controller_started = False
        self._prior_controller_report = None
        self._next_due = None
        self._ticks = 0
        self._reports: list[TickReport] = []
        self._last_report = None

    @property
    def busy(self):
        return self._task is not None or self._controller.busy

    @property
    def pending_stage(self):
        return self._stage

    @property
    def last_report(self):
        return self._last_report

    def _bind_loop(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise OperationalAdmissionError('runner belongs to another event loop')

    def _check_sync_loop(self):
        if self._loop is not None:
            self._bind_loop()

    def _drain(self):
        self._draining = True
        self._controller.close_admission()
        self._wake.set()

    def close_admission(self):
        """Wake a wait and finish retained work without requesting liquidation."""
        self._check_sync_loop()
        self._drain()

    def request_stop(self):
        """Drain synchronously; spend the reserved stop after owned work settles.

        A fresh, unsubmitted bootstrap has no state to stop. In that case the
        run ends drained. This method never queues a second controller call.
        """
        self._check_sync_loop()
        self._stop_requested = True
        self._drain()

    def _clock(self):
        try:
            now = self._monotonic()
            if (type(now) not in (int, float) or not math.isfinite(now) or now < 0
                    or self._last_mono is not None and now < self._last_mono):
                raise ValueError()
        except (Exception, asyncio.CancelledError):
            self._drain()
            raise OperationalAdmissionError('runner monotonic clock is invalid') from None
        self._last_mono = float(now)
        return self._last_mono

    def _report(self, status, *, finish=False):
        report = RunnerReport(status, self._ticks, self._stop_requested, tuple(self._reports))
        self._last_report = report
        if finish:
            self._finished = True
            self._stage = None
        return report

    async def _wait(self):
        while not self._draining:
            remaining = self._next_due - self._clock()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(self._wake.wait(), remaining)
            except TimeoutError:
                pass
            self._clock()

    def _next(self):
        if self._draining:
            if self._stop_requested and self._bootstrapped and not self._stop_done:
                self._stage = 'stop'
                return None
            return self._report('drained', finish=True)
        if self._ticks >= self._max_ticks:
            return self._report('complete', finish=True)
        self._next_due = self._clock() + self._interval
        self._stage = 'wait'
        return None

    async def _advance(self, *, resume=False):
        while True:
            stage = self._stage
            if stage == 'wait':
                await self._wait()
                if self._draining:
                    report = self._next()
                    if report is not None:
                        return report
                    continue
                self._stage = 'tick'
                continue
            if stage is None:
                report = self._next()
                if report is not None:
                    return report
                continue
            if self._draining and stage != 'stop' and not resume:
                # No command has been admitted for this new stage. Retained
                # controller stages must instead cross explicit settlement.
                self._stage = None
                continue
            if resume and not self._controller_started:
                # Scheduling failed or the task was interrupted before it
                # entered any controller coroutine. There is nothing to replay.
                self._drain()
                self._stage = None
                return self._report('drained', finish=True)
            if stage == 'tick' and not resume and not self._controller.accepting:
                self._drain()
                return self._report('closed' if self._controller.closed_reason else 'drained', finish=True)
            try:
                self._clock()
            except OperationalAdmissionError:
                # The pacing clock controls new ticks, never installation or
                # delivery of an already submitted original operation. An
                # explicit reserved stop uses the owner's independent clocks.
                if not resume and stage != 'stop':
                    raise
            if resume:
                result = await self._controller.settle()
                resume = False
            else:
                self._prior_controller_report = self._controller.last_report
                self._controller_started = True
                result = await getattr(self._controller, stage)()
            if (result is None or result is self._prior_controller_report) and not self._controller.busy:
                self._drain()
                return self._report('closed', finish=True)
            if type(result) is not TickReport or result.kind != stage:
                self._drain()
                raise OperationalAdmissionError('controller result differs from the owned runner stage')
            if result.status == 'pending':
                return self._report('pending')
            # Append only after the original controller operation completes.
            # Repeated pending readbacks cannot count or store it twice.
            if len(self._reports) >= self._max_ticks + 2:
                self._drain()
                raise OperationalAdmissionError('runner report budget is exhausted')
            self._reports.append(result)
            if stage == 'bootstrap':
                self._bootstrapped = result.revision >= 2
            elif stage == 'tick':
                self._ticks += 1
            elif stage == 'stop':
                self._stop_done = result.status == 'complete'
            self._stage = None
            self._controller_started = False
            self._prior_controller_report = None
            if result.status == 'closed':
                self._drain()
                return self._report('closed', finish=True)
            if stage == 'stop':
                return self._report('stopped' if self._stop_done else 'closed', finish=True)
            if result.status == 'drained':
                self._draining = True
            if stage == 'bootstrap' and not self._draining:
                # Bootstrap completes before the first immediate quote attempt.
                self._stage = 'tick'
                continue
            report = self._next()
            if report is not None:
                return report

    async def _consume(self, task):
        self._bind_loop()
        if self._waiter:
            raise CommandBusy('the original runner waiter is still active')
        self._waiter = True
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            # Drain before returning cancellation to the caller. Shielding keeps
            # only already owned work alive; no future acquisition is admitted.
            self._drain()
            if task.cancelled() and self._task is task:
                self._task = None
            raise
        except Exception:
            if task.done() and self._task is task:
                self._task = None
            raise
        else:
            if self._task is task:
                self._task = None
            return result
        finally:
            self._waiter = False

    async def _owned(self, operation, *, retained=False):
        self._bind_loop()
        if self._task is not None or self._controller.busy and not retained:
            raise CommandBusy('the original runner operation must settle first')
        ready = asyncio.get_running_loop().create_future()
        async def run():
            try:
                await ready
                return await operation()
            except asyncio.CancelledError:
                self._drain()
                raise
        coroutine = run()
        try:
            task = asyncio.create_task(coroutine)
        except (Exception, asyncio.CancelledError):
            coroutine.close()
            self._drain()
            raise OperationalAdmissionError('runner scheduling failed') from None
        self._task = task
        def completed(done):
            if done.cancelled():
                self._drain()
            else:
                done.exception()
        task.add_done_callback(completed)
        ready.set_result(None)
        return await self._consume(task)

    async def run(self):
        self._bind_loop()
        if self._task is not None or self._controller.busy or self._stage is not None:
            raise CommandBusy('settle the original runner operation first')
        if self._started:
            raise OperationalAdmissionError('a finite runner may be started only once')
        self._clock()
        self._started = True
        self._stage = 'bootstrap'
        return await self._owned(self._advance)

    async def settle(self):
        """Consume retained work, or make one explicit continuation attempt.

        Missing journal evidence returns ``pending`` immediately. A successful
        continuation resumes this run's remaining sequential schedule, unless
        it was drained or an explicit stop was requested.
        """
        self._bind_loop()
        if self._task is not None:
            return await self._consume(self._task)
        if self._stage is not None:
            return await self._owned(lambda: self._advance(resume=self._stage != 'wait'), retained=True)
        if self._controller.busy:
            raise CommandBusy('the original controller work remains owned')
        if self._stop_requested and self._bootstrapped and not self._stop_done:
            self._stage = 'stop'
            return await self._owned(self._advance)
        if self._started and self._draining and not self._finished:
            return self._report('drained', finish=True)
        return self._last_report
