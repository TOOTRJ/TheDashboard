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
import uvloop

from tools.provider_read_canary import quota_headers, summary
from vonneumann.server.paper_app import create_app, configured_service
from vonneumann.db.command_protocol import canonical_uuid

DEADLINE = 600
MAX_TICKS = 30
RPC_NAMES = frozenset(('create_run', 'commit_command', 'heartbeat', 'get_command',
                       'read_outbox', 'acknowledge_event', 'accept_event'))


class MeasuredTransport:
    def __init__(self, original, *, drop_bootstrap_reply=False):
        self.original = original
        self.samples = defaultdict(list)
        self.errors = Counter()
        self.calls = 0
        self.drop_bootstrap_reply = drop_bootstrap_reply
        self.reply_dropped = False
        self.dropped_command_id = None

    @property
    def last_failure_phases(self):
        return getattr(self.original, 'last_failure_phases', None)

    async def rpc(self, name, arguments):
        if name not in RPC_NAMES or self.calls >= 6000:
            raise ValueError('finite_rpc_budget')
        self.calls += 1
        started = time.monotonic()
        try:
            result = await self.original.rpc(name, arguments)
            if name == 'commit_command' and self.drop_bootstrap_reply and not self.reply_dropped:
                # The original transport has acknowledged COMMIT. Lose only
                # this reply; settlement must read that same command identity.
                self.reply_dropped = True
                self.dropped_command_id = arguments['command_id']
                raise ConnectionError('deliberate_original_reply_drill')
            return result
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
            or environment.get('VN_PAPER_ACCEPTANCE') not in ('finite-controller-v1', 'finite-expired-run-v1')
            or environment.get('VN_JUPITER_SOLE_CONSUMER') != '1'):
        raise ValueError('explicit_closed_controller_canary_required')
    drill = environment.get('VN_PAPER_REPLY_DRILL', '')
    if drill not in ('', 'bootstrap-commit-once'):
        raise ValueError('explicit_original_reply_drill_required')
    existing = environment['VN_PAPER_ACCEPTANCE'] == 'finite-expired-run-v1'
    if existing:
        if drill: raise ValueError('distinct_failure_operations_required')
        interrupt_id = canonical_uuid(environment['VN_PAPER_INTERRUPT_ID'])
        revision = int(environment['VN_PAPER_INTERRUPT_REVISION'])
        if not 2 <= revision <= 4000 or interrupt_id in (
            environment['VN_PAPER_START_ID'], environment['VN_PAPER_STOP_ID']):
            raise ValueError('original_expiry_operation_required')
    service = configured_service({**environment, 'VN_SERVICE_MODE': 'paper-v5'})
    if service is None or not 1 <= service._ticks <= MAX_TICKS or service._interval < 5:
        raise ValueError('finite_controller_canary_budget_required')
    service._acceptance_drop_bootstrap_reply = drill == 'bootstrap-commit-once'
    service._acceptance_existing = existing
    if existing:
        service._acceptance_interrupt = interrupt_id, revision
    return service


async def assess(service):
    transport = MeasuredTransport(service._economic,
        drop_bootstrap_reply=getattr(service, '_acceptance_drop_bootstrap_reply', False))
    service._economic = service._relay = service.repository._transport = transport
    feed = service._feed
    report = {'paper_controller_canary': 1, 'phase': 'started',
              'mode': 'closed-api-finite-paper', 'wallet_operations': False,
              'automatic_retry': False,
              'loop_implementation': 'uvloop' if isinstance(asyncio.get_running_loop(), uvloop.Loop) else 'asyncio'}
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
            if transport.reply_dropped:
                if service._phase != 'pending' or service.repository.pending is None:
                    raise ValueError('original_drill_command_must_remain_pending')
                original_id = service.repository.pending.command_id
                service.settle(service.owner_id, service.start_id)
                await asyncio.shield(service._task)
                if (original_id != transport.dropped_command_id
                        or service.repository.pending is not None
                        or transport.samples['get_command'] == []):
                    raise ValueError('original_drill_readback_required')
                report.update(lost_reply_injected=True,
                              original_command_settled=True)
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
                      service_phase=service._phase, revision=service.repository.revision,
                      last_operation_failure=service.status(service.owner_id).get('last_operation_failure'),
                      last_transport_failure_phases=service.status(service.owner_id).get('last_transport_failure_phases'))
        if service.controller is not None:
            report.update(controller_closed_reason=service.controller.closed_reason,
                last_controller_failure=service.controller.last_failure,
                owner_closed_reason=service.controller._owner.closed_reason,
                pending_stage=service.controller.pending_stage)
        if service.runner is not None and service.runner.last_report is not None:
            result = service.runner.last_report
            report.update(runner_status=result.status, ticks_completed=result.ticks_completed,
                controller_closed_reason=service.controller.closed_reason,
                last_stage=None if not result.reports else result.reports[-1].kind)
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


async def assess_expired(service):
    """One explicit original-run expiry/restart drill; no checkpoint adoption.

    Reuses the same scoped pair after an interrupted process has gone away.
    Freshness/lease failure is asserted on the actual native server. The sole
    economic change is one configured original interruption command; its
    checkpoint/cash/holdings remain intact. No price/history request is made.
    """
    from pathlib import Path
    import tempfile
    from tools.native_session_canary import expect
    pair = service._economic
    report = {'paper_controller_canary': 1, 'phase': 'started',
        'mode': 'closed-api-existing-run-expiry', 'wallet_operations': False,
        'automatic_retry': False}
    print(json.dumps(report), flush=True)
    started = time.monotonic()
    try:
        async with asyncio.timeout(90):
            original = await pair.rpc('get_command', {'owner_id': service.owner_id,
                'run': service.run_id, 'command_id': service.start_id})
            if not original or original['request']['kind'] != 'create':
                raise ValueError('original_create_readback_required')
            request = original['request']
            # A second process uses its fresh worker identity with the exact
            # original start ID. SQL refuses it; journal settlement cannot
            # bind the old process's receipt to this new worker.
            service.start(service.owner_id, service.start_id)
            await asyncio.shield(service._task)
            if service._phase != 'pending': raise ValueError('restart_must_be_refused')
            service.settle(service.owner_id, service.start_id)
            await asyncio.shield(service._task)
            if service._phase != 'pending' or service.repository.revision != 0 or service.runner is not None:
                raise ValueError('old_run_must_not_be_adopted')
            economic = pair._economic
            with tempfile.TemporaryDirectory(prefix='paper-expiry-', dir='/tmp') as directory:
                ca = Path(directory) / 'root.crt'; ca.write_bytes(economic._ca); ca.chmod(0o600)
                connection = await asyncio.wait_for(economic._connect(ca, Path(directory)/'absent.crl'), 3)
                try:
                    await expect(connection, 'economic',
                        'SELECT vn_durability.create_run(%s::uuid,%s::uuid,%s::uuid,%s::uuid,%s::jsonb,%s,120)',
                        (service.owner_id, service.run_id, service.repository.worker_id,
                         service.start_id, json.dumps(request['config']), request['initial_cash']),
                        'P0001', 'command_conflict')
                    await expect(connection, 'economic',
                        'SELECT vn_durability.heartbeat(%s::uuid,%s::uuid,%s::uuid,%s::bigint,120)',
                        (service.owner_id, service.run_id, request['worker'], original['response']['fence']),
                        'P0001', 'lease_lost')
                finally: await connection.close()
            interrupt_id, revision = service._acceptance_interrupt
            arguments = {'owner_id': service.owner_id, 'run': service.run_id,
                         'expected_revision': revision, 'command_id': interrupt_id}
            receipt = await pair.rpc('interrupt_expired', arguments)
            journal = await pair.rpc('get_command', {'owner_id': service.owner_id,
                'run': service.run_id, 'command_id': interrupt_id})
            if (not journal or journal['response'] != receipt or receipt['revision'] != revision+1
                    or receipt['status'] != 'failed' or receipt['requires_reconciliation'] is not True):
                raise ValueError('original_interrupt_receipt_required')
            from vonneumann.db.relay_acceptance import DurableRelayPublisher
            publisher = DurableRelayPublisher(pair, service.owner_id, service.run_id)
            page = await pair.rpc('read_outbox', {'owner_id': service.owner_id,
                'run': service.run_id, 'through_revision': receipt['revision'],
                'max_events': 100, 'max_bytes': 65536})
            if page['has_more']: raise ValueError('finite_interruption_outbox_required')
            for event in page['events']:
                await publisher(event)
                await pair.rpc('acknowledge_event', {'owner_id': service.owner_id,
                    'run': service.run_id, 'command_id': event['command_id'],
                    'event_index': event['event_index']})
            report.update(phase='passed', new_process_adoption_denied=True,
                expired_heartbeat_denied=True, original_interrupt_committed=True,
                final_status=receipt['status'], final_revision=receipt['revision'],
                requires_reconciliation=True, restored_checkpoint=False,
                api_calls={'jupiter': 0, 'birdeye': 0, 'rpc': 0})
    except asyncio.CancelledError:
        report.update(phase='interrupted', code='original_work_retained'); raise
    except Exception:
        report.update(phase='refused', code='original_expiry_operation_requires_inspection')
    finally:
        await service.close()
        report.update(elapsed_seconds=round(time.monotonic()-started, 6))
        print(json.dumps(report), flush=True)
    return report


async def main():
    service = configuration(os.environ)
    server = uvicorn.Server(uvicorn.Config(create_app(), host='0.0.0.0',
        port=int(os.environ['PORT']), workers=1, lifespan='on', access_log=False))
    async def owned_assessment():
        while not server.started:
            if server.should_exit: return
            await asyncio.sleep(.05)
        return await (assess_expired(service) if service._acceptance_existing else assess(service))
    task = asyncio.create_task(owned_assessment())
    try:
        await server.serve()
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await service.close()


if __name__ == '__main__':
    # Match ordinary start-worker.sh rather than assessing a different timer
    # implementation through asyncio.run's default event loop.
    uvloop.run(main())
