"""Bounded, fresh-state exact EMA rehearsal; no runtime or database authority.

The only entry point for state is bootstrap. State evidence is not a decoder or
cross-process checkpoint. Economic amounts never come from binary64 engine
state. Float views serve the existing EMA and optimizer mathematics only.
Protective and ordinary decisions are separate candidates: a failed candle or
selection cannot erase a previously accepted protective candidate.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from fractions import Fraction
from types import SimpleNamespace
from uuid import UUID

from .colony_config import ColonyConfig, GeneOverride, ExactMarkColonyConfig
from .decision_inputs import DecisionInputs
from .decimal_execution import (CASH_SCALE, PRICE_SCALE, DecimalExecutionConfig,
    EntryPlan, ExitPlan, _units, _text, debit_cash, credit_cash, mark_value)
from .evaluation import EvaluationCohort
from .evolution import compute_fitness
from .genome import Genome, NUMERIC_GENES, random_genome
from .gene_registry import GENOME_POLICY
from .parameter_codec import PARAMETER_POLICY
from .lineage import BirthLineage, lineage_plan_from_evolution
from .search_random import SearchRandomStreams, validate_search_seed
from .signal_profile import EMA_WARMUP_BARS, ema_crossing
from .strategy_fork import fork_strategy, fork_evaluation
from .strategies.genetic_algorithm import GeneticAlgorithmStrategy
from .strategies.differential_evolution import DifferentialEvolutionStrategy
from .strategies.particle_swarm import ParticleSwarmStrategy
from .strategies.cma_es import CMAEvolutionStrategy
from .optimizer_evidence import encode_optimizer_evidence


PROFILE = 'ema-baseline-exact-rehearsal-v1'
CODE_VERSION = 'bounded-exact-rehearsal-v1'
SOURCE = 'synthetic-exact-fixture-v1'
POPULATION = 8
MAX_GENERATIONS = 3
MAX_POSITIONS = 64
MAX_PAYLOAD_BYTES = 262144
CANDLE_SECONDS = 900
HORIZON_SECONDS = 3600
_STRATEGIES = {c.name: c for c in (GeneticAlgorithmStrategy,
    DifferentialEvolutionStrategy, ParticleSwarmStrategy, CMAEvolutionStrategy)}


class ExactRehearsalError(ValueError):
    """Unsupported input, capacity, or exact transition; source state is intact."""


class ExactCapacityError(ExactRehearsalError):
    """A complete candidate exceeds an explicit retention or wire limit."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def _uuid(value):
    if type(value) is not str:
        raise ExactRehearsalError('canonical UUID required')
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except ValueError:
        raise ExactRehearsalError('canonical UUID required') from None
    return value


def _amount(value, scale=CASH_SCALE, positive=False):
    number = _units(value, scale, positive=positive)
    if _text(number, scale) != value:
        raise ExactRehearsalError('canonical exact amount required')
    return number


def _stamp(value):
    if type(value) is not int or not 0 <= value <= 2**40:
        raise ExactRehearsalError('bounded integer source timestamp required')
    return value


@dataclass(frozen=True, slots=True)
class ExactRehearsalConfig:
    strategy: str
    owner_id: str
    run_id: str
    asset: str = 'SOL/USDC'
    initial_cash: str = '1000'
    seed_capital: str = '100'
    search_seed: str = '0'
    execution: DecimalExecutionConfig = DecimalExecutionConfig()

    def __post_init__(self):
        _uuid(self.owner_id); _uuid(self.run_id)
        if type(self.strategy) is not str or self.strategy not in _STRATEGIES:
            raise ExactRehearsalError('unsupported exact rehearsal strategy')
        config = self.colony_config()
        config.resolve_gene_domains()
        if (_amount(self.seed_capital, positive=True) * POPULATION > _amount(self.initial_cash, positive=True)
                or _amount(self.seed_capital) < 10**CASH_SCALE):
            raise ExactRehearsalError('eight fully funded exact accounts required')
        validate_search_seed(self.search_seed)
        if type(self.execution) is not DecimalExecutionConfig:
            raise ExactRehearsalError('exact execution configuration required')
        DecimalExecutionConfig.from_dict(self.execution.to_dict())

    def colony_config(self):
        # Pin this version independently of the mutable UI preset registry.
        if (GENOME_POLICY != {'version': 'configured-phenotype-v1',
                'integer_rounding': 'nearest_half_up', 'disabled': 'configured_default',
                'validation': 'deterministic_no_rng'} or PARAMETER_POLICY != {
                'version': 'effective-unit-domain-v1', 'coordinates': 'unit_interval',
                'integer_rounding': 'genome_nearest_half_up', 'assets': 'inherit_and_resize',
                'repairs': 'configured_phenotype'}):
            raise ExactRehearsalError('gene or parameter policy requires a reviewed version change')
        config_type = ExactMarkColonyConfig if self.asset == 'SOL/USD' else ColonyConfig
        config = config_type(strategy_profile='ema_baseline_v1',
            enabled_genes=['ema_fast', 'ema_slow'], available_assets=[self.asset],
            reproduction_interval=HORIZON_SECONDS // 60, gene_overrides={
                'ema_fast': GeneOverride(min=3, max=12, default=9),
                'ema_slow': GeneOverride(min=15, max=60, default=21),
                'position_size_pct': GeneOverride(fixed=.25),
                'stop_loss_pct': GeneOverride(fixed=.03),
                'take_profit_pct': GeneOverride(fixed=.07),
                'max_open_positions': GeneOverride(fixed=1),
                'timeframe_minutes': GeneOverride(fixed=15),
                'num_assets': GeneOverride(fixed=1)})
        fixed = {'rsi_period': 14., 'rsi_oversold': 32., 'rsi_overbought': 70.,
            'volume_threshold': 1.4, 'position_size_pct': .25, 'stop_loss_pct': .03,
            'take_profit_pct': .07, 'max_open_positions': 1., 'timeframe_minutes': 15.,
            'benchmark_target_pct': .08, 'reproduce_target_dollars': 10.,
            'death_drawdown_pct': .2, 'num_assets': 1.}
        domains = config.resolve_gene_domains()
        if (set(domains) != set(fixed) | {'ema_fast', 'ema_slow'} or
                set(NUMERIC_GENES) != set(domains) or any(
                (domains[key].minimum, domains[key].maximum, domains[key].default) != (value,) * 3
                for key, value in fixed.items())):
            raise ExactRehearsalError('fixed profile changed without a rehearsal version change')
        return config

    def to_dict(self):
        return {'profile': PROFILE, 'code_version': CODE_VERSION, 'source': SOURCE,
                'strategy': self.strategy, 'asset': self.asset, 'initial_cash': self.initial_cash,
                'seed_capital': self.seed_capital, 'search_seed': self.search_seed,
                'execution': self.execution.policy(), 'population': POPULATION,
                'horizon_seconds': HORIZON_SECONDS, 'candle_seconds': CANDLE_SECONDS,
                'max_generations': MAX_GENERATIONS, 'max_positions': MAX_POSITIONS}

    def run_configuration(self):
        return {'durability_contract_version': 3, 'execution': self.execution.policy(),
                'rehearsal': self.to_dict()}


@dataclass(frozen=True, slots=True)
class ExactObservation:
    timestamp: int
    price: str
    candle_end: int | None = None
    candle_close: str | None = None

    def __post_init__(self):
        _stamp(self.timestamp)
        _amount(self.price, PRICE_SCALE, positive=True)
        if (self.candle_end is None) != (self.candle_close is None):
            raise ExactRehearsalError('completed candle needs both end and exact close')
        if self.candle_end is not None:
            _stamp(self.candle_end)
            if self.candle_end % CANDLE_SECONDS or self.candle_end > self.timestamp:
                raise ExactRehearsalError('candle must be complete and aligned')
            _amount(self.candle_close, PRICE_SCALE, positive=True)

    def to_dict(self):
        return {'timestamp': self.timestamp, 'price': self.price,
                'candle_end': self.candle_end, 'candle_close': self.candle_close}


def _genome_dict(genome):
    return {**{key: float(getattr(genome, key)).hex() for key in NUMERIC_GENES},
            'assets': list(genome.assets), 'generation': genome.generation,
            'parent_ids': list(genome.parent_ids)}


def _genome(value, config):
    if set(value) != set(NUMERIC_GENES) | {'assets', 'generation', 'parent_ids'}:
        raise ExactRehearsalError('unknown genome fields')
    result = Genome(**{key: float.fromhex(value[key]) for key in NUMERIC_GENES},
                    assets=list(value['assets']), generation=value['generation'],
                    parent_ids=list(value['parent_ids']))
    config.assert_profile_genome(result)
    return result


def _views(value):
    """Explicit non-economic views for selection metadata and evaluation scores."""
    if type(value) is float:
        if not math.isfinite(value):
            raise ExactRehearsalError('nonfinite evaluation view')
        return {'float64': value.hex()}
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) in (list, tuple):
        return [_views(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _views(item) for key, item in value.items()}
    raise ExactRehearsalError('unsupported evaluation evidence')


class ExactState:
    """Sealed detached state. No caller JSON, old Probe or controller can enter."""
    __slots__ = ('__wire', '__strategy', '__cohort')

    def __init__(self, *args, **kwargs):
        raise ExactRehearsalError('exact states can only be freshly bootstrapped')

    def __setattr__(self, key, value):
        raise AttributeError('ExactState is immutable')

    def to_dict(self):
        return json.loads(self.__wire)

    @property
    def revision(self):
        return self.to_dict()['revision']

    @classmethod
    def _seal(cls, data, strategy, cohort):
        value = object.__new__(cls)
        object.__setattr__(value, '_ExactState__wire', _json(data))
        object.__setattr__(value, '_ExactState__strategy', fork_strategy(strategy))
        object.__setattr__(value, '_ExactState__cohort', fork_evaluation(cohort))
        return value

    def _fork(self):
        return self.to_dict(), fork_strategy(self.__strategy), fork_evaluation(self.__cohort)


@dataclass(frozen=True, slots=True)
class ExactCandidate:
    state: ExactState
    _wire: bytes
    _payload_bytes: int

    def __post_init__(self):
        # A candidate is not a commit receipt, but its two exposed views must
        # still describe the same owned state before C3 can retain the pair.
        if type(self.state) is not ExactState or type(self._wire) is not bytes:
            raise ExactRehearsalError('candidate requires bounded immutable state evidence')
        if len(self._wire) > MAX_PAYLOAD_BYTES:
            raise ExactCapacityError('whole candidate immutable wire exceeds payload capacity')
        try:
            payload = json.loads(self._wire)
            measured = len(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                      separators=(', ', ': '), allow_nan=False).encode('utf-8'))
            if (_json(payload['transition']['after']) != _json(self.state.to_dict())
                    or _json(payload) != self._wire or type(self._payload_bytes) is not int
                    or self._payload_bytes != measured or measured > MAX_PAYLOAD_BYTES):
                raise ValueError()
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ExactRehearsalError('candidate state and transition evidence differ') from None

    @property
    def operations(self):
        return json.loads(self._wire)['operations']

    @property
    def transition(self):
        return json.loads(self._wire)['transition']

    @property
    def payload_bytes(self):
        return self._payload_bytes


def _inputs(value, observation=None):
    if type(value) is not DecisionInputs:
        raise ExactRehearsalError('immutable DecisionInputs required')
    # Revalidate all allocations even if someone circumvented frozen dataclass setters.
    DecisionInputs(value.event_at, value.wall_at, value.monotonic_at, value.ids, value.names)
    at = value.event_at.timestamp()
    if at != int(at) or (observation is not None and at != observation.timestamp):
        raise ExactRehearsalError('event time must equal integer observation time')
    _stamp(int(at))
    return value.new_cursor(), int(at), {'event_at': value.event_at.isoformat(),
        'wall_at': value.wall_at.isoformat(), 'monotonic_at': value.monotonic_at.hex(),
        'ids': list(value.ids), 'names': [list(item) for item in value.names]}


def _new_id(engine, cursor):
    identity = cursor.next_id()
    if identity in engine['used_ids']:
        raise ExactRehearsalError('identity was already allocated in this rehearsal')
    engine['used_ids'].append(identity)
    return identity


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


class _Builder:
    def __init__(self, data, cursor, at):
        self.data, self.cursor, self.at = data, cursor, at
        self.operations, self.actions, self.events = [], [], []

    def add(self, operation, reason, account=None, position=None, signal_at=None, price=None):
        index = len(self.operations)
        self.operations.append(operation)
        self.actions.append({'operation_index': index, 'reason': reason, 'account_id': account,
            'position_id': position, 'signal_at': signal_at, 'reference_price': price})
        self.events.append({'kind': reason, 'at': self.at, 'account_id': account,
                            'position_id': position, 'operation_index': index})

    def close(self, member, price, reason, signal_at=None):
        position = _position(self.data, member['id'])
        if position is None:
            return
        plan = ExitPlan(EntryPlan.from_dict(position['entry']), price)
        account = _account(self.data, member['id'])
        account['cash'] = credit_cash(account['cash'], plan.cash_credit)
        position.update(exit=plan.to_dict(), closed=True)
        member['num_trades'] += 1
        member['pending'] = None
        self.add({'kind': 'close', 'id': position['id'], 'proceeds': plan.notional,
                  'fee': plan.fee, 'execution': plan.to_dict()}, reason, member['id'], position['id'], signal_at, price)
        _risk(self.data, member, price)

    def open(self, member, price, signal_at):
        if len(self.data['positions']) >= MAX_POSITIONS:
            raise ExactRehearsalError('retained position capacity reached')
        account = _account(self.data, member['id'])
        budget = _text(_amount(account['cash']) // 4, CASH_SCALE)
        config = DecimalExecutionConfig.from_dict(self.data['engine']['config']['execution']['config'])
        plan = EntryPlan(budget, price, config)
        identity = _new_id(self.data['engine'], self.cursor)
        account['cash'] = debit_cash(account['cash'], plan.cash_debit)
        self.data['positions'].append({'id': identity, 'account_id': member['id'],
            'asset': self.data['engine']['config']['asset'], 'entry': plan.to_dict(), 'exit': None, 'closed': False})
        self.add({'kind': 'open', 'id': identity, 'account_id': member['id'],
            'asset': self.data['engine']['config']['asset'], 'quantity': plan.quantity,
            'notional': plan.notional, 'fee': plan.fee, 'execution': plan.to_dict()},
            'entry_signal', member['id'], identity, signal_at, price)
        member['pending'] = None
        _risk(self.data, member, price)


def _candidate(before, data, strategy, cohort, builder, kind, input_evidence, observation):
    data['accounts'].sort(key=lambda row: row['id'])
    data['positions'].sort(key=lambda row: row['id'])
    data['engine']['optimizer'] = encode_optimizer_evidence(strategy, cohort)
    if len(data['accounts']) > POPULATION * (MAX_GENERATIONS + 1) or len(data['positions']) > MAX_POSITIONS:
        raise ExactCapacityError('rehearsal retention capacity reached')
    payload = {'version': 3, 'operations': builder.operations, 'transition': {
        'version': 1, 'before': before, 'after': data, 'evidence': {'kind': kind,
        'inputs': input_evidence, 'observation': None if observation is None else observation.to_dict(),
        'actions': builder.actions}, 'events': builder.events}}
    wire = _json(payload)
    # PostgreSQL jsonb::text uses spaces; this is the same conservative bound
    # as command_protocol rather than the smaller compact transport encoding.
    payload_size = len(json.dumps(payload, sort_keys=True, separators=(', ', ': '),
                                 ensure_ascii=False, allow_nan=False).encode('utf-8'))
    if payload_size > MAX_PAYLOAD_BYTES:
        raise ExactCapacityError('whole candidate exceeds payload capacity; splitting is forbidden')
    return ExactCandidate(ExactState._seal(data, strategy, cohort), wire, payload_size)


def bootstrap(config: ExactRehearsalConfig, inputs: DecisionInputs) -> ExactCandidate:
    if type(config) is not ExactRehearsalConfig:
        raise ExactRehearsalError('fresh exact configuration required')
    cursor, at, evidence = _inputs(inputs)
    colony = config.colony_config()
    streams = SearchRandomStreams(config.search_seed, config.strategy)
    strategy = _STRATEGIES[config.strategy]()
    strategy.configure_search(streams)
    engine = {'config': config.to_dict(), 'generation': 0, 'last_quote': None,
        'decision_timestamp': None, 'members': [], 'ema': {'count': 0, 'last_end': None,
        'closes': [], 'values': {}, 'previous': {}}, 'distribution_id': None,
        'used_ids': [], 'last_evaluation': None, 'optimizer': None}
    data = {'version': 1, 'owner_id': config.owner_id, 'run_id': config.run_id,
        'revision': 2, 'status': 'running', 'reserve': config.initial_cash,
        'accounts': [], 'positions': [], 'engine': engine}
    builder = _Builder(data, cursor, at)
    for index in range(POPULATION):
        genome = random_genome(0, colony_config=colony, rng=streams.rng('gen0', 0, index))
        identity = _new_id(engine, cursor)
        name = cursor.probe_name(genome.generation)
        data['reserve'] = debit_cash(data['reserve'], config.seed_capital)
        data['accounts'].append({'id': identity, 'cash': config.seed_capital,
                                 'initial_cash': config.seed_capital, 'retired': False})
        engine['members'].append(_member(identity, genome, name, config.seed_capital))
        builder.add({'kind': 'birth', 'id': identity, 'cash': config.seed_capital,
            'lineage': BirthLineage.founder(identity, config.strategy).to_dict()}, 'founder', identity)
    views = [_view(data, member, colony) for member in engine['members']]
    strategy.initialize(views, colony)
    cohort = EvaluationCohort(f'{config.run_id}:0', views, HORIZON_SECONDS)
    builder.add({'kind': 'lifecycle', 'status': 'running'}, 'lifecycle')
    return _candidate(None, data, strategy, cohort, builder, 'bootstrap', evidence, None)


def _start(state, observation, inputs):
    if type(state) is not ExactState or type(observation) is not ExactObservation:
        raise ExactRehearsalError('owned exact state and exact observation required')
    cursor, at, evidence = _inputs(inputs, observation)
    before = state.to_dict()
    data, strategy, cohort = state._fork()
    if data['engine']['generation'] >= MAX_GENERATIONS:
        raise ExactRehearsalError('completed-generation capacity reached')
    data['revision'] += 1
    return before, data, strategy, cohort, _Builder(data, cursor, at), evidence


def prepare_protective(state: ExactState, observation: ExactObservation,
                       inputs: DecisionInputs) -> ExactCandidate:
    before, data, strategy, cohort, builder, evidence = _start(state, observation, inputs)
    engine = data['engine']
    previous = engine['last_quote']
    if previous is not None and observation.timestamp <= previous['timestamp']:
        raise ExactRehearsalError('protective observations must advance source time')
    if observation.candle_end is not None:
        raise ExactRehearsalError('protective preparation accepts only quote evidence')
    for member in engine['members']:
        _risk(data, member, observation.price)
        position = _position(data, member['id'])
        if position is not None:
            reference = _amount(position['entry']['reference_price'], PRICE_SCALE, True)
            mark = _amount(observation.price, PRICE_SCALE, True)
            reason = ('stop_loss' if mark * 100 <= reference * 97 else
                      'take_profit' if mark * 100 >= reference * 107 else None)
            if reason is not None:
                builder.close(member, observation.price, reason)
    engine['last_quote'] = {'timestamp': observation.timestamp, 'price': observation.price}
    return _candidate(before, data, strategy, cohort, builder, 'protective', evidence, observation)


def _append_candle(engine, observation):
    ema = engine['ema']
    if observation.candle_end is None:
        return False
    if ema['last_end'] is not None:
        if observation.candle_end == ema['last_end']:
            if observation.candle_close != ema['closes'][-1]:
                raise ExactRehearsalError('completed candle revision forbidden')
            return False
        if observation.candle_end != ema['last_end'] + CANDLE_SECONDS:
            raise ExactRehearsalError('candle gaps and out-of-order history forbidden')
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
            raise ExactRehearsalError('unrepresentable indicator view')
        ema['values'][str(period)] = value.hex()
    return True


def _replace(data, strategy, cohort, builder, observation):
    engine, price = data['engine'], observation.price
    config = _configuration(data).colony_config()
    members = engine['members']
    for member in members:
        builder.close(member, price, 'cohort_liquidation')
    views = [_view(data, member, config) for member in members]
    evaluations = list(cohort.complete(views, observation.timestamp))
    result = strategy.evolve(evaluations, [], config)
    if len(result.offspring) != POPULATION or result.retire_ids != [member['id'] for member in members]:
        raise ExactRehearsalError('optimizer must replace the complete ordered cohort')
    ids = [_new_id(engine, builder.cursor) for _ in result.offspring]
    args = {'cohort_member_ids': [member['id'] for member in members]}
    if strategy.name == 'cma_es':
        args.update(distribution_id=_new_id(engine, builder.cursor),
                    previous_distribution_id=engine['distribution_id'])
    lineage = lineage_plan_from_evolution(strategy.name, result, evaluations, ids, **args)
    engine['last_evaluation'] = {'cohort': _views(cohort.to_dict()), 'selection': _views(result.metadata)}
    builder.events.append({'kind': 'evaluation', 'at': builder.at, 'account_id': None,
                           'position_id': None, 'operation_index': None})
    for member in members:
        account = _account(data, member['id'])
        data['reserve'] = credit_cash(data['reserve'], account['cash'])
        account.update(cash='0', retired=True)
        builder.add({'kind': 'retire', 'id': member['id']}, 'retire', member['id'])
    if lineage.distribution_operation is not None:
        builder.add(lineage.distribution_operation, 'distribution')
        engine['distribution_id'] = lineage.distribution.id
    next_members = []
    for identity, genome, birth in zip(ids, result.offspring, lineage.birth_lineages):
        config.assert_profile_genome(genome)
        # Flat ancestry remains a legacy view; typed lineage is the authoritative
        # operation evidence, including complete normalized CMA distributions.
        genome.parent_ids = list(result.parent_map[str(len(next_members))])
        name = builder.cursor.probe_name(genome.generation)
        if type(strategy) is ParticleSwarmStrategy:
            strategy.remap_probe_id(birth.sources[0].source_id, identity)
        seed = engine['config']['seed_capital']
        data['reserve'] = debit_cash(data['reserve'], seed)
        data['accounts'].append({'id': identity, 'cash': seed, 'initial_cash': seed, 'retired': False})
        next_members.append(_member(identity, genome, name, seed, engine['ema']['last_end']))
        builder.add({'kind': 'birth', 'id': identity, 'cash': seed, 'lineage': birth.to_dict()}, 'birth', identity)
    engine['members'] = next_members
    engine['generation'] += 1
    next_views = [_view(data, member, config) for member in next_members]
    strategy.bind_candidates(next_views)
    following = EvaluationCohort(f"{data['run_id']}:{engine['generation']}", next_views, HORIZON_SECONDS)
    following.start(observation.timestamp)
    return following


def _configuration(data):
    value = data['engine']['config']
    config = ExactRehearsalConfig(value['strategy'], data['owner_id'], data['run_id'],
        value['asset'], value['initial_cash'], value['seed_capital'], value['search_seed'],
        DecimalExecutionConfig.from_dict(value['execution']['config']))
    if config.to_dict() != value:
        raise ExactRehearsalError('unsupported rehearsal policy')
    return config


def prepare_decision(state: ExactState, observation: ExactObservation,
                     inputs: DecisionInputs) -> ExactCandidate:
    before, data, strategy, cohort, builder, evidence = _start(state, observation, inputs)
    engine = data['engine']
    if engine['last_quote'] != {'timestamp': observation.timestamp, 'price': observation.price}:
        raise ExactRehearsalError('decision requires this exact protective observation first')
    if engine['decision_timestamp'] is not None and observation.timestamp <= engine['decision_timestamp']:
        raise ExactRehearsalError('ordinary decision already consumed this source observation')
    new_candle = _append_candle(engine, observation)
    engine['decision_timestamp'] = observation.timestamp
    if cohort.phase == 'warming' and engine['ema']['count'] >= EMA_WARMUP_BARS:
        cohort.start(observation.timestamp)
    if cohort.due(observation.timestamp):
        cohort = _replace(data, strategy, cohort, builder, observation)
    elif cohort.phase == 'evaluating':
        config = _configuration(data).colony_config()
        for member in engine['members']:
            pending = member['pending']
            if pending is not None and observation.timestamp > pending['signal_at']:
                if observation.timestamp <= member['cursor'] + CANDLE_SECONDS:
                    position = _position(data, member['id'])
                    if pending['action'] == 'entry' and position is None:
                        builder.open(member, observation.price, pending['signal_at'])
                    elif (pending['action'] == 'exit' and position is not None
                          and position['id'] == pending['position_id']):
                        builder.close(member, observation.price, 'exit_signal', pending['signal_at'])
                member['pending'] = None
            if new_candle:
                ema = engine['ema']
                member['cursor'] = ema['last_end']
                member['pending'] = None
                # An old completed candle can warm indicators, never create a
                # retroactive fill permission at its delayed delivery time.
                if observation.timestamp <= ema['last_end'] + CANDLE_SECONDS:
                    genes = _genome(member['genome'], config).int_genes()
                    fast, slow = str(genes['ema_fast']), str(genes['ema_slow'])
                    values = (float.fromhex(ema['previous'][fast]), float.fromhex(ema['previous'][slow]),
                              float.fromhex(ema['values'][fast]), float.fromhex(ema['values'][slow]))
                    entry, exit = ema_crossing(*values)
                    position = _position(data, member['id'])
                    action = 'entry' if position is None and entry else 'exit' if position is not None and exit else None
                    if action is not None:
                        member['pending'] = {'action': action, 'signal_at': observation.timestamp,
                                             'position_id': None if position is None else position['id']}
    return _candidate(before, data, strategy, cohort, builder, 'decision', evidence, observation)


def prepare(state, observation, inputs):
    """Ordinary decision alias; protection remains an explicit prior candidate."""
    return prepare_decision(state, observation, inputs)
