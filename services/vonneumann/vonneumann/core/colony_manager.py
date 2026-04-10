"""Colony Manager — manages multiple concurrent GenesisController instances."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional, Callable, Awaitable

from .colony_config import ColonyConfig
from .genesis import GenesisController
from .types import ProbeEvent
from ..market.feed import MarketFeed

logger = logging.getLogger(__name__)


class ColonyManager:
    """Manages multiple concurrent GenesisController instances."""

    def __init__(self) -> None:
        self._colonies: dict[str, GenesisController] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def create_colony(
        self,
        colony_id: str,
        user_id: str,
        mode: str,
        strategy_name: str,
        colony_config: ColonyConfig,
        on_event: Callable[[ProbeEvent], Awaitable[None]],
        *,
        max_probes: int = 50,
        gen0_count: int = 10,
        seed_capital: float = 100,
        max_capital: float = 10_000,
        tick_interval_ms: int = 1000,
        mutation_rate: float = 0.20,
    ) -> str:
        """Create and start a new colony. Returns colony_id."""
        from .strategies import get_strategy

        strategy = get_strategy(strategy_name)
        market_feed = self._create_feed(mode)

        colony_config.mutation_rate = mutation_rate

        genesis = GenesisController(
            market_feed=market_feed,
            strategy=strategy,
            colony_id=colony_id,
            user_id=user_id,
            mode=mode,
            max_probes=max_probes,
            gen0_count=gen0_count,
            seed_capital=seed_capital,
            max_capital=max_capital,
            tick_interval_ms=tick_interval_ms,
            mutation_rate=mutation_rate,
            colony_config=colony_config,
            on_event=on_event,
        )

        self._colonies[colony_id] = genesis
        task = asyncio.create_task(genesis.start())
        self._tasks[colony_id] = task
        logger.info(f"[ColonyManager] Created colony {colony_id[:8]} strategy={strategy_name}")
        return colony_id

    async def stop_colony(self, colony_id: str) -> None:
        genesis = self._colonies.get(colony_id)
        if genesis:
            await genesis.stop()
        task = self._tasks.pop(colony_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._colonies.pop(colony_id, None)
        logger.info(f"[ColonyManager] Stopped colony {colony_id[:8]}")

    async def pause_colony(self, colony_id: str) -> None:
        genesis = self._colonies.get(colony_id)
        if genesis:
            genesis.pause()

    async def resume_colony(self, colony_id: str) -> None:
        genesis = self._colonies.get(colony_id)
        if genesis:
            genesis.resume()

    def get_colony(self, colony_id: str) -> Optional[GenesisController]:
        return self._colonies.get(colony_id)

    def list_colonies(self) -> list[dict]:
        """Return status of all active colonies."""
        return [
            {**genesis.status(), "colony_id": cid}
            for cid, genesis in self._colonies.items()
        ]

    def latest_colony_id(self) -> Optional[str]:
        """Return the most recently created colony's ID, or None."""
        if self._colonies:
            return list(self._colonies.keys())[-1]
        return None

    def active_count(self) -> int:
        return len(self._colonies)

    async def shutdown(self) -> None:
        """Stop all colonies. Called on server shutdown."""
        for colony_id in list(self._colonies.keys()):
            await self.stop_colony(colony_id)

    @staticmethod
    def _create_feed(mode: str) -> MarketFeed:
        if mode == "simulation":
            from ..market.sim_feed import SimulationFeed
            return SimulationFeed()
        else:
            from ..market.jupiter_feed import JupiterFeed
            return JupiterFeed()
