"""Strict inputs for a fresh Jupiter prospective GA research model.

These lexical bindings and supplied clocks are not authentication, acquisition,
calibration, native admission, a lease or activation. No old model is inherited.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from ..market import provider_acquisition_v3 as a, prospective_source_v3 as source
from ..core.colony_config import ExactMarkColonyConfig, GeneOverride
from ..core.decimal_execution import CASH_SCALE, DecimalExecutionConfig, _units, _text
from ..core.gene_registry import GENOME_POLICY
from ..core.parameter_codec import PARAMETER_POLICY
from ..core.genome import NUMERIC_GENES
from ..core.evolution import FITNESS_POLICY
from ..core.search_random import validate_search_seed
from ..core import integer_period_mutation as mutation
from . import numeric_wire

PROFILE = 'ema-ga-jupiter-prospective-research-v3'
CONFIG_FORMAT = 'ga-jupiter-prospective-config-research-v3'
MODEL_FORMAT = 'ga-jupiter-prospective-model-research-v3'
COMMAND_FORMAT = 'ga-jupiter-prospective-transition-research-v3'
ASSESSMENT_FORMAT = 'ga-jupiter-prospective-assessment-research-v3'
FILL_FORMAT = 'ga-jupiter-prospective-paper-fill-policy-research-v3'
LIFECYCLE_POLICY = 'ga-jupiter-prospective-integer-us-lifecycle-research-v3'
POPULATION, BAR_SECONDS, HORIZON_SECONDS = 8, 900, 3600
MAX_COUNTER, MAX_GENERATION = 2**63-1, 2**31-1
MAX_INPUTS, MAX_NAME_BYTES, MAX_PAYLOAD_BYTES = 4096, 128, 262144
MAX_EVENT_US = a.MAX_SECOND*1_000_000+999999
AUTHORITY = {name: False for name in ('provider_authenticated', 'calibration_authority',
    'profitability_authority', 'native_admission', 'restoration_authority',
    'lease_authority', 'hosted_authority', 'running_authority', 'live_trading_authority')}


class ModelError(ValueError):
    def __init__(self, *args): super().__init__('Prospective GA research input is invalid or unsupported')


class CapacityError(ModelError):
    pass


def require(condition):
    if not condition: raise ModelError()


def counter(value, maximum=MAX_COUNTER, minimum=0):
    require(type(value) is int and minimum <= value <= maximum)
    return value


def amount(value, *, positive=False):
    require(type(value) is str)
    units = _units(value, CASH_SCALE, positive=positive)
    require(_text(units, CASH_SCALE) == value)
    return units


@dataclass(frozen=True, slots=True)
class SourceBinding:
    """Independent caller trust input; this constructor checks syntax only."""
    owner_id: str
    run_id: str
    market_epoch: str
    acquisition_epoch: str
    issuer_principal_binding_id: str
    recorder_package_sha256: str

    def __post_init__(self):
        for name in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch', 'issuer_principal_binding_id'):
            a.uuid(getattr(self, name))
        a.digest(self.recorder_package_sha256)
        require(self.market_epoch != self.acquisition_epoch)

    def to_dict(self):
        self.__post_init__()
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class PaperFillPolicy:
    """Required explicit scenario costs, never a default or calibrated fill."""
    fee_bps: str
    half_spread_bps: str
    slippage_bps: str
    evidence_label: str
    evidence_id: str
    evidence_sha256: str

    def __post_init__(self):
        actual = {name: getattr(self, name) for name in ('fee_bps', 'half_spread_bps', 'slippage_bps')}
        require(all(type(value) is str for value in actual.values()))
        require(DecimalExecutionConfig.from_dict(actual).to_dict() == actual)
        label = self.evidence_label
        require(type(label) is str and bool(label) and label.strip() == label
            and label.isprintable() and len(label.encode('utf-8')) <= MAX_NAME_BYTES)
        a.uuid(self.evidence_id); a.digest(self.evidence_sha256)

    def execution(self):
        self.__post_init__()
        return DecimalExecutionConfig(self.fee_bps, self.half_spread_bps, self.slippage_bps)

    def to_dict(self):
        self.__post_init__()
        return {'format': FILL_FORMAT, 'valuation': 'reference_mark', 'execution': self.execution().policy(),
            'provenance': {'basis': 'explicit-operator-uncalibrated-scenario',
                'evidence_label': self.evidence_label, 'evidence_id': self.evidence_id,
                'evidence_sha256': self.evidence_sha256, 'authenticated': False},
            'calibrated': False, 'executable_quote': False, **AUTHORITY}

    @property
    def sha256(self): return hashlib.sha256(numeric_wire.encode(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class V3Inputs:
    clock: a.ClockBound
    event_us: int
    ids: tuple[str, ...] = ()
    names: tuple[tuple[int, str], ...] = ()

    def __post_init__(self):
        require(type(self.clock) is a.ClockBound); self.clock.__post_init__()
        counter(self.event_us, MAX_EVENT_US)
        require(self.clock.wall_lower_us <= self.event_us <= self.clock.wall_upper_us
            and self.clock.wall_upper_us <= MAX_EVENT_US and self.math_second <= 2**40)
        require(type(self.ids) is tuple and len(self.ids) <= MAX_INPUTS)
        for identity in self.ids: a.uuid(identity)
        require(len(self.ids) == len(set(self.ids)))
        require(type(self.names) is tuple and len(self.names) <= MAX_INPUTS)
        for pair in self.names:
            require(type(pair) is tuple and len(pair) == 2)
            generation, name = pair; counter(generation, MAX_GENERATION)
            require(type(name) is str and bool(name) and name.strip() == name and name.isprintable()
                and len(name.encode('utf-8')) <= MAX_NAME_BYTES)

    @property
    def math_second(self): return self.event_us // 1_000_000

    def to_dict(self):
        self.__post_init__()
        return {'event_us': self.event_us,
            'clock': {name: getattr(self.clock, name) for name in self.clock.__dataclass_fields__},
            'ids': list(self.ids), 'names': [list(pair) for pair in self.names]}

    def new_cursor(self):
        self.__post_init__(); return _Cursor(self)


class _Cursor:
    __slots__ = ('inputs', '_ids', '_names')
    def __init__(self, inputs): self.inputs, self._ids, self._names = inputs, 0, 0
    def next_id(self):
        require(self._ids < len(self.inputs.ids)); result = self.inputs.ids[self._ids]; self._ids += 1; return result
    def probe_name(self, generation):
        counter(generation, MAX_GENERATION); require(self._names < len(self.inputs.names))
        expected, result = self.inputs.names[self._names]; require(expected == generation)
        self._names += 1; return result


@dataclass(frozen=True, slots=True)
class V3Config:
    owner_id: str
    run_id: str
    market_epoch: str
    initial_binding: SourceBinding
    paper_fill: PaperFillPolicy
    initial_cash: str = '1000'
    seed_capital: str = '100'
    search_seed: str = '0'
    account_loss_bps: str = '2000'

    def __post_init__(self):
        for name in ('owner_id', 'run_id', 'market_epoch'): a.uuid(getattr(self, name))
        require(type(self.initial_binding) is SourceBinding and type(self.paper_fill) is PaperFillPolicy)
        self.initial_binding.__post_init__(); self.paper_fill.__post_init__()
        require(all(getattr(self.initial_binding, name) == getattr(self, name)
            for name in ('owner_id', 'run_id', 'market_epoch')))
        require(amount(self.seed_capital, positive=True)*POPULATION <= amount(self.initial_cash, positive=True)
            and amount(self.seed_capital) >= 10**CASH_SCALE)
        require(type(self.search_seed) is str); validate_search_seed(self.search_seed)
        require(type(self.account_loss_bps) is str
            and re.fullmatch(r'[1-9][0-9]{0,4}', self.account_loss_bps, re.ASCII) is not None
            and 1 <= int(self.account_loss_bps) <= 10000)
        self.colony_config()

    def colony_config(self):
        require(numeric_wire.encode(FITNESS_POLICY) == numeric_wire.encode({
            'version': 'equity-roi-historical-dd-v1',
            'formula': 'portfolio_roi - 2 * observed_historical_max_drawdown',
            'drawdown_weight': 2.0, 'status': 'provisional_heuristic', 'sharpe_in_fitness': False}))
        require(GENOME_POLICY == {'version': 'configured-phenotype-v1', 'integer_rounding': 'nearest_half_up',
            'disabled': 'configured_default', 'validation': 'deterministic_no_rng'})
        require(PARAMETER_POLICY == {'version': 'effective-unit-domain-v1', 'coordinates': 'unit_interval',
            'integer_rounding': 'genome_nearest_half_up', 'assets': 'inherit_and_resize', 'repairs': 'configured_phenotype'})
        config = ExactMarkColonyConfig(strategy_profile='ema_baseline_v1',
            enabled_genes=['ema_fast', 'ema_slow'], available_assets=['SOL/USD'],
            reproduction_interval=60, gene_overrides={'ema_fast': GeneOverride(min=3, max=12, default=9),
                'ema_slow': GeneOverride(min=15, max=60, default=21), 'position_size_pct': GeneOverride(fixed=.25),
                'stop_loss_pct': GeneOverride(fixed=.03), 'take_profit_pct': GeneOverride(fixed=.07),
                'max_open_positions': GeneOverride(fixed=1), 'timeframe_minutes': GeneOverride(fixed=15),
                'num_assets': GeneOverride(fixed=1)})
        fixed = {'rsi_period': 14., 'rsi_oversold': 32., 'rsi_overbought': 70., 'volume_threshold': 1.4,
            'position_size_pct': .25, 'stop_loss_pct': .03, 'take_profit_pct': .07, 'max_open_positions': 1.,
            'timeframe_minutes': 15., 'benchmark_target_pct': .08, 'reproduce_target_dollars': 10.,
            'death_drawdown_pct': .2, 'num_assets': 1.}
        domains = config.resolve_gene_domains()
        require(set(domains) == set(fixed) | {'ema_fast', 'ema_slow'} and set(NUMERIC_GENES) == set(domains)
            and all((domains[key].minimum, domains[key].maximum, domains[key].default) == (value,)*3
                for key, value in fixed.items()))
        return config

    @property
    def execution(self): return self.paper_fill.execution()

    def to_dict(self):
        self.__post_init__()
        return {'format': CONFIG_FORMAT, 'profile': PROFILE, 'owner_id': self.owner_id, 'run_id': self.run_id,
            'market_epoch': self.market_epoch, 'initial_binding': self.initial_binding.to_dict(),
            'source_profile': source.PROFILE, 'source_policy_sha256': source.POLICY_SHA256,
            'strategy': 'genetic_algorithm', 'asset': 'SOL/USD', 'initial_cash': self.initial_cash,
            'seed_capital': self.seed_capital, 'search_seed': self.search_seed,
            'execution': self.execution.policy(), 'paper_fill': self.paper_fill.to_dict(),
            'paper_fill_sha256': self.paper_fill.sha256, 'population': POPULATION,
            'horizon_seconds': HORIZON_SECONDS, 'candle_seconds': BAR_SECONDS, 'max_positions': POPULATION,
            'max_generations': MAX_GENERATION, 'mutation_policy': mutation.policy(),
            'lifecycle_policy': {'version': LIFECYCLE_POLICY, 'account_loss_bps': self.account_loss_bps,
                'death_drawdown_bps': '2000', 'max_lifespan_seconds': 0}, **AUTHORITY}

    @classmethod
    def from_dict(cls, value):
        require(type(value) is dict)
        binding = SourceBinding(**value['initial_binding'])
        fill = value['paper_fill']; costs = fill['execution']['config']; evidence = fill['provenance']
        policy = PaperFillPolicy(**costs, evidence_label=evidence['evidence_label'],
            evidence_id=evidence['evidence_id'], evidence_sha256=evidence['evidence_sha256'])
        config = cls(value['owner_id'], value['run_id'], value['market_epoch'], binding, policy,
            value['initial_cash'], value['seed_capital'], value['search_seed'],
            value['lifecycle_policy']['account_loss_bps'])
        require(numeric_wire.encode(config.to_dict()) == numeric_wire.encode(value))
        return config
