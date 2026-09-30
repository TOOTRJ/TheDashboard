"""Owner-scoped colonies with awaited preparation and supervised execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from .colony_config import ColonyConfig
from .genesis import GenesisController
from .types import ProbeEvent
from ..db.repository import PersistenceError
from ..market.feed import MarketFeed
from ..market.jupiter_feed import MarketFeedError

logger = logging.getLogger(__name__)
STARTUP_TIMEOUT_SECONDS = 30.0
CLEANUP_TIMEOUT_SECONDS = 5.0
QUIESCE_TIMEOUT_SECONDS = 30.0
StatusCallback = Callable[[dict], Awaitable[None]]
FAILURE_MESSAGES = {
    "startup_failed": "Colony preparation failed. Review configuration and service readiness before retrying.",
    "startup_timeout": "Colony preparation exceeded its deadline.",
    "startup_cancelled": "Colony preparation was cancelled.",
    "persistence_failed": "Colony persistence failed. Execution has stopped; reconciliation may be required.",
    "execution_failed": "Colony execution failed and has stopped. Reconciliation may be required.",
    "cleanup_failed": "Colony resource cleanup failed. Execution has stopped.",
    "feed_unavailable": "Required market data is unavailable. Colony execution has stopped.",
}


async def complete_operation(awaitable):
    """An accepted control must finish its transition even if its caller leaves."""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


class ColonyLifecycleError(RuntimeError):
    def __init__(self, code: str, *, conflict: bool = False):
        self.code = code
        self.conflict = conflict
        super().__init__("Colony is not in a state that permits this action" if conflict
                         else FAILURE_MESSAGES.get(code, FAILURE_MESSAGES["execution_failed"]))


def _failure_code(error: Exception, default: str) -> str:
    if isinstance(error, PersistenceError):
        return "persistence_failed"
    if isinstance(error, MarketFeedError):
        return "feed_unavailable"
    if isinstance(error, ColonyLifecycleError) and not error.conflict:
        return error.code
    return default


class _StartingColony:
    """Retain an owner-visible failure even when constructing the controller fails."""
    def __init__(self, colony_id: str, user_id: str, mode: str, strategy: str):
        self.colony_id = self.run_id = colony_id
        self.user_id = user_id
        self.mode = mode
        self.strategy_name = strategy
        self.lifecycle = "starting"
        self.state_persisted = True
        self.failure_code = self.failure_message = None
        self.market_feed = None

    def set_lifecycle(self, status: str) -> None:
        self.lifecycle = status

    def status(self) -> dict:
        return {"colony_id": self.colony_id, "run_id": self.run_id,
                "status": self.lifecycle, "mode": self.mode, "strategy": self.strategy_name,
                "state_persisted": self.state_persisted, "failure_code": self.failure_code,
                "failure_message": self.failure_message, "open_positions": 0,
                "requires_reconciliation": False, "live_probes": 0, "dead_probes": 0,
                "total_probes": 0, "generation": 0, "tick": 0, "reserve_capital": 0,
                "active_capital": 0, "total_capital": 0, "circuit_breaker": False,
                "diversity": 0, "uptime_secs": 0, "started_at": None}

    async def cleanup(self) -> None:
        if self.market_feed is not None and hasattr(self.market_feed, "close"):
            await self.market_feed.close()
            self.market_feed = None


class ColonyManager:
    """Keep terminal state visible; never confuse a scheduled task with a ready colony."""

    def __init__(self) -> None:
        self._colonies: dict[str, GenesisController | _StartingColony] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._persist: dict[str, StatusCallback] = {}
        self._publish: dict[str, StatusCallback] = {}
        self._pending_failures: dict[str, str] = {}

    def _register(self, colony_id, user_id, mode, strategy, persist_status, on_status):
        self._colonies[colony_id] = _StartingColony(colony_id, user_id, mode, strategy)
        self._locks[colony_id] = asyncio.Lock()
        if persist_status is not None:
            self._persist[colony_id] = persist_status
        if on_status is not None:
            self._publish[colony_id] = on_status

    async def record_start_failure(self, colony_id, user_id, mode, strategy_name,
                                   persist_status, on_status) -> None:
        """Cancellation after an initial insert still leaves a truthful terminal record."""
        self._register(colony_id, user_id, mode, strategy_name, persist_status, on_status)
        await self._fail(colony_id, "startup_cancelled")

    async def create_colony(
        self, colony_id: str, user_id: str, mode: str, strategy_name: str,
        colony_config: ColonyConfig, on_event: Callable[[ProbeEvent], Awaitable[None]], *,
        max_probes: int = 50, gen0_count: int = 10, seed_capital: float = 100,
        max_capital: float = 10_000, tick_interval_ms: int = 1000,
        mutation_rate: float = 0.20, persist_status: Optional[StatusCallback] = None,
        on_status: Optional[StatusCallback] = None,
    ) -> str:
        """The caller must persist the starting row before calling this method."""
        from .strategies import get_strategy

        self._register(colony_id, user_id, mode, strategy_name, persist_status, on_status)

        async def prepare() -> None:
            strategy = get_strategy(strategy_name)
            feed = self._create_feed(mode)
            self._colonies[colony_id].market_feed = feed
            colony_config.mutation_rate = mutation_rate
            genesis = GenesisController(
                market_feed=feed, strategy=strategy, colony_id=colony_id, user_id=user_id,
                mode=mode, max_probes=max_probes, gen0_count=gen0_count,
                seed_capital=seed_capital, max_capital=max_capital,
                tick_interval_ms=tick_interval_ms, mutation_rate=mutation_rate,
                colony_config=colony_config, on_event=on_event,
            )
            genesis.state_persisted = True  # The starting row already exists.
            self._colonies[colony_id] = genesis
            await genesis.prepare()
            await self._transition(colony_id, "running")

        try:
            # Repository cancellation drains a bounded in-flight write first, so a
            # late starting/running write cannot overwrite the following failure.
            await asyncio.wait_for(prepare(), timeout=STARTUP_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            await complete_operation(self._fail(colony_id, "startup_cancelled"))
            raise
        except Exception as error:
            code = _failure_code(error, "startup_timeout" if isinstance(error, asyncio.TimeoutError)
                                 else "startup_failed")
            await self._fail(colony_id, code)
            raise ColonyLifecycleError(code) from None

        self._tasks[colony_id] = asyncio.create_task(self._supervise(colony_id))
        logger.info("[ColonyManager] Prepared colony %s", colony_id[:8])
        return colony_id

    async def _supervise(self, colony_id: str) -> None:
        try:
            await self._colonies[colony_id].run()
            if self._colonies[colony_id].status()["status"] in {"running", "paused"}:
                raise RuntimeError("Execution ended unexpectedly")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = _failure_code(error, "execution_failed")
            # A control holding the lock must see the failure before it can
            # cancel this supervisor and accidentally label uncertain state stopped.
            self._pending_failures[colony_id] = code
            async with self._locks[colony_id]:
                if self._colonies[colony_id].status()["status"] != "failed":
                    await self._fail(colony_id, code)
        finally:
            if self._tasks.get(colony_id) is asyncio.current_task():
                self._tasks.pop(colony_id, None)

    async def _cancel_run(self, colony_id: str) -> None:
        task = self._tasks.pop(colony_id, None)
        if task is not None and task is not asyncio.current_task():
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _transition(self, colony_id: str, status: str) -> None:
        colony = self._colonies[colony_id]
        colony.set_lifecycle(status)
        colony.state_persisted = False
        callback = self._persist.get(colony_id)
        if callback is not None:
            await callback(colony.status())
            colony.state_persisted = True
        callback = self._publish.get(colony_id)
        if callback is not None:
            await callback(colony.status())

    async def _fail(self, colony_id: str, code: str) -> None:
        colony = self._colonies[colony_id]
        colony.set_lifecycle("failed")
        colony.failure_code = code
        colony.failure_message = FAILURE_MESSAGES[code]
        colony.state_persisted = False
        await self._cancel_run(colony_id)
        try:
            await asyncio.wait_for(colony.cleanup(), timeout=CLEANUP_TIMEOUT_SECONDS)
        except Exception:
            logger.warning("[ColonyManager] Cleanup failed for colony %s", colony_id[:8])
        callback = self._persist.get(colony_id)
        if callback is not None:
            try:
                await callback(colony.status())
                colony.state_persisted = True
            except Exception:
                # Report the in-memory failure honestly when storage is unavailable.
                logger.warning("[ColonyManager] Failure state not persisted for colony %s", colony_id[:8])
        callback = self._publish.get(colony_id)
        if callback is not None:
            try:
                await callback(colony.status())
            except Exception:
                logger.warning("[ColonyManager] Failure notification unavailable for colony %s", colony_id[:8])
        logger.warning("[ColonyManager] Colony %s stopped with %s", colony_id[:8], code)

    def _require_state(self, colony_id: str, states: set[str]):
        colony = self._colonies[colony_id]
        if colony.status()["status"] not in states:
            raise ColonyLifecycleError("invalid_state", conflict=True)
        return colony

    def _check_pending_failure(self, colony_id: str) -> None:
        if colony_id in self._pending_failures:
            raise ColonyLifecycleError(self._pending_failures[colony_id])

    async def stop_colony(self, colony_id: str) -> None:
        await complete_operation(self._stop_colony(colony_id))

    async def _stop_colony(self, colony_id: str) -> None:
        async with self._locks.setdefault(colony_id, asyncio.Lock()):
            colony = self._require_state(colony_id, {"running", "paused", "stopped"})
            if colony.status()["status"] == "stopped":
                return
            try:
                # Finish the current event batch before cancelling the sleeping loop.
                # If it cannot quiesce, failure retains the uncertain ledger state.
                await asyncio.wait_for(colony.quiesce(), timeout=QUIESCE_TIMEOUT_SECONDS)
                self._check_pending_failure(colony_id)
                await self._cancel_run(colony_id)
                await asyncio.wait_for(colony.stop(), timeout=CLEANUP_TIMEOUT_SECONDS)
                await self._transition(colony_id, "stopped")
            except Exception as error:
                code = _failure_code(error, "cleanup_failed")
                await self._fail(colony_id, code)
                raise ColonyLifecycleError(code) from None

    async def pause_colony(self, colony_id: str) -> None:
        await complete_operation(self._pause_colony(colony_id))

    async def _pause_colony(self, colony_id: str) -> None:
        async with self._locks.setdefault(colony_id, asyncio.Lock()):
            colony = self._require_state(colony_id, {"running"})
            colony.pause()
            try:
                await asyncio.wait_for(colony.wait_for_tick(), timeout=QUIESCE_TIMEOUT_SECONDS)
                self._check_pending_failure(colony_id)
                await self._transition(colony_id, "paused")
            except Exception as error:
                code = _failure_code(error, "execution_failed")
                await self._fail(colony_id, code)
                raise ColonyLifecycleError(code) from None

    async def resume_colony(self, colony_id: str) -> None:
        await complete_operation(self._resume_colony(colony_id))

    async def _resume_colony(self, colony_id: str) -> None:
        async with self._locks.setdefault(colony_id, asyncio.Lock()):
            colony = self._require_state(colony_id, {"paused"})
            try:
                self._check_pending_failure(colony_id)
                # Keep trading paused while its durable status change is in flight.
                callback = self._persist.get(colony_id)
                colony.state_persisted = False
                if callback is not None:
                    await callback({**colony.status(), "status": "running"})
                    colony.state_persisted = True
                colony.resume()
                colony.set_lifecycle("running")
                callback = self._publish.get(colony_id)
                if callback is not None:
                    await callback(colony.status())
            except Exception as error:
                code = _failure_code(error, "execution_failed")
                await self._fail(colony_id, code)
                raise ColonyLifecycleError(code) from None

    def get_colony(self, colony_id: str):
        return self._colonies.get(colony_id)

    def get_owned_colony(self, colony_id: str, user_id: str):
        colony = self._colonies.get(colony_id)
        return colony if colony and colony.user_id == user_id else None

    def list_colonies(self, user_id: str) -> list[dict]:
        return [{**colony.status(), "colony_id": cid} for cid, colony in self._colonies.items()
                if colony.user_id == user_id]

    def latest_colony_id(self, user_id: str) -> Optional[str]:
        for colony_id, colony in reversed(list(self._colonies.items())):
            if colony.user_id == user_id:
                return colony_id
        return None

    def active_count(self) -> int:
        return sum(colony.status()["status"] in {"starting", "running", "paused"}
                   for colony in self._colonies.values())

    async def shutdown(self) -> None:
        for colony_id, colony in list(self._colonies.items()):
            if colony.status()["status"] in {"running", "paused"}:
                try:
                    await self.stop_colony(colony_id)
                except ColonyLifecycleError:
                    pass  # Already failed closed and retained for inspection.

    @staticmethod
    def _create_feed(mode: str) -> MarketFeed:
        if mode == "simulation":
            from ..market.sim_feed import SimulationFeed
            return SimulationFeed()
        if mode == "paper":
            from ..market.jupiter_feed import JupiterFeed
            return JupiterFeed()
        raise ValueError("Only simulation and paper modes are supported")
