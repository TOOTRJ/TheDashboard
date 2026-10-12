"""Fresh provider-bound GA model and atomic provenance research boundary.

No production imports, native command version, decoder or activation authority.
SimulationLedger is a credential-free test ledger, NOT durable SQL admission.
The v3/v4/v5 policies and caps remain unchanged. Reviewed lifecycle rules below
are copied deliberately so this research version cannot alter old runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from fractions import Fraction
from datetime import datetime
import json
import re

from ..core import exact_rehearsal as base
from ..core.decision_inputs import DecisionInputs, MAX_GENERATION
from ..core.decimal_execution import CASH_SCALE, PRICE_SCALE, DecimalExecutionConfig, EntryPlan, credit_cash, debit_cash, mark_value
from ..core.evaluation import EvaluationCohort
from ..core.lineage import BirthLineage, SourceBinding, lineage_plan_from_evolution
from ..core.optimizer_evidence import encode_optimizer_evidence
from ..core.search_random import SearchRandomStreams
from ..core.signal_profile import EMA_WARMUP_BARS, ema_crossing
from ..core.evolution import FITNESS_POLICY
from . import provider_source as source
from .exact_configuration import ConfigurationFormatError, validate_configuration
from ..core.provider_lifecycle import evidence_clocks

ExactObservation = base.ExactObservation
ExactRehearsalError = base.ExactRehearsalError
PROFILE = 'ema-ga-provider-research-v1'
CODE_VERSION = 'fresh-ga-provider-research-v1'
LIFECYCLE_POLICY = 'ga-active-common-cohort-research-v1'
MODEL_FORMAT = 'ga-provider-model-research-v1'
COMMAND_FORMAT = 'ga-provider-transition-research-v1'
ASSESSMENT_FORMAT = 'ga-provider-assessment-research-v1'
SOURCE_POLICY = source.SOURCE_VERSION
MAX_COUNTER = 2**63 - 1
COUNTER_POLICY = {'version': 'signed-bigint-reserved-stop-research-v1',
    'maximum': str(MAX_COUNTER), 'ordinary_revision_maximum': str(MAX_COUNTER - 1),
    'timestamp_maximum': str(2**40),
    'generation_maximum': str(MAX_GENERATION),
    'overflow': 'reject_without_install', 'last_revision': 'stop_only'}
_PINNED_FITNESS = {'version': 'equity-roi-historical-dd-v1',
    'formula': 'portfolio_roi - 2 * observed_historical_max_drawdown',
    'drawdown_weight': 2.0, 'status': 'provisional_heuristic', 'sharpe_in_fitness': False}


def _counter(value, label, *, stop=False):
    if type(value) is not int or not 0 <= value < MAX_COUNTER - (0 if stop else 1):
        raise base.ExactCapacityError(f'{label} capacity reached; Stop remains reserved')


class GAState:
    """Owned in-process fork only; JSON and checkpoints cannot construct it."""
    __slots__ = ('__owned',)

    def __init__(self, *args, **kwargs):
        raise ExactRehearsalError('only fresh GA bootstrap can create state')

    def __setattr__(self, name, value):
        raise AttributeError('GA state is immutable')

    @classmethod
    def _seal(cls, data, strategy, cohort):
        value = object.__new__(cls)
        object.__setattr__(value, '_GAState__owned', base.ExactState._seal(data, strategy, cohort))
        return value

    def to_dict(self):
        return self.__owned.to_dict()

    def _fork(self):
        return self.__owned._fork()

    def __deepcopy__(self, memo):
        return self  # The private seal can only be accessed through detached forks.

    @property
    def revision(self):
        return self.__owned.revision


@dataclass(frozen=True, slots=True)
class GACandidate:
    state: GAState
    _wire: bytes
    _payload_bytes: int

    def __post_init__(self):
        if type(self.state) is not GAState or type(self._wire) is not bytes:
            raise ExactRehearsalError('owned fresh GA candidate required')
        if len(self._wire) > base.MAX_PAYLOAD_BYTES:
            raise base.ExactCapacityError('complete GA candidate exceeds capacity')
        try:
            value = json.loads(self._wire)
            size = len(json.dumps(value, sort_keys=True, ensure_ascii=False,
                allow_nan=False, separators=(', ', ': ')).encode('utf-8'))
            if (value['format'] != COMMAND_FORMAT or base._json(value) != self._wire
                    or value['transition']['after'] != self.state.to_dict()
                    or type(self._payload_bytes) is not int or self._payload_bytes != size):
                raise ValueError()
            # Plain dictionary equality above cannot distinguish False from 0.
            # Require the configuration contract independently for both wires.
            _configuration(value['transition']['after'])
            if value['transition']['before'] is not None:
                _configuration(value['transition']['before'])
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ExactRehearsalError('GA candidate evidence differs from its state') from None
        if size > base.MAX_PAYLOAD_BYTES:
            raise base.ExactCapacityError('complete GA candidate exceeds capacity')

    @property
    def operations(self):
        return json.loads(self._wire)['operations']

    @property
    def transition(self):
        return json.loads(self._wire)['transition']

    @property
    def history(self):
        return json.loads(self._wire)['history']

    @property
    def payload_bytes(self):
        return self._payload_bytes


class SimulationLedger:
    """Offline append-only acceptance oracle, deliberately not a DB capability.

    Identity/history indexes grow HERE, never in a prepared active checkpoint.
    Preparation only reads them; acceptance replays exact cash/holdings and
    publishes all delta rows together. SQL enforcement is still PAPER-COMPACT-03.
    """
    def __init__(self, owner_id, run_id):
        base._uuid(owner_id); base._uuid(run_id)
        self.owner_id, self.run_id = owner_id, run_id
        self._current = None
        self._owned_current = None
        self._identities = set()
        self._history = []
        self._accepted = set()

    def check(self, before, owner, run):
        if (owner, run) != (self.owner_id, self.run_id) or before != self._current:
            raise ExactRehearsalError('simulation ledger owner/run/prior state differs')

    def used(self, identity):
        return identity in self._identities

    @property
    def history(self):
        return [json.loads(row) for row in self._history]

    def accept(self, candidate):
        if type(candidate) is not GACandidate:
            raise ExactRehearsalError('simulation accepts only owned fresh GA candidates')
        candidate.__post_init__()
        if candidate._wire in self._accepted:
            # Original-wire replay only; this is no native commit receipt.
            return self._owned_current
        before, after = candidate.transition['before'], candidate.state.to_dict()
        self.check(before, after['owner_id'], after['run_id'])
        # Reexecute the original preparation from the held in-process seal.
        # This is model consistency, not independent SQL/source admission.
        evidence = candidate.transition['evidence']
        supplied = evidence['inputs']
        inputs = DecisionInputs(datetime.fromisoformat(supplied['event_at']),
            datetime.fromisoformat(supplied['wall_at']), float.fromhex(supplied['monotonic_at']),
            tuple(supplied['ids']), tuple(tuple(name) for name in supplied['names']))
        provider = supplied['provider']
        observation = evidence['observation']
        observation = None if observation is None else ExactObservation(**observation)
        if before is None:
            replayed = bootstrap(_configuration(after), provider['history'], inputs, ledger=self)
        elif evidence['kind'] == 'protective':
            replayed = prepare_protective(self._owned_current, provider['frame'], inputs, ledger=self)
        elif evidence['kind'] == 'decision':
            replayed = prepare_decision(self._owned_current, provider['frame'], provider['history'], inputs, ledger=self)
        elif evidence['kind'] == 'control':
            control = evidence['control']
            replayed = prepare_control(self._owned_current, control['action'], inputs,
                frame=provider['frame'], history=provider['history'], trip_id=control['trip_id'], ledger=self)
        else:
            raise ExactRehearsalError('unknown original GA preparation')
        if candidate._wire != replayed._wire:
            raise ExactRehearsalError('complete history/provenance boundary differs from original preparation')
        history = candidate.history
        identities = history['allocated_ids']
        if (len(identities) != len(set(identities))
                or any(self.used(identity) for identity in identities)):
            raise ExactRehearsalError('historical identity reuse')
        accounts = {} if before is None else {a['id']: deepcopy(a) for a in before['accounts']}
        positions = {} if before is None else {p['id']: deepcopy(p) for p in before['positions']}
        reserve = after['engine']['config']['initial_cash'] if before is None else before['reserve']
        closed, retired, allocated = [], [], []
        for op in candidate.operations:
            kind = op['kind']
            if kind == 'birth':
                identity = op['id']; allocated.append(identity)
                if identity in accounts: raise ExactRehearsalError('duplicate birth')
                reserve = debit_cash(reserve, op['cash'])
                accounts[identity] = {'id': identity, 'cash': op['cash'],
                    'initial_cash': op['cash'], 'retired': False}
            elif kind == 'open':
                identity = op['id']; allocated.append(identity)
                if identity in positions or any(p['account_id'] == op['account_id'] for p in positions.values()):
                    raise ExactRehearsalError('duplicate or second held position')
                plan = EntryPlan.from_dict(op['execution'])
                account = accounts[op['account_id']]
                account['cash'] = debit_cash(account['cash'], plan.cash_debit)
                positions[identity] = {'id': identity, 'account_id': op['account_id'],
                    'asset': op['asset'], 'entry': plan.to_dict(), 'exit': None, 'closed': False}
            elif kind == 'close':
                from ..core.decimal_execution import ExitPlan
                position = positions.pop(op['id'])
                plan = ExitPlan.from_dict(op['execution'])
                if plan.entry.to_dict() != position['entry']:
                    raise ExactRehearsalError('close changed original entry')
                account = accounts[position['account_id']]
                account['cash'] = credit_cash(account['cash'], plan.cash_credit)
                position.update(exit=plan.to_dict(), closed=True)
                closed.append(position)
            elif kind == 'retire':
                account = accounts[op['id']]
                if account['retired'] or any(p['account_id'] == op['id'] for p in positions.values()):
                    raise ExactRehearsalError('retire requires liquidated active account')
                # The immutable history retains PRE-transfer cash.
                retired.append(deepcopy(account))
                reserve = credit_cash(reserve, account['cash'])
                account.update(cash='0', retired=True)
            elif kind != 'lifecycle':
                raise ExactRehearsalError('unsupported GA ledger operation')
        old_trip = None if before is None else before['engine']['lifecycle']['risk']['trip_id']
        new_trip = after['engine']['lifecycle']['risk']['trip_id']
        if new_trip is not None and new_trip != old_trip: allocated.append(new_trip)
        members = {m['id'] for m in after['engine']['members']}
        expected_accounts = sorted((a for key, a in accounts.items() if key in members), key=lambda a: a['id'])
        if (set(allocated) != set(identities) or len(allocated) != len(identities)
                or after['reserve'] != reserve or after['accounts'] != expected_accounts
                or after['positions'] != sorted(positions.values(), key=lambda p: p['id'])
                or sorted(closed, key=lambda p: p['id']) != history['closed_positions']
                or retired != [row['account'] for row in history['retired_accounts']]):
            raise ExactRehearsalError('complete cash/holding/history boundary differs')
        # No published state/index/history mutation occurs before all checks.
        self._identities.update(identities)
        self._history.append(base._json(history))
        self._current = after
        self._owned_current = candidate.state
        self._accepted.add(candidate._wire)
        return candidate.state


class _Builder(base._Builder):
    def __init__(self, data, cursor, at, ledger):
        super().__init__(data, cursor, at)
        self.ledger = ledger
        self.allocations, self.retired, self.assessments = [], [], []
        self.selection = None

    def allocate(self, identity):
        base._uuid(identity)
        if self.ledger.used(identity) or identity in self.allocations:
            raise ExactRehearsalError('historical identity reuse')
        self.allocations.append(identity)
        return identity

    def new_id(self):
        return self.allocate(self.cursor.next_id())

    def close(self, member, price, reason, signal_at=None):
        if base._position(self.data, member['id']) is not None:
            _counter(member['num_trades'], 'closed trade count')
        super().close(member, price, reason, signal_at)

    def open(self, member, price, signal_at):
        if sum(not p['closed'] for p in self.data['positions']) >= 8:
            raise base.ExactCapacityError('eight active holdings capacity reached')
        if base._position(self.data, member['id']) is not None:
            raise ExactRehearsalError('one holding per candidate required')
        account = base._account(self.data, member['id'])
        budget = base._text(base._amount(account['cash']) // 4, CASH_SCALE)
        config = DecimalExecutionConfig.from_dict(self.data['engine']['config']['execution']['config'])
        plan = EntryPlan(budget, price, config)
        identity = self.new_id()
        account['cash'] = debit_cash(account['cash'], plan.cash_debit)
        self.data['positions'].append({'id': identity, 'account_id': member['id'],
            'asset': self.data['engine']['config']['asset'], 'entry': plan.to_dict(), 'exit': None, 'closed': False})
        self.add({'kind': 'open', 'id': identity, 'account_id': member['id'],
            'asset': self.data['engine']['config']['asset'], 'quantity': plan.quantity,
            'notional': plan.notional, 'fee': plan.fee, 'execution': plan.to_dict()},
            'entry_signal', member['id'], identity, signal_at, price)
        member['pending'] = None
        base._risk(self.data, member, price)


def _source_cursor(data, at):
    state = data['source']
    frame = state['last_quote']
    return {'policy': SOURCE_POLICY, 'epoch': state['epoch'], 'sequence': state['quote_sequence'],
        'at': at, 'candle_count': data['engine']['ema']['count'],
        'bar': deepcopy(state['bars'][-1]),
        'frame': deepcopy(frame)}


def _snapshot(data, member, cohort, builder, result=None):
    account = base._account(data, member['id'])
    cash, initial = base._amount(account['cash']), base._amount(account['initial_cash'])
    roi = Fraction(cash - initial, initial)
    dd = deepcopy(member['max_drawdown'])
    view = base._view(data, member, _configuration(data).colony_config())
    if result is not None and (view.fitness != result.fitness or view.roi != result.roi
                              or view.num_trades != result.num_trades):
        raise ExactRehearsalError('final assessment disagrees with optimizer result')
    held = base._position(data, member['id'])
    return {'captured_revision': data['revision'], 'captured_at': builder.at,
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
            raise ExactRehearsalError('complete ordered assessment batch required')
        builder.assessments.append({'format': ASSESSMENT_FORMAT,
            'owner_id': data['owner_id'], 'run_id': data['run_id'],
            'finalized_revision': data['revision'], 'finalized_at': builder.at,
            'iteration_id': cohort.iteration_id, 'evaluation_id': cohort._evaluation_ids[member['id']],
            'member_index': index, 'probe_id': member['id'], 'generation': data['engine']['generation'],
            'status': 'aborted' if aborted else 'completed', 'reason': reason if aborted else result.reason,
            'selection_eligible': not aborted, 'cohort_complete': not aborted,
            'window_started_at': cohort.started_at, 'window_ends_at': cohort.ends_at,
            'window_source_start': deepcopy(data['engine']['cohort_source']),
            'window_source_end': _source_cursor(data, builder.at),
            'fitness_policy': base._views(dict(FITNESS_POLICY)),
            'evaluation_policy': deepcopy(cohort.to_dict()['policy']),
            'execution': deepcopy(data['engine']['config']['execution']),
            'measurement_basis': 'post-liquidation-closed-fills' if not aborted else 'interrupted-unscored-snapshot',
            'early_terminal_frozen': frozen is not None,
            'roi_float64': None if aborted else metrics['roi_float64'],
            'fitness_float64': None if aborted else metrics['fitness_float64'],
            'metrics': metrics})


def _candidate(before, data, strategy, cohort, builder, kind, evidence, observation, control=None):
    members = {m['id'] for m in data['engine']['members']}
    birth_ids = {op['id'] for op in builder.operations if op['kind'] == 'birth'}
    births = [deepcopy(m) for m in data['engine']['members'] if m['id'] in birth_ids]
    closed = sorted((deepcopy(p) for p in data['positions'] if p['closed']), key=lambda p: p['id'])
    data['accounts'] = sorted((a for a in data['accounts'] if a['id'] in members), key=lambda a: a['id'])
    data['positions'] = sorted((p for p in data['positions'] if not p['closed']), key=lambda p: p['id'])
    data['engine']['optimizer'] = encode_optimizer_evidence(strategy, cohort)
    data['engine']['cohort'] = base._views(cohort.to_dict())
    if (len(data['accounts']) != 8 or len(members) != 8 or len(data['positions']) > 8
            or len(closed) > 8 or len(builder.retired) > 8 or len(builder.assessments) > 8
            or len(builder.allocations) > 17 or len(builder.operations) > 33
            or any(p['account_id'] not in members for p in data['positions'])):
        raise base.ExactCapacityError('active/history boundary exceeds fixed fanout')
    payload = {'format': COMMAND_FORMAT, 'operations': builder.operations,
        'history': {'owner_id': data['owner_id'], 'run_id': data['run_id'], 'revision': data['revision'],
            'allocated_ids': builder.allocations, 'closed_positions': closed,
            'birth_members': births, 'retired_accounts': builder.retired, 'assessments': builder.assessments,
            'selection': builder.selection},
        'transition': {'before': before, 'after': data, 'evidence': {'kind': kind,
            'inputs': evidence, 'observation': None if observation is None else observation.to_dict(),
            'actions': builder.actions, 'control': control}, 'events': builder.events}}
    wire = base._json(payload)
    size = len(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(', ', ': ')).encode('utf-8'))
    return GACandidate(GAState._seal(data, strategy, cohort), wire, size)


@dataclass(frozen=True, slots=True)
class GAConfig(base.ExactRehearsalConfig):
    account_loss_bps: str = '3000'
    source_epoch: str = '00000000-0000-0000-0000-000000000001'

    def __post_init__(self):
        base.ExactRehearsalConfig.__post_init__(self)
        source.source_policy(self.source_epoch)
        if self.asset != 'SOL/USD':
            raise ExactRehearsalError('provider GA requires exact SOL/USD')
        if self.strategy != 'genetic_algorithm':
            raise ExactRehearsalError('fresh active model is GA-only')
        if base._json(FITNESS_POLICY) != base._json(_PINNED_FITNESS):
            raise ExactRehearsalError('fitness policy changed without model review')
        if (type(self.account_loss_bps) is not str
                or re.fullmatch(r'[1-9][0-9]{0,4}', self.account_loss_bps) is None
                or not 1 <= int(self.account_loss_bps) <= 10000):
            raise ExactRehearsalError('account loss limit requires canonical integer bps from 1 to 10000')

    def to_dict(self):
        value = base.ExactRehearsalConfig.to_dict(self)
        value.update(profile=PROFILE, code_version=CODE_VERSION, max_generations=MAX_GENERATION,
                     max_positions=8, counter_policy=dict(COUNTER_POLICY),
                     source_policy=source.source_policy(self.source_epoch),
                     assessment_policy=ASSESSMENT_FORMAT, lifecycle_policy={
            'version': LIFECYCLE_POLICY, 'account_loss_bps': self.account_loss_bps,
            'death_drawdown_bps': '2000', 'max_lifespan_seconds': 0})
        return value

    def run_configuration(self):
        return {'research_model': MODEL_FORMAT, 'execution': self.execution.policy(),
                'rehearsal': self.to_dict()}


# Trusted defaults supply only the immutable field/type/policy shape. Caller
# evidence is checked against these bytes before its scalar values are consumed.
_CONFIGURATION_TEMPLATE_WIRE = base._json(GAConfig('genetic_algorithm',
    '00000000-0000-0000-0000-000000000000', '00000000-0000-0000-0000-000000000000',
    asset='SOL/USD').to_dict())


def _configuration(data):
    value = data['engine']['config']
    try:
        validate_configuration(value, _CONFIGURATION_TEMPLATE_WIRE)
    except ConfigurationFormatError:
        raise ExactRehearsalError('unsupported exact configuration types/policy') from None
    config = GAConfig(value['strategy'], data['owner_id'], data['run_id'],
        value['asset'], value['initial_cash'], value['seed_capital'], value['search_seed'],
        DecimalExecutionConfig.from_dict(value['execution']['config']),
        value['lifecycle_policy']['account_loss_bps'], value['source_policy']['epoch'])
    if base._json(config.to_dict()) != base._json(value):
        raise ExactRehearsalError('unsupported exact lifecycle policy')
    return config



def bootstrap(config: GAConfig, history, inputs: DecisionInputs, *, ledger: SimulationLedger) -> GACandidate:
    if type(config) is not GAConfig:
        raise ExactRehearsalError('fresh exact lifecycle configuration required')
    config.__post_init__()
    ledger.check(None, config.owner_id, config.run_id)
    wall, mono = evidence_clocks(inputs)
    source.validate_history(history, prior_bars=[], seed=True, wall_us=wall, monotonic_us=mono)
    plain = base.ExactRehearsalConfig(config.strategy, config.owner_id, config.run_id,
        config.asset, config.initial_cash, config.seed_capital, config.search_seed, config.execution)
    original = base.bootstrap(plain, inputs)
    data, strategy, cohort = original.state._fork()
    cursor, at, evidence = base._inputs(inputs)
    engine = data['engine']
    allocations = engine.pop('used_ids')
    engine.pop('distribution_id'); engine.pop('last_evaluation')
    data['version'] = MODEL_FORMAT
    bars = source.derive_bars(history)
    data['source'] = source.source_state(config.source_epoch, None, bars)
    for end, close, _ in bars:
        base._append_candle(engine, ExactObservation(at, close, end, close))
    evidence['provider'] = {'phase': 'bootstrap', 'frame': None, 'history': history,
                            'wall_us': wall, 'monotonic_us': mono}
    engine['cohort_source'] = None
    engine['config'] = config.to_dict()
    engine['lifecycle'] = {'search_epoch': 0, 'restart_required': False, 'signals_after': None,
        'last_control_at': None, 'risk': {'active': False, 'baseline_equity': config.initial_cash,
        'observed_equity': config.initial_cash, 'observed_at': at, 'trip_id': None,
        'tripped_at': None, 'trip_equity': None, 'recovery_count': 0, 'last_recovered_at': None}}
    for member in engine['members']:
        member['terminal'] = None
        member['assessment'] = None
    builder = _Builder(data, cursor, at, ledger)
    for identity in allocations:
        builder.allocate(identity)
    builder.operations = original.operations
    builder.actions = original.transition['evidence']['actions']
    builder.events = original.transition['events']
    return _candidate(None, data, strategy, cohort, builder, 'bootstrap', evidence, None)


def _start(state, inputs, observation=None, *, ledger, stop=False):
    if type(state) is not GAState or (observation is not None and type(observation) is not ExactObservation):
        raise ExactRehearsalError('owned lifecycle state and exact observation required')
    cursor, at, evidence = base._inputs(inputs, observation)
    before = state.to_dict()
    _configuration(before)
    ledger.check(before, before['owner_id'], before['run_id'])
    _counter(before['revision'], 'revision', stop=stop)
    if before['status'] not in {'running', 'paused', 'risk_halted'}:
        raise ExactRehearsalError('terminal lifecycle state cannot advance')
    previous = before['engine']['last_quote']
    control_at = before['engine']['lifecycle']['last_control_at']
    if ((previous is not None and at < previous['timestamp'])
            or (control_at is not None and at < control_at)):
        raise ExactRehearsalError('lifecycle inputs cannot regress source or control time')
    data, strategy, cohort = state._fork()
    staged = ledger._staged_provider
    if staged is None:
        raise ExactRehearsalError('validated provider envelope required')
    evidence['provider'] = deepcopy(staged['evidence'])
    data['source'] = deepcopy(staged['after'])
    data['revision'] += 1
    return before, data, strategy, cohort, _Builder(data, cursor, at, ledger), evidence


def _equity(data, price):
    total = base._amount(data['reserve']) + sum(base._amount(row['cash']) for row in data['accounts'])
    for position in data['positions']:
        if not position['closed']:
            total += base._amount(mark_value(EntryPlan.from_dict(position['entry']), price))
    return total


def _abort(data, strategy, cohort, builder, reason):
    if cohort.phase not in {'aborted', 'completed'}:
        _finalize(data, cohort, builder, reason, aborted=True)
        cohort.abort(reason, builder.at)
        strategy.abort_cohort()
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
    trip = builder.new_id()
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
    builder.retired.append({'account': deepcopy(account), 'member': deepcopy(member)})
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
        result = cohort.record_terminal(base._view(data, member, _configuration(data).colony_config()),
                                        'drawdown', builder.at)
        member['assessment'] = _snapshot(data, member, cohort, builder, result)
    _retire(data, member, builder, 'terminal')


def _prepare_protective(state: GAState, observation: ExactObservation,
                       inputs: DecisionInputs, *, ledger: SimulationLedger) -> GACandidate:
    if type(observation) is not ExactObservation:
        raise ExactRehearsalError('exact protective observation required')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation, ledger=ledger)
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
    if data['engine']['generation'] >= MAX_GENERATION:
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
    member['assessment'] = None
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
            (SourceBinding('clone_source', source['id']), SourceBinding('asset_template', source['id'])),
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
    # Explicitly discarded interrupted optimizer state is never told. Restart
    # uses the original bound phenotypes and a new deterministic search epoch.
    strategy.configure_search(SearchRandomStreams(engine['config']['search_seed'], strategy.name),
                              lifecycle['search_epoch'])
    views = [base._view(data, member, config) for member in next_members]
    strategy.initialize(views, config)
    following = EvaluationCohort(f"{data['run_id']}:{engine['generation']}", views, base.HORIZON_SECONDS)
    engine['cohort_source'] = None
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
    _finalize(data, cohort, builder, 'window_complete')
    _counter(strategy._mutation_event, 'mutation event')
    result = strategy.evolve(evaluations, [], config)
    if len(result.offspring) != base.POPULATION or result.retire_ids != [member['id'] for member in members]:
        raise ExactRehearsalError('optimizer must replace the complete ordered original cohort')
    ids = [builder.new_id() for _ in result.offspring]
    args = {'cohort_member_ids': [member['id'] for member in members]}
    lineage = lineage_plan_from_evolution(strategy.name, result, evaluations, ids, **args)
    builder.selection = base._views(result.metadata)
    builder.events.append({'kind': 'evaluation', 'at': builder.at, 'account_id': None,
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
    views = [base._view(data, member, config) for member in next_members]
    strategy.bind_candidates(views)
    following = EvaluationCohort(f"{data['run_id']}:{engine['generation']}", views, base.HORIZON_SECONDS)
    engine['cohort_source'] = None
    if _history_ready(engine, observation.timestamp):
        following.start(observation.timestamp)
        engine['cohort_source'] = _source_cursor(data, observation.timestamp)
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


def _prepare_decision(state: GAState, observation: ExactObservation,
                     inputs: DecisionInputs, *, ledger: SimulationLedger) -> GACandidate:
    if type(observation) is not ExactObservation:
        raise ExactRehearsalError('exact decision observation required')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation, ledger=ledger)
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
    if observation.candle_end is not None and observation.candle_end != engine['ema']['last_end']:
        _counter(engine['ema']['count'], 'candle count')
    new_candle = base._append_candle(engine, observation)
    if lifecycle['restart_required']:
        if _history_ready(engine, observation.timestamp):
            cohort = _restart(data, strategy, cohort, builder, observation)
    elif cohort.phase == 'warming':
        if _history_ready(engine, observation.timestamp):
            cohort.start(observation.timestamp)
            engine['cohort_source'] = _source_cursor(data, observation.timestamp)
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


def _prepare_control(state: GAState, action: str, inputs: DecisionInputs,
                    observation: ExactObservation | None = None, trip_id: str | None = None,
                    *, ledger: SimulationLedger) -> GACandidate:
    if type(action) is not str or action not in {'pause', 'resume', 'stop', 'recover'}:
        raise ExactRehearsalError('unsupported lifecycle action')
    before, data, strategy, cohort, builder, evidence = _start(state, inputs, observation, ledger=ledger, stop=action == 'stop')
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
        if observation.candle_end != engine['ema']['last_end']:
            _counter(engine['ema']['count'], 'candle count')
        _counter(risk['recovery_count'], 'recovery count')
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



@dataclass(frozen=True, slots=True)
class _ProviderLedgerView:
    ledger: SimulationLedger
    _staged_provider: dict

    def check(self, *args): return self.ledger.check(*args)
    def used(self, identity): return self.ledger.used(identity)


def _stage(state, phase, frame, history, inputs, ledger, *, recovery=False):
    if type(state) is not GAState or type(ledger) is not SimulationLedger:
        raise ExactRehearsalError('owned provider GA state/ledger required')
    before = state.to_dict()
    ledger.check(before, before['owner_id'], before['run_id'])
    source.validate_source_state(before['source'], epoch=_configuration(before).source_epoch)
    wall, mono = evidence_clocks(inputs)
    after_source = deepcopy(before['source'])
    if phase == 'protective':
        source.validate_frame(frame, prior_source=before['source'], epoch=before['source']['epoch'])
        source.check_frame(frame, wall_us=wall, monotonic_us=mono)
        after_source.update(quote_sequence=frame['sequence'], last_quote=deepcopy(frame))
    elif phase == 'decision' or recovery:
        source.check_frame(frame, wall_us=wall, monotonic_us=mono)
        if frame != before['source']['last_quote']:
            raise source.ProviderSourceError()
    elif frame is not None or history is not None:
        raise source.ProviderSourceError()
    if history is not None:
        if before['engine']['lifecycle']['risk']['active'] and not recovery:
            raise source.ProviderSourceError()
        source.validate_history(history, prior_bars=before['source']['bars'], seed=False,
                                wall_us=wall, monotonic_us=mono)
        after_source['bars'] = (after_source['bars'] + source.derive_bars(history))[-64:]
    if frame is not None:
        bar = after_source['bars'][-1] if history is not None or recovery else None
        observation = ExactObservation(frame['decision_second'], frame['quote']['price'],
                                       None if bar is None else bar[0], None if bar is None else bar[1])
    else:
        observation = None
    evidence = {'phase': phase, 'frame': deepcopy(frame), 'history': deepcopy(history),
                'wall_us': wall, 'monotonic_us': mono}
    return _ProviderLedgerView(ledger, {'evidence': evidence, 'after': after_source}), observation


def prepare_protective(state, frame, inputs, *, ledger):
    view, observation = _stage(state, 'protective', frame, None, inputs, ledger)
    return _prepare_protective(state, observation, inputs, ledger=view)


def prepare_decision(state, frame, history, inputs, *, ledger):
    view, observation = _stage(state, 'decision', frame, history, inputs, ledger)
    return _prepare_decision(state, observation, inputs, ledger=view)


def prepare_control(state, action, inputs, *, frame=None, history=None, trip_id=None, ledger):
    if action != 'recover' and (frame is not None or history is not None):
        raise source.ProviderSourceError()
    view, observation = _stage(state, 'control', frame, history, inputs, ledger, recovery=action == 'recover')
    return _prepare_control(state, action, inputs, observation, trip_id, ledger=view)
