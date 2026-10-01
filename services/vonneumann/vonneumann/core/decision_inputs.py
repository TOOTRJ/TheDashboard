"""Explicit clocks and bounded identity budgets for one engine decision.

These inputs make time and identity consumption repeatable; they are not a
complete market context, exact ledger, checkpoint, or permission to commit.
Monotonic readings require a known compatible clock epoch; this record does not
establish that compatibility after restart. Reusing these clocks does not
establish quote freshness or renew a worker lease.
Complete transition, revision, and source binding remain separate work.

Each cursor owns its allocation counters. Exhaustion raises rather than reading
the system clock, generating an identifier, or consulting the global name pool.
Display names may repeat; only the supplied UUID identifiers must be unique.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from uuid import UUID


__all__ = ("DecisionInputs", "DecisionInputError")

MAX_ALLOCATIONS = 4096
MAX_NAME_BYTES = 128
MAX_GENERATION = 2**31 - 1


class DecisionInputError(ValueError):
    """Decision inputs are invalid or their preallocated budget is exhausted."""


def _utc_datetime(value: datetime) -> None:
    # Builtin timezone only: validating an input must not execute a caller's
    # custom tzinfo methods. Distinct builtin zero-offset UTC labels are valid.
    if (type(value) is not datetime or type(value.tzinfo) is not timezone
            or value.utcoffset() != timedelta(0)):
        raise DecisionInputError("decision clocks require aware UTC datetimes")


def _generation(value: int) -> None:
    if type(value) is not int or not 0 <= value <= MAX_GENERATION:
        raise DecisionInputError("probe generation is outside the supported range")


@dataclass(frozen=True, slots=True)
class DecisionInputs:
    """Immutable caller-supplied inputs; all allocations validate at creation.

    ``ids`` and ``names`` each contain at most 4096 allocations. A name is a
    printable, nonblank UTF-8 string of at most 128 bytes without edge whitespace.
    Generations are nonnegative signed-32-bit integers. Timestamps need not be
    equal: event time can follow a historical/replay timeline while wall time
    represents the explicit decision observation. Neither clock is read here.
    """

    event_at: datetime
    wall_at: datetime
    monotonic_at: float
    ids: tuple[str, ...] = ()
    names: tuple[tuple[int, str], ...] = ()

    def __post_init__(self) -> None:
        _utc_datetime(self.event_at)
        _utc_datetime(self.wall_at)
        if (type(self.monotonic_at) is not float or not math.isfinite(self.monotonic_at)
                or self.monotonic_at < 0):
            raise DecisionInputError("monotonic time requires a finite nonnegative float")
        if type(self.ids) is not tuple or len(self.ids) > MAX_ALLOCATIONS:
            raise DecisionInputError("identifier allocations require a bounded tuple")
        seen: set[str] = set()
        for identifier in self.ids:
            if type(identifier) is not str or len(identifier) != 36:
                raise DecisionInputError("identifiers require canonical UUID strings")
            try:
                canonical = str(UUID(identifier))
            except ValueError:
                raise DecisionInputError("identifiers require canonical UUID strings") from None
            if canonical != identifier or identifier in seen:
                raise DecisionInputError("identifiers must be canonical and unique")
            seen.add(identifier)
        if type(self.names) is not tuple or len(self.names) > MAX_ALLOCATIONS:
            raise DecisionInputError("name allocations require a bounded tuple")
        for allocation in self.names:
            if type(allocation) is not tuple or len(allocation) != 2:
                raise DecisionInputError("name allocations require generation and name pairs")
            generation, name = allocation
            _generation(generation)
            if (type(name) is not str or not name or len(name) > MAX_NAME_BYTES
                    or name.strip() != name or not name.isprintable()):
                raise DecisionInputError("probe names require bounded printable strings")
            try:
                size = len(name.encode("utf-8"))
            except UnicodeEncodeError:
                raise DecisionInputError("probe names require valid UTF-8") from None
            if size > MAX_NAME_BYTES:
                raise DecisionInputError("probe name exceeds its byte budget")

    def new_cursor(self) -> _DecisionCursor:
        """Return independent consumption state starting at both budget origins."""
        return _DecisionCursor(self)


class _DecisionCursor:
    """Caller-owned, synchronous cursor; share the record, not this cursor."""

    __slots__ = ("__inputs", "__id_index", "__name_index")

    def __init__(self, inputs: DecisionInputs) -> None:
        self.__inputs = inputs
        self.__id_index = 0
        self.__name_index = 0

    def event_time(self) -> datetime:
        return self.__inputs.event_at

    def wall_time(self) -> datetime:
        return self.__inputs.wall_at

    def monotonic_time(self) -> float:
        return self.__inputs.monotonic_at

    def next_id(self) -> str:
        if self.__id_index == len(self.__inputs.ids):
            raise DecisionInputError("decision identifier budget is exhausted")
        result = self.__inputs.ids[self.__id_index]
        self.__id_index += 1
        return result

    def probe_name(self, generation: int) -> str:
        _generation(generation)
        if self.__name_index == len(self.__inputs.names):
            raise DecisionInputError("decision name budget is exhausted")
        expected_generation, name = self.__inputs.names[self.__name_index]
        if generation != expected_generation:
            raise DecisionInputError("probe generation does not match its name allocation")
        self.__name_index += 1
        return name
