#!/usr/bin/env python3
"""Offline planning bounds for one SOL market and one writer. No runtime authority."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import ast
import hashlib
import json
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = {
    'acquisition': 'vonneumann/market/provider_acquisition_v3.py',
    'transport': 'vonneumann/market/provider_recorded_transport_v3.py',
    'admission': 'vonneumann/market/source_admission_v3_policy.py',
    'canary': 'tools/provider_read_canary.py',
}
SECOND = 1_000_000
MINUTE = 60 * SECOND


def unsigned(*values):
    if any(type(value) is not int or value < 0 for value in values):
        raise ValueError('expected nonnegative integer inputs')


def rounded_up(numerator, denominator):
    return (numerator + denominator - 1) // denominator


def constant(node):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left, right = constant(node.left), constant(node.right)
        unsigned(left, right)
        return left * right
    return ast.literal_eval(node)


def literal(tree, name):
    found = [node.value for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(found) != 1:
        raise ValueError('reviewed source constant shape changed')
    node = found[0]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'MappingProxyType':
        node = node.args[0]
    return constant(node)


def annotated(tree, klass, name):
    matches = [node for item in tree.body if isinstance(item, ast.ClassDef) and item.name == klass
               for node in item.body if isinstance(node, ast.AnnAssign)
               and isinstance(node.target, ast.Name) and node.target.id == name]
    if len(matches) != 1:
        raise ValueError('reviewed transport bound shape changed')
    return constant(matches[0].value)


@dataclass(frozen=True)
class SourceLimits:
    receipt_age_us: int
    source_age_us: int
    future_us: int
    bodies: tuple[int, int, int]
    hot_result_bytes: int
    pre_io_bytes: int
    packet_results: int
    supplied_inventory: int
    quota_reserve: int
    quota_age_us: int


def source_limits(root=ROOT):
    raw = {name: (root / rel).read_bytes() for name, rel in SOURCE_FILES.items()}
    trees = {name: ast.parse(body) for name, body in raw.items()}
    a, t, s, c = (trees[key] for key in ('acquisition', 'transport', 'admission', 'canary'))
    bodies = literal(a, 'BODY_LIMITS')
    transport = {
        name: annotated(t, 'TransportBounds', name)
        for name in ('result_bytes_limit', 'packet_limit')
    }
    limits = SourceLimits(
        literal(a, 'MAX_RECEIPT_AGE_US'), literal(a, 'MAX_SOURCE_AGE_US'), literal(a, 'FUTURE_US'),
        (bodies['jupiter-price-v3'], bodies['solana-rpc'], bodies['solana-rpc']),
        transport['result_bytes_limit'], literal(t, 'PACKET_RESERVE_BYTES'), transport['packet_limit'],
        int(literal(s, '_DESCRIPTOR')['bounds']['inventory_entries']), literal(c, 'QUOTA_RESERVE'),
        literal(c, 'QUOTA_OBSERVATION_MAX_AGE') * SECOND,
    )
    bounds = [value for key, value in asdict(limits).items() if key != 'bodies']
    unsigned(*bounds, *limits.bodies)
    if min(*bounds, *limits.bodies) == 0 or limits.pre_io_bytes > limits.hot_result_bytes:
        raise ValueError('reviewed source bounds are invalid')
    return limits, {name: hashlib.sha256(body).hexdigest() for name, body in raw.items()}


@dataclass(frozen=True)
class Demand:
    positions: int = 0
    allocated_ids: int = 0
    provider_records: int = 0
    dependency_views: int = 0
    body_bytes: int = 0
    hot_result_bytes: int = 0
    packet_results: int = 0

    def __post_init__(self):
        unsigned(*asdict(self).values())

    def __add__(self, other):
        return Demand(*(getattr(self, field.name) + getattr(other, field.name) for field in fields(self)))


def over_limits(used, claim, reserved, caps):
    """Ordinary claim must leave the entire separately declared reserve."""
    total = used + claim + reserved
    return tuple(field.name for field in fields(total)
                 if getattr(total, field.name) > getattr(caps, field.name))


def transport_can_start(used, limits):
    return (used.hot_result_bytes + limits.pre_io_bytes <= limits.hot_result_bytes
            and used.packet_results < limits.packet_results)


def quota_can_start(remaining, observed_us, now_us, limits):
    """Conservative continuation check, not a provider budget or bootstrap rule."""
    return (type(remaining) is int and remaining >= 1 + limits.quota_reserve
            and type(observed_us) is int and type(now_us) is int
            and 0 <= observed_us <= now_us <= observed_us + limits.quota_age_us)


@dataclass(frozen=True)
class Deadline:
    ordinary_writer_us: int
    fence_us: int
    stop_writer_us: int
    reader_us: int
    stop_bound_us: int
    recovery_bound_us: int

    def __post_init__(self):
        unsigned(*asdict(self).values())
        if not self.stop_bound_us or not self.recovery_bound_us:
            raise ValueError('Stop and recovery planning bounds must be positive')

    def headroom(self, projected_commit_us):
        unsigned(projected_commit_us)
        stop_finish = projected_commit_us + self.stop_bound_us
        return {
            'writer': self.ordinary_writer_us - projected_commit_us,
            'fence': self.fence_us - projected_commit_us,
            'stop_writer': self.stop_writer_us - stop_finish,
            'reader': self.reader_us - stop_finish - self.recovery_bound_us,
        }

    def stop_can_start(self, now_us):
        """Retirement planning assumes an independently authorized original Stop."""
        unsigned(now_us)
        headroom = self.headroom(now_us)
        return min(headroom['stop_writer'], headroom['reader']) > 0

    def ordinary_can_start(self, now_us, commit_bound_us):
        unsigned(now_us, commit_bound_us)
        if not commit_bound_us:
            raise ValueError('ordinary planning bound must be positive')
        return min(self.headroom(now_us + commit_bound_us).values()) > 0


@dataclass(frozen=True)
class Timing:
    """Synthetic conservative clock inputs, not a replacement native validator."""
    original_id: str
    expected_minute: int
    started_us: int
    earliest_receipt_us: int
    collection_finished_us: int
    process_lower_us: int
    estimated_source_us: int
    native_accepted_us: int
    recognized_commit_us: int
    visible_us: Optional[int]
    readback_id: Optional[str]

    def classify(self, limits):
        unsigned(self.expected_minute, self.started_us, self.earliest_receipt_us,
                 self.collection_finished_us, self.process_lower_us, self.estimated_source_us,
                 self.native_accepted_us, self.recognized_commit_us)
        if self.visible_us is not None:
            unsigned(self.visible_us)
        if (not self.original_id or not self.started_us <= self.earliest_receipt_us
                <= self.collection_finished_us <= self.process_lower_us
                <= self.native_accepted_us <= self.recognized_commit_us):
            return 'clock_order'
        if self.collection_finished_us - self.started_us >= limits.receipt_age_us:
            return 'acquisition_deadline'
        source_age = self.recognized_commit_us - self.estimated_source_us
        if (source_age > limits.source_age_us
                or self.estimated_source_us - self.process_lower_us > limits.future_us):
            return 'source_age'
        if self.recognized_commit_us - self.earliest_receipt_us >= limits.receipt_age_us:
            return 'receipt_age_at_guard'
        if self.visible_us is None or self.readback_id != self.original_id:
            return 'original_readback_required'
        if self.visible_us < self.recognized_commit_us:
            return 'clock_order'
        minute_start = self.expected_minute * MINUTE
        minute_end = minute_start + MINUTE
        if not (minute_start <= self.native_accepted_us < minute_end
                and minute_start < self.visible_us <= minute_end):
            return 'minute_missed'
        if self.visible_us - self.earliest_receipt_us >= limits.receipt_age_us:
            return 'receipt_age_at_visibility'
        return 'eligible_fixture'


def max_body_lower_bound(limits):
    """Raw and base64 bytes alone. Actual charge includes further metadata."""
    return sum(limits.bodies) + sum(4 * rounded_up(size, 3) for size in limits.bodies)


def forecast(minutes, interval, control_reserve, limits):
    unsigned(minutes, interval, control_reserve)
    if not minutes or not interval or not control_reserve:
        raise ValueError('positive minutes, illustrative renewal cadence and reserve required')
    fences = rounded_up(minutes * 60, interval)
    per_packet = max_body_lower_bound(limits)
    maximum_body_admitted = min(limits.packet_results,
        (limits.hot_result_bytes - limits.pre_io_bytes) // per_packet + 1)
    return {
        'planning_assumptions': 'one successful original trio per minute, no failed packets or economic writes',
        'minutes': minutes,
        'minimum_source_positions': minutes * 4,
        'prepared_allocated_ids': minutes * 11,
        'provider_records': minutes * 3,
        'naive_dependency_views': minutes * 20,
        'price_requests': minutes,
        'rpc_requests': minutes * 2,
        'illustrative_fence_positions': fences,
        'illustrative_other_event_reserve': control_reserve,
        'supplied_inventory_margin': limits.supplied_inventory - minutes * 4 - fences - control_reserve,
        'provider_body_envelope_bytes': minutes * sum(limits.bodies),
        'hot_result_charge_lower_bound_for_maximum_bodies': per_packet,
        'max_admitted_maximum_body_packets_without_eviction': maximum_body_admitted,
        'uniform_hot_charge_ceiling_for_last_attempt': (
            (limits.hot_result_bytes - limits.pre_io_bytes) // (minutes - 1) if minutes > 1 else None),
    }


def main():
    limits, pins = source_limits()
    result = {
        'kind': 'offline-synthetic-capacity-fault-worksheet',
        'source_sha256': pins,
        'source_limits': asdict(limits),
        'forecasts': [forecast(minutes, cadence, 32, limits)
                      for minutes in (915, 945) for cadence in (120, 180, 300)],
        'runtime_admission': False,
    }
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
