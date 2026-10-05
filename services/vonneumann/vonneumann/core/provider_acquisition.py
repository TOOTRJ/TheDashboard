"""Bounded price acquisition for an exclusively owned v5 paper controller.

This is an acquisition prerequisite, not a controller or production entry point.
It cannot submit commands, publish events, restore state or trade a wallet.
The future controller must own the WHOLE tick through commit/publication; this
helper's lock covers acquisition only. No other caller may use its owner/feed.
"""
from __future__ import annotations

import asyncio

from ..db.command_repository import CommandBusy
from ..db.provider_owner import ProviderAdmissionOwner
from ..db.provider_pilot_owner import ProviderPilotOwner, PilotAdmissionRefused
from ..db.rehearsal_owner import OperationalAdmissionError
from ..market.jupiter_feed import PriceCapture
from ..market.provider_contract import ProviderDeferred

ACQUISITION_TIMEOUT_SECONDS = 5


class ProviderPriceAcquisition:
    """Retain fractional receipts and cancelled callers' original results.

    A normal deferral returns None; the caller schedules another attempt using
    its actual clock. An unchanged accepted block is discarded so a later poll
    can discover a newer block, but the owner retains its original age anchors.
    No automatic retry, timestamp rewriting or background polling is performed.
    """

    def __init__(self, feed, owner: ProviderAdmissionOwner):
        if (type(owner) not in (ProviderAdmissionOwner, ProviderPilotOwner)
                or not callable(getattr(feed, 'get_price_captures', None))):
            raise OperationalAdmissionError('provider acquisition requires its feed and v5 owner')
        self._feed, self._owner = feed, owner
        self._capture: PriceCapture | None = None
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiter = False
        self._closed = False

    @property
    def busy(self):
        """Includes a completed result retained for a cancelled caller."""
        return self._task is not None

    @property
    def has_deferred_capture(self):
        return self._capture is not None

    @property
    def accepting(self):
        return not self._closed and not self.busy and self._owner.accepting

    def close_admission(self):
        """Drain acquisition; leave admitted work/result and owner intact."""
        self._closed = True

    def _bind_loop(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise OperationalAdmissionError('provider acquisition belongs to another event loop')

    def _fail(self):
        self._closed = True
        self._owner.close_admission()
        raise OperationalAdmissionError('provider_acquisition_failed') from None

    def _deadline(self, deadline):
        # A dependency may suppress cancellation. Also check loop time after
        # synchronous parsing: a timeout callback cannot preempt CPU work.
        if deadline.expired() or asyncio.get_running_loop().time() >= deadline.when():
            self._fail()

    async def _acquire(self):
        try:
            async with asyncio.timeout(ACQUISITION_TIMEOUT_SECONDS) as deadline:
                if self._capture is None:
                    captures = await self._feed.get_price_captures(['SOL/USDC'])
                    if (type(captures) is not dict or set(captures) != {'SOL/USDC'}
                            or type(captures['SOL/USDC']) is not PriceCapture):
                        self._fail()
                    self._capture = captures['SOL/USDC']
                self._deadline(deadline)
                try:
                    ticket = self._owner.capture_quote(self._capture)
                except ProviderDeferred as deferred:
                    self._deadline(deadline)
                    if deferred.reason == 'unchanged_quote':
                        self._capture = None
                    return None
                self._deadline(deadline)
                self._capture = None
                return ticket
        except PilotAdmissionRefused:
            # A normal pilot limit drains acquisition but preserves its reserved
            # terminal path. No command was prepared by this helper.
            self._capture = None
            self._closed = True
            raise
        except (Exception, asyncio.CancelledError):
            self._fail()

    def _observe(self, task):
        # A cancelled waiter leaves work owned. Retrieve the exception to avoid
        # an unobserved-task warning; awaiting the same task still raises it.
        if task.cancelled():
            # Cancellation before the coroutine's first instruction bypasses
            # _acquire's exception handler. It still closes both admission gates.
            self._closed = True
            self._owner.close_admission()
        else:
            task.exception()

    async def capture_quote(self):
        self._bind_loop()
        if self._waiter or self._task is not None and not self._task.done():
            raise CommandBusy('provider acquisition is still owned')
        if self._task is None:
            if self._closed:
                raise OperationalAdmissionError('provider acquisition admission is closed')
            if self._owner.busy:
                raise CommandBusy('provider owner work must settle before acquisition')
            if not self._owner.accepting:
                raise OperationalAdmissionError('provider owner admission is closed')
            coroutine = self._acquire()
            try:
                self._task = asyncio.create_task(coroutine)
                self._task.add_done_callback(self._observe)
            except (Exception, asyncio.CancelledError):
                coroutine.close()
                self._fail()
        task = self._task
        self._waiter = True
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                self._task = None
                self._fail()
            # Preserve task and result for explicit settlement/retrieval.
            raise
        except Exception:
            self._task = None
            raise
        else:
            self._task = None
            return result
        finally:
            self._waiter = False

    async def settle(self):
        """Await retained work without consuming its original result."""
        self._bind_loop()
        if self._task is not None:
            task = self._task
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                if task.cancelled():
                    self._fail()
                raise
        return None
