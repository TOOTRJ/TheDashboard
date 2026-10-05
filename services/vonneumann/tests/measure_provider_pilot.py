"""Reproduce an offline, dense single-window ProviderPilotOwner measurement.

Run from the worker directory with::

    PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
        python -m tests.measure_provider_pilot --measure

There are no unittest cases in this module. Every economic operation uses the
actual owner, sealed lifecycle preparation, stop-capacity witness, coordinator,
PreparedCommand validation, and receipt installation. Only RPC ledger/outbox
delivery is fake. Literal provider response fixtures are parsed normally while
network access is denied. Sparse simulated timestamp jumps exercise a dense
retained-position window; they do not establish sustainable quote cadence.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from uuid import UUID

from tests.security_support import deny_network

with deny_network():
    from tests.test_exact_rehearsal import ALGORITHMS, OWNER, RUN, WORKER
    from tests.test_provider_contract import EPOCH, END, WALL, MONO, raw_capture, raw_minutes
    from tests.test_transition_coordinator import Clock, CommittingTransport
    from vonneumann.core import exact_lifecycle as kernel
    from vonneumann.core import provider_lifecycle as life
    from vonneumann.core.exact_rehearsal import MAX_PAYLOAD_BYTES
    from vonneumann.db.command_protocol import PreparedCommand, canonical_json
    from vonneumann.db.command_repository import CommandRepository
    from vonneumann.db.provider_pilot_owner import ProviderPilotOwner


def _postgres_payload_bytes(payload):
    """Match the UTF-8, JSONB-spacing representation used for command limits."""
    return len(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                          allow_nan=False, separators=(', ', ': ')).encode('utf-8'))


async def pilot_trace(algorithm):
    """Measure real owned admission without relaxing caps or replacing planners."""
    started = time.perf_counter()
    wall, mono = Clock(), Clock()
    wall.value, mono.value = float(WALL), MONO
    transport = CommittingTransport()
    repository = CommandRepository(transport, OWNER, RUN, WORKER, monotonic=mono)
    identity_counter = 51_000_000

    def identity():
        nonlocal identity_counter
        identity_counter += 1
        return str(UUID(int=identity_counter))

    def allocation(generation):
        return {'ids': tuple(identity() for _ in range(9)),
                'names': tuple((generation, f'Pilot-{generation}-{index}')
                               for index in range(8)),
                'command_id': identity()}

    timings = []

    async def timed(kind, operation):
        before = time.perf_counter()
        result = await operation
        timings.append({'operation': kind,
                        'seconds': time.perf_counter() - before})
        return result

    config = life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(
        algorithm, OWNER, RUN, asset='SOL/USD'), EPOCH)
    creation = PreparedCommand.create(OWNER, RUN, WORKER,
        config.run_configuration(), config.initial_cash, command_id=identity())
    await timed('create', repository.submit(creation))
    owner = ProviderPilotOwner(repository, transport, config,
        stop_command_id=identity(), wall_clock=wall, monotonic=mono)
    await owner.heartbeat()

    delivered = []

    async def sink(event):
        delivered.append(event)

    reserved_stop_max = 0

    async def publish_and_sample():
        nonlocal reserved_stop_max
        await owner.publish_pending(sink)
        witness = owner.reserved_stop_bytes
        if witness is not None:
            reserved_stop_max = max(reserved_stop_max, witness)

    await timed('bootstrap', owner.bootstrap(
        raw_minutes(closes=['100'] * 900 + ['80'] * 15), **allocation(0)))
    await publish_and_sample()

    protections = decision_commands = suppressed_noops = 0
    trace = []
    # Every bar alternates high/low and has a distinct later executable quote.
    # The +2 quote explicitly exercises the owner's no-op decision suppression.
    offsets = (1, 2, 900, 901, 1800, 1801, 2700, 2701, 3600, 3601)
    for serial, offset in enumerate(offsets, 1):
        wall.value, mono.value = float(WALL + offset), MONO + offset
        # Renew the fake lease before every sparse timestamp jump. This does
        # not stand in for a measured production heartbeat cadence.
        await owner.heartbeat()
        ticket = owner.capture_quote(raw_capture(block=100 + serial,
            source_second=int(wall.value) - 2,
            wall=wall.value - 1, mono=mono.value - 1))
        generation = owner.installed_state.to_dict()['engine']['generation']
        await timed('protect', owner.protect(ticket, **allocation(generation + 1)))
        protections += 1
        await publish_and_sample()
        records = ()
        if offset % 900 == 0:
            high = (offset // 900) % 2 == 1
            records = raw_minutes(end=END + offset, count=15,
                close='120' if high else '80',
                wall=wall.value - 1, mono=mono.value - 1)
        result = await timed('decide', owner.decide(
            ticket, records, **allocation(generation + 1)))
        if result is None:
            suppressed_noops += 1
        else:
            decision_commands += 1
            await publish_and_sample()
        state = owner.installed_state.to_dict()
        trace.append({'offset_seconds': offset, 'decision_committed': result is not None,
                      'generation': state['engine']['generation'],
                      'retained_positions': len(state['positions']),
                      'open_positions': sum(not row['closed'] for row in state['positions']),
                      'owned_command_count': owner.owned_command_count})

    before_stop = owner.installed_state.to_dict()
    if before_stop['engine']['generation'] != 1 or owner.refusal_reason != 'pilot_completed':
        raise AssertionError('Dense pilot did not complete its single supported evaluation window')
    if not owner.stop_available:
        raise AssertionError('Supported pilot must retain a usable reserved stop after publication')
    await timed('stop', owner.stop())
    await owner.publish_pending(sink)
    stopped = owner.installed_state.to_dict()
    if (stopped['status'] != 'stopped'
            or stopped['positions'] != before_stop['positions']
            or stopped['accounts'] != before_stop['accounts']
            or stopped['reserve'] != before_stop['reserve']):
        raise AssertionError('Reserved stop changed retained economic state')
    if owner.pending_candidate is not None or len(transport.acknowledged) != len(transport.events):
        raise AssertionError('Measurement left owned command or publication work unsettled')

    payloads = [arguments['payload'] for name, arguments in transport.calls
                if name == 'commit_command']
    payload_sizes = [_postgres_payload_bytes(payload) for payload in payloads]
    compact_sizes = [len(canonical_json(payload)) for payload in payloads]
    if max(payload_sizes) > MAX_PAYLOAD_BYTES or max(compact_sizes) > MAX_PAYLOAD_BYTES:
        raise AssertionError('An admitted command exceeded an existing whole-payload limit')
    stop_payload = payloads[-1]
    if stop_payload['transition']['evidence']['control']['action'] != 'stop':
        raise AssertionError('Last economic command must be the reserved stop')
    economic_commands = transport.count('create_run') + transport.count('commit_command')
    if economic_commands != owner.owned_command_count:
        raise AssertionError('Fake ledger and actual owner command budget differ')
    longest = max(timings, key=lambda row: row['seconds'])
    return {'algorithm': algorithm, 'economic_commands_including_create_bootstrap_stop': economic_commands,
            'protections': protections, 'decision_commands': decision_commands,
            'suppressed_noop_decisions': suppressed_noops,
            'max_postgres_spacing_request_payload_bytes': max(payload_sizes),
            'max_compact_request_payload_bytes': max(compact_sizes),
            'creation_configuration_postgres_spacing_bytes':
                _postgres_payload_bytes(creation.expected_request['config']),
            'max_reserved_stop_witness_bytes': reserved_stop_max,
            'actual_stop_payload_bytes': _postgres_payload_bytes(stop_payload),
            'completed_generation': before_stop['engine']['generation'],
            'retained_positions_at_stop': len(stopped['positions']),
            'account_count_at_stop': len(stopped['accounts']),
            'stable_events_delivered': len(delivered),
            'longest_owned_prepare_validate_fake_rpc_seconds': longest['seconds'],
            'longest_owned_operation': longest['operation'],
            'total_runtime_seconds': time.perf_counter() - started,
            'trace': trace}


async def measure():
    with deny_network():
        results = [await pilot_trace(algorithm) for algorithm in ALGORITHMS]
    return {'measurement': 'offline-dense-single-window-provider-pilot-v1',
            'limitations': [
                'Uses literal raw provider fixtures and a fake RPC ledger/outbox; no network requests.',
                'Timing includes actual owner preparation, reserved-stop witness, command validation, '
                'fake RPC, receipt validation, and installation; excludes real provider, database, '
                'socket, and durable outbox delivery latency.',
                'Simulated clock jumps are sparse and heartbeats are explicit; this is not cadence '
                'acceptance or proof that the five-second real source budget is sustainable.',
                'All existing byte limits and pilot admission rules remain active.'
            ], 'results': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measure', action='store_true', required=True,
                        help='Measure all four solvers offline and print JSON')
    parser.parse_args()
    print(json.dumps(asyncio.run(measure()), indent=2, sort_keys=True))
