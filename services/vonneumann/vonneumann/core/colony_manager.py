"""Owner-scoped colonies with awaited preparation and supervised execution."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Optional, Callable, Awaitable

from .colony_config import ColonyConfig
from .signal_profile import signal_policy
from .genesis import GenesisController
from .funding import FundingError
from .market_validation import MarketValueError
from .risk_control import RiskRecoveryError, RISK_RECOVERY_MESSAGES
from .types import ProbeEvent
from ..db.repository import PersistenceError
from ..market.feed import MarketFeed, MarketFeedError

logger = logging.getLogger(__name__)
STARTUP_TIMEOUT_SECONDS = 30.0
CLEANUP_TIMEOUT_SECONDS = 5.0
QUIESCE_TIMEOUT_SECONDS = 30.0
SHUTDOWN_TIMEOUT_SECONDS = 40.0
MAX_RETAINED_COLONIES = 32
StatusCallback = Callable[[dict], Awaitable[None]]
FAILURE_MESSAGES = {
    "worker_draining": "The worker is shutting down. Execution cannot be started or resumed.",
    "startup_failed": "Colony preparation failed. Review configuration and service readiness before retrying.",
    "startup_timeout": "Colony preparation exceeded its deadline.",
    "startup_cancelled": "Colony preparation was cancelled.",
    "persistence_failed": "Colony persistence failed. Execution has stopped; reconciliation may be required.",
    "execution_failed": "Colony execution failed and has stopped. Reconciliation may be required.",
    "cleanup_failed": "Colony resource cleanup failed. Execution has stopped.",
    "feed_unavailable": "Required market data is unavailable. Colony execution has stopped.",
    "feed_configuration": "Paper mode requires a configured HTTPS Solana mainnet RPC for source-time validation.",
    "feed_stale": "A required market quote is stale. Execution has stopped; retained positions require reconciliation.",
    "feed_source_invalid": "A required quote has missing, invalid, or regressing source-time evidence. Execution has stopped.",
    "candle_configuration": "Completed candles require the worker's Birdeye key in paper mode or aligned one-minute simulation steps.",
    "candle_history_invalid": "Completed candle history is missing, incomplete, revised, or invalid. Execution has stopped; review retained positions and the data source.",
    "invalid_market_value": "A market observation or trade calculation was invalid. Execution has stopped; retained positions may require reconciliation.",
    "funding_insufficient": "The colony cannot fully fund its next candidate population. Execution has stopped.",
    "funding_capacity": "The replacement population exceeds the configured capacity. Execution has stopped.",
    "funding_invalid_plan": "The population replacement plan or capital ledger is invalid. Execution has stopped.",
    "population_extinct": "No active candidates remain and recovery could not be funded. Execution has stopped.",
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
        super().__init__(RISK_RECOVERY_MESSAGES.get(code, "Colony is not in a state that permits this action") if conflict
                         else FAILURE_MESSAGES.get(code, FAILURE_MESSAGES["execution_failed"]))


class ColonyAdmissionError(RuntimeError):
    """A start rejected before any repository, feed or startup side effect."""
    def __init__(self, code: str):
        if code not in {"worker_draining", "worker_capacity"}:
            raise ValueError("Invalid admission reason")
        self.code = code
        super().__init__("Worker cannot accept a new colony.")


def _failure_code(error: Exception, default: str) -> str:
    if isinstance(error, PersistenceError):
        return "persistence_failed"
    if isinstance(error, MarketFeedError):
        if error.code in {"candles_configuration", "candle_clock_configuration"}:
            return "candle_configuration"
        if error.code.startswith(("candle_", "candles_")) and error.code not in {
                "candles_unavailable", "candles_rate_limited"}:
            return "candle_history_invalid"
        if error.code in {"rpc_configuration", "rpc_wrong_network"}:
            return "feed_configuration"
        if error.code == "price_stale":
            return "feed_stale"
        if error.code in {"source_time_unavailable", "source_time_invalid", "source_slot_regressed"}:
            return "feed_source_invalid"
        return "feed_unavailable"
    if isinstance(error, MarketValueError):
        return "invalid_market_value"
    if isinstance(error, FundingError):
        return error.code if error.code in FAILURE_MESSAGES else "funding_invalid_plan"
    if isinstance(error, ColonyLifecycleError) and not error.conflict:
        return error.code
    return default


class _StartingColony:
    """Retain an owner-visible failure even when constructing the controller fails."""
    def __init__(self, colony_id: str, user_id: str, mode: str, strategy: str,
                 strategy_profile: str | None = None):
        self.colony_id = self.run_id = colony_id
        self.user_id = user_id
        self.mode = mode
        self.strategy_name = strategy
        self.lifecycle = "starting"
        self.state_persisted = False
        self.failure_code = self.failure_message = None
        self.market_feed = None
        self.strategy_profile = strategy_profile

    def set_lifecycle(self, status: str) -> None:
        self.lifecycle = status

    @property
    def lifecycle_status(self) -> str:
        return self.lifecycle

    def status(self) -> dict:
        return {"colony_id": self.colony_id, "run_id": self.run_id,
                "strategy_profile": self.strategy_profile,
                "signal_policy": signal_policy(self.strategy_profile) if self.strategy_profile is not None else None,
                "status": self.lifecycle, "mode": self.mode, "strategy": self.strategy_name,
                "state_persisted": self.state_persisted, "failure_code": self.failure_code,
                "failure_message": self.failure_message, "open_positions": 0,
                "requires_reconciliation": self.lifecycle == "failed", "live_probes": 0, "dead_probes": 0,
                "total_probes": 0, "generation": 0, "tick": 0, "reserve_capital": 0,
                "active_capital": 0, "total_capital": 0, "circuit_breaker": False,
                "diversity": 0, "uptime_secs": 0, "started_at": None}

    async def cleanup(self) -> None:
        if self.market_feed is not None and hasattr(self.market_feed, "close"):
            await self.market_feed.close()
            self.market_feed = None


class ColonyManager:
    """Keep terminal state visible; never confuse a scheduled task with a ready colony."""

    def __init__(self, *, max_retained_colonies: int = MAX_RETAINED_COLONIES) -> None:
        if type(max_retained_colonies) is not int or not 1 <= max_retained_colonies <= 128:
            raise ValueError("Retained colony limit must be an integer from 1 through 128")
        self.max_retained_colonies = max_retained_colonies
        self._colonies: dict[str, GenesisController | _StartingColony] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._persist: dict[str, StatusCallback] = {}
        self._publish: dict[str, StatusCallback] = {}
        self._pending_failures: dict[str, str] = {}
        self._start_tasks: dict[str, asyncio.Task] = {}
        self._control_tasks: set[asyncio.Task] = set()
        self._cleanup_tasks: dict[str, asyncio.Task] = {}
        self._cleanup_failures: set[str] = set()
        self._drain_tasks: set[asyncio.Task] = set()
        self._draining = False
        self._shutdown_task: asyncio.Task | None = None
        self._shutdown_deadline: float | None = None
        self._drain_failed = False

    def admission_status(self) -> str:
        if self._draining:
            return "closed_draining"
        if len(set(self._colonies) | set(self._start_tasks)) >= self.max_retained_colonies:
            return "closed_capacity"
        return "open"

    async def run_start(self, colony_id: str, operation: Callable[[], Awaitable]):
        """Reserve and own the whole start before it can perform its first write.

        No await separates checking admission from registering the owned task;
        this is atomic within this manager's event loop, not a database fence.
        """
        admission = self.admission_status()
        if admission == "closed_draining":
            raise ColonyAdmissionError("worker_draining")
        if colony_id in self._colonies or colony_id in self._start_tasks:
            raise ColonyLifecycleError("colony_exists", conflict=True)
        if admission == "closed_capacity":
            raise ColonyAdmissionError("worker_capacity")

        async def accepted():
            return await operation()

        task = asyncio.create_task(accepted())
        self._start_tasks[colony_id] = task

        def finished(done):
            if self._start_tasks.get(colony_id) is done:
                self._start_tasks.pop(colony_id, None)
            if not done.cancelled():
                done.exception()
        task.add_done_callback(finished)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Cancel the owned operation only once. Its accepted database write
            # and compensating status must finish before the request unwinds.
            caller_cancelled = bool(asyncio.current_task().cancelling())
            if not task.done() and not task.cancelling():
                task.cancel()
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                task.exception()
            if not caller_cancelled and not asyncio.current_task().cancelling() and self._draining:
                raise ColonyLifecycleError("worker_draining") from None
            raise

    async def _control(self, operation):
        if self._draining:
            raise ColonyLifecycleError("worker_draining")
        task = asyncio.create_task(operation())
        self._control_tasks.add(task)
        task.add_done_callback(self._control_tasks.discard)
        return await complete_operation(task)

    def _register(self, colony_id, user_id, mode, strategy, persist_status, on_status,
                  strategy_profile=None):
        if colony_id in self._colonies:
            raise ColonyLifecycleError("colony_exists", conflict=True)
        self._colonies[colony_id] = _StartingColony(colony_id, user_id, mode, strategy, strategy_profile)
        self._locks[colony_id] = asyncio.Lock()
        if persist_status is not None:
            self._persist[colony_id] = persist_status
        if on_status is not None:
            self._publish[colony_id] = on_status

    async def record_start_failure(self, colony_id, user_id, mode, strategy_name,
                                   persist_status, on_status, *, strategy_profile=None,
                                   code="startup_cancelled") -> None:
        """Cancellation after an initial insert still leaves a truthful terminal record."""
        self._register(colony_id, user_id, mode, strategy_name, persist_status, on_status, strategy_profile)
        await self._fail(colony_id, code)

    async def create_colony(self, colony_id: str, **kwargs) -> str:
        if self._start_tasks.get(colony_id) is asyncio.current_task():
            return await self._create_colony(colony_id=colony_id, **kwargs)
        return await self.run_start(colony_id, lambda: self._create_colony(colony_id=colony_id, **kwargs))

    async def _create_colony(
        self, colony_id: str, user_id: str, mode: str, strategy_name: str,
        colony_config: ColonyConfig, on_event: Callable[[ProbeEvent], Awaitable[None]], *,
        max_probes: int = 50, gen0_count: int = 10, seed_capital: float = 100,
        max_capital: float = 10_000, tick_interval_ms: int = 1000,
        mutation_rate: float = 0.20, persist_status: Optional[StatusCallback] = None,
        on_status: Optional[StatusCallback] = None,
        search_seed: str = "0",
        execution_config=None,
    ) -> str:
        """The caller must persist the starting row before calling this method."""
        from .strategies import get_strategy

        self._register(colony_id, user_id, mode, strategy_name, persist_status, on_status,
                       colony_config.strategy_profile)

        async def prepare() -> None:
            if self._draining:
                raise ColonyLifecycleError("worker_draining")
            strategy = get_strategy(strategy_name)
            feed = self._create_feed(mode)
            self._colonies[colony_id].market_feed = feed
            colony_config.mutation_rate = mutation_rate
            genesis = GenesisController(
                market_feed=feed, strategy=strategy, colony_id=colony_id, user_id=user_id,
                mode=mode, max_probes=max_probes, gen0_count=gen0_count,
                seed_capital=seed_capital, max_capital=max_capital,
                tick_interval_ms=tick_interval_ms, mutation_rate=mutation_rate,
                colony_config=colony_config, on_event=on_event, persist_risk_status=persist_status,
                search_seed=search_seed, execution_config=execution_config,
            )
            genesis.state_persisted = True  # The starting row already exists.
            self._colonies[colony_id] = genesis
            await genesis.prepare()
            if self._draining:
                raise ColonyLifecycleError("worker_draining")
            await self._transition(colony_id, "running")
            if self._draining:
                raise ColonyLifecycleError("worker_draining")

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
            if self._colonies[colony_id].lifecycle_status in {"running", "paused", "risk_halted"}:
                raise RuntimeError("Execution ended unexpectedly")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = _failure_code(error, "execution_failed")
            # A control holding the lock must see the failure before it can
            # cancel this supervisor and accidentally label uncertain state stopped.
            self._pending_failures[colony_id] = code
            async with self._locks[colony_id]:
                if self._colonies[colony_id].lifecycle_status != "failed":
                    await self._fail(colony_id, code)
        finally:
            if self._tasks.get(colony_id) is asyncio.current_task():
                self._tasks.pop(colony_id, None)

    async def _cancel_run(self, colony_id: str) -> None:
        task = self._tasks.get(colony_id)
        if task is not None and task is not asyncio.current_task():
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            finally:
                if task.done() and self._tasks.get(colony_id) is task:
                    self._tasks.pop(colony_id, None)

    async def _cleanup(self, colony_id: str, *, stop=False) -> None:
        """One owned close attempt; a deadline never abandons or duplicates it."""
        task = self._cleanup_tasks.get(colony_id)
        if task is None:
            colony = self._colonies[colony_id]
            task = asyncio.create_task(colony.stop() if stop else colony.cleanup())
            self._cleanup_tasks[colony_id] = task

            def finished(done):
                if done.cancelled() or done.exception() is not None:
                    self._cleanup_failures.add(colony_id)
            task.add_done_callback(finished)
        done, _ = await asyncio.wait({task}, timeout=CLEANUP_TIMEOUT_SECONDS)
        if not done:
            raise TimeoutError("Resource cleanup is still pending")
        if task.cancelled():
            raise RuntimeError("Resource cleanup was interrupted")
        task.result()

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
            await self._cleanup(colony_id)
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
        if colony.lifecycle_status not in states:
            raise ColonyLifecycleError("invalid_state", conflict=True)
        return colony

    def _check_pending_failure(self, colony_id: str) -> None:
        if colony_id in self._pending_failures:
            raise ColonyLifecycleError(self._pending_failures[colony_id])

    async def stop_colony(self, colony_id: str) -> None:
        await self._control(lambda: self._stop_colony(colony_id))

    async def _stop_colony(self, colony_id: str) -> None:
        async with self._locks.setdefault(colony_id, asyncio.Lock()):
            colony = self._require_state(colony_id, {"running", "paused", "risk_halted", "stopped"})
            if colony.lifecycle_status == "stopped":
                return
            try:
                # Finish the current event batch before cancelling the sleeping loop.
                # If it cannot quiesce, failure retains the uncertain ledger state.
                await asyncio.wait_for(colony.quiesce(), timeout=QUIESCE_TIMEOUT_SECONDS)
                self._check_pending_failure(colony_id)
                await self._cancel_run(colony_id)
                await self._cleanup(colony_id, stop=True)
                await self._transition(colony_id, "stopped")
            except Exception as error:
                code = _failure_code(error, "cleanup_failed")
                await self._fail(colony_id, code)
                raise ColonyLifecycleError(code) from None

    async def pause_colony(self, colony_id: str) -> None:
        await self._control(lambda: self._pause_colony(colony_id))

    async def _pause_colony(self, colony_id: str) -> None:
        async with self._locks.setdefault(colony_id, asyncio.Lock()):
            colony = self._require_state(colony_id, {"running"})
            colony.pause()
            try:
                await asyncio.wait_for(colony.wait_for_tick(), timeout=QUIESCE_TIMEOUT_SECONDS)
                self._check_pending_failure(colony_id)
                # The in-flight tick may have tripped while this control waited.
                # Keep its risk loop active rather than overwriting the durable halt.
                if colony.lifecycle_status != "running":
                    if colony.lifecycle_status == "risk_halted":
                        colony.resume()
                    raise ColonyLifecycleError("invalid_state", conflict=True)
                await self._transition(colony_id, "paused")
            except Exception as error:
                if isinstance(error, ColonyLifecycleError) and error.conflict:
                    raise
                code = _failure_code(error, "execution_failed")
                await self._fail(colony_id, code)
                raise ColonyLifecycleError(code) from None

    async def recover_colony(self, colony_id: str, trip_id: str) -> None:
        await self._control(lambda: self._recover_colony(colony_id, trip_id))

    async def _recover_colony(self, colony_id: str, trip_id: str) -> None:
        async with self._locks.setdefault(colony_id, asyncio.Lock()):
            colony = self._colonies[colony_id]
            if colony.lifecycle_status != "risk_halted":
                raise ColonyLifecycleError("risk_not_halted", conflict=True)
            try:
                self._check_pending_failure(colony_id)
                # The controller owns tick serialization, valuation validation,
                # durable acknowledgement and publication of this transition.
                await asyncio.wait_for(colony.recover_circuit_breaker(trip_id),
                                       timeout=QUIESCE_TIMEOUT_SECONDS)
                if self._draining:
                    raise ColonyLifecycleError("worker_draining")
            except RiskRecoveryError as error:
                raise ColonyLifecycleError(error.code, conflict=True) from None
            except Exception as error:
                code = _failure_code(error, "execution_failed")
                await self._fail(colony_id, code)
                raise ColonyLifecycleError(code) from None

    async def resume_colony(self, colony_id: str) -> None:
        await self._control(lambda: self._resume_colony(colony_id))

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
                if self._draining:
                    raise ColonyLifecycleError("worker_draining")
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
        return sum(colony.lifecycle_status in {"starting", "running", "paused", "risk_halted"}
                   for colony in self._colonies.values())

    async def _drain_colony(self, colony_id: str) -> None:
        # An accepted control may own this lock while its write drains. Examine
        # lifecycle only after that operation finishes, then stop if needed.
        async with self._locks.setdefault(colony_id, asyncio.Lock()):
            active = self._colonies[colony_id].lifecycle_status in {"running", "paused", "risk_halted"}
        if active:
            try:
                await self._stop_colony(colony_id)
            except ColonyLifecycleError:
                pass  # Its failure/cleanup evidence remains owned and visible.

    async def _drain(self) -> None:
        starts = list(self._start_tasks.values())
        starting_ids = set(self._start_tasks)
        for task in starts:
            if not task.done() and not task.cancelling():
                task.cancel()
        for cid in self._colonies:
            if cid not in starting_ids:
                self._drain_tasks.add(asyncio.create_task(self._drain_colony(cid)))
        results = await asyncio.gather(*starts, *self._control_tasks, *self._drain_tasks,
                                       return_exceptions=True)
        self._drain_failed = any(isinstance(result, Exception) and not isinstance(
            result, ColonyLifecycleError) for result in results)
        # Supervisors may already be recording a failed tick; cleanup can finish
        # after its local deadline. Keep both owned through the global drain.
        tasks = {*self._tasks.values(), *self._cleanup_tasks.values()}
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            self._drain_failed |= any(isinstance(result, BaseException) for result in results)

    def _drain_report(self) -> dict:
        tasks = {*self._start_tasks.values(), *self._tasks.values(), *self._control_tasks,
                 *self._cleanup_tasks.values(), *self._drain_tasks}
        pending = sum(not task.done() for task in tasks)
        unsaved = any(not self._colonies[cid].state_persisted for cid in self._persist)
        incomplete = (pending or self._drain_failed or self._cleanup_failures or unsaved or
                      self._shutdown_task is None or not self._shutdown_task.done())
        return {"status": "incomplete" if incomplete else "complete", "pending_operations": pending}

    async def shutdown(self) -> dict:
        """Close admission immediately; keep one bounded, independently owned drain.

        A timed-out or cancelled caller never cancels the drain or releases an
        in-flight write lock. Repeated calls observe the original deadline.
        """
        if self._shutdown_task is None:
            self._draining = True
            for colony in self._colonies.values():
                if isinstance(colony, GenesisController):
                    colony.begin_drain()
            timeout = SHUTDOWN_TIMEOUT_SECONDS
            if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0:
                raise ValueError("Invalid shutdown deadline")
            self._shutdown_deadline = asyncio.get_running_loop().time() + timeout
            self._shutdown_task = asyncio.create_task(self._drain())
        remaining = max(0, self._shutdown_deadline - asyncio.get_running_loop().time())
        await asyncio.wait({self._shutdown_task}, timeout=remaining)
        if self._shutdown_task.done() and (self._shutdown_task.cancelled() or self._shutdown_task.exception()):
            self._drain_failed = True
        return self._drain_report()

    @staticmethod
    def _create_feed(mode: str) -> MarketFeed:
        if mode == "simulation":
            from ..market.sim_feed import SimulationFeed
            return SimulationFeed()
        if mode == "paper":
            from ..market.jupiter_feed import JupiterFeed
            return JupiterFeed()
        raise ValueError("Only simulation and paper modes are supported")
