"""Fresh owned prospective Jupiter two-EMA GA research kernel.

The reviewed GA/economic algorithms are ported into this independent engine.
No old model is imported, inherited, bootstrapped, relabelled or cast. Source
witnesses and supplied clocks remain research evidence, never native authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from copy import deepcopy
from fractions import Fraction
import hashlib
import math
from types import SimpleNamespace, MappingProxyType
from uuid import UUID

from ..core.decimal_execution import (CASH_SCALE, PRICE_SCALE, DecimalExecutionConfig,
    EntryPlan, ExitPlan, _units, _text, debit_cash, credit_cash, mark_value)
from ..core.evaluation import EvaluationCohort
from ..core.evolution import compute_fitness, FITNESS_POLICY
from ..core.genome import Genome, NUMERIC_GENES, random_genome
from ..core.lineage import BirthLineage, SourceBinding as LineageSourceBinding, lineage_plan_from_evolution
from ..core.optimizer_evidence import encode_optimizer_evidence
from ..core.search_random import SearchRandomStreams
from ..core.signal_profile import EMA_WARMUP_BARS, ema_crossing
from ..core.strategy_fork import fork_strategy, fork_evaluation
from ..core.strategies.genetic_algorithm import GeneticAlgorithmStrategy
from ..core import integer_period_mutation as period_mutation
from ..market import provider_acquisition_v3 as acquisition, prospective_source_v3 as source
from . import numeric_wire as numbers
from .prospective_ga_v3_policy import (V3Config, V3Inputs, SourceBinding, PaperFillPolicy, ModelError,
    CapacityError, PROFILE, MODEL_FORMAT, COMMAND_FORMAT, ASSESSMENT_FORMAT, AUTHORITY,
    POPULATION, BAR_SECONDS, HORIZON_SECONDS, MAX_COUNTER, MAX_GENERATION, MAX_PAYLOAD_BYTES,
    counter, require)

SOURCE_POLICY = source.POLICY_SHA256

def _json(value): return numbers.encode(value)
def _configuration(data): return V3Config.from_dict(data['engine']['config'])


@dataclass(frozen=True, slots=True)
class ModelObservation:
    timestamp: int
    price: str
    candle_end: int | None = None
    candle_close: str | None = None
    def __post_init__(self):
        counter(self.timestamp, 2**40); _amount(self.price, PRICE_SCALE, True)
        if self.candle_end is None:
            require(self.candle_close is None)
        else:
            counter(self.candle_end, acquisition.MAX_SECOND)
            require(self.candle_end % BAR_SECONDS == 0 and self.candle_end <= self.timestamp)
            _amount(self.candle_close, PRICE_SCALE, True)
    def to_dict(self):
        self.__post_init__()
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


class V3State:
    """Fresh private engine only; old states, dictionaries and DTOs cannot enter."""
    __slots__ = ('__wire', '__strategy', '__cohort')
    def __init__(self, *args, **kwargs): raise ModelError()
    def __setattr__(self, key, value): raise AttributeError('Research state is immutable')
    @classmethod
    def _seal(cls, data, strategy, cohort):
        require(type(strategy) is GeneticAlgorithmStrategy and type(cohort) is EvaluationCohort)
        result = object.__new__(cls)
        object.__setattr__(result, '_V3State__wire', _json(data))
        object.__setattr__(result, '_V3State__strategy', fork_strategy(strategy))
        object.__setattr__(result, '_V3State__cohort', fork_evaluation(cohort))
        return result
    def to_dict(self): return numbers.decode(self.__wire)
    def _fork(self): return self.to_dict(), fork_strategy(self.__strategy), fork_evaluation(self.__cohort)
    @property
    def revision(self): return self.to_dict()['revision']
    @property
    def native_admission(self): return False
    @property
    def running_authority(self): return False
    def __deepcopy__(self, memo): return self


@dataclass(frozen=True, slots=True)
class V3Candidate:
    state: V3State
    _wire: bytes
    _witness: object
    def __post_init__(self):
        require(type(self.state) is V3State and type(self._wire) is bytes)
        if type(self._witness) is dict:
            object.__setattr__(self, '_witness', MappingProxyType(dict(self._witness)))
        require(type(self._witness) is MappingProxyType)
        common = {'kind', 'inputs', 'mark', 'expected_mark_sha256', 'history', 'series', 'expected_history_sha256'}
        fields = {'bootstrap': {'kind', 'config', 'history', 'series', 'expected_history_sha256', 'inputs'},
            'protective': common, 'decision': common, 'control': common | {'action', 'trip_id'},
            'epoch_rollover': {'kind', 'successor_binding', 'inputs'}}
        require(self._witness.get('kind') in fields
            and set(self._witness) == fields[self._witness['kind']]
            and type(self._witness['inputs']) is V3Inputs)
        value = numbers.decode(self._wire)
        require(value['format'] == COMMAND_FORMAT and _json(value) == self._wire
            and _json(value['transition']['after']) == _json(self.state.to_dict()))
        _configuration(value['transition']['after'])
        if value['transition']['before'] is not None: _configuration(value['transition']['before'])
        require(all(value[name] is False for name in AUTHORITY))
    @property
    def operations(self): return numbers.decode(self._wire)['operations']
    @property
    def transition(self): return numbers.decode(self._wire)['transition']
    @property
    def history(self): return numbers.decode(self._wire)['history']
    @property
    def payload_bytes(self): return len(self._wire)
    @property
    def native_admission(self): return False
    @property
    def running_authority(self): return False


class OfflineLedger:
    """Owned append-only fixture oracle, never database/source authentication."""
    def __init__(self, owner_id, run_id):
        acquisition.uuid(owner_id); acquisition.uuid(run_id)
        self.owner_id, self.run_id = owner_id, run_id
        self._current, self._owned_current = None, None
        self._identities, self._history, self._accepted = set(), [], {}
        self._acquisition_epochs = set()
        self._history_witness = None
    def check(self, before, owner, run):
        require((owner, run) == (self.owner_id, self.run_id) and _json(before) == _json(self._current))
    def used(self, identity): return identity in self._identities
    def used_epoch(self, epoch):
        acquisition.uuid(epoch); return epoch in self._acquisition_epochs
    @property
    def history(self): return [numbers.decode(row) for row in self._history]
    def accept(self, candidate):
        require(type(candidate) is V3Candidate); candidate.__post_init__()
        if candidate._wire in self._accepted: return self._accepted[candidate._wire]
        before, after = candidate.transition['before'], candidate.state.to_dict()
        self.check(before, after['owner_id'], after['run_id'])
        witness = candidate._witness; kind = witness['kind']; inputs = witness['inputs']
        if kind == 'bootstrap':
            replay = bootstrap(witness['config'], witness['history'], witness['series'],
                expected_history_sha256=witness['expected_history_sha256'], inputs=inputs, ledger=self)
        elif kind == 'protective':
            replay = prepare_protective(self._owned_current, witness['mark'],
                expected_mark_sha256=witness['expected_mark_sha256'], inputs=inputs, ledger=self)
        elif kind == 'decision':
            replay = prepare_decision(self._owned_current, witness['mark'],
                expected_mark_sha256=witness['expected_mark_sha256'], inputs=inputs, ledger=self,
                history=witness['history'], series=witness['series'],
                expected_history_sha256=witness['expected_history_sha256'])
        elif kind == 'control':
            replay = prepare_control(self._owned_current, witness['action'], inputs, ledger=self,
                mark=witness['mark'], expected_mark_sha256=witness['expected_mark_sha256'],
                history=witness['history'], series=witness['series'],
                expected_history_sha256=witness['expected_history_sha256'], trip_id=witness['trip_id'])
        elif kind == 'epoch_rollover':
            replay = prepare_epoch_rollover(self._owned_current, witness['successor_binding'], inputs, ledger=self)
        else: raise ModelError()
        require(replay._wire == candidate._wire)
        history = candidate.history; allocations = history['allocated_ids']
        require(len(set(allocations)) == len(allocations) and not any(self.used(identity) for identity in allocations))
        # Reconstruct original exact economic deltas independently of the after mirror.
        accounts = {} if before is None else {row['id']: deepcopy(row) for row in before['accounts']}
        positions = {} if before is None else {row['id']: deepcopy(row) for row in before['positions']}
        reserve = after['engine']['config']['initial_cash'] if before is None else before['reserve']
        closed, retired, allocated = [], [], []
        for op in candidate.operations:
            kind = op['kind']
            if kind == 'birth':
                identity = op['id']; require(identity not in accounts); allocated.append(identity)
                reserve = debit_cash(reserve, op['cash'])
                accounts[identity] = {'id': identity, 'cash': op['cash'], 'initial_cash': op['cash'], 'retired': False}
            elif kind == 'open':
                identity = op['id']; require(identity not in positions
                    and not any(row['account_id'] == op['account_id'] for row in positions.values()))
                allocated.append(identity); plan = EntryPlan.from_dict(op['execution'])
                accounts[op['account_id']]['cash'] = debit_cash(accounts[op['account_id']]['cash'], plan.cash_debit)
                positions[identity] = {'id': identity, 'account_id': op['account_id'], 'asset': op['asset'],
                    'entry': plan.to_dict(), 'exit': None, 'closed': False}
            elif kind == 'close':
                position = positions.pop(op['id']); plan = ExitPlan.from_dict(op['execution'])
                require(plan.entry.to_dict() == position['entry'])
                accounts[position['account_id']]['cash'] = credit_cash(accounts[position['account_id']]['cash'], plan.cash_credit)
                position.update(exit=plan.to_dict(), closed=True); closed.append(position)
            elif kind == 'retire':
                account = accounts[op['id']]
                require(not account['retired'] and not any(row['account_id'] == op['id'] for row in positions.values()))
                retired.append(deepcopy(account)); reserve = credit_cash(reserve, account['cash'])
                account.update(cash='0', retired=True)
            elif kind == 'lifecycle': require(op['status'] == after['status'])
            else: raise ModelError()
        old_trip = None if before is None else before['engine']['lifecycle']['risk']['trip_id']
        new_trip = after['engine']['lifecycle']['risk']['trip_id']
        if new_trip is not None and new_trip != old_trip: allocated.append(new_trip)
        members = {member['id'] for member in after['engine']['members']}
        require(sorted((account for identity, account in accounts.items() if identity in members), key=lambda row: row['id']) == after['accounts']
            and sorted(positions.values(), key=lambda row: row['id']) == after['positions'] and reserve == after['reserve'])
        require(sorted(closed, key=lambda row: row['id']) == history['closed_positions'])
        require(retired == [row['account'] for row in history['retired_accounts']])
        require(set(allocated) == set(allocations) and len(allocated) == len(allocations))
        epoch = after['source']['current_binding']['acquisition_epoch'] if witness['kind'] in {'bootstrap', 'epoch_rollover'} else None
        if epoch is not None: require(not self.used_epoch(epoch))
        history_wire = _json(history)
        # The owned original witness remains external to the bounded active state.
        if witness.get('history') is not None: self._history_witness = witness['history']
        if epoch is not None: self._acquisition_epochs.add(epoch)
        self._identities.update(allocations); self._history.append(history_wire)
        self._current, self._owned_current = after, candidate.state
        self._accepted[candidate._wire] = candidate.state
        return candidate.state


class _Builder:
    def __init__(self, data, cursor, at, ledger):
        self.data, self.cursor, self.at, self.ledger = data, cursor, at, ledger
        self.operations, self.actions, self.events = [], [], []
        self.allocations, self.retired, self.assessments, self.selection = [], [], [], None
        self.event_us = cursor.inputs.event_us
    def allocate(self, identity):
        acquisition.uuid(identity); require(not self.ledger.used(identity) and identity not in self.allocations)
        self.allocations.append(identity); return identity
    def new_id(self): return self.allocate(self.cursor.next_id())
    def add(self, operation, reason, account=None, position=None, signal_at=None, price=None):
        index = len(self.operations); self.operations.append(operation)
        self.actions.append({'operation_index': index, 'reason': reason, 'account_id': account,
            'position_id': position, 'signal_at': signal_at, 'reference_price': price})
        self.events.append({'kind': reason, 'at': self.at, 'event_us': self.event_us,
            'account_id': account, 'position_id': position, 'operation_index': index})
    def close(self, member, price, reason, signal_at=None):
        position = _position(self.data, member['id'])
        if position is None: return
        _counter(member['num_trades'], 'closed trade count')
        plan = ExitPlan(EntryPlan.from_dict(position['entry']), price)
        account = _account(self.data, member['id']); account['cash'] = credit_cash(account['cash'], plan.cash_credit)
        position.update(exit=plan.to_dict(), closed=True); member['num_trades'] += 1; member['pending'] = None
        self.add({'kind': 'close', 'id': position['id'], 'proceeds': plan.notional, 'fee': plan.fee,
            'execution': plan.to_dict()}, reason, member['id'], position['id'], signal_at, price)
        _risk(self.data, member, price)
    def open(self, member, price, signal_at):
        require(sum(not position['closed'] for position in self.data['positions']) < POPULATION
            and _position(self.data, member['id']) is None)
        account = _account(self.data, member['id']); budget = _text(_amount(account['cash'])//4, CASH_SCALE)
        plan = EntryPlan(budget, price, _configuration(self.data).execution); identity = self.new_id()
        account['cash'] = debit_cash(account['cash'], plan.cash_debit)
        self.data['positions'].append({'id': identity, 'account_id': member['id'], 'asset': 'SOL/USD',
            'entry': plan.to_dict(), 'exit': None, 'closed': False})
        self.add({'kind': 'open', 'id': identity, 'account_id': member['id'], 'asset': 'SOL/USD',
            'quantity': plan.quantity, 'notional': plan.notional, 'fee': plan.fee, 'execution': plan.to_dict()},
            'entry_signal', member['id'], identity, signal_at, price)
        member['pending'] = None; _risk(self.data, member, price)


def _source_cursor(data, at):
    state = data['source']
    # Preserve the full original mark once in the active source/witness and raw
    # source journal. Assessment batches refer to that immutable original;
    # repeating every pin/body-shaped field per member defeats fixed fanout.
    original = state['last_quote']
    frame = None if original is None else {'mark_sha256': state['last_mark_sha256'],
        'observation_id': original['reference']['observation_id'],
        'record_admission_id': original['reference']['record_admission_id'],
        'native_record_receipt_sha256': original['reference']['native_record_receipt_sha256'],
        'recorder_package_sha256': original['reference']['recorder_package_sha256'],
        'price_decimal': original['price_decimal'], 'block_ref': original['block_ref'],
        'estimated_source_second': original['estimated_source_second']}
    return {'policy': SOURCE_POLICY, 'epoch': state['epoch'], 'sequence': state['quote_sequence'],
        'at': at, 'event_us': data['engine']['lifecycle']['last_action_us'],
        'candle_count': data['engine']['ema']['count'], 'bar': deepcopy(state['bars'][-1]),
        'frame': frame, 'history_sha256': state['history_sha256'],
        'close_series_sha256': state['close_series_sha256']}


def _candidate(before, data, strategy, cohort, builder, kind, evidence, observation, control=None):
    members = {member['id'] for member in data['engine']['members']}
    birth_ids = {operation['id'] for operation in builder.operations if operation['kind'] == 'birth'}
    births = [deepcopy(member) for member in data['engine']['members'] if member['id'] in birth_ids]
    closed = sorted((deepcopy(position) for position in data['positions'] if position['closed']), key=lambda row: row['id'])
    data['accounts'] = sorted((row for row in data['accounts'] if row['id'] in members), key=lambda row: row['id'])
    data['positions'] = sorted((row for row in data['positions'] if not row['closed']), key=lambda row: row['id'])
    data['engine']['optimizer'] = encode_optimizer_evidence(strategy, cohort)
    data['engine']['cohort'] = _views(cohort.to_dict())
    require(len(data['accounts']) == len(members) == POPULATION and len(data['positions']) <= POPULATION
        and len(closed) <= POPULATION and len(builder.retired) <= POPULATION and len(builder.assessments) <= POPULATION
        and len(builder.allocations) <= 17 and len(builder.operations) <= 33
        and all(position['account_id'] in members for position in data['positions']))
    data.update(AUTHORITY)
    payload = {'format': COMMAND_FORMAT, 'operations': builder.operations,
        'history': {'owner_id': data['owner_id'], 'run_id': data['run_id'], 'revision': data['revision'],
            'allocated_ids': builder.allocations, 'closed_positions': closed, 'birth_members': births,
            'retired_accounts': builder.retired, 'assessments': builder.assessments, 'selection': builder.selection},
        'transition': {'before': before, 'after': data, 'evidence': {'kind': kind, 'inputs': evidence,
            'observation': None if observation is None else observation.to_dict(), 'actions': builder.actions,
            'control': control}, 'events': builder.events}, **AUTHORITY}
    return V3Candidate(V3State._seal(data, strategy, cohort), _json(payload), builder.witness)

def _uuid(value):
    if type(value) is not str:
        raise ModelError('canonical UUID required')
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise ModelError('canonical UUID required') from None
    return value

def _amount(value, scale=CASH_SCALE, positive=False):
    number = _units(value, scale, positive=positive)
    if _text(number, scale) != value:
        raise ModelError('canonical exact amount required')
    return number

def _stamp(value):
    if type(value) is not int or not 0 <= value <= 2**40:
        raise ModelError('bounded integer source timestamp required')
    return value

def _genome_dict(genome):
    return {**{key: float(getattr(genome, key)).hex() for key in NUMERIC_GENES},
            'assets': list(genome.assets), 'generation': genome.generation,
            'parent_ids': list(genome.parent_ids)}

def _genome(value, config):
    if set(value) != set(NUMERIC_GENES) | {'assets', 'generation', 'parent_ids'}:
        raise ModelError('unknown genome fields')
    result = Genome(**{key: float.fromhex(value[key]) for key in NUMERIC_GENES},
                    assets=list(value['assets']), generation=value['generation'],
                    parent_ids=list(value['parent_ids']))
    config.assert_profile_genome(result)
    return result

def _views(value):
    """Explicit non-economic views for selection metadata and evaluation scores."""
    if type(value) is float:
        if not math.isfinite(value):
            raise ModelError('nonfinite evaluation view')
        return {'float64': value.hex()}
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) in (list, tuple):
        return [_views(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _views(item) for key, item in value.items()}
    raise ModelError('unsupported evaluation evidence')

def _member(identity, genome, name, seed, cursor=None):
    return {'id': identity, 'name': name, 'genome': _genome_dict(genome), 'cursor': cursor,
            'pending': None, 'num_trades': 0, 'peak_equity': seed,
            'max_drawdown': {'numerator': '0', 'denominator': '1'}}

def _account(data, identity):
    return next(row for row in data['accounts'] if row['id'] == identity)

def _position(data, identity):
    return next((row for row in data['positions'] if row['account_id'] == identity and not row['closed']), None)

def _view(data, member, config):
    account = _account(data, member['id'])
    cash, initial = _amount(account['cash']), _amount(account['initial_cash'])
    roi = float(Fraction(cash - initial, initial))
    dd = member['max_drawdown']
    drawdown = float(Fraction(int(dd['numerator']), int(dd['denominator'])))
    return SimpleNamespace(probe_id=member['id'], genome=_genome(member['genome'], config),
        fitness=compute_fitness(roi, drawdown), roi=roi, num_trades=member['num_trades'])

def _risk(data, member, price):
    equity = _amount(_account(data, member['id'])['cash'])
    position = _position(data, member['id'])
    if position is not None:
        equity += _amount(mark_value(EntryPlan.from_dict(position['entry']), price))
    peak = max(equity, _amount(member['peak_equity']))
    member['peak_equity'] = _text(peak, CASH_SCALE)
    drawdown = Fraction(peak - equity, peak)
    old = member['max_drawdown']
    if drawdown > Fraction(int(old['numerator']), int(old['denominator'])):
        member['max_drawdown'] = {'numerator': str(drawdown.numerator), 'denominator': str(drawdown.denominator)}

def _append_candle(engine, observation):
    ema = engine['ema']
    if observation.candle_end is None:
        return False
    if ema['last_end'] is not None:
        if observation.candle_end == ema['last_end']:
            if observation.candle_close != ema['closes'][-1]:
                raise ModelError('completed candle revision forbidden')
            return False
        if observation.candle_end != ema['last_end'] + BAR_SECONDS:
            raise ModelError('candle gaps and out-of-order history forbidden')
    ema['previous'] = dict(ema['values'])
    ema['count'] += 1
    ema['last_end'] = observation.candle_end
    ema['closes'].append(observation.candle_close)
    del ema['closes'][:-64]
    price = float(observation.candle_close)  # Indicator view only; never ledger input.
    for period in range(2, 61):
        if ema['count'] == period:
            window = [float(item) for item in ema['closes'][-period:]]
            scale = max(window)
            value = scale * (math.fsum(item / scale for item in window) / period)
        elif ema['count'] > period:
            previous = float.fromhex(ema['values'][str(period)])
            value = previous + (price - previous) * (2.0 / (period + 1))
        else:
            continue
        if not math.isfinite(value) or value <= 0:
            raise ModelError('unrepresentable indicator view')
        ema['values'][str(period)] = value.hex()
    return True


def _counter(value, label, *, stop=False):
    if label in {'search epoch', 'mutation event'}:
        if type(value) is not int or not 0 <= value < MAX_GENERATION:
            raise CapacityError(f'{label} capacity reached; Stop remains reserved')
        return
    if type(value) is not int or not 0 <= value < MAX_COUNTER - (0 if stop else 1):
        raise CapacityError(f'{label} capacity reached; Stop remains reserved')

def _snapshot(data, member, cohort, builder, result=None):
    account = _account(data, member['id'])
    cash, initial = _amount(account['cash']), _amount(account['initial_cash'])
    roi = Fraction(cash - initial, initial)
    dd = deepcopy(member['max_drawdown'])
    view = _view(data, member, _configuration(data).colony_config())
    if result is not None and (view.fitness != result.fitness or view.roi != result.roi
                              or view.num_trades != result.num_trades):
        raise ModelError('final assessment disagrees with optimizer result')
    held = _position(data, member['id'])
    return {'captured_revision': data['revision'], 'captured_at': builder.at,
        'captured_event_us': builder.event_us,
        'cash_balance': account['cash'], 'terminal_cash': account['cash'] if held is None else None,
        'has_open_position': held is not None, 'initial_cash': account['initial_cash'],
        'peak_equity': member['peak_equity'], 'max_drawdown': dd,
        'roi_ratio': {'numerator': str(roi.numerator), 'denominator': str(roi.denominator)},
        'roi_float64': view.roi.hex(), 'fitness_float64': view.fitness.hex(),
        'closed_trade_count': member['num_trades'], 'source': _source_cursor(data, builder.at)}

def _finalize(data, cohort, builder, reason, *, aborted=False):
    results = {r.probe_id: r for r in cohort.evaluations}
    for index, member in enumerate(data['engine']['members']):
        result = results.get(member['id'])
        frozen = member['assessment']
        metrics = deepcopy(frozen) if frozen is not None else _snapshot(
            data, member, cohort, builder, None if aborted else result)
        if aborted:
            # Preserve observed economics, never publish a partial-window score.
            metrics.update(roi_ratio=None, roi_float64=None, fitness_float64=None)
        if not aborted and (result is None or not result.cohort_complete
                or metrics['fitness_float64'] != result.fitness.hex()
                or metrics['roi_float64'] != result.roi.hex()
                or metrics['closed_trade_count'] != result.num_trades):
            raise ModelError('complete ordered assessment batch required')
        builder.assessments.append({'format': ASSESSMENT_FORMAT,
            'owner_id': data['owner_id'], 'run_id': data['run_id'],
            'finalized_revision': data['revision'], 'finalized_at': builder.at,
            'finalized_event_us': builder.event_us,
            'iteration_id': cohort.iteration_id, 'evaluation_id': cohort._evaluation_ids[member['id']],
            'member_index': index, 'probe_id': member['id'], 'generation': data['engine']['generation'],
            'status': 'aborted' if aborted else 'completed', 'reason': reason if aborted else result.reason,
            'selection_eligible': not aborted, 'cohort_complete': not aborted,
            'window_started_at': cohort.started_at, 'window_ends_at': cohort.ends_at,
            'window_started_us': None if cohort.started_at is None else data['source']['cohort_start_us'],
            'window_ends_us': None if cohort.started_at is None else data['source']['cohort_start_us']+HORIZON_SECONDS*1_000_000,
            'window_source_start': deepcopy(data['engine']['cohort_source']),
            'window_source_end': _source_cursor(data, builder.at),
            'fitness_policy': _views(dict(FITNESS_POLICY)),
            'evaluation_policy': deepcopy(cohort.to_dict()['policy']),
            'execution': deepcopy(data['engine']['config']['execution']),
            'measurement_basis': 'uncalibrated-reference-mark-paper-closed-fills' if not aborted else 'interrupted-unscored-snapshot',
            'paper_fill': deepcopy(data['engine']['config']['paper_fill']),
            'paper_fill_sha256': data['engine']['config']['paper_fill_sha256'],
            'authority': dict(AUTHORITY),
            'early_terminal_frozen': frozen is not None,
            'roi_float64': None if aborted else metrics['roi_float64'],
            'fitness_float64': None if aborted else metrics['fitness_float64'],
            'metrics': metrics})

def _equity(data, price):
    total = _amount(data['reserve']) + sum(_amount(row['cash']) for row in data['accounts'])
    for position in data['positions']:
        if not position['closed']:
            total += _amount(mark_value(EntryPlan.from_dict(position['entry']), price))
    return total

def _abort(data, strategy, cohort, builder, reason):
    if cohort.phase not in {'aborted', 'completed'}:
        _finalize(data, cohort, builder, reason, aborted=True)
        cohort.abort(reason, builder.at)
        strategy.abort_cohort()
        builder.events.append({'kind': 'evaluation_aborted', 'at': builder.at, 'event_us': builder.event_us,
            'account_id': None, 'position_id': None, 'operation_index': None})
    data['engine']['lifecycle']['restart_required'] = True

def _account_risk(data, strategy, cohort, builder, price):
    lifecycle = data['engine']['lifecycle']
    risk = lifecycle['risk']
    equity = _equity(data, price)
    risk.update(observed_equity=_text(equity, CASH_SCALE), observed_at=builder.at,
        observed_us=builder.event_us)
    baseline = _amount(risk['baseline_equity'])
    bps = int(data['engine']['config']['lifecycle_policy']['account_loss_bps'])
    if risk['active'] or equity * 10000 > baseline * (10000 - bps):
        return False
    # A rejected pure candidate cannot install this latch. Its caller must stop
    # decision admission after preparation failure rather than reuse old marks.
    trip = builder.new_id()
    risk.update(active=True, trip_id=trip, tripped_at=builder.at, tripped_us=builder.event_us,
                trip_equity=_text(equity, CASH_SCALE))
    for member in data['engine']['members']:
        if member['pending'] is not None and member['pending']['action'] == 'entry':
            member['pending'] = None
    _abort(data, strategy, cohort, builder, 'risk_halted')
    data['status'] = 'risk_halted'
    builder.add({'kind': 'lifecycle', 'status': 'risk_halted'}, 'risk_halt')
    return True

def _member_equity(data, member, price):
    total = _amount(_account(data, member['id'])['cash'])
    position = _position(data, member['id'])
    if position is not None:
        total += _amount(mark_value(EntryPlan.from_dict(position['entry']), price))
    return total

def _retire(data, member, builder, reason):
    account = _account(data, member['id'])
    if account['retired'] or _position(data, member['id']) is not None:
        raise ModelError('retirement requires one owned liquidated account')
    builder.retired.append({'account': deepcopy(account), 'member': deepcopy(member)})
    data['reserve'] = credit_cash(data['reserve'], account['cash'])
    account.update(cash='0', retired=True)
    member['pending'] = None
    builder.add({'kind': 'retire', 'id': member['id']}, reason, member['id'])

def _terminal(data, strategy, cohort, builder, member, price):
    if member['terminal'] is not None:
        return
    _risk(data, member, price)
    equity, peak = _member_equity(data, member, price), _amount(member['peak_equity'])
    if equity * 10000 > peak * 8000:
        return
    builder.close(member, price, 'death_liquidation')
    account = _account(data, member['id'])
    member['terminal'] = {'reason': 'drawdown', 'at': builder.at, 'cash': account['cash']}
    if cohort.phase == 'evaluating':
        result = cohort.record_terminal(_view(data, member, _configuration(data).colony_config()),
                                        'drawdown', builder.at)
        member['assessment'] = _snapshot(data, member, cohort, builder, result)
    _retire(data, member, builder, 'terminal')

def _prepare_protective(state: V3State, observation: ModelObservation,
                       inputs: V3Inputs, *, ledger: OfflineLedger) -> V3Candidate:
    if type(observation) is not ModelObservation:
        raise ModelError('exact protective observation required')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation, ledger=ledger)
    if data['status'] not in {'running', 'risk_halted'}:
        raise ModelError('paused lifecycle does not consume quotes')
    engine = data['engine']
    previous = engine['last_quote']
    if observation.candle_end is not None:
        raise ModelError('protective quote must strictly advance source time without a candle')
    engine['last_quote'] = {'timestamp': observation.timestamp, 'price': observation.price}
    _account_risk(data, strategy, cohort, builder, observation.price)
    # Finish every valid protective close before ordinary decisions. Terminal
    # cash remains as frozen evidence in its original evaluation membership.
    for member in engine['members']:
        if member['terminal'] is not None:
            continue
        _risk(data, member, observation.price)
        position = _position(data, member['id'])
        if position is not None:
            reference = _amount(position['entry']['reference_price'], PRICE_SCALE, True)
            mark = _amount(observation.price, PRICE_SCALE, True)
            reason = ('stop_loss' if mark * 100 <= reference * 97 else
                      'take_profit' if mark * 100 >= reference * 107 else None)
            if reason is not None:
                builder.close(member, observation.price, reason)
                _account_risk(data, strategy, cohort, builder, observation.price)
        _terminal(data, strategy, cohort, builder, member, observation.price)
        _account_risk(data, strategy, cohort, builder, observation.price)
    return _candidate(before, data, strategy, cohort, builder, 'protective', evidence, observation)

def _capacity(data):
    if data['engine']['generation'] >= MAX_GENERATION:
        raise ModelError('completed-generation capacity reached')
    required = _amount(data['engine']['config']['seed_capital']) * POPULATION
    available = _amount(data['reserve']) + sum(
        _amount(_account(data, member['id'])['cash'])
        for member in data['engine']['members'] if member['terminal'] is None)
    if available < required:
        raise ModelError('complete next cohort cannot be funded')

def _liquidate(data, strategy, cohort, builder, price, reason):
    for member in data['engine']['members']:
        if member['terminal'] is None:
            builder.close(member, price, reason)
            # Costs may latch during the first close even if a later close's
            # outcome would improve a mark. The active trip is never unlatchable
            # by later operations inside the same preparation.
            _account_risk(data, strategy, cohort, builder, price)

def _new_member(identity, genome, name, seed, cursor):
    member = _member(identity, genome, name, seed, cursor)
    member['terminal'] = None
    member['assessment'] = None
    return member

def _restart(data, strategy, cohort, builder, observation):
    engine, lifecycle = data['engine'], data['engine']['lifecycle']
    if cohort.phase != 'aborted' or not lifecycle['restart_required']:
        raise ModelError('restart requires a retained interrupted cohort')
    if lifecycle['signals_after_us'] is None or data['source']['protected_action_us'] <= lifecycle['signals_after_us']:
        raise ModelError('restart requires a later independently accepted quote')
    _liquidate(data, strategy, cohort, builder, observation.price, 'restart_liquidation')
    if lifecycle['risk']['active']:
        return cohort
    _capacity(data)
    config = _configuration(data).colony_config()
    sources = engine['members']
    genomes = [_genome(member['genome'], config) for member in sources]
    ids = [builder.new_id() for _ in sources]
    names = [builder.cursor.probe_name(engine['generation'] + 1) for _ in sources]
    for member in sources:
        if member['terminal'] is None:
            _retire(data, member, builder, 'restart_retire')
    next_members = []
    seed = engine['config']['seed_capital']
    for index, (source, identity, genome, name) in enumerate(zip(sources, ids, genomes, names)):
        genome.generation = engine['generation'] + 1
        genome.parent_ids = [source['id']]
        lineage = BirthLineage(identity, strategy.name, 'restart_clone', cohort.iteration_id, index,
            (LineageSourceBinding('clone_source', source['id']), LineageSourceBinding('asset_template', source['id'])),
            version=2)
        data['reserve'] = debit_cash(data['reserve'], seed)
        data['accounts'].append({'id': identity, 'cash': seed, 'initial_cash': seed, 'retired': False})
        next_members.append(_new_member(identity, genome, name, seed, engine['ema']['last_end']))
        builder.add({'kind': 'birth', 'id': identity, 'cash': seed, 'lineage': lineage.to_dict()},
                    'restart_birth', identity)
    engine['members'] = next_members
    engine['generation'] += 1
    _counter(lifecycle['search_epoch'], 'search epoch')
    lifecycle['search_epoch'] += 1
    lifecycle['restart_required'] = False
    lifecycle['signals_after'] = observation.timestamp
    lifecycle['signals_after_us'] = data['source']['protected_action_us']
    # Explicitly discarded interrupted optimizer state is never told. Restart
    # uses the original bound phenotypes and a new deterministic search epoch.
    strategy.configure_search(SearchRandomStreams(engine['config']['search_seed'], strategy.name),
                              lifecycle['search_epoch'])
    views = [_view(data, member, config) for member in next_members]
    strategy.initialize(views, config)
    following = EvaluationCohort(f"{data['run_id']}:{engine['generation']}", views, HORIZON_SECONDS)
    engine['cohort_source'] = None
    data['source']['cohort_start_us'] = None
    return following

def _replace(data, strategy, cohort, builder, observation):
    engine = data['engine']
    _liquidate(data, strategy, cohort, builder, observation.price, 'cohort_liquidation')
    if engine['lifecycle']['risk']['active']:
        return cohort
    _capacity(data)
    config = _configuration(data).colony_config()
    members = engine['members']
    survivors = [_view(data, member, config) for member in members if member['terminal'] is None]
    evaluations = list(cohort.complete(survivors, observation.timestamp))
    _finalize(data, cohort, builder, 'window_complete')
    _counter(strategy._mutation_event, 'mutation event')
    result = strategy.evolve(evaluations, [], config, period_operator=period_mutation.VERSION)
    if len(result.offspring) != POPULATION or result.retire_ids != [member['id'] for member in members]:
        raise ModelError('optimizer must replace the complete ordered original cohort')
    ids = [builder.new_id() for _ in result.offspring]
    args = {'cohort_member_ids': [member['id'] for member in members]}
    lineage = lineage_plan_from_evolution(strategy.name, result, evaluations, ids, **args)
    builder.selection = _views(result.metadata)
    builder.events.append({'kind': 'evaluation', 'at': builder.at, 'event_us': builder.event_us, 'account_id': None,
                           'position_id': None, 'operation_index': None})
    names = [builder.cursor.probe_name(genome.generation) for genome in result.offspring]
    for member in members:
        if member['terminal'] is None:
            _retire(data, member, builder, 'retire')
    next_members = []
    seed = engine['config']['seed_capital']
    for index, (identity, genome, birth, name) in enumerate(zip(ids, result.offspring, lineage.birth_lineages, names)):
        config.assert_profile_genome(genome)
        genome.parent_ids = list(result.parent_map[str(index)])
        data['reserve'] = debit_cash(data['reserve'], seed)
        data['accounts'].append({'id': identity, 'cash': seed, 'initial_cash': seed, 'retired': False})
        next_members.append(_new_member(identity, genome, name, seed, engine['ema']['last_end']))
        builder.add({'kind': 'birth', 'id': identity, 'cash': seed, 'lineage': birth.to_dict()}, 'birth', identity)
    engine['members'] = next_members
    engine['generation'] += 1
    views = [_view(data, member, config) for member in next_members]
    strategy.bind_candidates(views)
    following = EvaluationCohort(f"{data['run_id']}:{engine['generation']}", views, HORIZON_SECONDS)
    engine['cohort_source'] = None
    data['source']['cohort_start_us'] = None
    if _history_ready(engine, observation.timestamp, data['source']['protected_action_us']):
        following.start(observation.timestamp)
        data['source']['cohort_start_us'] = data['source']['protected_action_us']
        engine['cohort_source'] = _source_cursor(data, observation.timestamp)
    return following

def _pending(data, strategy, cohort, builder, member, observation, allow_entry):
    pending = member['pending']
    if pending is None or data['source']['protected_action_us'] <= pending['signal_us']:
        return
    if data['source']['protected_action_us'] <= (member['cursor'] + BAR_SECONDS)*1_000_000:
        position = _position(data, member['id'])
        if pending['action'] == 'entry' and position is None and allow_entry:
            builder.open(member, observation.price, pending['signal_at'])
        elif pending['action'] == 'exit' and position is not None and position['id'] == pending['position_id']:
            builder.close(member, observation.price, 'exit_signal', pending['signal_at'])
        _account_risk(data, strategy, cohort, builder, observation.price)
        _terminal(data, strategy, cohort, builder, member, observation.price)
        _account_risk(data, strategy, cohort, builder, observation.price)
    member['pending'] = None

def _history_ready(engine, timestamp, event_us):
    end = engine['ema']['last_end']
    return (engine['ema']['count'] >= EMA_WARMUP_BARS and end is not None
            and end <= timestamp <= end + BAR_SECONDS
            and end*1_000_000 <= event_us <= (end+BAR_SECONDS)*1_000_000)

def _prepare_decision(state: V3State, observation: ModelObservation,
                     inputs: V3Inputs, *, ledger: OfflineLedger) -> V3Candidate:
    if type(observation) is not ModelObservation:
        raise ModelError('exact decision observation required')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation, ledger=ledger)
    if data['status'] not in {'running', 'risk_halted'}:
        raise ModelError('paused lifecycle does not consume decisions')
    engine, lifecycle = data['engine'], data['engine']['lifecycle']
    if engine['last_quote'] != {'timestamp': observation.timestamp, 'price': observation.price}:
        raise ModelError('decision requires this exact accepted protective observation')
    # Exact original mark identity and true-us ordering are checked by the new
    # source stage. Different causal marks may share this coarse math second.
    engine['decision_timestamp'] = observation.timestamp
    # Risk monitoring and previously eligible exits need no candle provider.
    # Supplied candles are deliberately not ingested while halted.
    if lifecycle['risk']['active']:
        for member in engine['members']:
            if member['terminal'] is None:
                _pending(data, strategy, cohort, builder, member, observation, False)
        return _candidate(before, data, strategy, cohort, builder, 'decision', evidence, observation)
    if observation.candle_end is not None and observation.candle_end != engine['ema']['last_end']:
        _counter(engine['ema']['count'], 'candle count')
    new_candle = _append_candle(engine, observation)
    if lifecycle['restart_required']:
        if _history_ready(engine, observation.timestamp, data['source']['protected_action_us']):
            cohort = _restart(data, strategy, cohort, builder, observation)
    elif cohort.phase == 'warming':
        if _history_ready(engine, observation.timestamp, data['source']['protected_action_us']):
            cohort.start(observation.timestamp)
            data['source']['cohort_start_us'] = data['source']['protected_action_us']
            engine['cohort_source'] = _source_cursor(data, observation.timestamp)
    elif (cohort.due(observation.timestamp) and data['source']['cohort_start_us'] is not None
            and data['source']['protected_action_us'] >= data['source']['cohort_start_us']+HORIZON_SECONDS*1_000_000):
        cohort = _replace(data, strategy, cohort, builder, observation)
    elif cohort.phase == 'evaluating':
        config = _configuration(data).colony_config()
        for member in engine['members']:
            if member['terminal'] is not None:
                continue
            _pending(data, strategy, cohort, builder, member, observation, not lifecycle['risk']['active'])
            if member['terminal'] is not None or lifecycle['risk']['active']:
                continue
            if new_candle:
                ema = engine['ema']
                member['cursor'], member['pending'] = ema['last_end'], None
                after = lifecycle['signals_after_us']
                if (data['source']['protected_action_us'] <= (ema['last_end']+BAR_SECONDS)*1_000_000
                        and (after is None or ema['last_end']*1_000_000 > after)):
                    genes = _genome(member['genome'], config).int_genes()
                    fast, slow = str(genes['ema_fast']), str(genes['ema_slow'])
                    values = (float.fromhex(ema['previous'][fast]), float.fromhex(ema['previous'][slow]),
                              float.fromhex(ema['values'][fast]), float.fromhex(ema['values'][slow]))
                    entry, exit_signal = ema_crossing(*values)
                    position = _position(data, member['id'])
                    action = 'entry' if position is None and entry else 'exit' if position is not None and exit_signal else None
                    if action is not None:
                        member['pending'] = {'action': action, 'signal_at': observation.timestamp,
                            'signal_us': inputs.event_us,
                            'position_id': None if position is None else position['id']}
    return _candidate(before, data, strategy, cohort, builder, 'decision', evidence, observation)

def _prepare_control(state: V3State, action: str, inputs: V3Inputs,
                    observation: ModelObservation | None = None, trip_id: str | None = None,
                    *, ledger: OfflineLedger) -> V3Candidate:
    if type(action) is not str or action not in {'pause', 'resume', 'stop', 'recover'}:
        raise ModelError('unsupported lifecycle action')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation, ledger=ledger, stop=action == 'stop')
    engine, lifecycle = data['engine'], data['engine']['lifecycle']
    risk = lifecycle['risk']
    required = {'pause': {'running'}, 'resume': {'paused'}, 'recover': {'risk_halted'},
                'stop': {'running', 'paused', 'risk_halted'}}[action]
    if data['status'] not in required or (action != 'recover' and (trip_id is not None or observation is not None)):
        raise ModelError('control does not match current lifecycle state')
    if action == 'recover':
        _uuid(trip_id)
        if not risk['active'] or trip_id != risk['trip_id']:
            raise ModelError('recovery must acknowledge the current active trip')
        if (observation is None or observation.candle_end is None
                or engine['last_quote'] != {'timestamp': observation.timestamp, 'price': observation.price}
                or observation.timestamp > observation.candle_end + BAR_SECONDS):
            raise ModelError('recovery requires the accepted quote and current completed candle')
        if not any(member['terminal'] is None for member in engine['members']):
            raise ModelError('recovery requires surviving candidates')
        if observation.candle_end != engine['ema']['last_end']:
            _counter(engine['ema']['count'], 'candle count')
        _counter(risk['recovery_count'], 'recovery count')
        _append_candle(engine, observation)
        if engine['ema']['count'] < EMA_WARMUP_BARS:
            raise ModelError('recovery requires fully warmed contiguous history')
        _account_risk(data, strategy, cohort, builder, observation.price)
        equity, baseline = _amount(risk['observed_equity']), _amount(risk['baseline_equity'])
        bps = int(engine['config']['lifecycle_policy']['account_loss_bps'])
        if equity * 10000 <= baseline * (10000 - bps):
            raise ModelError('original account-loss boundary remains breached')
        risk.update(active=False, recovery_count=risk['recovery_count'] + 1, last_recovered_at=builder.at,
            last_recovered_us=builder.event_us)
    if action in {'pause', 'stop'}:
        _abort(data, strategy, cohort, builder, 'paused' if action == 'pause' else 'stopped')
    for member in engine['members']:
        member['pending'] = None
    if action in {'resume', 'recover'}:
        lifecycle['signals_after'] = builder.at
        lifecycle['signals_after_us'] = inputs.event_us
    lifecycle['last_control_at'] = builder.at
    lifecycle['last_control_us'] = inputs.event_us
    data['status'] = {'pause': 'paused', 'resume': 'running', 'recover': 'running', 'stop': 'stopped'}[action]
    builder.add({'kind': 'lifecycle', 'status': data['status']}, action)
    return _candidate(before, data, strategy, cohort, builder, 'control', evidence, observation,
                      {'action': action, 'trip_id': trip_id})


def _safe(function):
    def guarded(*args, **kwargs):
        try: return function(*args, **kwargs)
        except ModelError: raise
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            raise ModelError() from None
    return guarded


def _inputs(inputs, observation=None):
    require(type(inputs) is V3Inputs); inputs.__post_init__()
    if observation is not None:
        require(type(observation) is ModelObservation); observation.__post_init__()
    return inputs.new_cursor(), inputs.math_second if observation is None else observation.timestamp, inputs.to_dict()


@dataclass(frozen=True, slots=True)
class _Stage:
    ledger: OfflineLedger
    after_source: dict
    provider_evidence: dict
    witness: dict
    def check(self, *args): return self.ledger.check(*args)
    def used(self, identity): return self.ledger.used(identity)


def _bind_clock(inputs, binding):
    require(type(inputs) is V3Inputs and type(binding) is SourceBinding)
    inputs.__post_init__(); binding.__post_init__()
    require(all(getattr(inputs.clock, name) == getattr(binding, name)
        for name in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch')))


def _series(history, series, expected, config, inputs):
    require(type(history) is source.SampledHistory and type(series) is source.SampledCloseSeries)
    derived = source.derive_close_series(history, expected_history_sha256=expected)
    require(derived.wire == series.wire)
    value = series.to_dict()
    require(value['scope'] == {'owner_id': config.owner_id, 'run_id': config.run_id, 'market_epoch': config.market_epoch})
    end = acquisition.counter(value['range']['end'], acquisition.MAX_SECOND)
    completed_cutoff = (inputs.clock.wall_lower_us-source.COMPLETION_MARGIN_US)//(BAR_SECONDS*1_000_000)*BAR_SECONDS
    require(end == completed_cutoff)
    return value


def _source_state(config, series, value):
    return {'profile': source.PROFILE, 'policy_sha256': source.POLICY_SHA256,
        'epoch': config.market_epoch, 'current_binding': config.initial_binding.to_dict(),
        'history_sha256': value['history_sha256'], 'close_series_sha256': series.sha256,
        'history_end': acquisition.counter(value['range']['end']),
        'history_recorder_package_sha256': value['recorder_package_sha256'],
        'bars': [[acquisition.counter(bar['end']), bar['close']] for bar in value['closes']],
        'quote_sequence': 0, 'last_quote': None, 'last_mark_sha256': None,
        'protected_action_us': None, 'protected_math_second': None,
        'decision_mark_sha256': None, 'cohort_start_us': None}


@_safe
def bootstrap(config, history, series, *, expected_history_sha256, inputs, ledger):
    require(type(config) is V3Config and type(ledger) is OfflineLedger)
    config.__post_init__(); _bind_clock(inputs, config.initial_binding)
    ledger.check(None, config.owner_id, config.run_id)
    values = _series(history, series, expected_history_sha256, config, inputs)
    require(values['recorder_package_sha256'] == config.initial_binding.recorder_package_sha256
        and history.to_dict()['previous_history_sha256'] is None)
    cursor, at, evidence = _inputs(inputs)
    colony = config.colony_config(); streams = SearchRandomStreams(config.search_seed, 'genetic_algorithm')
    strategy = GeneticAlgorithmStrategy(); strategy.configure_search(streams)
    engine = {'config': config.to_dict(), 'generation': 0, 'last_quote': None, 'decision_timestamp': None,
        'members': [], 'ema': {'count': 0, 'last_end': None, 'closes': [], 'values': {}, 'previous': {}},
        'optimizer': None, 'cohort_source': None, 'lifecycle': {'search_epoch': 0, 'restart_required': False,
            'signals_after': None, 'signals_after_us': None, 'last_control_at': None, 'last_control_us': None,
            'last_action_us': inputs.event_us, 'last_clock_epoch': inputs.clock.acquisition_epoch,
            'last_monotonic_us': inputs.clock.monotonic_us, 'risk': {'active': False, 'baseline_equity': config.initial_cash,
                'observed_equity': config.initial_cash, 'observed_at': at, 'observed_us': inputs.event_us,
                'trip_id': None, 'tripped_at': None, 'tripped_us': None,
                'trip_equity': None, 'recovery_count': 0, 'last_recovered_at': None, 'last_recovered_us': None}}}
    data = {'version': MODEL_FORMAT, 'owner_id': config.owner_id, 'run_id': config.run_id,
        'revision': 2, 'status': 'running', 'reserve': config.initial_cash, 'accounts': [], 'positions': [],
        'engine': engine, 'source': _source_state(config, series, values), **AUTHORITY}
    builder = _Builder(data, cursor, at, ledger)
    builder.witness = {'kind': 'bootstrap', 'config': config, 'history': history, 'series': series,
        'expected_history_sha256': expected_history_sha256, 'inputs': inputs}
    for index in range(POPULATION):
        genome = random_genome(0, colony_config=colony, rng=streams.rng('gen0', 0, index))
        identity = builder.new_id(); name = cursor.probe_name(0)
        data['reserve'] = debit_cash(data['reserve'], config.seed_capital)
        data['accounts'].append({'id': identity, 'cash': config.seed_capital, 'initial_cash': config.seed_capital, 'retired': False})
        member = _member(identity, genome, name, config.seed_capital)
        member.update(terminal=None, assessment=None); engine['members'].append(member)
        builder.add({'kind': 'birth', 'id': identity, 'cash': config.seed_capital,
            'lineage': BirthLineage.founder(identity, 'genetic_algorithm').to_dict()}, 'founder', identity)
    for end, close in data['source']['bars']:
        _append_candle(engine, ModelObservation(at, close, end, close))
    views = [_view(data, member, colony) for member in engine['members']]
    strategy.initialize(views, colony); cohort = EvaluationCohort(f'{config.run_id}:0', views, HORIZON_SECONDS)
    evidence['provider'] = {'phase': 'bootstrap', 'mark_sha256': None, 'history_sha256': history.sha256,
        'close_series_sha256': series.sha256, 'source_policy_sha256': source.POLICY_SHA256}
    builder.add({'kind': 'lifecycle', 'status': 'running'}, 'lifecycle')
    return _candidate(None, data, strategy, cohort, builder, 'bootstrap', evidence, None)


def _start(state, inputs, observation=None, *, ledger, stop=False):
    require(type(state) is V3State and type(ledger) is _Stage)
    cursor, at, evidence = _inputs(inputs, observation)
    before = state.to_dict(); _configuration(before)
    ledger.check(before, before['owner_id'], before['run_id']); _counter(before['revision'], 'revision', stop=stop)
    require(before['status'] in {'running', 'paused', 'risk_halted'})
    lifecycle = before['engine']['lifecycle']
    require(inputs.event_us >= lifecycle['last_action_us']
        and (lifecycle['last_control_us'] is None or inputs.event_us >= lifecycle['last_control_us']))
    if inputs.clock.acquisition_epoch == lifecycle['last_clock_epoch']:
        require(inputs.clock.monotonic_us >= lifecycle['last_monotonic_us'])
    else:
        require(ledger.witness['kind'] == 'epoch_rollover')
    data, strategy, cohort = state._fork(); data['revision'] += 1
    data['source'] = deepcopy(ledger.after_source); data['engine']['lifecycle']['last_action_us'] = inputs.event_us
    data['engine']['lifecycle'].update(last_clock_epoch=inputs.clock.acquisition_epoch,
        last_monotonic_us=inputs.clock.monotonic_us)
    builder = _Builder(data, cursor, at, ledger); builder.witness = ledger.witness
    evidence['provider'] = ledger.provider_evidence
    return before, data, strategy, cohort, builder, evidence


def _stage(state, phase, mark, expected_mark_sha256, history, series, expected_history_sha256, inputs, ledger, *, recovery=False):
    require(type(state) is V3State and type(ledger) is OfflineLedger)
    before = state.to_dict(); config = _configuration(before)
    ledger.check(before, config.owner_id, config.run_id)
    binding = SourceBinding(**before['source']['current_binding']); _bind_clock(inputs, binding)
    after = deepcopy(before['source']); observed = None
    if mark is not None:
        source.validate_current_mark(mark, inputs.clock, expected_mark_sha256=expected_mark_sha256)
        value = mark.to_dict(); ref = value['reference']
        require(ref['issuer_principal_binding_id'] == binding.issuer_principal_binding_id
            and ref['recorder_package_sha256'] == binding.recorder_package_sha256)
        if phase == 'protective':
            require(acquisition.counter(ref['ingest_sequence']) > after['quote_sequence']
                and (after['protected_action_us'] is None or inputs.event_us > after['protected_action_us'])
                and (before['engine']['lifecycle']['last_control_us'] is None
                    or inputs.event_us > before['engine']['lifecycle']['last_control_us']))
            previous = after['last_quote']
            if previous is not None:
                old, new = acquisition.counter(previous['block_ref']), acquisition.counter(value['block_ref'])
                old_time, new_time = acquisition.counter(previous['estimated_source_second']), acquisition.counter(value['estimated_source_second'])
                require(new >= old and new_time >= old_time
                    and (new != old or (new_time == old_time and value['price_decimal'] == previous['price_decimal'])))
            after.update(quote_sequence=acquisition.counter(ref['ingest_sequence']), last_quote=value,
                last_mark_sha256=mark.sha256, protected_action_us=inputs.event_us, protected_math_second=inputs.math_second)
        else:
            require(mark.sha256 == after['last_mark_sha256'] and value == after['last_quote'])
        observed = ModelObservation(after['protected_math_second'], value['price_decimal'])
    else:
        require(phase == 'control' and not recovery and expected_mark_sha256 is None)
    if history is not None or series is not None or expected_history_sha256 is not None:
        require(mark is not None and (not before['engine']['lifecycle']['risk']['active'] or recovery)
            and ledger._history_witness is not None)
        values = _series(history, series, expected_history_sha256, config, inputs)
        require(values['recorder_package_sha256'] == after['history_recorder_package_sha256']
            == binding.recorder_package_sha256)
        old = ledger._history_witness.to_dict(); new = history.to_dict()
        require(old['format'] == source.HISTORY_FORMAT and old['scope'] == new['scope']
            and old['source_policy_sha256'] == source.POLICY_SHA256
            and old['range']['end'] == str(after['history_end']) and ledger._history_witness.sha256 == after['history_sha256'])
        if history.sha256 != after['history_sha256']:
            require(new['previous_history_sha256'] == after['history_sha256']
                and acquisition.counter(values['range']['end']) == after['history_end']+BAR_SECONDS
                and new['minutes'][:900] == old['minutes'][15:] and new['bars'][:60] == old['bars'][1:])
        else: require(recovery)
        after.update(history_sha256=history.sha256, close_series_sha256=series.sha256,
            history_end=acquisition.counter(values['range']['end']),
            history_recorder_package_sha256=values['recorder_package_sha256'],
            bars=[[acquisition.counter(bar['end']), bar['close']] for bar in values['closes']])
        last_end, last_close = after['bars'][-1]
        require(last_end*1_000_000+source.COMPLETION_MARGIN_US <= after['protected_action_us'])
        observed = ModelObservation(after['protected_math_second'], value['price_decimal'], last_end, last_close)
    elif phase == 'decision' and not before['engine']['lifecycle']['risk']['active']:
        cutoff = (inputs.clock.wall_lower_us-source.COMPLETION_MARGIN_US)//(BAR_SECONDS*1_000_000)*BAR_SECONDS
        require(after['history_end'] == cutoff)
    provider = {'phase': phase, 'mark_sha256': None if mark is None else mark.sha256,
        'history_sha256': None if history is None else history.sha256,
        'close_series_sha256': None if series is None else series.sha256,
        'source_policy_sha256': source.POLICY_SHA256}
    witness = {'kind': phase, 'inputs': inputs, 'mark': mark, 'expected_mark_sha256': expected_mark_sha256,
        'history': history, 'series': series, 'expected_history_sha256': expected_history_sha256}
    return _Stage(ledger, after, provider, witness), observed


@_safe
def prepare_protective(state, mark, *, expected_mark_sha256, inputs, ledger):
    staged, observed = _stage(state, 'protective', mark, expected_mark_sha256, None, None, None, inputs, ledger)
    return _prepare_protective(state, observed, inputs, ledger=staged)


@_safe
def prepare_decision(state, mark, *, expected_mark_sha256, inputs, ledger, history=None, series=None, expected_history_sha256=None):
    staged, observed = _stage(state, 'decision', mark, expected_mark_sha256, history, series, expected_history_sha256, inputs, ledger)
    require(staged.after_source['decision_mark_sha256'] != mark.sha256)
    staged.after_source['decision_mark_sha256'] = mark.sha256
    return _prepare_decision(state, observed, inputs, ledger=staged)


@_safe
def prepare_control(state, action, inputs, *, ledger, mark=None, expected_mark_sha256=None,
                    history=None, series=None, expected_history_sha256=None, trip_id=None):
    require(type(action) is str and action in {'pause', 'resume', 'recover', 'stop'})
    if action != 'recover': require(mark is None and history is None and series is None and expected_history_sha256 is None)
    staged, observed = _stage(state, 'control', mark, expected_mark_sha256, history, series,
        expected_history_sha256, inputs, ledger, recovery=action == 'recover')
    staged.witness.update(action=action, trip_id=trip_id)
    return _prepare_control(state, action, inputs, observed, trip_id, ledger=staged)


@_safe
def prepare_epoch_rollover(state, successor_binding, inputs, *, ledger):
    require(type(state) is V3State and type(ledger) is OfflineLedger and type(successor_binding) is SourceBinding)
    before = state.to_dict(); config = _configuration(before)
    old = SourceBinding(**before['source']['current_binding']); successor_binding.__post_init__()
    require(all(getattr(successor_binding, name) == getattr(config, name) for name in ('owner_id', 'run_id', 'market_epoch'))
        and successor_binding.acquisition_epoch != old.acquisition_epoch
        and not ledger.used_epoch(successor_binding.acquisition_epoch)
        and successor_binding.recorder_package_sha256 == old.recorder_package_sha256)
    _bind_clock(inputs, successor_binding)
    following_source = deepcopy(before['source']); following_source['current_binding'] = successor_binding.to_dict()
    witness = {'kind': 'epoch_rollover', 'successor_binding': successor_binding, 'inputs': inputs}
    staged = _Stage(ledger, following_source, {'phase': 'epoch_rollover', 'source_policy_sha256': source.POLICY_SHA256}, witness)
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, ledger=staged)
    _abort(data, strategy, cohort, builder, 'acquisition_epoch_rollover')
    lifecycle = data['engine']['lifecycle']
    lifecycle.update(last_control_at=builder.at, last_control_us=inputs.event_us,
        signals_after=builder.at, signals_after_us=inputs.event_us)
    for member in data['engine']['members']: member['pending'] = None
    if data['status'] != 'risk_halted': data['status'] = 'paused'
    builder.add({'kind': 'lifecycle', 'status': data['status']}, 'acquisition_epoch_rollover')
    return _candidate(before, data, strategy, cohort, builder, 'epoch_rollover', evidence, None,
        {'action': 'acquisition_epoch_rollover', 'trip_id': None})
