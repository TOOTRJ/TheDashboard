"""
FastAPI application -- REST endpoints + WebSocket for the Von Neumann system.

Start with: uvicorn vonneumann.server.app:app --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import VN_API_KEY, VN_WS_PORT
from ..core.colony_config import ColonyConfig, GeneOverride, PRESET_CONFIGS
from ..core.gene_registry import GENE_REGISTRY
from ..core.genesis import GenesisController
from ..core.genome import AVAILABLE_ASSETS
from ..core.types import ProbeEvent
from ..db.repository import VonNeumannRepository, EventPersister
from ..market.sim_feed import SimulationFeed
from .websocket import ws_manager

logger = logging.getLogger(__name__)

# Global state
_genesis: Optional[GenesisController] = None
_genesis_task: Optional[asyncio.Task] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("[Server] Von Neumann service starting")
    yield
    # Shutdown
    global _genesis, _genesis_task
    if _genesis:
        await _genesis.stop()
    if _genesis_task:
        _genesis_task.cancel()
    logger.info("[Server] Von Neumann service stopped")


app = FastAPI(title="Von Neumann Trading Probes", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth ─────────────────────────────────────────────────────────────────────


def verify_api_key(x_api_key: str = Header(alias="x-api-key", default="")) -> str:
    if x_api_key != VN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ── Event handler (bridges Genesis -> WS + DB) ──────────────────────────────


async def _on_event(event: ProbeEvent) -> None:
    """Dual-write: persist to DB + broadcast to WS clients."""
    # Broadcast to WebSocket clients
    await ws_manager.broadcast(event.to_ws_message())


# ── Models ───────────────────────────────────────────────────────────────────


class GeneOverrideModel(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    default: Optional[float] = None
    fixed: Optional[float] = None


class ColonyConfigModel(BaseModel):
    gene_overrides: Optional[dict[str, GeneOverrideModel]] = None
    enabled_genes: Optional[list[str]] = None
    available_assets: Optional[list[str]] = None
    max_lifespan_ticks: Optional[int] = None
    reproduction_interval: int = 100


class StartRequest(BaseModel):
    user_id: str
    mode: str = "simulation"
    preset: Optional[str] = None  # "default", "rsi_focus", etc.
    colony_config: Optional[ColonyConfigModel] = None
    max_probes: int = 50
    max_capital: float = 10_000.0
    seed_capital: float = 100.0
    gen0_count: int = 10
    tick_interval_ms: int = 1000
    mutation_rate: float = 0.20


def _build_colony_config(req: StartRequest) -> ColonyConfig:
    """Convert API request to internal ColonyConfig."""
    # Start with preset if specified
    if req.preset and req.preset in PRESET_CONFIGS:
        config = ColonyConfig.from_dict(PRESET_CONFIGS[req.preset].to_dict())
    else:
        config = ColonyConfig()

    # Overlay explicit colony_config on top of preset
    if req.colony_config:
        if req.colony_config.gene_overrides:
            for name, override in req.colony_config.gene_overrides.items():
                config.gene_overrides[name] = GeneOverride(
                    min=override.min, max=override.max,
                    default=override.default, fixed=override.fixed,
                )
        if req.colony_config.enabled_genes is not None:
            config.enabled_genes = req.colony_config.enabled_genes
        if req.colony_config.available_assets is not None:
            config.available_assets = req.colony_config.available_assets
        if req.colony_config.max_lifespan_ticks is not None:
            config.max_lifespan_ticks = req.colony_config.max_lifespan_ticks
        config.reproduction_interval = req.colony_config.reproduction_interval

    return config


# ── REST Endpoints ───────────────────────────────────────────────────────────


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "ws_clients": ws_manager.client_count}


@app.get("/api/v1/status")
async def get_status(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    if not _genesis:
        return {"status": "stopped", "message": "No simulation running"}
    return _genesis.status()


@app.post("/api/v1/simulation/start")
async def start_simulation(
    req: StartRequest,
    x_api_key: str = Header(alias="x-api-key", default=""),
):
    verify_api_key(x_api_key)
    global _genesis, _genesis_task

    if _genesis and _genesis._running:
        raise HTTPException(status_code=409, detail="Simulation already running")

    # Create the right market feed based on mode
    mode = req.mode if req.mode in ("simulation", "paper") else "simulation"
    if mode == "paper":
        from ..market.jupiter_feed import JupiterFeed
        feed = JupiterFeed()
        logger.info("[Server] Paper trading mode — using live Jupiter prices")
    else:
        feed = SimulationFeed()
        logger.info("[Server] Simulation mode — using synthetic prices")

    colony_config = _build_colony_config(req)

    _genesis = GenesisController(
        market_feed=feed,
        user_id=req.user_id,
        mode=mode,
        max_probes=req.max_probes,
        max_capital=req.max_capital,
        seed_capital=req.seed_capital,
        gen0_count=req.gen0_count,
        tick_interval_ms=req.tick_interval_ms,
        mutation_rate=req.mutation_rate,
        colony_config=colony_config,
    )

    # Set up DB persistence with run_id from Genesis
    repo = VonNeumannRepository(req.user_id, run_id=_genesis.run_id)
    persister = EventPersister(repo, mode=mode)

    async def dual_handler(event: ProbeEvent) -> None:
        await persister.handle(event)
        await _on_event(event)

    _genesis._on_event = dual_handler

    _genesis_task = asyncio.create_task(_genesis.start())
    return {"status": "started", "run_id": _genesis.run_id, "config": req.model_dump()}


@app.post("/api/v1/simulation/stop")
async def stop_simulation(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    if not _genesis:
        raise HTTPException(status_code=404, detail="No simulation running")
    await _genesis.stop()
    return {"status": "stopped"}


@app.post("/api/v1/simulation/pause")
async def pause_simulation(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    if not _genesis:
        raise HTTPException(status_code=404, detail="No simulation running")
    _genesis.pause()
    return {"status": "paused"}


@app.post("/api/v1/simulation/resume")
async def resume_simulation(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    if not _genesis:
        raise HTTPException(status_code=404, detail="No simulation running")
    _genesis.resume()
    return {"status": "resumed"}


@app.get("/api/v1/gene-registry")
async def get_gene_registry():
    """Returns the full gene registry + available assets + presets for the config UI."""
    return {
        "genes": GENE_REGISTRY.to_json_schema(),
        "available_assets": AVAILABLE_ASSETS,
        "presets": {
            name: cfg.to_dict() for name, cfg in PRESET_CONFIGS.items()
        },
    }


# ── WebSocket ────────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type")
                if msg_type == "command":
                    action = msg.get("data", {}).get("action")
                    if action == "stop" and _genesis:
                        await _genesis.stop()
                    elif action == "pause" and _genesis:
                        _genesis.pause()
                    elif action == "resume" and _genesis:
                        _genesis.resume()
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
