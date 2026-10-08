"""Explicit finite paper controller acceptance; the public API remains closed.

This operator entrypoint owns one fresh configured run and original control IDs.
It uses the ordinary service, real providers, native SQL and durable relay. It
never retries a failed run, restores a checkpoint or performs wallet operations.
Only bounded timing/count facts are logged; credentials and provider/SQL bodies
are never logged. Select it deliberately after exact-target release review.
"""
from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
import json
import os
import resource
import sys
import time

import aiohttp
import uvicorn

from tools.provider_read_canary import quota_headers, summary
from vonneumann.server.paper_app import create_app, configured_service

DEADLINE = 600
MAX_TICKS = 30
RPC_NAMES = frozenset(('create_run', 'commit_command', 'heartbeat', 'get_command',
                       'read_outbox', 'acknowledge_event', 'accept_event'))


class MeasuredTransport:
    def __init__(self, original):
        self.original = original
        self.samples = defaultdict(list)
        self.errors = Counter()
        self.calls = 0

    async def rpc(self, name, arguments):
        if name not in RPC_NAMES or self.calls >= 6000:
            raise ValueError('finite_rpc_budget')
        self.calls += 1
        started = time.monotonic()
        try:
            return await self.original.rpc(name, arguments)
        except (Exception, asyncio.CancelledError):
            self.errors[name] += 1
            raise
        finally:
            self.samples[name].append(round(time.monotonic()-started, 6))

    async def accept_event(self, arguments):
        return await self.rpc('accept_event', arguments)

    async def aclose(self):
        await self.original.aclose()


def configuration(environment):
    if (environment.get('VN_SERVICE_MODE') != 'closed'
            or environment.get('VN_PAPER_ACCEPTANCE') != 'finite-controller-v1'
            or environment.get('VN_JUPITER_SOLE_CONSUMER') != '1'):
        raise ValueError('explicit_closed_controller_canary_required')
    service = configured_service({**environment, 'VN_SERVICE_MODE': 'paper-v5'})
    if service is None or not 1 <= service._ticks <= MAX_TICKS or service._interval < 5:
        raise ValueError('finite_controller_canary_budget_required')
    return service


async def assess(service):
    transport = MeasuredTransport(service._economic)
    service._economic = service._relay = service.repository._transport = transport
    feed = service._feed
    report = {'paper_controller_canary': 1, 'phase': 'started',
              'mode': 'closed-api-finite-paper', 'wallet_operations': False,
              'automatic_retry': False}
    quotas, ages, lag = [], [], []
    last_capture = None
    original_capture = feed.get_price_captures

    async def capture(*args, **kwargs):
        nonlocal last_capture
        now = time.monotonic()
        if (feed.api_call_count >= MAX_TICKS or last_capture is not None
                and now-last_capture < 5):
            raise ValueError('finite_provider_budget')
        last_capture = now
        captures = await original_capture(*args, **kwargs)
        ages.extend(round(row.evidence.source_age_at_receipt, 6) for row in captures.values())
        return captures

    feed.get_price_captures = capture
    trace = aiohttp.TraceConfig()
    async def ended(session, context, params):
        if params.url.host == 'api.jup.ag' and params.url.path == '/price/v3':
            if len(quotas) >= MAX_TICKS:
                raise ValueError('finite_quota_observation_budget')
            quotas.append(quota_headers(params.response.headers))
    trace.on_request_end.append(ended)
    feed._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5),
                                        trust_env=False, trace_configs=[trace])

    async def loop_probe():
        while True:
            before = time.monotonic()
            await asyncio.sleep(.1)
            lag.append(max(0, time.monotonic()-before-.1))
            if len(lag) > 6000:
                raise ValueError('finite_monitor_budget')
    monitor = asyncio.create_task(loop_probe())
    started, cpu = time.monotonic(), sum(os.times()[:2])
    print(json.dumps(report), flush=True)
    try:
        async with asyncio.timeout(DEADLINE):
            service.start(service.owner_id, service.start_id)
            # The service retains its task even if this assessment is cancelled.
            await asyncio.shield(service._task)
            status = service.status(service.owner_id)
            if status['phase'] != 'stopped' or service.repository.pending is not None:
                raise ValueError('original_paper_operation_needs_inspection')
            rows = service.runner.last_report.reports
            if (not rows or rows[-1].kind != 'stop' or rows[-1].status != 'complete'
                    or len(rows) > MAX_TICKS+2):
                raise ValueError('terminal_paper_ack_required')
            state = service.controller._owner.installed_state.to_dict()
            phases = defaultdict(list)
            for row in rows:
                for label, seconds in row.phase_seconds:
                    phases[label].append(round(seconds, 6))
            report.update(phase='passed', final_revision=state['revision'],
                accepted_quotes=state['source']['quote_sequence'],
                generation=state['engine']['generation'], final_status=state['status'],
                ticks_completed=service.runner.last_report.ticks_completed,
                idle_renewals=service.runner.last_report.idle_renewals,
                owned_commands=service.controller._owner.owned_command_count,
                accounts=len(state['accounts']), positions=len(state['positions']),
                open_positions=sum(not row['closed'] for row in state['positions']),
                operation_seconds=summary([round(row.elapsed_seconds, 6) for row in rows]),
                phase_seconds={k: summary(v) for k,v in sorted(phases.items())})
    except asyncio.CancelledError:
        report.update(phase='interrupted', code='original_work_retained')
        raise
    except Exception:
        report.update(phase='refused', code='original_operation_requires_inspection',
                      service_phase=service._phase, revision=service.repository.revision)
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        try:
            await service.close()
        except Exception:
            report.update(phase='refused', cleanup='unverified')
        report.update(elapsed_seconds=round(time.monotonic()-started, 6),
            sql_seconds={k: summary(v) for k,v in sorted(transport.samples.items())},
            sql_counts={k: len(v) for k,v in sorted(transport.samples.items())},
            sql_errors=dict(transport.errors), source_age_seconds=summary(ages),
            quota_observations=quotas,
            api_calls={'jupiter': feed.api_call_count, 'birdeye': feed._candles.api_call_count,
                       'rpc': feed._source_time.api_call_count},
            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                * (1 if sys.platform == 'darwin' else 1024),
            process_cpu_seconds=round(sum(os.times()[:2])-cpu, 6),
            maximum_loop_lag_seconds=round(max(lag, default=0), 6),
            finite_measurement=True, statistical_tail_acceptance=False)
        print(json.dumps(report, allow_nan=False), flush=True)
    return report


async def main():
    service = configuration(os.environ)
    server = uvicorn.Server(uvicorn.Config(create_app(), host='0.0.0.0',
        port=int(os.environ['PORT']), workers=1, lifespan='on', access_log=False))
    async def owned_assessment():
        while not server.started:
            if server.should_exit: return
            await asyncio.sleep(.05)
        return await assess(service)
    task = asyncio.create_task(owned_assessment())
    try:
        await server.serve()
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await service.close()


if __name__ == '__main__':
    asyncio.run(main())
