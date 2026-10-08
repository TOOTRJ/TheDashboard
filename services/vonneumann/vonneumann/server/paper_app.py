"""Closed-by-default ASGI entrypoint for the authoritative bounded paper pilot."""
from __future__ import annotations
from contextlib import asynccontextmanager
import os
import asyncio
import json
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import require_user, VerifiedUser
from .paper_service import PaperService, ServiceRefused

ORIGIN = 'https://the-dashboard-chi.vercel.app'


def configured_service(environment=None):
    env = os.environ if environment is None else environment
    if env.get('VN_SERVICE_MODE', 'closed') == 'closed': return None
    if env.get('VN_SERVICE_MODE') != 'paper-v5':
        raise RuntimeError('invalid_service_selection')
    if (env.get('PYTHON_DOTENV_DISABLED') != '1'
        or env.get('VN_ENVIRONMENT') != 'production'
        or env.get('SUPABASE_URL') != 'https://fxpxsciltakyypunglzr.supabase.co'
        or env.get('VN_ALLOWED_ORIGINS') != ORIGIN
        or env.get('VN_JUPITER_SOLE_CONSUMER') != '1'
        or not env.get('SUPABASE_PUBLISHABLE_KEY', '').startswith('sb_publishable_')
        or any(env.get(k) for k in ('SUPABASE_SERVICE_ROLE_KEY',
            'SUPABASE_SECRET_KEY', 'RAILWAY_TOKEN', 'RAILWAY_API_TOKEN'))):
        raise RuntimeError('explicit_private_paper_configuration_required')
    from ..db.command_sql import DashboardCommandSQLPair, CommandSQLBounds
    from ..market.jupiter_feed import JupiterFeed
    try:
        interval = int(env['VN_PAPER_INTERVAL_SECONDS'])
        if interval < 5:
            raise ValueError('paper_cadence_budget_required')
        ca = env['VN_DATABASE_CA_PEM'].encode('ascii')
        owner, run = env['VN_PAPER_OWNER_ID'], env['VN_PAPER_RUN_ID']
        pair = DashboardCommandSQLPair(env['VN_ECONOMIC_LOGIN'],
            env['VN_ECONOMIC_PASSWORD'], env['VN_RELAY_LOGIN'],
            env['VN_RELAY_PASSWORD'], ca, owner, run,
            bounds=CommandSQLBounds(connect_seconds=1.0))
        provider_keys = tuple(env[k] for k in
            ('JUPITER_API_KEY', 'BIRDEYE_API_KEY', 'VN_SOLANA_RPC_URL'))
        if not all(provider_keys): raise ValueError()
        feed = JupiterFeed(api_key=provider_keys[0], birdeye_api_key=provider_keys[1],
                           rpc_url=provider_keys[2])
        return PaperService(pair, pair, feed, owner_id=owner, run_id=run,
            epoch_id=env['VN_PAPER_EPOCH_ID'], start_id=env['VN_PAPER_START_ID'],
            stop_id=env['VN_PAPER_STOP_ID'],
            interval=interval,
            max_ticks=int(env['VN_PAPER_MAX_TICKS']))
    except Exception:
        raise RuntimeError('invalid_private_paper_configuration') from None


def create_app(service=None, *, verify=require_user):
    @asynccontextmanager
    async def lifespan(app):
        yield
        if service is not None: await service.close()

    app = FastAPI(title='Dashboard paper worker', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN],
        allow_methods=['GET', 'POST'], allow_headers=['Authorization', 'Content-Type'],
        allow_credentials=False, max_age=600)

    @app.middleware('http')
    async def scope(request, call_next):
        origin = request.headers.get('origin')
        if origin is not None and origin != ORIGIN:
            return JSONResponse({'detail': 'Origin unavailable'}, status_code=403,
                                headers={'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/health')
    async def health(): return {'alive': True, 'version': 'paper-service-v1'}

    def selected(user):
        if service is None: raise HTTPException(503, 'Paper service is closed')
        if user.id != service.owner_id: raise HTTPException(404, 'Run unavailable')
        return service

    @app.get('/v5/status')
    async def status(user: VerifiedUser = Depends(verify)):
        result = selected(user).status(user.id)
        # Configuration/process readiness is not successful hosted acceptance.
        result['hosted_acceptance_required'] = True
        return result

    @app.get('/v5/controls')
    async def controls(user: VerifiedUser = Depends(verify)):
        pilot = selected(user)
        return {'version': 1, 'owner_id': pilot.owner_id, 'run_id': pilot.run_id,
                'start_id': pilot.start_id, 'stop_id': pilot.stop_id}

    @app.post('/v5/{action}')
    async def command(action: str, request: Request, user: VerifiedUser = Depends(verify)):
        pilot = selected(user)
        if action not in ('start', 'stop', 'settle'):
            raise HTTPException(404, 'Control unavailable')
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise HTTPException(415, 'JSON required')
        # Bound streamed bytes; Content-Length alone does not bound chunked input.
        body = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 256: raise HTTPException(413, 'Control too large')
        except TimeoutError:
            raise HTTPException(408, 'Control body timed out') from None
        try:
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result: raise ValueError()
                    result[key] = value
                return result
            data = json.loads(body, object_pairs_hook=pairs)
            if type(data) is not dict or data.keys() != {'request_id'}:
                raise ValueError()
            result = getattr(pilot, action)(user.id, data['request_id'])
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, 'Invalid control') from None
        except ServiceRefused:
            raise HTTPException(409, 'Original control unavailable; inspect status') from None
        return JSONResponse(result, status_code=202)
    return app


app = create_app(configured_service())
