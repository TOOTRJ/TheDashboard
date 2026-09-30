"""
FastAPI application -- REST endpoints + WebSocket for the Von Neumann system.

Start with: uvicorn vonneumann.server.app:app --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..config import VN_ALLOWED_ORIGINS
from ..core.colony_config import PRESET_CONFIGS
from ..core.colony_manager import ColonyManager, ColonyLifecycleError, complete_operation
from ..core.gene_registry import GENE_REGISTRY
from ..core.genome import AVAILABLE_ASSETS
from ..core.strategies import list_strategies
from ..core.types import ProbeEvent, EventType
from ..db.repository import VonNeumannRepository, EventPersister, PersistenceError
from .auth import VerifiedUser, require_user, verify_access_token
from .websocket import ws_manager
from .models import StartRequest, build_colony_config as _build_colony_config

logger = logging.getLogger(__name__)

# Colony manager (replaces the old _genesis singleton)
colony_manager = ColonyManager()
WS_AUTH_TIMEOUT_SECONDS = 5.0
WS_AUTH_MAX_BYTES = 16_384
WS_SEND_TIMEOUT_SECONDS = 5.0
WS_MAX_WAIT_SECONDS = 60.0


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
    allow_origins=list(VN_ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Auth ─────────────────────────────────────────────────────────────────────


def _owned_colony(colony_id: str, user: VerifiedUser):
    colony = colony_manager.get_owned_colony(colony_id, user.id)
    if colony is None:
        raise HTTPException(status_code=404, detail="Colony not found")
    return colony


# ── Event handler factory ────────────────────────────────────────────────────


def _make_dual_handler(
    colony_id: str, user_id: str, persister: EventPersister
):
    """Create an event handler that persists to DB and broadcasts to WS with colony_id."""
    async def handler(event: ProbeEvent) -> None:
        await persister.handle(event)
        msg = event.to_ws_message()
        msg["colony_id"] = colony_id
        await ws_manager.broadcast_to_user(user_id, msg)
    return handler


# ── Models ───────────────────────────────────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def invalid_request(_request, error: RequestValidationError):
    # Do not reflect arbitrary body values, unknown field names, or exception ctx.
    known_fields = set(StartRequest.model_fields) | {
        "body", "colony_config", "gene_overrides", "enabled_genes", "available_assets",
        "max_lifespan_ticks", "reproduction_interval", "min", "max", "default", "fixed",
    } | set(GENE_REGISTRY.numeric_gene_names())
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": [item if isinstance(item, int) or item in known_fields else "unknown_field"
                 for item in issue["loc"]], "type": issue["type"], "msg": issue["msg"]}
        for issue in error.errors()[:100]
    ]})


def _lifecycle_http_error(error: ColonyLifecycleError, colony_id: str) -> HTTPException:
    colony = colony_manager.get_colony(colony_id)
    return HTTPException(status_code=409 if error.conflict else 503, detail={
        "code": error.code, "message": str(error), "colony_id": colony_id,
        "state_persisted": bool(colony and colony.status().get("state_persisted")),
    })


async def _start_colony(req: StartRequest, user: VerifiedUser) -> dict:
    """Shared logic for starting a colony (used by both new and compat endpoints)."""
    colony_id = str(uuid.uuid4())
    mode = req.mode
    colony_config = _build_colony_config(req)
    resolved_colony_config = colony_config.to_dict()
    resolved_colony_config.pop("mutation_rate", None)  # The request exposes this once, at top level.
    resolved_request = {**req.model_dump(), "mutation_rate": colony_config.mutation_rate,
                        "colony_config": resolved_colony_config}

    try:
        repo = VonNeumannRepository(user.id, run_id=colony_id)
    except PersistenceError:
        raise HTTPException(status_code=503, detail={
            "code": "persistence_failed", "message": "The colony could not be saved; it was not started.",
            "colony_id": colony_id, "state_persisted": False,
        }) from None

    persister = EventPersister(repo, mode=mode)
    handler = _make_dual_handler(colony_id, user.id, persister)

    async def persist_status(status: dict) -> None:
        await repo.execute_async("update_colony_status", colony_id, status["status"], details={
            name: status.get(name) for name in ("failure_code", "failure_message", "state_persisted",
                                               "open_positions", "requires_reconciliation", "valuation_available")
        })

    async def publish_status(status: dict) -> None:
        # Failure notification remains possible when the database itself is down.
        message = ProbeEvent(event_type=EventType.SIMULATION_STATUS,
                             probe_id="genesis", data=status).to_ws_message()
        message["colony_id"] = colony_id
        await ws_manager.broadcast_to_user(user.id, message)

    # Retain the insert independently of a disconnected request. If cancellation
    # arrives after it commits, record failed rather than leaving an orphan start.
    insert = asyncio.create_task(repo.execute_async(
        "insert_colony", colony_id, req.strategy, resolved_request, mode, status="starting"))
    try:
        await complete_operation(insert)
    except asyncio.CancelledError:
        async def persist_cancelled(status: dict) -> None:
            if not insert.cancelled() and insert.exception() is None:
                await persist_status(status)
            else:
                # An unacknowledged insert may still have committed. Preserve its
                # original config if attempting the terminal status finds a row.
                await repo.execute_async("update_colony_status", colony_id, "failed")
        await complete_operation(colony_manager.record_start_failure(
            colony_id, user.id, mode, req.strategy, persist_cancelled, publish_status))
        raise
    except PersistenceError:
        raise HTTPException(status_code=503, detail={
            "code": "persistence_failed", "message": "The colony could not be saved; it was not started.",
            "colony_id": colony_id, "state_persisted": False,
        }) from None

    try:
        await colony_manager.create_colony(
            colony_id=colony_id, user_id=user.id, mode=mode, strategy_name=req.strategy,
            colony_config=colony_config, on_event=handler,
            max_probes=req.max_probes, gen0_count=req.gen0_count,
            seed_capital=req.seed_capital, max_capital=req.max_capital,
            tick_interval_ms=req.tick_interval_ms, mutation_rate=colony_config.mutation_rate,
            persist_status=persist_status, on_status=publish_status,
        )
    except ColonyLifecycleError as error:
        raise _lifecycle_http_error(error, colony_id) from None

    return {"status": "started", "run_id": colony_id, "colony_id": colony_id,
            "strategy": req.strategy, "config": resolved_request}


# ── REST Endpoints ───────────────────────────────────────────────────────────


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1/status")
async def get_status(user: VerifiedUser = Depends(require_user)):
    cid = colony_manager.latest_colony_id(user.id)
    if not cid:
        return {"status": "stopped", "message": "No simulation running"}
    return _owned_colony(cid, user).status()


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
    user: VerifiedUser = Depends(require_user),
):
    result = await _start_colony(req, user)
    return result


@app.get("/api/v1/colonies/")
async def list_colonies(user: VerifiedUser = Depends(require_user)):
    return colony_manager.list_colonies(user.id)


@app.get("/api/v1/colonies/{colony_id}")
async def get_colony(colony_id: str, user: VerifiedUser = Depends(require_user)):
    return _owned_colony(colony_id, user).status()


@app.post("/api/v1/colonies/{colony_id}/stop")
async def stop_colony(colony_id: str, user: VerifiedUser = Depends(require_user)):
    _owned_colony(colony_id, user)
    try:
        await colony_manager.stop_colony(colony_id)
    except ColonyLifecycleError as error:
        raise _lifecycle_http_error(error, colony_id) from None
    return {"status": "stopped", "colony_id": colony_id}


@app.post("/api/v1/colonies/{colony_id}/pause")
async def pause_colony(colony_id: str, user: VerifiedUser = Depends(require_user)):
    _owned_colony(colony_id, user)
    try:
        await colony_manager.pause_colony(colony_id)
    except ColonyLifecycleError as error:
        raise _lifecycle_http_error(error, colony_id) from None
    return {"status": "paused", "colony_id": colony_id}


@app.post("/api/v1/colonies/{colony_id}/resume")
async def resume_colony(colony_id: str, user: VerifiedUser = Depends(require_user)):
    _owned_colony(colony_id, user)
    try:
        await colony_manager.resume_colony(colony_id)
    except ColonyLifecycleError as error:
        raise _lifecycle_http_error(error, colony_id) from None
    return {"status": "resumed", "colony_id": colony_id}


# ── Backward-compatible simulation endpoints ────────────────────────────────


@app.post("/api/v1/simulation/start")
async def start_simulation(
    req: StartRequest,
    user: VerifiedUser = Depends(require_user),
):
    result = await _start_colony(req, user)
    return result


@app.post("/api/v1/simulation/stop")
async def stop_simulation(user: VerifiedUser = Depends(require_user)):
    raise HTTPException(status_code=410, detail="Use the colony-specific stop endpoint")


@app.post("/api/v1/simulation/pause")
async def pause_simulation(user: VerifiedUser = Depends(require_user)):
    raise HTTPException(status_code=410, detail="Use the colony-specific pause endpoint")


@app.post("/api/v1/simulation/resume")
async def resume_simulation(user: VerifiedUser = Depends(require_user)):
    raise HTTPException(status_code=410, detail="Use the colony-specific resume endpoint")


# ── WebSocket ────────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if websocket.headers.get("origin") not in VN_ALLOWED_ORIGINS:
        await _close_ws(websocket, 4403)
        return

    await websocket.accept()
    try:
        raw = await asyncio.wait_for(
            _receive_ws_text(websocket), timeout=WS_AUTH_TIMEOUT_SECONDS
        )
        msg = json.loads(raw, object_pairs_hook=_unique_json_object)
        if (
            not isinstance(msg, dict)
            or set(msg) != {"type", "access_token"}
            or msg.get("type") != "auth"
            or not isinstance(msg.get("access_token"), str)
        ):
            raise ValueError("Invalid authentication frame")
        user = await verify_access_token(msg["access_token"])
        if user.expires_at <= time.time():
            await _close_ws(websocket, 4401)
            return
        await asyncio.wait_for(websocket.send_json({
            "type": "auth_ok",
            "data": {"user_id": user.id, "expires_at": user.expires_at},
        }), timeout=WS_SEND_TIMEOUT_SECONDS)
        # No application event may precede authentication and its acknowledgement.
        ws_manager.register(websocket, user)
        while True:
            remaining = user.expires_at - time.time()
            if remaining <= 0:
                await _close_ws(websocket, 4401)
                return
            try:
                await asyncio.wait_for(
                    _receive_ws_text(websocket), timeout=min(remaining, WS_MAX_WAIT_SECONDS)
                )
            except asyncio.TimeoutError:
                continue
            # Commands deliberately have no path to the colony manager.
            await asyncio.wait_for(websocket.send_json({
                "type": "error",
                "data": {"code": "read_only", "message": "Use authenticated HTTP colony controls"},
            }), timeout=WS_SEND_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        await _close_ws(websocket, 4408)
    except HTTPException as exc:
        await _close_ws(websocket, 4401 if exc.status_code == 401 else 1013)
    except (ValueError, TypeError):
        await _close_ws(websocket, 4400)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Avoid logging authentication payloads or raw transport exceptions.
        await _close_ws(websocket, 1011)
    finally:
        ws_manager.disconnect(websocket)


async def _close_ws(websocket: WebSocket, code: int) -> None:
    try:
        await asyncio.wait_for(websocket.close(code=code), timeout=WS_SEND_TIMEOUT_SECONDS)
    except Exception:
        pass


async def _receive_ws_text(websocket: WebSocket) -> str:
    frame = await websocket.receive()
    if frame["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(frame.get("code", 1000))
    text = frame.get("text")
    if not isinstance(text, str) or len(text.encode("utf-8")) > WS_AUTH_MAX_BYTES:
        raise ValueError("Invalid WebSocket frame")
    return text


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate authentication field")
        result[key] = value
    return result
