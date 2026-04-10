"""
FastAPI application -- REST endpoints + WebSocket for the Von Neumann system.

Start with: uvicorn vonneumann.server.app:app --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..config import VN_API_KEY
from ..core.colony_config import ColonyConfig, GeneOverride, PRESET_CONFIGS
from ..core.colony_manager import ColonyManager
from ..core.gene_registry import GENE_REGISTRY
from ..core.genome import AVAILABLE_ASSETS
from ..core.strategies import list_strategies
from ..core.types import ProbeEvent
from ..db.repository import VonNeumannRepository, EventPersister
from .websocket import ws_manager

logger = logging.getLogger(__name__)

# Colony manager (replaces the old _genesis singleton)
colony_manager = ColonyManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("[Server] Von Neumann service starting")
    yield
    await colony_manager.shutdown()
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


# ── Event handler factory ────────────────────────────────────────────────────


def _make_dual_handler(
    colony_id: str, persister: EventPersister
):
    """Create an event handler that persists to DB and broadcasts to WS with colony_id."""
    async def handler(event: ProbeEvent) -> None:
        await persister.handle(event)
        msg = event.to_ws_message()
        msg["colony_id"] = colony_id
        await ws_manager.broadcast(msg)
    return handler


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
    reproduction_interval: Optional[int] = None


class StartRequest(BaseModel):
    user_id: str
    mode: str = "simulation"
    strategy: str = "genetic_algorithm"
    preset: Optional[str] = None
    colony_config: Optional[ColonyConfigModel] = None
    max_probes: int = 50
    max_capital: float = 10_000.0
    seed_capital: float = 100.0
    gen0_count: int = 10
    tick_interval_ms: int = 1000
    mutation_rate: float = 0.20


def _build_colony_config(req: StartRequest) -> ColonyConfig:
    """Convert API request to internal ColonyConfig."""
    if req.preset and req.preset in PRESET_CONFIGS:
        config = ColonyConfig.from_dict(PRESET_CONFIGS[req.preset].to_dict())
    else:
        config = ColonyConfig()

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
        if req.colony_config.reproduction_interval is not None:
            config.reproduction_interval = req.colony_config.reproduction_interval

    return config


async def _start_colony(req: StartRequest) -> dict:
    """Shared logic for starting a colony (used by both new and compat endpoints)."""
    colony_id = str(uuid.uuid4())
    mode = req.mode if req.mode in ("simulation", "paper") else "simulation"
    colony_config = _build_colony_config(req)

    repo = VonNeumannRepository(req.user_id, run_id=colony_id)
    persister = EventPersister(repo, mode=mode)
    handler = _make_dual_handler(colony_id, persister)

    await colony_manager.create_colony(
        colony_id=colony_id,
        user_id=req.user_id,
        mode=mode,
        strategy_name=req.strategy,
        colony_config=colony_config,
        on_event=handler,
        max_probes=req.max_probes,
        gen0_count=req.gen0_count,
        seed_capital=req.seed_capital,
        max_capital=req.max_capital,
        tick_interval_ms=req.tick_interval_ms,
        mutation_rate=req.mutation_rate,
    )

    repo.insert_colony(colony_id, req.strategy, req.model_dump(), mode)

    return {
        "status": "started",
        "run_id": colony_id,
        "colony_id": colony_id,
        "strategy": req.strategy,
        "config": req.model_dump(),
    }


# ── REST Endpoints ───────────────────────────────────────────────────────────


@app.get("/api/v1/health")
async def health():
    return {
        "status": "ok",
        "ws_clients": ws_manager.client_count,
        "active_colonies": colony_manager.active_count(),
    }


@app.get("/api/v1/status")
async def get_status(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    cid = colony_manager.latest_colony_id()
    if not cid:
        return {"status": "stopped", "message": "No simulation running"}
    colony = colony_manager.get_colony(cid)
    return colony.status() if colony else {"status": "stopped"}


@app.get("/api/v1/strategies")
async def get_strategies():
    """List all available evolution strategies."""
    return list_strategies()


@app.get("/api/v1/gene-registry")
async def get_gene_registry():
    """Returns the full gene registry + available assets + presets for the config UI."""
    return {
        "genes": GENE_REGISTRY.to_json_schema(),
        "available_assets": AVAILABLE_ASSETS,
        "presets": {name: cfg.to_dict() for name, cfg in PRESET_CONFIGS.items()},
    }


# ── Colony endpoints (new) ──────────────────────────────────────────────────


@app.post("/api/v1/colonies/")
async def create_colony(
    req: StartRequest,
    x_api_key: str = Header(alias="x-api-key", default=""),
):
    verify_api_key(x_api_key)
    result = await _start_colony(req)
    return result


@app.get("/api/v1/colonies/")
async def list_colonies(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    return colony_manager.list_colonies()


@app.get("/api/v1/colonies/{colony_id}")
async def get_colony(colony_id: str, x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    colony = colony_manager.get_colony(colony_id)
    if not colony:
        raise HTTPException(status_code=404, detail="Colony not found")
    return colony.status()


@app.post("/api/v1/colonies/{colony_id}/stop")
async def stop_colony(colony_id: str, x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    colony = colony_manager.get_colony(colony_id)
    if not colony:
        raise HTTPException(status_code=404, detail="Colony not found")
    await colony_manager.stop_colony(colony_id)
    return {"status": "stopped", "colony_id": colony_id}


@app.post("/api/v1/colonies/{colony_id}/pause")
async def pause_colony(colony_id: str, x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    colony = colony_manager.get_colony(colony_id)
    if not colony:
        raise HTTPException(status_code=404, detail="Colony not found")
    await colony_manager.pause_colony(colony_id)
    return {"status": "paused", "colony_id": colony_id}


@app.post("/api/v1/colonies/{colony_id}/resume")
async def resume_colony(colony_id: str, x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    colony = colony_manager.get_colony(colony_id)
    if not colony:
        raise HTTPException(status_code=404, detail="Colony not found")
    await colony_manager.resume_colony(colony_id)
    return {"status": "resumed", "colony_id": colony_id}


# ── Backward-compatible simulation endpoints ────────────────────────────────


@app.post("/api/v1/simulation/start")
async def start_simulation(
    req: StartRequest,
    x_api_key: str = Header(alias="x-api-key", default=""),
):
    verify_api_key(x_api_key)
    result = await _start_colony(req)
    return result


@app.post("/api/v1/simulation/stop")
async def stop_simulation(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    cid = colony_manager.latest_colony_id()
    if not cid:
        raise HTTPException(status_code=404, detail="No simulation running")
    await colony_manager.stop_colony(cid)
    return {"status": "stopped"}


@app.post("/api/v1/simulation/pause")
async def pause_simulation(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    cid = colony_manager.latest_colony_id()
    if not cid:
        raise HTTPException(status_code=404, detail="No simulation running")
    await colony_manager.pause_colony(cid)
    return {"status": "paused"}


@app.post("/api/v1/simulation/resume")
async def resume_simulation(x_api_key: str = Header(alias="x-api-key", default="")):
    verify_api_key(x_api_key)
    cid = colony_manager.latest_colony_id()
    if not cid:
        raise HTTPException(status_code=404, detail="No simulation running")
    await colony_manager.resume_colony(cid)
    return {"status": "resumed"}


# ── WebSocket ────────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "command":
                    action = msg.get("data", {}).get("action")
                    target = msg.get("data", {}).get("colony_id") or colony_manager.latest_colony_id()
                    if not target:
                        continue
                    if action == "stop":
                        await colony_manager.stop_colony(target)
                    elif action == "pause":
                        await colony_manager.pause_colony(target)
                    elif action == "resume":
                        await colony_manager.resume_colony(target)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
