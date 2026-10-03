"""Version-four exact lifecycle rehearsal, isolated from the active controller.

Fresh exact state only. Every operation forks owned solver/evaluation state and
returns a sealed candidate; none of these functions commits or installs it.
The version-three rehearsal and its historical command shape remain unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

from . import exact_rehearsal as base
from .decision_inputs import DecisionInputs
from .decimal_execution import CASH_SCALE, PRICE_SCALE, DecimalExecutionConfig, EntryPlan, credit_cash, debit_cash, mark_value
from .evaluation import EvaluationCohort
from .lineage import BirthLineage, SourceBinding, lineage_plan_from_evolution
from .optimizer_evidence import encode_optimizer_evidence
from .search_random import SearchRandomStreams
from .signal_profile import EMA_WARMUP_BARS, ema_crossing
from .strategies.particle_swarm import ParticleSwarmStrategy

ExactState = base.ExactState
ExactCandidate = base.ExactCandidate
ExactObservation = base.ExactObservation
ExactRehearsalError = base.ExactRehearsalError
PROFILE = 'ema-baseline-exact-lifecycle-v1'
CODE_VERSION = 'bounded-exact-lifecycle-v1'
LIFECYCLE_POLICY = 'exact-common-cohort-lifecycle-v1'


@dataclass(frozen=True, slots=True)
class ExactLifecycleConfig(base.ExactRehearsalConfig):
    account_loss_bps: str = '3000'

    def __post_init__(self):
        base.ExactRehearsalConfig.__post_init__(self)
        if (type(self.account_loss_bps) is not str
                or re.fullmatch(r'[1-9][0-9]{0,4}', self.account_loss_bps) is None
                or not 1 <= int(self.account_loss_bps) <= 10000):
            raise ExactRehearsalError('account loss limit requires canonical integer bps from 1 to 10000')

    def to_dict(self):
        value = base.ExactRehearsalConfig.to_dict(self)
        value.update(profile=PROFILE, code_version=CODE_VERSION, lifecycle_policy={
            'version': LIFECYCLE_POLICY, 'account_loss_bps': self.account_loss_bps,
            'death_drawdown_bps': '2000', 'max_lifespan_seconds': 0})
        return value

    def run_configuration(self):
        return {'durability_contract_version': 4, 'execution': self.execution.policy(),
                'rehearsal': self.to_dict()}


def _configuration(data):
    value = data['engine']['config']
    if (value.get('profile') != PROFILE or value.get('code_version') != CODE_VERSION
            or type(value.get('lifecycle_policy')) is not dict):
        raise ExactRehearsalError('only fresh version-four lifecycle state is supported')
    config = ExactLifecycleConfig(value['strategy'], data['owner_id'], data['run_id'],
        value['asset'], value['initial_cash'], value['seed_capital'], value['search_seed'],
        DecimalExecutionConfig.from_dict(value['execution']['config']),
        value['lifecycle_policy']['account_loss_bps'])
    if config.to_dict() != value:
        raise ExactRehearsalError('unsupported exact lifecycle policy')
    return config


def _candidate(before, data, strategy, cohort, builder, kind, evidence, observation, control=None):
    data['accounts'].sort(key=lambda row: row['id'])
    data['positions'].sort(key=lambda row: row['id'])
    data['engine']['optimizer'] = encode_optimizer_evidence(strategy, cohort)
    data['engine']['cohort'] = base._views(cohort.to_dict())
    if (len(data['accounts']) > base.POPULATION * (base.MAX_GENERATIONS + 1)
            or len(data['positions']) > base.MAX_POSITIONS
            or len(data['engine']['used_ids']) > 100):
        raise ExactRehearsalError('lifecycle rehearsal retention capacity reached')
    payload = {'version': 4, 'operations': builder.operations, 'transition': {
        'version': 1, 'before': before, 'after': data, 'evidence': {
            'kind': kind, 'inputs': evidence,
            'observation': None if observation is None else observation.to_dict(),
            'actions': builder.actions, 'control': control}, 'events': builder.events}}
    wire = base._json(payload)
    size = len(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(', ', ': ')).encode('utf-8'))
    if size > base.MAX_PAYLOAD_BYTES:
        raise ExactRehearsalError('whole lifecycle candidate exceeds payload capacity; splitting is forbidden')
    return ExactCandidate(ExactState._seal(data, strategy, cohort), wire, size)


def bootstrap(config: ExactLifecycleConfig, inputs: DecisionInputs) -> ExactCandidate:
    if type(config) is not ExactLifecycleConfig:
        raise ExactRehearsalError('fresh exact lifecycle configuration required')
    config.__post_init__()
    plain = base.ExactRehearsalConfig(config.strategy, config.owner_id, config.run_id,
        config.asset, config.initial_cash, config.seed_capital, config.search_seed, config.execution)
    original = base.bootstrap(plain, inputs)
    data, strategy, cohort = original.state._fork()
    cursor, at, evidence = base._inputs(inputs)
    engine = data['engine']
    engine['config'] = config.to_dict()
    engine['lifecycle'] = {'search_epoch': 0, 'restart_required': False, 'signals_after': None,
        'last_control_at': None, 'risk': {'active': False, 'baseline_equity': config.initial_cash,
        'observed_equity': config.initial_cash, 'observed_at': at, 'trip_id': None,
        'tripped_at': None, 'trip_equity': None, 'recovery_count': 0, 'last_recovered_at': None}}
    for member in engine['members']:
        member['terminal'] = None
    builder = base._Builder(data, cursor, at)
    builder.operations = original.operations
    builder.actions = original.transition['evidence']['actions']
    builder.events = original.transition['events']
    return _candidate(None, data, strategy, cohort, builder, 'bootstrap', evidence, None)


def _start(state, inputs, observation=None):
    if type(state) is not ExactState or (observation is not None and type(observation) is not ExactObservation):
        raise ExactRehearsalError('owned lifecycle state and exact observation required')
    cursor, at, evidence = base._inputs(inputs, observation)
    before = state.to_dict()
    _configuration(before)
    if before['status'] not in {'running', 'paused', 'risk_halted'}:
        raise ExactRehearsalError('terminal lifecycle state cannot advance')
    previous = before['engine']['last_quote']
    control_at = before['engine']['lifecycle']['last_control_at']
    if ((previous is not None and at < previous['timestamp'])
            or (control_at is not None and at < control_at)):
        raise ExactRehearsalError('lifecycle inputs cannot regress source or control time')
    data, strategy, cohort = state._fork()
    data['revision'] += 1
    return before, data, strategy, cohort, base._Builder(data, cursor, at), evidence


def _equity(data, price):
    total = base._amount(data['reserve']) + sum(base._amount(row['cash']) for row in data['accounts'])
    for position in data['positions']:
        if not position['closed']:
            total += base._amount(mark_value(EntryPlan.from_dict(position['entry']), price))
    return total


def _abort(data, strategy, cohort, builder, reason):
    if cohort.phase not in {'aborted', 'completed'}:
        cohort.abort(reason, builder.at)
        strategy.abort_cohort()
        data['engine']['last_evaluation'] = {'cohort': base._views(cohort.to_dict()), 'selection': None}
        builder.events.append({'kind': 'evaluation_aborted', 'at': builder.at,
            'account_id': None, 'position_id': None, 'operation_index': None})
    data['engine']['lifecycle']['restart_required'] = True


def _account_risk(data, strategy, cohort, builder, price):
    lifecycle = data['engine']['lifecycle']
    risk = lifecycle['risk']
    equity = _equity(data, price)
    risk.update(observed_equity=base._text(equity, CASH_SCALE), observed_at=builder.at)
    baseline = base._amount(risk['baseline_equity'])
    bps = int(data['engine']['config']['lifecycle_policy']['account_loss_bps'])
    if risk['active'] or equity * 10000 > baseline * (10000 - bps):
        return False
    # A rejected pure candidate cannot install this latch. Its caller must stop
    # decision admission after preparation failure rather than reuse old marks.
    trip = base._new_id(data['engine'], builder.cursor)
    risk.update(active=True, trip_id=trip, tripped_at=builder.at,
                trip_equity=base._text(equity, CASH_SCALE))
    for member in data['engine']['members']:
        if member['pending'] is not None and member['pending']['action'] == 'entry':
            member['pending'] = None
    _abort(data, strategy, cohort, builder, 'risk_halted')
    data['status'] = 'risk_halted'
    builder.add({'kind': 'lifecycle', 'status': 'risk_halted'}, 'risk_halt')
    return True


def _member_equity(data, member, price):
    total = base._amount(base._account(data, member['id'])['cash'])
    position = base._position(data, member['id'])
    if position is not None:
        total += base._amount(mark_value(EntryPlan.from_dict(position['entry']), price))
    return total


def _retire(data, member, builder, reason):
    account = base._account(data, member['id'])
    if account['retired'] or base._position(data, member['id']) is not None:
        raise ExactRehearsalError('retirement requires one owned liquidated account')
    data['reserve'] = credit_cash(data['reserve'], account['cash'])
    account.update(cash='0', retired=True)
    member['pending'] = None
    builder.add({'kind': 'retire', 'id': member['id']}, reason, member['id'])


def _terminal(data, strategy, cohort, builder, member, price):
    if member['terminal'] is not None:
        return
    base._risk(data, member, price)
    equity, peak = _member_equity(data, member, price), base._amount(member['peak_equity'])
    if equity * 10000 > peak * 8000:
        return
    builder.close(member, price, 'death_liquidation')
    account = base._account(data, member['id'])
    member['terminal'] = {'reason': 'drawdown', 'at': builder.at, 'cash': account['cash']}
    if cohort.phase == 'evaluating':
        cohort.record_terminal(base._view(data, member, _configuration(data).colony_config()),
                               'drawdown', builder.at)
    _retire(data, member, builder, 'terminal')


def prepare_protective(state: ExactState, observation: ExactObservation,
                       inputs: DecisionInputs) -> ExactCandidate:
    if type(observation) is not ExactObservation:
        raise ExactRehearsalError('exact protective observation required')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation)
    if data['status'] not in {'running', 'risk_halted'}:
        raise ExactRehearsalError('paused lifecycle does not consume quotes')
    engine = data['engine']
    previous = engine['last_quote']
    if (observation.candle_end is not None
            or previous is not None and observation.timestamp <= previous['timestamp']):
        raise ExactRehearsalError('protective quote must strictly advance source time without a candle')
    engine['last_quote'] = {'timestamp': observation.timestamp, 'price': observation.price}
    _account_risk(data, strategy, cohort, builder, observation.price)
    # Finish every valid protective close before ordinary decisions. Terminal
    # cash remains as frozen evidence in its original evaluation membership.
    for member in engine['members']:
        if member['terminal'] is not None:
            continue
        base._risk(data, member, observation.price)
        position = base._position(data, member['id'])
        if position is not None:
            reference = base._amount(position['entry']['reference_price'], PRICE_SCALE, True)
            mark = base._amount(observation.price, PRICE_SCALE, True)
            reason = ('stop_loss' if mark * 100 <= reference * 97 else
                      'take_profit' if mark * 100 >= reference * 107 else None)
            if reason is not None:
                builder.close(member, observation.price, reason)
                _account_risk(data, strategy, cohort, builder, observation.price)
        _terminal(data, strategy, cohort, builder, member, observation.price)
        _account_risk(data, strategy, cohort, builder, observation.price)
    return _candidate(before, data, strategy, cohort, builder, 'protective', evidence, observation)


def _capacity(data):
    if data['engine']['generation'] >= base.MAX_GENERATIONS:
        raise ExactRehearsalError('completed-generation capacity reached')
    required = base._amount(data['engine']['config']['seed_capital']) * base.POPULATION
    available = base._amount(data['reserve']) + sum(
        base._amount(base._account(data, member['id'])['cash'])
        for member in data['engine']['members'] if member['terminal'] is None)
    if available < required:
        raise ExactRehearsalError('complete next cohort cannot be funded')


def _liquidate(data, strategy, cohort, builder, price, reason):
    for member in data['engine']['members']:
        if member['terminal'] is None:
            builder.close(member, price, reason)
            # Costs may latch during the first close even if a later close's
            # outcome would improve a mark. The active trip is never unlatchable
            # by later operations inside the same preparation.
            _account_risk(data, strategy, cohort, builder, price)


def _new_member(identity, genome, name, seed, cursor):
    member = base._member(identity, genome, name, seed, cursor)
    member['terminal'] = None
    return member


def _restart(data, strategy, cohort, builder, observation):
    engine, lifecycle = data['engine'], data['engine']['lifecycle']
    if cohort.phase != 'aborted' or not lifecycle['restart_required']:
        raise ExactRehearsalError('restart requires a retained interrupted cohort')
    if lifecycle['signals_after'] is None or observation.timestamp <= lifecycle['signals_after']:
        raise ExactRehearsalError('restart requires a later independently accepted quote')
    _liquidate(data, strategy, cohort, builder, observation.price, 'restart_liquidation')
    if lifecycle['risk']['active']:
        return cohort
    _capacity(data)
    config = _configuration(data).colony_config()
    sources = engine['members']
    genomes = [base._genome(member['genome'], config) for member in sources]
    ids = [base._new_id(engine, builder.cursor) for _ in sources]
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
            (SourceBinding('clone_source', source['id']), SourceBinding('asset_template', source['id'])),
            version=2)
        data['reserve'] = debit_cash(data['reserve'], seed)
        data['accounts'].append({'id': identity, 'cash': seed, 'initial_cash': seed, 'retired': False})
        next_members.append(_new_member(identity, genome, name, seed, engine['ema']['last_end']))
        builder.add({'kind': 'birth', 'id': identity, 'cash': seed, 'lineage': lineage.to_dict()},
                    'restart_birth', identity)
    engine['members'] = next_members
    engine['generation'] += 1
    engine['distribution_id'] = None
    lifecycle['search_epoch'] += 1
    lifecycle['restart_required'] = False
    lifecycle['signals_after'] = observation.timestamp
    # Explicitly discarded interrupted optimizer state is never told. Restart
    # uses the original bound phenotypes and a new deterministic search epoch.
    strategy.configure_search(SearchRandomStreams(engine['config']['search_seed'], strategy.name),
                              lifecycle['search_epoch'])
    views = [base._view(data, member, config) for member in next_members]
    strategy.initialize(views, config)
    following = EvaluationCohort(f"{data['run_id']}:{engine['generation']}", views, base.HORIZON_SECONDS)
    return following


def _replace(data, strategy, cohort, builder, observation):
    engine = data['engine']
    _liquidate(data, strategy, cohort, builder, observation.price, 'cohort_liquidation')
    if engine['lifecycle']['risk']['active']:
        return cohort
    _capacity(data)
    config = _configuration(data).colony_config()
    members = engine['members']
    survivors = [base._view(data, member, config) for member in members if member['terminal'] is None]
    evaluations = list(cohort.complete(survivors, observation.timestamp))
    result = strategy.evolve(evaluations, [], config)
    if len(result.offspring) != base.POPULATION or result.retire_ids != [member['id'] for member in members]:
        raise ExactRehearsalError('optimizer must replace the complete ordered original cohort')
    ids = [base._new_id(engine, builder.cursor) for _ in result.offspring]
    args = {'cohort_member_ids': [member['id'] for member in members]}
    if strategy.name == 'cma_es':
        args.update(distribution_id=base._new_id(engine, builder.cursor),
                    previous_distribution_id=engine['distribution_id'])
    lineage = lineage_plan_from_evolution(strategy.name, result, evaluations, ids, **args)
    engine['last_evaluation'] = {'cohort': base._views(cohort.to_dict()), 'selection': base._views(result.metadata)}
    builder.events.append({'kind': 'evaluation', 'at': builder.at, 'account_id': None,
                           'position_id': None, 'operation_index': None})
    names = [builder.cursor.probe_name(genome.generation) for genome in result.offspring]
    for member in members:
        if member['terminal'] is None:
            _retire(data, member, builder, 'retire')
    if lineage.distribution_operation is not None:
        builder.add(lineage.distribution_operation, 'distribution')
        engine['distribution_id'] = lineage.distribution.id
    next_members = []
    seed = engine['config']['seed_capital']
    for index, (identity, genome, birth, name) in enumerate(zip(ids, result.offspring, lineage.birth_lineages, names)):
        config.assert_profile_genome(genome)
        genome.parent_ids = list(result.parent_map[str(index)])
        if type(strategy) is ParticleSwarmStrategy:
            strategy.remap_probe_id(birth.sources[0].source_id, identity)
        data['reserve'] = debit_cash(data['reserve'], seed)
        data['accounts'].append({'id': identity, 'cash': seed, 'initial_cash': seed, 'retired': False})
        next_members.append(_new_member(identity, genome, name, seed, engine['ema']['last_end']))
        builder.add({'kind': 'birth', 'id': identity, 'cash': seed, 'lineage': birth.to_dict()}, 'birth', identity)
    engine['members'] = next_members
    engine['generation'] += 1
    views = [base._view(data, member, config) for member in next_members]
    strategy.bind_candidates(views)
    following = EvaluationCohort(f"{data['run_id']}:{engine['generation']}", views, base.HORIZON_SECONDS)
    if _history_ready(engine, observation.timestamp):
        following.start(observation.timestamp)
    return following


def _pending(data, strategy, cohort, builder, member, observation, allow_entry):
    pending = member['pending']
    if pending is None or observation.timestamp <= pending['signal_at']:
        return
    if observation.timestamp <= member['cursor'] + base.CANDLE_SECONDS:
        position = base._position(data, member['id'])
        if pending['action'] == 'entry' and position is None and allow_entry:
            builder.open(member, observation.price, pending['signal_at'])
        elif pending['action'] == 'exit' and position is not None and position['id'] == pending['position_id']:
            builder.close(member, observation.price, 'exit_signal', pending['signal_at'])
        _account_risk(data, strategy, cohort, builder, observation.price)
        _terminal(data, strategy, cohort, builder, member, observation.price)
        _account_risk(data, strategy, cohort, builder, observation.price)
    member['pending'] = None


def _history_ready(engine, timestamp):
    end = engine['ema']['last_end']
    return (engine['ema']['count'] >= EMA_WARMUP_BARS and end is not None
            and end <= timestamp <= end + base.CANDLE_SECONDS)


def prepare_decision(state: ExactState, observation: ExactObservation,
                     inputs: DecisionInputs) -> ExactCandidate:
    if type(observation) is not ExactObservation:
        raise ExactRehearsalError('exact decision observation required')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation)
    if data['status'] not in {'running', 'risk_halted'}:
        raise ExactRehearsalError('paused lifecycle does not consume decisions')
    engine, lifecycle = data['engine'], data['engine']['lifecycle']
    if engine['last_quote'] != {'timestamp': observation.timestamp, 'price': observation.price}:
        raise ExactRehearsalError('decision requires this exact accepted protective observation')
    if engine['decision_timestamp'] is not None and observation.timestamp <= engine['decision_timestamp']:
        raise ExactRehearsalError('decision already consumed this observation')
    engine['decision_timestamp'] = observation.timestamp
    # Risk monitoring and previously eligible exits need no candle provider.
    # Supplied candles are deliberately not ingested while halted.
    if lifecycle['risk']['active']:
        for member in engine['members']:
            if member['terminal'] is None:
                _pending(data, strategy, cohort, builder, member, observation, False)
        return _candidate(before, data, strategy, cohort, builder, 'decision', evidence, observation)
    new_candle = base._append_candle(engine, observation)
    if lifecycle['restart_required']:
        if _history_ready(engine, observation.timestamp):
            cohort = _restart(data, strategy, cohort, builder, observation)
    elif cohort.phase == 'warming':
        if _history_ready(engine, observation.timestamp):
            cohort.start(observation.timestamp)
    elif cohort.due(observation.timestamp):
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
                after = lifecycle['signals_after']
                if (observation.timestamp <= ema['last_end'] + base.CANDLE_SECONDS
                        and (after is None or ema['last_end'] > after)):
                    genes = base._genome(member['genome'], config).int_genes()
                    fast, slow = str(genes['ema_fast']), str(genes['ema_slow'])
                    values = (float.fromhex(ema['previous'][fast]), float.fromhex(ema['previous'][slow]),
                              float.fromhex(ema['values'][fast]), float.fromhex(ema['values'][slow]))
                    entry, exit_signal = ema_crossing(*values)
                    position = base._position(data, member['id'])
                    action = 'entry' if position is None and entry else 'exit' if position is not None and exit_signal else None
                    if action is not None:
                        member['pending'] = {'action': action, 'signal_at': observation.timestamp,
                            'position_id': None if position is None else position['id']}
    return _candidate(before, data, strategy, cohort, builder, 'decision', evidence, observation)


def prepare_control(state: ExactState, action: str, inputs: DecisionInputs,
                    observation: ExactObservation | None = None, trip_id: str | None = None) -> ExactCandidate:
    if type(action) is not str or action not in {'pause', 'resume', 'stop', 'recover'}:
        raise ExactRehearsalError('unsupported lifecycle action')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation)
    engine, lifecycle = data['engine'], data['engine']['lifecycle']
    risk = lifecycle['risk']
    required = {'pause': {'running'}, 'resume': {'paused'}, 'recover': {'risk_halted'},
                'stop': {'running', 'paused', 'risk_halted'}}[action]
    if data['status'] not in required or (action != 'recover' and (trip_id is not None or observation is not None)):
        raise ExactRehearsalError('control does not match current lifecycle state')
    if action == 'recover':
        base._uuid(trip_id)
        if not risk['active'] or trip_id != risk['trip_id']:
            raise ExactRehearsalError('recovery must acknowledge the current active trip')
        if (observation is None or observation.candle_end is None
                or engine['last_quote'] != {'timestamp': observation.timestamp, 'price': observation.price}
                or observation.timestamp > observation.candle_end + base.CANDLE_SECONDS):
            raise ExactRehearsalError('recovery requires the accepted quote and current completed candle')
        if not any(member['terminal'] is None for member in engine['members']):
            raise ExactRehearsalError('recovery requires surviving candidates')
        base._append_candle(engine, observation)
        if engine['ema']['count'] < EMA_WARMUP_BARS:
            raise ExactRehearsalError('recovery requires fully warmed contiguous history')
        _account_risk(data, strategy, cohort, builder, observation.price)
        equity, baseline = base._amount(risk['observed_equity']), base._amount(risk['baseline_equity'])
        bps = int(engine['config']['lifecycle_policy']['account_loss_bps'])
        if equity * 10000 <= baseline * (10000 - bps):
            raise ExactRehearsalError('original account-loss boundary remains breached')
        risk.update(active=False, recovery_count=risk['recovery_count'] + 1, last_recovered_at=builder.at)
    if action in {'pause', 'stop'}:
        _abort(data, strategy, cohort, builder, 'paused' if action == 'pause' else 'stopped')
    for member in engine['members']:
        member['pending'] = None
    if action in {'resume', 'recover'}:
        lifecycle['signals_after'] = builder.at
    lifecycle['last_control_at'] = builder.at
    data['status'] = {'pause': 'paused', 'resume': 'running', 'recover': 'running', 'stop': 'stopped'}[action]
    builder.add({'kind': 'lifecycle', 'status': data['status']}, action)
    return _candidate(before, data, strategy, cohort, builder, 'control', evidence, observation,
                      {'action': action, 'trip_id': trip_id})


def prepare(state, observation, inputs):
    return prepare_decision(state, observation, inputs)
