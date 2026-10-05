"""Local admission policy for one bounded, opt-in v5 paper pilot.

The wire contract and the exact model retain their existing limits. This policy
does not restore state, grant commit authority, or establish a sustainable live
polling rate. Its stop witness is detached pure preparation: callers must never
submit or install it, and must reserve a separate real command for an actual
stop at the owner's current clocks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from . import exact_rehearsal as base
from . import provider_lifecycle as life
from .decision_inputs import DecisionInputs
from .signal_profile import EMA_WARMUP_BARS
from ..market.provider_contract import CANDLE_COMPLETION_US, MAX_SOURCE_SECOND


class PilotCapacityError(ValueError):
    """The local paper pilot cannot safely admit the requested work."""


@dataclass(frozen=True, slots=True)
class ProviderPilotLimits:
    """Narrower local bounds; the acknowledged v5 configuration is unchanged.

    Both configurable values require exact integers. Revalidate at an admission
    boundary with ``__post_init__`` even if frozen setters were circumvented.
    The command count includes creation, bootstrap, and a reserved final stop.
    """

    max_quotes: int = 3601
    max_commands: int = 4000

    MAX_ELAPSED_QUOTE_SECONDS: ClassVar[int] = 3600
    MAX_GENERATION: ClassVar[int] = 1
    MAX_SEARCH_EPOCH: ClassVar[int] = 0
    MAX_IDS: ClassVar[int] = 9
    MAX_NAMES: ClassVar[int] = 8

    def __post_init__(self):
        if type(self.max_quotes) is not int or not 1 <= self.max_quotes <= 3601:
            raise PilotCapacityError('pilot quotes require an integer from 1 to 3601')
        if type(self.max_commands) is not int or not 4 <= self.max_commands <= 4000:
            raise PilotCapacityError('pilot commands require an integer from 4 to 4000')


def _owned_data(state):
    if type(state) is not base.ExactState:
        raise PilotCapacityError('owned provider state required')
    data = state.to_dict()
    if ('source' not in data or data.get('status') not in
            {'running', 'paused', 'risk_halted', 'stopped'}):
        raise PilotCapacityError('owned provider lifecycle state required')
    return data


def stop_capacity_bytes(state):
    """Return a conservative whole v5 stop payload bound without installing it.

    A real stop may append an aborted evaluation rather than merely change a
    status. Preparing that real semantic operation on an owned fork measures
    the complete resulting before/after, optimizer, events, and source evidence.
    The witness uses the greatest provider event second, wall microsecond, and
    monotonic reading. Integer fields therefore have maximal allowed width.

    Both existing candidate byte limits apply: PostgreSQL-spacing UTF-8 JSON
    and the compact ASCII wire. Unicode names may make ASCII escape sequences
    larger than the PostgreSQL representation, so reserve the larger encoding.

    Add seven bytes for an actual wall ISO timestamp's optional ``.ffffff`` and
    two for the longest nonnegative subnormal float hexadecimal exponent. The
    witness's event time is integral, as every accepted event time must be.
    No identities or names are needed to stop. This returns a bound, never a
    candidate or permission to dispatch the synthetic future-clock operation.
    """
    data = _owned_data(state)
    if data['status'] not in {'running', 'paused', 'risk_halted'}:
        raise PilotCapacityError('terminal provider state has no stop witness')
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    inputs = DecisionInputs(epoch + timedelta(seconds=MAX_SOURCE_SECOND),
        epoch + timedelta(microseconds=10**16), float(MAX_SOURCE_SECOND), (), ())
    try:
        witness = life.prepare_control(state, 'stop', inputs)
    except (base.ExactRehearsalError, ValueError, KeyError, TypeError, OverflowError) as error:
        raise PilotCapacityError('complete provider stop cannot fit or be prepared') from error
    bound = max(witness.payload_bytes, len(witness._wire)) + 9
    if bound > base.MAX_PAYLOAD_BYTES:
        raise PilotCapacityError('complete provider stop exceeds reserved payload capacity')
    return bound


def decision_required(state, decision_second):
    """Select economic/candle work without spending a command on a no-op tick.

    Protection remains required separately for every accepted quote. Selecting
    a decision is conservative: a pending action needs clearing even when its
    fill window expired or its position no longer matches. A halted run admits
    retained exits only, without requesting history or restarting evaluation.
    This selector never advances a cursor, consumes randomness, or adopts JSON.
    """
    data = _owned_data(state)
    if type(decision_second) is not int or not 0 <= decision_second <= MAX_SOURCE_SECOND:
        raise PilotCapacityError('pilot decision time requires a bounded integer second')
    if data['status'] not in {'running', 'risk_halted'}:
        return False
    engine = data['engine']
    previous = engine['decision_timestamp']
    if previous is not None and decision_second <= previous:
        return False
    halted = data['status'] == 'risk_halted' or engine['lifecycle']['risk']['active']
    for member in engine['members']:
        pending = member['pending']
        if (member['terminal'] is None and pending is not None
                and decision_second > pending['signal_at']
                and (not halted or pending['action'] == 'exit')):
            return True
    if halted:
        return False
    bars = data['source']['bars']
    # A provider bar is eligible five seconds after its close. Selecting on
    # the exact 900-second boundary would otherwise spend commands on up to
    # five ticks while the acquisition adapter correctly returns no new bar.
    completed_end = ((decision_second * 1_000_000 - CANDLE_COMPLETION_US)
                     // (base.CANDLE_SECONDS * 1_000_000) * base.CANDLE_SECONDS)
    if not bars or completed_end > bars[-1][0]:
        return True
    lifecycle = engine['lifecycle']
    if lifecycle['restart_required']:
        return True
    cohort = engine['cohort']
    if cohort['phase'] == 'warming':
        last_end = engine['ema']['last_end']
        return (engine['ema']['count'] >= EMA_WARMUP_BARS and last_end is not None
                and last_end <= decision_second <= last_end + base.CANDLE_SECONDS)
    if cohort['phase'] == 'evaluating' and cohort['ends_at'] is not None:
        return decision_second >= float.fromhex(cohort['ends_at']['float64'])
    return False
