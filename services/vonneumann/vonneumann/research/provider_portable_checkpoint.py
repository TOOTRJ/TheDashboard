"""Portable-period provider GA v2 components; no decoder or durable admission.

Pinned fork of provider_checkpoint.py at PR96; old components remain unchanged.

The original v5 capture remains unchanged. Hashes bind canonical numeric wire,
not PostgreSQL JSONB text, provider authenticity or authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
import hashlib
import json
import re

from ..core import exact_rehearsal as base
from . import provider_portable_ga_model as kernel
from . import provider_source as source
from . import numeric_wire as numbers
from ..core.decimal_execution import EntryPlan
from ..core.evaluation import EVALUATION_POLICY
from ..core.optimizer_evidence import validate_optimizer_evidence
from ..db import lifecycle_protocol as model
from ..db import provider_protocol as provider
from ..db.command_protocol import (
    CommandValidationError, MAX_BIGINT, _keys, bounded_integer, canonical_json,
    canonical_uuid,
)
from ..db.provider_protocol import validate_transition
from .checkpoint_reference import jsonb_text_bytes

FORMAT = 'ga-portable-provider-checkpoint-research-v2'
COMPONENT_FORMAT = 'ga-portable-provider-component-research-v2'
HASH_POLICY = 'tagged-numeric-json-utf8-sha256-research-v1'
MAX_MANIFEST_BYTES = 65536
MAX_COMPONENT_BYTES = 196608
MAX_RESOLVED_BYTES = 262144
MAX_COMPONENTS = 11  # configuration, optimizer, cohort and eight genomes
MAX_NODES = 20000
MAX_DEPTH = 64
MAX_STRING_BYTES = 16384
_KINDS = {'configuration', 'optimizer', 'cohort', 'genome'}
_ENGINE_MUTABLE = {'generation', 'last_quote', 'decision_timestamp', 'ema', 'lifecycle', 'cohort_source'}
_MEMBER_MUTABLE = {'id', 'name', 'cursor', 'pending', 'num_trades', 'peak_equity',
                   'max_drawdown', 'terminal', 'assessment'}


def _require(condition, message):
    if not condition:
        raise CommandValidationError(message)


def _safe(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except CommandValidationError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeError,
                OverflowError, RecursionError):
            raise CommandValidationError('Active checkpoint evidence is invalid') from None
    return wrapped


def _bounded(value):
    """Bound traversal/allocation before calling the ordinary JSON encoder."""
    visits, budget, active = 0, 0, set()

    def visit(item, depth=0):
        nonlocal visits, budget
        visits += 1
        budget += 8
        _require(visits <= MAX_NODES and depth <= MAX_DEPTH and
                 budget <= MAX_RESOLVED_BYTES, 'Active format exceeds structural budget')
        kind = type(item)
        if kind is str:
            _require(len(item) <= MAX_STRING_BYTES and '\x00' not in item,
                     'Active format string exceeds capacity')
            try:
                size = len(item.encode('utf-8'))
            except UnicodeError:
                raise CommandValidationError('Active format string is invalid') from None
            _require(size <= MAX_STRING_BYTES, 'Active format string exceeds capacity')
            budget += size
        elif item is None or kind is bool:
            pass
        elif kind is int:
            _require(item.bit_length() <= 256, 'Active format integer exceeds capacity')
            budget += len(str(item))
        else:
            _require(kind in (dict, list) and len(item) <= 4096 and id(item) not in active,
                     'Active format requires bounded acyclic exact JSON')
            active.add(id(item))
            if kind is dict:
                for key, child in item.items():
                    _require(type(key) is str, 'Active format keys must be strings')
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            active.remove(id(item))
        _require(budget <= MAX_RESOLVED_BYTES, 'Active format exceeds structural budget')

    visit(value)
    return value


def _scope(owner, run):
    canonical_uuid(owner); canonical_uuid(run)


def _slot(kind, entity, generation):
    _require(type(kind) is str and kind in _KINDS, 'Unknown component kind')
    bounded_integer(generation, minimum=0, maximum=kernel.MAX_GENERATION)
    if kind == 'genome':
        canonical_uuid(entity)
    else:
        _require(entity == kind, 'Component entity differs from its typed slot')
    _require(kind != 'configuration' or generation == 0,
             'Immutable configuration cannot change generation')


@dataclass(frozen=True, slots=True)
class TypedComponent:
    """Opaque immutable JSON block; constructing it does not grant authority."""
    _wire: bytes

    def __post_init__(self):
        self._checked_value()

    def _checked_value(self):
        """One bounded decode/shape audit per use; hashes need no second decode."""
        _require(type(self._wire) is bytes and len(self._wire) <= MAX_COMPONENT_BYTES,
                 'Component wire exceeds capacity')
        try:
            value = numbers.decode(self._wire, maximum=MAX_COMPONENT_BYTES)
            _bounded(value)
            _keys(value, {'format', 'hash_policy', 'owner_id', 'run_id', 'kind',
                          'entity_id', 'generation', 'body'})
            _require(value['format'] == COMPONENT_FORMAT and value['hash_policy'] == HASH_POLICY,
                     'Unknown component format/hash policy')
            _scope(value['owner_id'], value['run_id'])
            _slot(value['kind'], value['entity_id'], value['generation'])
            _require(type(value['body']) is dict, 'Typed component body must be an object')
            _require(numbers.encode(value, maximum=MAX_COMPONENT_BYTES) == self._wire and
                     jsonb_text_bytes(value) <= MAX_COMPONENT_BYTES,
                     'Component encoding is noncanonical or exceeds capacity')
            return value
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as error:
            if isinstance(error, CommandValidationError):
                raise
            raise CommandValidationError('Invalid typed component') from None

    @classmethod
    def make(cls, owner, run, kind, entity, generation, body):
        _scope(owner, run); _slot(kind, entity, generation)
        value = {'format': COMPONENT_FORMAT, 'hash_policy': HASH_POLICY,
                 'owner_id': owner, 'run_id': run, 'kind': kind,
                 'entity_id': entity, 'generation': generation, 'body': body}
        return cls(numbers.encode(_bounded(value), maximum=MAX_COMPONENT_BYTES))

    @property
    def identity(self):
        return hashlib.sha256(self._wire).hexdigest()

    def to_dict(self):
        return self._checked_value()

    def reference(self):
        value = self.to_dict()
        return {key: value[key] for key in ('kind', 'entity_id', 'generation')} | {
            'sha256': self.identity}


@_safe
def resolve_manifest(manifest, components, *, owner_id, run_id, revision):
    """Resolve flat JSON evidence only. SQL must still validate ledger/authority.

    No optimizer object, RNG, runtime state or lease is constructed. The caller
    supplies the expected checkpoint revision; it is never taken on trust from
    the manifest. Unknown, extra, unavailable, foreign or substituted blocks
    fail closed. Hashes authenticate bytes under the pinned local encoding, not
    PostgreSQL JSONB text or a provider response's authenticity.
    """
    _scope(owner_id, run_id)
    bounded_integer(revision, minimum=2, maximum=MAX_BIGINT)
    _bounded(manifest)
    _require(jsonb_text_bytes(manifest) <= MAX_MANIFEST_BYTES,
             'Active manifest exceeds capacity')
    _keys(manifest, {'format', 'source_model_version', 'owner_id', 'run_id',
                     'revision', 'status', 'reserve', 'accounts', 'positions',
                     'engine', 'source', 'components'})
    _require(manifest['format'] == FORMAT and manifest['source_model_version'] == kernel.MODEL_FORMAT and manifest['owner_id'] == owner_id
             and manifest['run_id'] == run_id and type(manifest['revision']) is int
             and manifest['revision'] == revision, 'Active manifest binding differs')
    refs = manifest['components']
    _require(type(refs) is list and len(refs) == MAX_COMPONENTS and
             type(components) is tuple and len(components) == MAX_COMPONENTS,
             'Complete bounded component set required')
    blocks = {}
    aggregate_bytes = len(numbers.encode(manifest, maximum=MAX_MANIFEST_BYTES))
    for block in components:
        _require(type(block) is TypedComponent, 'Only immutable typed components are supported')
        value = block._checked_value()
        aggregate_bytes += len(block._wire)
        _require(aggregate_bytes <= MAX_RESOLVED_BYTES,
                 'Component aggregate exceeds capacity before resolution')
        _require(value['owner_id'] == owner_id and value['run_id'] == run_id,
                 'Component owner/run differs')
        _require(block.identity not in blocks, 'Repeated component identity')
        blocks[block.identity] = value
    result = json.loads(canonical_json(manifest))
    engine = result['engine']
    _keys(engine, _ENGINE_MUTABLE | {'members'})
    # Fresh policy is explicit; this never relaxes the original v5 validator.
    bounded_integer(engine['generation'], minimum=0, maximum=kernel.MAX_GENERATION)
    members = engine['members']
    _require(type(members) is list and len(members) == 8,
             'Active state requires all eight original members')
    ids = []
    for member in members:
        _keys(member, _MEMBER_MUTABLE)
        ids.append(canonical_uuid(member['id']))
    _require(len(set(ids)) == 8, 'Active membership repeats an identity')
    slots, resolved_ids = {}, set()
    for ref in refs:
        _keys(ref, {'kind', 'entity_id', 'generation', 'sha256'})
        _slot(ref['kind'], ref['entity_id'], ref['generation'])
        digest = ref['sha256']
        _require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None
                 and digest in blocks and digest not in resolved_ids,
                 'Component is unavailable, duplicated or has an invalid digest')
        resolved_ids.add(digest)
        block = blocks[digest]
        _require(all(block[key] == ref[key] and type(block[key]) is type(ref[key])
                     for key in ('kind', 'entity_id', 'generation')),
                 'Component differs from its typed reference')
        expected_generation = 0 if ref['kind'] == 'configuration' else engine['generation']
        _require(ref['generation'] == expected_generation, 'Component generation differs')
        slot = (ref['kind'], ref['entity_id'])
        _require(slot not in slots, 'Repeated component slot')
        slots[slot] = block['body']
    _require(set(slots) == {('configuration', 'configuration'), ('optimizer', 'optimizer'),
                            ('cohort', 'cohort')} | {('genome', identity) for identity in ids},
             'Component slots omit or invent active evidence')
    engine['config'] = slots['configuration', 'configuration']
    engine['optimizer'] = slots['optimizer', 'optimizer']
    engine['cohort'] = slots['cohort', 'cohort']
    for member in members:
        member['genome'] = slots['genome', member['id']]
    result.pop('components')
    _bounded(result)
    _require(len(numbers.encode(result)) <= MAX_RESOLVED_BYTES and jsonb_text_bytes(result) <= MAX_RESOLVED_BYTES,
             'Resolved active aggregate exceeds capacity')
    _require(engine['config'].get('strategy') == 'genetic_algorithm'
             and engine['cohort'].get('member_ids') == ids,
             'Only the complete GA cohort is supported')
    config = kernel._configuration(result)
    _require(result['status'] in {'running', 'paused', 'risk_halted', 'stopped', 'failed'},
             'Unsupported active lifecycle status')
    ema = engine['ema']
    _keys(ema, {'count', 'last_end', 'closes', 'values', 'previous'})
    count = bounded_integer(ema['count'], minimum=61, maximum=MAX_BIGINT - 1)
    _require(type(ema['closes']) is list and len(ema['closes']) == min(64, count),
             'Completed close retention differs')
    base._stamp(ema['last_end'])
    for close in ema['closes']:
        base._amount(close, base.PRICE_SCALE, positive=True)
    for key in ('values', 'previous'):
        _require(type(ema[key]) is dict and set(ema[key]) == {str(period) for period in range(2, 61)},
                 'Indicator periods differ from the fixed profile')
        for value in ema[key].values(): model._hex(value, positive=True)
    if engine['decision_timestamp'] is not None:
        base._stamp(engine['decision_timestamp'])
        _require(engine['last_quote'] is not None and engine['decision_timestamp'] <= engine['last_quote']['timestamp'],
                 'Decision cursor exceeds its observed quote')
    for member in members:
        genome = member['genome']
        for gene in base.NUMERIC_GENES:
            model._hex(genome[gene])
        base._genome(genome, config.colony_config())
        _require(type(genome['generation']) is int and genome['generation'] == engine['generation']
                 and genome['assets'] == [config.asset] and type(genome['parent_ids']) is list
                 and len(genome['parent_ids']) <= 2 and len(set(genome['parent_ids'])) == len(genome['parent_ids']),
                 'Genome belongs to another generation/profile or repeats parents')
        for parent in genome['parent_ids']:
            _require(canonical_uuid(parent) != member['id'], 'Genome cannot be its own parent')
        name = member['name']
        _require(type(name) is str and 0 < len(name.encode('utf-8')) <= 128
                 and name.isprintable() and name == name.strip(), 'Invalid active member name')
        bounded_integer(member['num_trades'], minimum=0, maximum=MAX_BIGINT - 1)
        base._amount(member['peak_equity'], positive=True)
        ratio = member['max_drawdown']
        _keys(ratio, {'numerator', 'denominator'})
        for number in ratio.values():
            _require(type(number) is str and 1 <= len(number) <= 75 and number.isascii()
                     and number.isdigit() and str(int(number)) == number, 'Invalid exact drawdown ratio')
        _require(0 <= int(ratio['numerator']) <= int(ratio['denominator'])
                 and int(ratio['denominator']) > 0, 'Drawdown ratio is outside its range')
        if member['cursor'] is not None:
            base._stamp(member['cursor'])
            _require(engine['ema']['last_end'] is not None and member['cursor'] <= engine['ema']['last_end'],
                     'Member cursor exceeds completed history')
        terminal = member['terminal']
        if terminal is not None:
            _keys(terminal, {'reason', 'at', 'cash'})
            _require(terminal['reason'] == 'drawdown' and member['pending'] is None,
                     'Unsupported terminal member policy')
            base._stamp(terminal['at']); base._amount(terminal['cash'])
    validate_optimizer_evidence(engine['optimizer'])
    _require(engine['optimizer']['strategy'].get('class') == 'GeneticAlgorithmStrategy',
             'Non-GA optimizer evidence is unsupported')
    accounts = result['accounts']
    _require(type(accounts) is list and len(accounts) == 8, 'Active accounts omit a cohort member')
    for account in accounts:
        _keys(account, {'id', 'cash', 'initial_cash', 'retired'})
        _require(canonical_uuid(account['id']) in ids, 'Account is outside active membership')
        base._amount(account['cash']); base._amount(account['initial_cash'], positive=True)
        _require(account['initial_cash'] == config.seed_capital, 'Account seed capital differs')
        member = members[ids.index(account['id'])]
        _require(type(account['retired']) is bool and account['retired'] == (member['terminal'] is not None)
                 and (not account['retired'] or account['cash'] == '0'),
                 'Early terminal account/evidence differs')
    _require([a['id'] for a in accounts] == sorted(ids), 'Active accounts repeat or reorder identities')
    base._amount(result['reserve'])
    positions = result['positions']
    _require(type(positions) is list and len(positions) <= 8,
             'Open positions exceed active capacity')
    position_ids, held = [], set()
    for position in positions:
        _keys(position, {'id', 'account_id', 'asset', 'entry', 'exit', 'closed'})
        position_ids.append(canonical_uuid(position['id']))
        _require(position['account_id'] in ids and position['account_id'] not in held
                 and members[ids.index(position['account_id'])]['terminal'] is None
                 and position['closed'] is False and position['exit'] is None,
                 'Open position is duplicated, terminal or outside active membership')
        held.add(position['account_id'])
        plan = EntryPlan.from_dict(position['entry'])
        _require(position['asset'] == config.asset and plan.config == config.execution,
                 'Open position execution/profile differs')
    _require(position_ids == sorted(set(position_ids)) and not set(position_ids).intersection(ids),
             'Position identities overlap or repeat')
    for member in members:
        pending = member['pending']
        if pending is None:
            continue
        _keys(pending, {'action', 'signal_at', 'position_id'})
        base._stamp(pending['signal_at'])
        _require(member['cursor'] is not None and member['cursor'] <= pending['signal_at'] <= member['cursor'] + 900
                 and engine['decision_timestamp'] is not None
                 and pending['signal_at'] <= engine['decision_timestamp'], 'Pending decision time differs')
        opened = next((p for p in positions if p['account_id'] == member['id']), None)
        _require((pending['action'] == 'entry' and pending['position_id'] is None and opened is None)
                 or (pending['action'] == 'exit' and opened is not None and pending['position_id'] == opened['id']),
                 'Pending decision differs from the active position')
    cohort = engine['cohort']
    _keys(cohort, {'policy', 'iteration_id', 'phase', 'member_ids', 'member_count',
                  'completed_count', 'horizon_seconds', 'started_at', 'ends_at',
                  'completed_at', 'abort_reason', 'evaluations'})
    _require(canonical_json(cohort['policy']) == canonical_json(EVALUATION_POLICY)
             and cohort['iteration_id'] == f'{run_id}:{engine["generation"]}'
             and type(cohort['member_count']) is int and cohort['member_count'] == 8
             and cohort['phase'] in {'warming', 'evaluating', 'completed', 'aborted'}
             and model._float_record(cohort['horizon_seconds']) == 3600,
             'Unsupported cohort identity/policy')
    _require(type(cohort['evaluations']) is list and len(cohort['evaluations']) <= 8,
             'Too many terminal results')
    start, end, complete = (None if cohort[key] is None else model._float_record(cohort[key])
                           for key in ('started_at', 'ends_at', 'completed_at'))
    phase = cohort['phase']
    _require((start is None) == (end is None) and (start is None or 0 <= start <= 2**40 and end == start + 3600),
             'Common window time differs')
    _require((phase == 'warming' and start is None and complete is None)
             or (phase == 'evaluating' and start is not None and complete is None)
             or (phase == 'completed' and start is not None and complete is not None and complete >= end)
             or (phase == 'aborted' and complete is not None and complete >= (start or 0)),
             'Common window phase/time differs')
    _require((phase == 'aborted' and cohort['abort_reason'] in {'paused', 'stopped', 'risk_halted'})
             or (phase != 'aborted' and cohort['abort_reason'] is None), 'Common window interruption differs')
    _require(phase not in {'completed', 'aborted'} or len(cohort['evaluations']) == 8,
             'Finished cohort must account for all eight members')
    recorded_ids = []
    for row in cohort['evaluations']:
        _keys(row, {'probe_id', 'evaluation_id', 'iteration_id', 'fitness', 'roi',
                    'num_trades', 'reason', 'status', 'cohort_complete',
                    'window_started_at', 'window_ends_at', 'terminated_at'})
        _require(row['probe_id'] in ids, 'Foreign terminal result')
        identity = row['probe_id']; recorded_ids.append(identity)
        _require(row['evaluation_id'] == f'{cohort["iteration_id"]}:{ids.index(identity)}'
                 and row['iteration_id'] == cohort['iteration_id']
                 and row['window_started_at'] == cohort['started_at']
                 and row['window_ends_at'] == cohort['ends_at'], 'Terminal result binding differs')
        at = model._float_record(row['terminated_at'])
        _require((start is None or at >= start) and 0 <= at <= 2**40
                 and type(row['cohort_complete']) is bool and row['cohort_complete'] == (phase == 'completed'),
                 'Terminal result completion/time differs')
        bounded_integer(row['num_trades'], minimum=0, maximum=MAX_BIGINT - 1)
        if row['status'] == 'aborted':
            _require(phase == 'aborted' and row['reason'] == cohort['abort_reason'] and at == complete
                     and row['fitness'] is None and row['roi'] is None and row['num_trades'] == 0,
                     'Aborted result cannot carry an invented assessment')
        else:
            _require(row['status'] == 'completed' and row['reason'] in {'drawdown', 'window_complete'}
                     and phase != 'warming' and start is not None, 'Invalid terminal result status')
            model._float_record(row['fitness']); model._float_record(row['roi'])
            _require((row['reason'] == 'window_complete' and phase == 'completed' and at == complete)
                     or (row['reason'] == 'drawdown' and next(a for a in accounts if a['id'] == identity)['retired']),
                     'Premature or unretired terminal assessment')
    _require(recorded_ids == [identity for identity in ids if identity in recorded_ids]
             and len(set(recorded_ids)) == len(recorded_ids)
             and type(cohort['completed_count']) is int
             and cohort['completed_count'] == sum(r['status'] == 'completed' for r in cohort['evaluations']),
             'Terminal results omit unique order or count')
    # Primitive mirror/RNG/phenotype audits do not establish historical
    # uniqueness or closed-fill counts. Those require the locked SQL contract.
    projected = json.loads(canonical_json(result))
    projected.pop('format'); projected.pop('source_model_version')
    projected['version'] = 1
    projected['engine']['used_ids'] = ids + position_ids
    trip = engine['lifecycle']['risk']['trip_id']
    if trip is not None:
        _require(trip not in ids and trip not in position_ids, 'Trip identity overlaps an active economic identity')
        projected['engine']['used_ids'].append(canonical_uuid(trip))
    _source_state(projected)
    _lifecycle_state(projected)
    # This checks typed completeness, not the new economic transition contract.
    # Capture below additionally requires byte equality with the admitted source.
    return result


class ActiveCheckpoint:
    """Detached capture, not an ExactState or receipt. No public constructor."""
    __slots__ = ('__wire', '__components', '__expected')

    def __init__(self, *args, **kwargs):
        raise CommandValidationError('Capture an owned candidate first')

    def __setattr__(self, name, value):
        raise AttributeError('ActiveCheckpoint is immutable')

    def to_dict(self):
        return numbers.decode(self.__wire, maximum=MAX_MANIFEST_BYTES)

    @property
    def components(self):
        return self.__components

    @property
    def manifest_bytes(self):
        return len(self.__wire)

    @property
    def resolved_bytes(self):
        return jsonb_text_bytes(json.loads(self.__expected))

    def resolve(self):
        manifest = self.to_dict()
        result = resolve_manifest(manifest, self.components, owner_id=manifest['owner_id'],
            run_id=manifest['run_id'], revision=manifest['revision'])
        _require(canonical_json(result) == self.__expected,
                 'Active capture differs from its owned original evidence')
        return result


def capture_owned_candidate(candidate):
    """Capture owned fresh evidence; no history deletion or commit authority."""
    _require(type(candidate) is kernel.GACandidate, 'Owned fresh provider GA candidate required')
    candidate.__post_init__()
    original = json.loads(candidate._wire)
    _keys(original, {'format', 'operations', 'history', 'transition'})
    _require(original['format'] == kernel.COMMAND_FORMAT, 'Fresh provider command required')
    state = candidate.state.to_dict()
    before = original['transition']['before']
    _require(original['transition']['after'] == state, 'Owned candidate state differs')
    engine = state['engine']
    _require(engine['config']['strategy'] == 'genetic_algorithm', 'GA-only active format')
    members = engine['members']
    ids = {member['id'] for member in members}
    _require({a['id'] for a in state['accounts'] if not a['retired']} <= ids
             and all(a['cash'] == '0' for a in state['accounts'] if a['id'] not in ids)
             and all(p['account_id'] in ids for p in state['positions'] if not p['closed']),
             'Active pruning would omit a live ledger account or holding')
    owner, run, generation = state['owner_id'], state['run_id'], engine['generation']
    components = tuple([
        TypedComponent.make(owner, run, 'configuration', 'configuration', 0, engine['config']),
        TypedComponent.make(owner, run, 'optimizer', 'optimizer', generation, engine['optimizer']),
        TypedComponent.make(owner, run, 'cohort', 'cohort', generation, engine['cohort']),
    ] + [TypedComponent.make(owner, run, 'genome', member['id'], generation, member['genome'])
         for member in members])
    manifest = {key: state[key] for key in ('owner_id', 'run_id', 'revision', 'status', 'reserve', 'source')}
    manifest.update(format=FORMAT, source_model_version=kernel.MODEL_FORMAT,
        accounts=[a for a in state['accounts'] if a['id'] in ids],
        positions=[p for p in state['positions'] if not p['closed']],
        engine={key: engine[key] for key in _ENGINE_MUTABLE},
        components=[component.reference() for component in components])
    manifest['engine']['members'] = [{key: member[key] for key in _MEMBER_MUTABLE} for member in members]
    # Expected projection comes directly from the source, independently of the
    # reference resolver, so an omitted or substituted field cannot pass capture.
    expected = {key: value for key, value in manifest.items() if key != 'components'}
    expected = json.loads(canonical_json(expected))
    expected['engine'].update(config=engine['config'], optimizer=engine['optimizer'], cohort=engine['cohort'])
    expected['engine']['members'] = members
    resolved = resolve_manifest(manifest, components, owner_id=owner, run_id=run, revision=state['revision'])
    _require(canonical_json(resolved) == canonical_json(expected), 'Active format loses original evidence')
    value = object.__new__(ActiveCheckpoint)
    object.__setattr__(value, '_ActiveCheckpoint__wire', numbers.encode(manifest, maximum=MAX_MANIFEST_BYTES))
    object.__setattr__(value, '_ActiveCheckpoint__components', components)
    object.__setattr__(value, '_ActiveCheckpoint__expected', canonical_json(expected))
    return value


def component_updates(previous, following):
    """Diff two owned captures only; NOT proof of server component retention."""
    _require(type(previous) is ActiveCheckpoint and type(following) is ActiveCheckpoint,
             'Owned captures required for component comparison')
    old, new = previous.resolve(), following.resolve()
    _require(old['owner_id'] == new['owner_id'] and old['run_id'] == new['run_id']
             and old['revision'] < new['revision'], 'Component comparison scope/revision differs')
    retained = {component.identity for component in previous.components}
    return tuple(component for component in following.components if component.identity not in retained)


def _source_state(state):
    src, engine = state['source'], state['engine']
    source.validate_source_state(src, epoch=engine['config']['source_policy']['epoch'])
    frame = src['last_quote']
    quote = None if frame is None else {'timestamp': frame['decision_second'], 'price': frame['quote']['price']}
    _require(engine['last_quote'] == quote, 'Reference quote differs from original provider frame')
    _require(engine['ema']['last_end'] == src['bars'][-1][0]
             and engine['ema']['closes'] == [bar[1] for bar in src['bars']],
             'Source and indicator history differ')
    if frame is None:
        _require(src['quote_sequence'] == 0 and engine['decision_timestamp'] is None
                 and engine['ema'] == provider._seed_ema(src['bars']), 'Bootstrap source differs')
    for member in engine['members']:
        frozen = member['assessment']
        # A risk halt aborts the cohort BEFORE protective liquidation/retirement.
        # Members that become terminal afterward have no scored evaluation to
        # freeze. Earlier scored terminals must retain their original snapshot.
        scored_terminal = any(row['probe_id'] == member['id']
            and row['status'] == 'completed' and row['reason'] == 'drawdown'
            for row in engine['cohort']['evaluations'])
        _require((frozen is not None) == scored_terminal
                 and (frozen is None or member['terminal'] is not None),
                 'Early terminal snapshot differs')
        if frozen is not None:
            _require(frozen['closed_trade_count'] == member['num_trades']
                     and frozen['max_drawdown'] == member['max_drawdown']
                     and not frozen['has_open_position'] and frozen['terminal_cash'] == member['terminal']['cash'],
                     'Frozen terminal economics differ')

def _lifecycle_state(state):
    engine, cfg = state['engine'], state['engine']['config']
    life = engine['lifecycle']
    _keys(life, {'search_epoch','restart_required','signals_after','last_control_at','risk'})
    bounded_integer(life['search_epoch'], minimum=0, maximum=engine['generation'])
    _require(type(life['restart_required']) is bool, 'Restart flag must be explicit')
    for key in ('signals_after','last_control_at'):
        if life[key] is not None: model._timestamp(life[key])
    risk = life['risk']
    _keys(risk, {'active','baseline_equity','observed_equity','observed_at','trip_id','tripped_at',
        'trip_equity','recovery_count','last_recovered_at'})
    _require(type(risk['active']) is bool and risk['baseline_equity'] == cfg['initial_cash'],
        'Risk must retain its original account capital baseline')
    model._amount(risk['observed_equity']); model._timestamp(risk['observed_at'])
    bounded_integer(risk['recovery_count'], minimum=0, maximum=MAX_BIGINT - 1)
    if risk['trip_id'] is None:
        _require(not risk['active'] and risk['tripped_at'] is None and risk['trip_equity'] is None
            and risk['recovery_count'] == 0 and risk['last_recovered_at'] is None, 'Missing trip evidence')
    else:
        _require(canonical_uuid(risk['trip_id']) in engine['used_ids'], 'Trip identity was not allocated')
        model._timestamp(risk['tripped_at']); model._amount(risk['trip_equity'])
        _require(model._below(risk['trip_equity'], cfg), 'Recorded risk trip did not cross the original threshold')
        if risk['last_recovered_at'] is not None: model._timestamp(risk['last_recovered_at'])
    _require((not risk['active'] or state['status'] in {'risk_halted','stopped'}) and
        (state['status'] != 'risk_halted' or risk['active']), 'Risk latch disagrees with lifecycle status')
    _require(life['restart_required'] == (engine['cohort']['phase'] == 'aborted'),
        'Interrupted cohort requires a fresh unscored restart')
    _require(not risk['active'] or all(m['pending'] is None or m['pending']['action'] != 'entry'
        for m in engine['members']), 'Risk halt retained an entry intent')
    strategy, cohort = model._optimizer_views(engine['optimizer'])
    mirror = engine['cohort']
    for key in ('iteration_id','phase','horizon_seconds','started_at','ends_at','completed_at','abort_reason','member_ids'):
        _require(model._same(cohort[key], mirror[key]), 'Cohort mirror differs from actual optimizer evidence')
    results = cohort['_evaluations']
    _require(set(results) == {r['probe_id'] for r in mirror['evaluations']}, 'Optimizer cohort omits terminal evidence')
    if mirror['phase'] == 'evaluating':
        _require({r['probe_id'] for r in mirror['evaluations']} ==
                 {m['id'] for m in engine['members'] if m['terminal'] is not None},
                 'Active cohort must freeze every early terminal member')
    for row in mirror['evaluations']:
        saved = results[row['probe_id']]
        _require(model._same({key: saved[key] for key in row}, row), 'Optimizer frozen result differs from cohort mirror')
    _require(strategy['_search_epoch'] == life['search_epoch'], 'Solver search epoch differs from lifecycle')
    for member in engine['members']:
        expected = dict(member['genome'])
        for key,value in expected.items():
            if type(value) is str: expected[key] = {'float64': value}
        _require(model._same(cohort['_genomes'][member['id']], expected), 'Optimizer cohort phenotype differs from its member')
        _require(cohort['_evaluation_ids'][member['id']] == f'{mirror["iteration_id"]}:{mirror["member_ids"].index(member["id"])}',
            'Optimizer evaluation identity differs from its slot')



TRANSPORT_FORMAT = 'ga-portable-provider-compact-command-research-v2'
STOP_RESERVE_BYTES = 65536  # extra capacity below the ordinary 192 KiB command cap
ORDINARY_COMMAND_BYTES = MAX_RESOLVED_BYTES - STOP_RESERVE_BYTES


def prepare_transport(candidate, following, *, command_id, previous=None):
    """Complete compact research request, never a native/SQL command or receipt.

    The prior digest is a client evidence reference, not server authority.
    Changed blocks require durable server retention/readback in PAPER-COMPACT-03.
    All blocks and the resolved model are separately charged before encoding.
    """
    canonical_uuid(command_id)
    _require(type(candidate) is kernel.GACandidate and type(following) is ActiveCheckpoint,
             'Owned provider candidate/capture required')
    candidate.__post_init__()
    following_state = following.resolve()
    following_state.pop('format'); following_state.pop('source_model_version')
    following_state['version'] = kernel.MODEL_FORMAT
    _require(following_state == candidate.state.to_dict(), 'Capture differs from candidate')
    before = candidate.transition['before']
    if previous is None:
        _require(before is None, 'Missing prior owned checkpoint')
        changes, prior = following.components, None
    else:
        _require(type(previous) is ActiveCheckpoint, 'Prior owned checkpoint required')
        prior_state = previous.resolve()
        prior_state.pop('format'); prior_state.pop('source_model_version'); prior_state['version'] = kernel.MODEL_FORMAT
        _require(prior_state == before, 'Prior checkpoint evidence differs')
        retained = {block.identity for block in previous.components}
        changes = tuple(block for block in following.components if block.identity not in retained)
        prior = {'revision': before['revision'], 'sha256': hashlib.sha256(numbers.encode(previous.to_dict())).hexdigest()}
    body = {'format': TRANSPORT_FORMAT, 'command_id': command_id,
        'owner_id': candidate.state.to_dict()['owner_id'], 'run_id': candidate.state.to_dict()['run_id'],
        'prior': prior, 'checkpoint': following.to_dict(), 'components': [block.to_dict() for block in changes],
        'operations': candidate.operations, 'history': candidate.history,
        'evidence': candidate.transition['evidence'], 'events': candidate.transition['events']}
    control = body['evidence']['control']
    is_stop = control is not None and control['action'] == 'stop'
    maximum = MAX_RESOLVED_BYTES if is_stop else ORDINARY_COMMAND_BYTES
    wire = numbers.encode(body, maximum=maximum)
    # PostgreSQL stores tagged JSON, while a future numeric validator sees the
    # decoded primitive values. Charge both whole forms; neither is a SQL ACK.
    expanded = len(json.dumps(numbers.decode(wire), sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(', ', ': ')).encode('utf-8'))
    _require(jsonb_text_bytes(json.loads(wire)) <= maximum and expanded <= maximum,
             'Complete expanded command exceeds capacity')
    return wire
