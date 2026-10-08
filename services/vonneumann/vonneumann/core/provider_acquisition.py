"""Bounded price acquisition for an exclusively owned v5 paper controller.

This is an acquisition prerequisite, not a controller or production entry point.
It cannot submit commands, publish events, restore state or trade a wallet.
The future controller must own the WHOLE tick through commit/publication; this
helper's lock covers acquisition only. No other caller may use its owner/feed.
"""
from __future__ import annotations

import asyncio
import math
import time

from ..db.command_repository import CommandBusy
from ..db.provider_owner import ProviderAdmissionOwner
from ..db.provider_pilot_owner import ProviderPilotOwner, PilotAdmissionRefused
from ..db.rehearsal_owner import OperationalAdmissionError
from ..market.jupiter_feed import PriceCapture
from ..market.feed import MarketFeedError
from ..market.provider_contract import ProviderDeferred, clock_us
from .operation_diagnostics import PROVIDER_CODES, failure_labels

ACQUISITION_TIMEOUT_SECONDS = 5
SOURCE_ORDER_MAX_CONSECUTIVE_DISCARDS = 2
SOURCE_ORDER_MAX_TOTAL_DISCARDS = 8
SOURCE_ORDER_EPISODE_SECONDS = 15


class ProviderPriceAcquisition:
    """Retain fractional receipts and cancelled callers' original results.

    A normal deferral returns None; the caller schedules another attempt using
    its actual clock. An unchanged accepted block is discarded so a later poll
    can discover a newer block, but the owner retains its original age anchors.
    An explicitly enabled paper policy may also discard two out-of-order feed
    responses between admitted quotes, eight in total, for at most 15 seconds
    per episode. Each discard ends this attempt; the runner owns the next poll.
    No automatic retry, timestamp rewriting or background polling is performed.
    """

    def __init__(self, feed, owner: ProviderAdmissionOwner, *,
                 quarantine_regressions=False, monotonic=time.monotonic):
        if (type(owner) not in (ProviderAdmissionOwner, ProviderPilotOwner)
                or not callable(getattr(feed, 'get_price_captures', None))):
            raise OperationalAdmissionError('provider acquisition requires its feed and v5 owner')
        if type(quarantine_regressions) is not bool or not callable(monotonic):
            raise OperationalAdmissionError('invalid source order policy')
        self._feed, self._owner = feed, owner
        self._capture: PriceCapture | None = None
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiter = False
        self._closed = False
        self._last_failure = None
        self._stage = 'acquisition_start'
        self._quarantine_regressions = quarantine_regressions
        self._monotonic, self._last_mono = monotonic, None
        self._source_order_discarded = self._episode_discarded = 0
        self._episode_started = self._source_order_limit = None

    @property
    def source_order_status(self):
        """Bounded local counters, never provider bodies or exception text."""
        return {'enabled': self._quarantine_regressions,
                'discarded_total': self._source_order_discarded,
                'episode_discarded': self._episode_discarded,
                'episode_active': self._episode_started is not None,
                'limit_reason': self._source_order_limit,
                'max_consecutive_discards': SOURCE_ORDER_MAX_CONSECUTIVE_DISCARDS,
                'max_total_discards': SOURCE_ORDER_MAX_TOTAL_DISCARDS,
                'episode_seconds': SOURCE_ORDER_EPISODE_SECONDS}

    def _source_order_clock(self):
        now = self._monotonic()
        if (type(now) not in (int, float) or not math.isfinite(now) or now < 0
                or self._last_mono is not None and now < self._last_mono):
            raise OperationalAdmissionError('invalid source order clock')
        self._last_mono = now
        if (self._episode_started is not None
                and now - self._episode_started >= SOURCE_ORDER_EPISODE_SECONDS):
            self._source_order_limit = 'episode_deadline'
            raise MarketFeedError('source_slot_regressed')
        return now

    def _discard_regression(self, error):
        # Only a feed refusal before admission qualifies. Owner validation,
        # malformed data, stale source time and other provider failures remain
        # fatal. No response, ticket, identity or command is retained here.
        if (not self._quarantine_regressions or type(error) is not MarketFeedError
                or type(error.code) is not str or error.code != 'source_slot_regressed'):
            raise error
        now = self._source_order_clock()
        if self._episode_discarded >= SOURCE_ORDER_MAX_CONSECUTIVE_DISCARDS:
            self._source_order_limit = 'consecutive_limit'
            raise error
        if self._source_order_discarded >= SOURCE_ORDER_MAX_TOTAL_DISCARDS:
            self._source_order_limit = 'total_limit'
            raise error
        if self._episode_started is None:
            self._episode_started = now
        self._episode_discarded += 1
        self._source_order_discarded += 1

    @property
    def last_failure(self):
        return None if self._last_failure is None else self._last_failure.to_dict()

    @property
    def busy(self):
        """Includes a completed result retained for a cancelled caller."""
        return self._task is not None

    @property
    def has_deferred_capture(self):
        return self._capture is not None

    @property
    def deferred_until_second(self):
        """Earliest actual second for the retained original receipt."""
        if self._capture is None:
            return None
        received = clock_us(self._capture.record.document.received_at)
        second = (received + 999_999) // 1_000_000
        state = self._owner.installed_state
        prior = None if state is None else state.to_dict()['source']['last_quote']
        return second if prior is None else max(second, prior['decision_second'] + 1)

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

    def _fail(self, error=None, stage=None):
        if self._last_failure is None:
            self._last_failure = failure_labels(self._stage if stage is None else stage, error)
        self._closed = True
        if (self._quarantine_regressions and type(self._owner) is ProviderPilotOwner
                and self._stage == 'provider_capture' and stage is None
                and type(error) is MarketFeedError and type(error.code) is str
                and error.code in PROVIDER_CODES):
            # An owned feed refusal before quote admission has no uncertain
            # economic effect. Close ordinary pilot admission while retaining
            # its existing terminal reservation. Never reopen a hard latch.
            self._owner.refuse_acquisition()
        self._owner.close_admission()
        raise OperationalAdmissionError('provider_acquisition_failed') from None

    def _deadline(self, deadline):
        # A dependency may suppress cancellation. Also check loop time after
        # synchronous parsing: a timeout callback cannot preempt CPU work.
        if deadline.expired() or asyncio.get_running_loop().time() >= deadline.when():
            self._fail(TimeoutError(), 'acquisition_deadline')

    async def _acquire(self):
        try:
            async with asyncio.timeout(ACQUISITION_TIMEOUT_SECONDS) as deadline:
                if self._capture is None:
                    self._stage = 'provider_capture'
                    if self._quarantine_regressions:
                        self._source_order_clock()
                    try:
                        captures = await self._feed.get_price_captures(['SOL/USDC'])
                    except MarketFeedError as error:
                        self._deadline(deadline)
                        self._discard_regression(error)
                        return None
                    if (type(captures) is not dict or set(captures) != {'SOL/USDC'}
                            or type(captures['SOL/USDC']) is not PriceCapture):
                        self._fail(stage='invalid_capture')
                    self._capture = captures['SOL/USDC']
                self._deadline(deadline)
                if self._quarantine_regressions:
                    self._source_order_clock()
                try:
                    self._stage = 'quote_admission'
                    ticket = self._owner.capture_quote(self._capture)
                except ProviderDeferred as deferred:
                    self._deadline(deadline)
                    if deferred.reason == 'unchanged_quote':
                        self._capture = None
                    return None
                self._deadline(deadline)
                self._capture = None
                # Only an admitted ticket ends a rejection episode. Unchanged
                # or fractional receipts cannot reset its deadline/budget.
                self._episode_started = None
                self._episode_discarded = 0
                return ticket
        except PilotAdmissionRefused:
            # A normal pilot limit drains acquisition but preserves its reserved
            # terminal path. No command was prepared by this helper.
            self._capture = None
            self._closed = True
            raise
        except (Exception, asyncio.CancelledError) as error:
            self._fail(error)

    def _observe(self, task):
        # A cancelled waiter leaves work owned. Retrieve the exception to avoid
        # an unobserved-task warning; awaiting the same task still raises it.
        if task.cancelled():
            # Cancellation before the coroutine's first instruction bypasses
            # _acquire's exception handler. It still closes both admission gates.
            self._closed = True
            if self._last_failure is None:
                self._last_failure = failure_labels(self._stage, asyncio.CancelledError())
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
            self._stage = 'acquisition_start'
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
