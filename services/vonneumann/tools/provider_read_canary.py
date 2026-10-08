"""Explicit finite provider-only acceptance while the ordinary API stays closed.

Select this module deliberately as the Railway start command. It uses the actual
adapters and has no database connection, economic command or execution path.
One assessment is retained for this process; failures never trigger a retry.
"""
from __future__ import annotations

import asyncio
import json
import os
import resource
import time

import aiohttp
import uvicorn

from vonneumann.market.feed import MarketFeedError
from vonneumann.market.jupiter_feed import JupiterFeed
from vonneumann.server.paper_app import create_app

SAMPLES = 12
INTERVAL = 5
DEADLINE = 90
# Each sample owns one request, spaced at least five seconds apart. Reserving
# every future sample in the current window incorrectly assumes a burst. This
# observed-header reserve is only for a finite read probe, not account admission.
QUOTA_RESERVE = 2
QUOTA_OBSERVATION_MAX_AGE = 10


def configuration(env):
    if (env.get('VN_SERVICE_MODE') != 'closed'
            or env.get('PYTHON_DOTENV_DISABLED') != '1'
            or env.get('VN_ENVIRONMENT') != 'production'
            or env.get('SUPABASE_URL') != 'https://fxpxsciltakyypunglzr.supabase.co'
            or env.get('VN_ALLOWED_ORIGINS') != 'https://the-dashboard-chi.vercel.app'
            or any(env.get(k) for k in ('SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_SECRET_KEY',
                'RAILWAY_TOKEN', 'RAILWAY_API_TOKEN', 'VN_ECONOMIC_LOGIN',
                'VN_ECONOMIC_PASSWORD', 'VN_RELAY_LOGIN', 'VN_RELAY_PASSWORD'))):
        raise ValueError('closed_provider_canary_configuration_required')
    keys = tuple(env.get(k, '') for k in ('JUPITER_API_KEY', 'BIRDEYE_API_KEY', 'VN_SOLANA_RPC_URL'))
    if not all(keys):
        raise ValueError('explicit_provider_configuration_required')
    return keys


def quota_headers(headers):
    """Only small numeric quota facts; never headers, URLs, bodies or credentials."""
    value = {}
    for key in ('x-ratelimit-current', 'x-ratelimit-limit',
                'x-ratelimit-remaining', 'x-ratelimit-reset'):
        item = headers.get(key)
        if isinstance(item, str) and len(item) <= 20 and item.lstrip('-').isdigit():
            value[key.removeprefix('x-ratelimit-')] = int(item)
    return value


def quota_has_headroom(observation, *, received, now):
    remaining = observation.get('remaining')
    return (type(remaining) is int and remaining >= 1 + QUOTA_RESERVE
            and received is not None and 0 <= now-received <= QUOTA_OBSERVATION_MAX_AGE)


def summary(samples):
    if not samples:
        return None
    ordered = sorted(samples)
    return {'count': len(ordered), 'minimum': ordered[0],
            'median': ordered[(len(ordered)-1)//2], 'maximum': ordered[-1],
            'tail_acceptance': False}


async def assess(keys, *, feed_factory=JupiterFeed):
    feed = feed_factory(api_key=keys[0], birdeye_api_key=keys[1], rpc_url=keys[2])
    report = {'provider_read_canary': 1, 'phase': 'started', 'mode': 'closed',
              'economic_writes': False, 'wallet_operations': False}
    clocks, ages, receipt, quotas, lag = [], [], [], [], []
    quota_received = None
    trace = aiohttp.TraceConfig()
    async def ended(session, context, params):
        nonlocal quota_received
        # Only the actual Jupiter price path updates this quota observation.
        if params.url.host == 'api.jup.ag' and params.url.path == '/price/v3':
            quotas.append(quota_headers(params.response.headers))
            quota_received = time.monotonic()
    trace.on_request_end.append(ended)
    feed._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5),
        trust_env=False, trace_configs=[trace])
    async def loop_probe():
        while True:
            before = time.monotonic()
            await asyncio.sleep(.1)
            lag.append(max(0, time.monotonic()-before-.1))
            if len(lag) > 1000:
                raise ValueError()
    monitor = asyncio.create_task(loop_probe())
    before_cpu = sum(os.times()[:2])
    started = time.monotonic()
    print(json.dumps(report), flush=True)
    try:
        async with asyncio.timeout(DEADLINE):
            before = time.monotonic()
            rows = await feed.get_provider_history()
            report['history'] = {'minutes': len(rows), 'bars': len(rows)//15,
                'elapsed_seconds': round(time.monotonic()-before, 6),
                'raw_bytes': len(rows[0].document.raw_body),
                'raw_sha256': rows[0].document.response_sha256,
                'null_multiplier': all(row.multiplier is None for row in rows)}
            for index in range(SAMPLES):
                if index and (not quotas or not quota_has_headroom(
                        quotas[-1], received=quota_received, now=time.monotonic())):
                    raise MarketFeedError('shared_quota_margin_unavailable')
                before = time.monotonic()
                cap = (await feed.get_price_captures(['SOL/USDC']))['SOL/USDC']
                clocks.append(round(time.monotonic()-before, 6))
                ages.append(round(cap.evidence.source_age_at_receipt, 6))
                receipt.append(round(time.monotonic()-cap.evidence.received_monotonic, 6))
                if index+1 < SAMPLES:
                    await asyncio.sleep(INTERVAL)
        report['phase'] = 'passed'
    except MarketFeedError as error:
        report.update(phase='refused', code=error.code)
    except asyncio.CancelledError:
        report.update(phase='interrupted', code='closed_canary_cancelled')
        raise
    except Exception:
        report.update(phase='refused', code='private_diagnostic_suppressed')
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        await feed.close()
        report.update(elapsed_seconds=round(time.monotonic()-started, 6),
            price_seconds=summary(clocks), source_age_seconds=summary(ages),
            receipt_processing_seconds=summary(receipt),
            quota_observations=quotas,
            quota_policy={'sample_limit': SAMPLES, 'minimum_spacing_seconds': INTERVAL,
                'next_request_count': 1, 'remaining_reserve': QUOTA_RESERVE,
                'maximum_observation_age_seconds': QUOTA_OBSERVATION_MAX_AGE,
                'reset_means_one_slot_not_full_window': True,
                'account_budget_accepted': False},
            api_calls={'jupiter': feed.api_call_count,
                'birdeye': feed._candles.api_call_count, 'rpc': feed._source_time.api_call_count},
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            process_cpu_seconds=round(sum(os.times()[:2])-before_cpu, 6),
            maximum_loop_lag_seconds=round(max(lag, default=0), 6),
            tail_or_shared_account_budget_acceptance=False)
        print(json.dumps(report, allow_nan=False), flush=True)
    return report


async def main():
    keys = configuration(os.environ)
    # Serve the existing closed API immediately. Dependency checks are never
    # health probes and the finite task cannot change the API selection.
    server = uvicorn.Server(uvicorn.Config(create_app(), host='0.0.0.0',
        port=int(os.environ['PORT']), workers=1, lifespan='on', access_log=False))
    task = None
    async def owned_assessment():
        while not server.started:
            if server.should_exit:
                return
            await asyncio.sleep(.05)
        return await assess(keys)
    task = asyncio.create_task(owned_assessment())
    try:
        await server.serve()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


if __name__ == '__main__':
    asyncio.run(main())
