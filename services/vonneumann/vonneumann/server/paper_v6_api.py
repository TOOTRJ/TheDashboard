"""Owner-authenticated HTTP boundary for the durable prospective paper runtime."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import inspect
import json
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import VerifiedUser, require_user

ORIGIN = "https://the-dashboard-chi.vercel.app"
MAX_RESPONSE_BYTES = 262144


async def _result(value):
    return await value if inspect.isawaitable(value) else value


def _response(value, *, owner, status=200):
    if (type(value) is not dict or value.get("version") != 6
            or value.get("owner_id") != owner):
        raise HTTPException(503, "Paper service response unavailable")
    try:
        encoded = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise HTTPException(503, "Paper service response unavailable") from None
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise HTTPException(503, "Paper service response unavailable")
    return JSONResponse(value, status_code=status)


async def _request_id(request):
    if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
        raise HTTPException(415, "JSON required")
    body = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 256:
                    raise HTTPException(413, "Control too large")
    except TimeoutError:
        raise HTTPException(408, "Control body timed out") from None

    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError()
            value[key] = item
        return value

    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=unique)
        if type(value) is not dict or value.keys() != {"request_id"}:
            raise ValueError()
        request_id = value["request_id"]
        if type(request_id) is not str or str(UUID(request_id)) != request_id:
            raise ValueError()
        return request_id
    except (TypeError, ValueError, UnicodeError):
        raise HTTPException(422, "Invalid control") from None


def create_app(service=None, *, verify=require_user):
    @asynccontextmanager
    async def lifespan(app):
        if service is not None and hasattr(service, "initialize"):
            await _result(service.initialize())
        yield
        if service is not None:
            await _result(service.close())

    app = FastAPI(title="Dashboard prospective paper worker", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN],
                       allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"],
                       allow_credentials=False, max_age=600)

    @app.middleware("http")
    async def scope(request, call_next):
        origin = request.headers.get("origin")
        if origin is not None and origin != ORIGIN:
            return JSONResponse({"detail": "Origin unavailable"}, status_code=403,
                                headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    async def health():
        return {"alive": True, "version": "paper-service-v6"}

    def selected(user):
        if service is None:
            raise HTTPException(503, "Paper service is closed")
        if user.id != service.owner_id:
            raise HTTPException(404, "Run unavailable")
        return service

    async def invoke(user, name, *args):
        pilot = selected(user)
        try:
            value = await _result(getattr(pilot, name)(user.id, *args))
        except (ValueError, RuntimeError):
            raise HTTPException(409, "Original control unavailable; inspect status") from None
        except Exception:
            raise HTTPException(503, "Paper service response unavailable") from None
        return _response(value, owner=user.id, status=202 if name in {"start", "stop"} else 200)

    @app.get("/v6/status")
    async def status(user: VerifiedUser = Depends(verify)):
        return await invoke(user, "status")

    @app.get("/v6/history")
    async def history(request: Request, user: VerifiedUser = Depends(verify)):
        selected(user)
        params = request.query_params
        try:
            if (set(params) - {"after_sequence", "limit"}
                    or any(len(params.getlist(key)) != 1 for key in params)):
                raise ValueError()
            after = params.get("after_sequence", "0")
            count = params.get("limit", "25")
            if (str(int(after)) != after or str(int(count)) != count
                    or not 0 <= int(after) <= 2**53 - 1 or not 1 <= int(count) <= 100):
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "Invalid history page") from None
        return await invoke(user, "history", int(after), int(count))

    @app.post("/v6/start")
    async def start(request: Request, user: VerifiedUser = Depends(verify)):
        selected(user)
        return await invoke(user, "start", await _request_id(request))

    @app.post("/v6/stop")
    async def stop(request: Request, user: VerifiedUser = Depends(verify)):
        selected(user)
        return await invoke(user, "stop", await _request_id(request))

    return app


app = create_app()
