"""Opt-in, current-clock controller timings against owned offline PostgreSQL.

From services/vonneumann with the already installed development environment:

    PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
      python -m tests.postgres.provider_controller_latency --allow-isolated-postgres

This creates/removes only the harness's uniquely owned no-network container. It
never starts Docker, switches its context, pulls an image, contacts a provider,
reads real credentials or uses production Supabase. Fake HTTP transport feeds
literal replies through the real adapters; PostgreSQL transactions and outbox
acknowledgements remain real. Results measure this local laboratory, not provider
network latency, hosted-worker latency or a sustainable production cadence.

``owner_submission`` includes pure preparation, the complete-stop witness and
SQL acknowledgement; it is deliberately not labeled database-only latency.
Fractional receipt deferrals are actual waits, not synthetic clock advances.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import json
import os
import time

# Install explicit fake settings before importing application/provider modules.
from tests.security_support import deny_network
from tests.postgres.harness import IsolatedPostgres, OPT_IN
from tests.postgres.test_command_adapter import FixtureRpcTransport, identity, literal
from tests.postgres.test_provider_controller import LiteralProviderSession
from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
from vonneumann.core.provider_lifecycle import ProviderLifecycleConfig
from vonneumann.core.provider_controller import CommandAllocation, ProviderPilotController
from vonneumann.db.command_protocol import PreparedCommand
from vonneumann.db.command_repository import CommandRepository
from vonneumann.db.provider_pilot_owner import ProviderPilotOwner
with deny_network():
    from vonneumann.market.jupiter_feed import JupiterFeed


def milliseconds(value):
    return None if value is None else round(value * 1000, 3)


def phase_milliseconds(report):
    return {label: milliseconds(value) for label, value in report.phase_seconds}


async def measure(database):
    owner_id, run_id, worker_id = identity(), identity(), identity()
    database.sql('INSERT INTO auth.users(id) VALUES ('+literal(owner_id)+');')
    config = ProviderLifecycleConfig(ExactLifecycleConfig('genetic_algorithm',
        owner_id, run_id, asset='SOL/USD'), identity())
    transport = FixtureRpcTransport(database)
    repository = CommandRepository(transport, owner_id, run_id, worker_id)
    await repository.submit(PreparedCommand.create(owner_id, run_id, worker_id,
        config.run_configuration(), config.initial_cash, command_id=identity(), lease_seconds=120))
    owner = ProviderPilotOwner(repository, transport, config, stop_command_id=identity())
    feed = JupiterFeed(api_key='controller-latency-fixture-key',
        rpc_url='https://controller-fixture.invalid/rpc',
        birdeye_api_key='controller-latency-fixture-key')
    price_session = LiteralProviderSession()
    candle_session = LiteralProviderSession(candles=True)
    feed._session, feed._candles._session = price_session, candle_session
    published = []

    def allocate(_kind, generation):
        return CommandAllocation(identity(), tuple(identity() for _ in range(9)),
            tuple((generation, f'Latency-{generation}-{index}') for index in range(8)))

    async def publish(event):
        if owner.installed_state is None:
            raise AssertionError('Publication preceded exact installation')
        published.append(event['event_id'])

    controller = ProviderPilotController(owner, feed, publish, allocate, lease_seconds=120)
    samples = []

    async def sample(kind, operation, *, accept_deferred=False):
        started = time.monotonic()
        before_rpc = len(transport.calls)
        before_events = len(published)
        phases = Counter()
        deferred = 0
        while True:
            report = await operation()
            for label, value in report.phase_seconds:
                phases[label] += value
            if report.status == 'complete':
                break
            if not accept_deferred or report.status != 'deferred':
                raise AssertionError('Unexpected controller measurement status')
            deferred += 1
            if time.monotonic() - started >= 8 or deferred >= 160:
                raise TimeoutError('Literal current-clock tick did not complete')
            await asyncio.sleep(.05)
        calls = Counter(name for name, _ in transport.calls[before_rpc:])
        samples.append({'kind': kind, 'status': report.status, 'revision': report.revision,
            'quote_sequence': report.quote_sequence, 'decision_committed': report.decision_committed,
            'accepted_operation_ms': milliseconds(report.elapsed_seconds),
            'request_through_completion_ms': milliseconds(time.monotonic() - started),
            'accepted_phase_ms': phase_milliseconds(report),
            'all_attempt_phase_ms': {name: milliseconds(phases[name]) for name in sorted(phases)},
            'deferred_attempts': deferred, 'rpc_counts': dict(sorted(calls.items())),
            'published_events': len(published) - before_events})
        return report

    try:
        await sample('bootstrap', controller.bootstrap)
        for index in range(3):
            report = await sample(f'tick_{index + 1}', controller.tick, accept_deferred=True)
            if report.quote_sequence != index + 1:
                raise AssertionError('Measurement did not accept three distinct quotes')
        await sample('reserved_stop', controller.stop)
        state = owner.installed_state.to_dict()
        actual = json.loads(database.scalar('SELECT engine_state FROM vn_durability.runs WHERE id='
                                            +literal(run_id)+';'))
        if actual != state or state['status'] != 'stopped' or len(published) != len(set(published)):
            raise AssertionError('Measured controller state or stable event sequence differed')
        pending = await transport.rpc('read_outbox', {'owner_id': owner_id, 'run': run_id,
            'through_revision': state['revision'], 'max_events': 50, 'max_bytes': 65536})
        if pending['events'] or pending['has_more']:
            raise AssertionError('Measured outbox did not settle completely')
        return {'status': 'complete', 'measurement': 'offline-current-clock-controller-sql-v1',
            'isolation': {**database.identity, 'container_name': database.name}, 'samples': samples,
            'total_rpc_counts': dict(sorted(Counter(name for name, _ in transport.calls).items())),
            'literal_http_counts': {'jupiter_get': sum(call[0] == 'GET' for call in price_session.calls),
                'solana_rpc_post': sum(call[0] == 'POST' for call in price_session.calls),
                'birdeye_get': len(candle_session.calls)},
            'published_events': len(published), 'unique_published_events': len(set(published)),
            'final_revision': state['revision'], 'accepted_quotes': state['source']['quote_sequence'],
            'production_cadence_established': False}
    finally:
        controller.close_admission()
        try:
            # Drain only already retained work before removing its own fixture.
            await asyncio.wait_for(controller.settle(), 5)
        finally:
            await feed.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-isolated-postgres', action='store_true', required=True,
        help='Allow this process to create/remove one uniquely owned offline PostgreSQL container')
    args = parser.parse_args()
    if not args.allow_isolated_postgres:
        parser.error('Explicit isolated PostgreSQL opt-in is required')
    os.environ[OPT_IN] = '1'
    os.environ['PYTHON_DOTENV_DISABLED'] = '1'
    try:
        with deny_network(), IsolatedPostgres() as database:
            database.apply_contract()
            result = asyncio.run(measure(database))
    except Exception as error:
        # The exception may contain SQL/provider diagnostic material; emit only
        # its bounded type, never a body, authenticated URL or environment value.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__},
                         sort_keys=True, separators=(',', ':')))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
