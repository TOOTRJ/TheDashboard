"""Fixed-grid EMA mechanics experiments over immutable synthetic observations.

Each account is independent. Genesis funding, evolution and shared circuit
breakers are deliberately absent. Actual Probe signals/protective exits and the
existing cost calculator are reused. No provider or database client is imported.
"""
from __future__ import annotations

import asyncio
import hashlib
import math
import platform
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..core.colony_config import ColonyConfig, GeneOverride, PRESET_CONFIGS
from ..core.evolution import FITNESS_POLICY, compute_fitness
from ..core.execution import ExecutionConfig, buy_fill, sell_fill, mark_value, execution_record, parse_execution
from ..core.genome import Genome
from ..core.probe import Probe
from ..core.search_random import SearchRandomStreams, validate_search_seed
from ..core.signal_profile import EMA_BASELINE_PROFILE, EMA_WARMUP_BARS, signal_policy
from ..core.types import EventType, ProbeEvent, ProbeState
from ..market.candles import CandleHistory, CANDLE_POLICY
from ..market.dataset import MAX_FRAMES, DatasetError, canonical_bytes
from ..market.replay_feed import ReplayFeed

VERSION = 'ema-grid-mechanics-v1'
GRID = tuple((fast, slow) for fast in (3, 5, 8, 12) for slow in (15, 20, 30, 45, 60))


class ResearchError(ValueError):
    def __init__(self, code='research_invalid'):
        self.code = code if code in {'research_invalid', 'research_dataset', 'research_coverage', 'research_accounting',
                                    'research_software_changed'} else 'research_invalid'
        super().__init__('Offline research experiment failed validation.')


@dataclass(frozen=True)
class ResearchConfig:
    asset: str = 'SOL/USDC'
    timeframe_minutes: int = 15
    train_minutes: int = 1440
    holdout_minutes: int = 1440
    initial_capital: float = 1000.0
    random_seed: str = '0'
    random_budget: int = 10
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    def __post_init__(self):
        for name, lo, hi in [('timeframe_minutes', 5, 60), ('train_minutes', 2, MAX_FRAMES),
                             ('holdout_minutes', 2, MAX_FRAMES), ('random_budget', 1, len(GRID))]:
            value = getattr(self, name)
            if type(value) is not int or not lo <= value <= hi:
                raise ResearchError()
        if (type(self.initial_capital) not in (int, float) or
                not 1 <= self.initial_capital <= 1_000_000 or
                not isinstance(self.asset, str) or not isinstance(self.execution, ExecutionConfig)):
            raise ResearchError()
        try:
            validate_search_seed(self.random_seed)
            ExecutionConfig.from_dict(self.execution.to_dict())
            self.colony_config().resolve_gene_domains()
        except (ValueError, TypeError, OverflowError):
            raise ResearchError() from None
        if self.required_frames > MAX_FRAMES:
            raise ResearchError('research_coverage')

    @property
    def required_frames(self):
        return EMA_WARMUP_BARS * self.timeframe_minutes + self.train_minutes + self.holdout_minutes

    def colony_config(self):
        config = ColonyConfig.from_dict(PRESET_CONFIGS[EMA_BASELINE_PROFILE].to_dict())
        config.available_assets = [self.asset]
        config.gene_overrides['timeframe_minutes'] = GeneOverride(fixed=self.timeframe_minutes)
        config.reproduction_interval = self.train_minutes
        return config

    def to_dict(self):
        return {name: getattr(self, name) for name in ('asset', 'timeframe_minutes', 'train_minutes',
                'holdout_minutes', 'initial_capital', 'random_seed', 'random_budget')} | {
                    'execution': self.execution.to_dict()}

    @classmethod
    def from_dict(cls, value):
        names = {'asset', 'timeframe_minutes', 'train_minutes', 'holdout_minutes',
                 'initial_capital', 'random_seed', 'random_budget', 'execution'}
        if not isinstance(value, dict) or set(value) != names:
            raise ResearchError()
        try:
            return cls(**(value | {'execution': ExecutionConfig.from_dict(value['execution'])}))
        except (ValueError, TypeError, OverflowError):
            raise ResearchError() from None


def _candidate_id(pair):
    return f'ema-{pair[0]:02d}-{pair[1]:02d}'


def candidates():
    return [dict(id=_candidate_id(pair), kind='ema', ema_fast=pair[0], ema_slow=pair[1]) for pair in GRID] + [
        dict(id='fixed-ema-09-21', kind='ema', ema_fast=9, ema_slow=21),
        dict(id='cash', kind='cash', ema_fast=None, ema_slow=None),
        dict(id='buy-hold-25', kind='buy_hold', ema_fast=None, ema_slow=None),
        dict(id='buy-hold-100', kind='buy_hold', ema_fast=None, ema_slow=None)]


def source_fingerprint():
    root = Path(__file__).resolve().parents[1]
    files = ['research/runner.py', 'core/colony_config.py', 'core/genome.py', 'core/gene_registry.py',
             'core/probe.py', 'core/execution.py', 'core/evolution.py', 'core/equity_metrics.py',
             'core/signal_profile.py', 'core/types.py', 'core/clock.py', 'core/market_validation.py',
             'core/search_random.py', 'market/candles.py', 'market/dataset.py', 'market/replay_feed.py',
             'market/feed.py']
    return {'services/vonneumann/vonneumann/' + name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in files}


def _same(left, right):
    return math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-9)


class _Ledger:
    """Reconcile every fill immediately; never rely on Probe's bounded trade cache."""
    def __init__(self, candidate_id, capital):
        self.candidate_id, self.cash = candidate_id, capital
        self.ids, self.positions = {}, {}
        self.sequence = self.closed_count = 0
        self.pnl = self.costs = 0.0

    def trade_id(self, raw):
        if raw not in self.ids:
            self.ids[raw] = f'{self.candidate_id}:trade-{len(self.ids) + 1:05d}'
        return self.ids[raw]

    def equity(self, price):
        return self.cash + math.fsum(mark_value(entry, price) for entry in self.positions.values())

    def consume(self, events, price):
        result = []
        for event in events:
            item = {'seq': self.sequence, 'kind': event.event_type.value}
            self.sequence += 1
            data = event.data
            if event.event_type in (EventType.TRADE_OPENED, EventType.TRADE_CLOSED):
                ident = self.trade_id(data['trade_id'])
                config, entry, exit_fill = parse_execution(data['execution'])
                item.update(trade_id=ident, execution=deepcopy(data['execution']))
                if event.event_type == EventType.TRADE_OPENED:
                    if ident in self.positions or exit_fill is not None:
                        raise ResearchError('research_accounting')
                    self.positions[ident] = entry
                    self.cash -= entry.cash_debit
                    self.costs += entry.fee + entry.spread_cost + entry.slippage_cost
                else:
                    if self.positions.pop(ident, None) != entry or exit_fill is None:
                        raise ResearchError('research_accounting')
                    self.cash += exit_fill.cash_credit
                    self.pnl += exit_fill.net_pnl
                    self.closed_count += 1
                    self.costs += exit_fill.fee + exit_fill.spread_cost + exit_fill.slippage_cost
                    item['reason'] = data['exit_reason']
            elif event.event_type in (EventType.PROBE_DYING, EventType.PROBE_DEAD):
                item['reason'] = data['reason']
            else:
                raise ResearchError('research_accounting')
            item.update(cash_after=self.cash, equity_after=self.equity(price))
            result.append(item)
        return result


def _intents(probe, ledger):
    return [{'action': intent.action, 'candle_end': intent.candle_end,
             'receipt_boundary': intent.receipt_boundary,
             'trade_id': ledger.trade_id(intent.trade_id) if intent.trade_id is not None else None,
             'signals': dict(intent.signals)} for _, intent in sorted(probe._pending_intents.items())]


class _EmaAccount:
    def __init__(self, definition, config, history, boundary_at, colony_config=None):
        self.definition, self.config = definition, config
        self.now = boundary_at
        colony = deepcopy(colony_config) if colony_config is not None else config.colony_config()
        genome = Genome(assets=[config.asset], ema_fast=definition['ema_fast'], ema_slow=definition['ema_slow']).validate(colony)
        colony.assert_profile_genome(genome)
        self.probe = Probe(genome, config.initial_capital, probe_id=definition['id'],
                           clock=lambda: datetime.fromtimestamp(self.now, timezone.utc),
                           candle_history=history, execution_config=config.execution,
                           strategy_profile=EMA_BASELINE_PROFILE)
        self.probe.set_funded()
        self.probe.set_observing()
        self.probe.reset_signal_boundary(boundary_at)
        self.audit = _Ledger(definition['id'], config.initial_capital)
        self.rows = []
        self.last_candle_end = None

    def advance(self, tick, frame, *, start=False, terminal=False):
        self.now = tick.timestamp
        probe = self.probe
        probe.on_quote(tick)
        pre_equity = probe.total_value
        before = _intents(probe, self.audit)
        candle = None
        snapshot = probe._latest_candle(self.config.asset)
        if snapshot is not None and snapshot.end != self.last_candle_end:
            self.last_candle_end = snapshot.end
            fast, slow = probe.genome.int_genes()['ema_fast'], probe.genome.int_genes()['ema_slow']
            pf, ps = snapshot.previous_emas.get(fast), snapshot.previous_emas.get(slow)
            cf, cs = snapshot.emas.get(fast), snapshot.emas.get(slow)
            candle = dict(end=snapshot.end, previous_end=snapshot.previous_end,
                          completed_bars=snapshot.completed_count, fast=cf, slow=cs,
                          previous_fast=pf, previous_slow=ps,
                          bullish=pf is not None and ps is not None and cf is not None and cs is not None and pf <= ps and cf > cs,
                          bearish=pf is not None and ps is not None and cf is not None and cs is not None and pf >= ps and cf < cs)
        if start:
            if not probe.evaluation_ready(self.now):
                raise ResearchError('research_coverage')
            events = []
        elif terminal:
            events = probe.risk_tick()
            probe._observe_drawdown()
            if probe.state in (ProbeState.OBSERVING, ProbeState.TRADING) and probe._should_die():
                events.extend(probe._trigger_die('drawdown'))
            events.extend(probe.close_all_positions({self.config.asset: tick.price}, 'EVOLUTION'))
            probe.reset_signal_boundary(self.now)
        else:
            events = probe.tick(allow_reproduction=False)
        normalized = self.audit.consume(events, tick.price)
        if not _same(self.audit.cash, probe.capital) or not _same(self.audit.equity(tick.price), probe.total_value):
            raise ResearchError('research_accounting')
        self.rows.append(dict(frame=frame, observed_at=self.now, pre_equity=pre_equity,
            cash=probe.capital, position_value=probe.open_position_value, equity=probe.total_value,
            max_drawdown=probe.max_drawdown, state=probe.state.value, candle=candle,
            intents_before=before, intents_after=_intents(probe, self.audit), events=normalized))

    def result(self):
        if self.probe.open_positions or not _same(self.probe.capital - self.config.initial_capital, self.audit.pnl):
            raise ResearchError('research_accounting')
        return dict(candidate_id=self.definition['id'], genome=self.probe.genome.to_dict(),
                    summary=_summary(self.config, self.audit, self.probe.max_drawdown), ledger=self.rows)


class _PassiveAccount:
    def __init__(self, definition, config, history, boundary_at, colony_config=None):
        self.definition, self.config = definition, config
        self.audit = _Ledger(definition['id'], config.initial_capital)
        self.peak, self.drawdown = config.initial_capital, 0.0
        self.entry = None
        self.rows = []

    def advance(self, tick, frame, *, start=False, terminal=False):
        price = tick.price
        before = self.audit.equity(price)
        self.peak = max(self.peak, before)
        self.drawdown = max(self.drawdown, 1 - before / self.peak)
        events = []
        if terminal and self.entry is not None:
            exit_fill = sell_fill(self.entry, price, self.config.execution)
            events.append(ProbeEvent(EventType.TRADE_CLOSED, self.definition['id'],
                {'trade_id': 'passive', 'exit_reason': 'EVOLUTION',
                 'execution': execution_record(self.config.execution, self.entry, exit_fill)}))
        elif not start and not terminal and self.entry is None and self.definition['kind'] == 'buy_hold':
            fraction = .25 if self.definition['id'] == 'buy-hold-25' else 1.0
            self.entry = buy_fill(self.config.initial_capital * fraction, price, self.config.execution)
            events.append(ProbeEvent(EventType.TRADE_OPENED, self.definition['id'],
                {'trade_id': 'passive', 'execution': execution_record(self.config.execution, self.entry)}))
        normalized = self.audit.consume(events, price)
        after = self.audit.equity(price)
        self.peak = max(self.peak, after)
        self.drawdown = max(self.drawdown, 1 - after / self.peak)
        self.rows.append(dict(frame=frame, observed_at=tick.timestamp, pre_equity=before,
            cash=self.audit.cash, position_value=after - self.audit.cash, equity=after,
            max_drawdown=self.drawdown, state='holding' if self.audit.positions else 'cash',
            candle=None, intents_before=[], intents_after=[], events=normalized))

    def result(self):
        if self.audit.positions or not _same(self.audit.cash - self.config.initial_capital, self.audit.pnl):
            raise ResearchError('research_accounting')
        return dict(candidate_id=self.definition['id'], genome=None,
                    summary=_summary(self.config, self.audit, self.drawdown), ledger=self.rows)


def _summary(config, audit, drawdown):
    roi = (audit.cash - config.initial_capital) / config.initial_capital
    return dict(cash=audit.cash, roi=roi, fitness=compute_fitness(roi=roi, max_drawdown=drawdown),
                max_drawdown=drawdown, num_trades=audit.closed_count,
                net_pnl=audit.cash - config.initial_capital, trade_net_pnl=audit.pnl, total_costs=audit.costs)


def _winner(ids, summaries):
    return min(ids, key=lambda ident: (-summaries[ident]['fitness'], ident))


async def run_experiment(dataset_path, config: ResearchConfig) -> dict:
    """Return reproducible JSON data. Invalid/interrupted runs publish no results."""
    if not isinstance(config, ResearchConfig):
        raise ResearchError()
    # Revalidate even a deliberately mutated frozen configuration.
    config = ResearchConfig.from_dict(config.to_dict())
    fixed_controls = config.colony_config()
    fingerprint = source_fingerprint()
    try:
        feed = ReplayFeed(dataset_path)
    except DatasetError:
        raise ResearchError('research_dataset') from None
    spec = feed.simulation_spec
    if (config.asset not in feed._assets or
            spec['start_timestamp'] % (config.timeframe_minutes * 60) or
            feed.dataset_spec['frame_count'] < config.required_frames):
        raise ResearchError('research_coverage')
    history = CandleHistory([config.asset])
    definitions = candidates()
    train_boundary = EMA_WARMUP_BARS * config.timeframe_minutes - 1
    train_end = train_boundary + config.train_minutes
    holdout_end = train_end + config.holdout_minutes
    windows = {name: dict(boundary_frame=start, end_frame=end,
               boundary_at=spec['start_timestamp'] + (start + 1) * 60,
               end_at=spec['start_timestamp'] + (end + 1) * 60)
               for name, start, end in [('train', train_boundary, train_end), ('holdout', train_end, holdout_end)]}
    train, holdout, selection = [], [], None
    for index in range(holdout_end + 1):
        # Real cooperative cancellation; an interrupted experiment never reaches
        # result publication. No sleep or wall-clock value enters the experiment.
        await asyncio.sleep(0)
        ticks = await feed.get_ticks([config.asset])
        tick = ticks[config.asset]
        if tick.timestamp != spec['start_timestamp'] + (index + 1) * 60:
            raise ResearchError('research_coverage')
        history.ingest(await feed.get_candles([config.asset]), available_at=feed.current_timestamp)
        # This strict synthetic experiment requires each completed minute when
        # its quote frame arrives. A valid archive alone does not guarantee
        # complete evaluation coverage; never silently score missing history.
        if history.last_start(config.asset) != tick.timestamp - 60:
            raise ResearchError('research_coverage')
        if index == train_boundary:
            train = [_account(d, config, history, tick.timestamp, fixed_controls) for d in definitions]
        if train_boundary <= index <= train_end:
            for account in train:
                account.advance(tick, index, start=index == train_boundary, terminal=index == train_end)
        if index == train_end:
            training = [account.result() for account in train]
            scores = {item['candidate_id']: item['summary'] for item in training}
            grid_ids = [_candidate_id(pair) for pair in GRID]
            order = list(grid_ids)
            SearchRandomStreams(config.random_seed, 'ema_grid_random').rng('grid-permutation').shuffle(order)
            selected = _winner(order[:config.random_budget], scores)
            selection = dict(objective=deepcopy(FITNESS_POLICY), tie_break='candidate_id_ascending',
                grid_winner=_winner(grid_ids, scores),
                random=dict(seed=config.random_seed, order=order, budget=config.random_budget,
                    sampling='without_replacement', unique_trials=config.random_budget,
                    duplicate_trials=0, score_cache_hits=config.random_budget,
                    additional_computed_evaluations=0,
                    trial_ids=order[:config.random_budget], winner=selected,
                    best_by_budget=[dict(budget=n, winner=_winner(order[:n], scores),
                                        fitness=scores[_winner(order[:n], scores)]['fitness'])
                                    for n in range(1, len(order) + 1)]))
            # Bind the complete training evidence before any holdout decision.
            selection['training_evidence_sha256'] = hashlib.sha256(canonical_bytes(training)).hexdigest()
            selected_ids = {selection['grid_winner'], selected,
                            'fixed-ema-09-21', 'cash', 'buy-hold-25', 'buy-hold-100'}
            holdout = [_account(d, config, history, tick.timestamp, fixed_controls) for d in definitions if d['id'] in selected_ids]
        if train_end <= index <= holdout_end:
            for account in holdout:
                account.advance(tick, index, start=index == train_end, terminal=index == holdout_end)
    if source_fingerprint() != fingerprint:
        raise ResearchError('research_software_changed')
    return dict(schema_version='ema-research-v1', scope='synthetic_mechanics_only',
        engine=dict(version=VERSION, python=platform.python_version(), source_sha256=fingerprint),
        dataset=feed.dataset_spec, config=config.to_dict(), windows=windows, candidates=definitions,
        policy=dict(signal=signal_policy(EMA_BASELINE_PROFILE), candles=deepcopy(CANDLE_POLICY),
            execution=config.execution.policy(), fixed_controls=fixed_controls.to_dict(),
            grid_domain=[list(pair) for pair in GRID], fixed_ema_outside_grid=[9, 21],
            selection='training_only; net terminal fitness; no holdout ranking',
            coverage='every completed minute delivered on its modeled quote frame; gaps/delays rejected',
            random_search='seeded permutation without replacement; score-cache prefixes; 20 equals exhaustive by construction',
            equity='pre-decision mark and post-action cash/equity; each fill records intermediate cash/equity; terminal costs included',
            risk='independent EMA probe drawdown retirement; no shared Genesis capital or circuit breaker',
            passive_controls='cash zero interest; buy-hold 25%/100% initial cash on first quote after boundary; no rebalance or protective exits',
            windows='boundary observation cash-only; strict interior signals; terminal quote risk then costed liquidation; pending intents discarded',
            holdout='fresh accounts/cash/positions/intents/risk; causal indicator prefix retained; only training winners and prespecified controls',
            lifecycle='no reproduction/age retirement/replacement; early death holds cash to the deadline',
            reporting='no Sharpe or empirical-performance claim; partial/interrupted runs not published'),
        selection=selection, evaluations=dict(train=training, holdout=[account.result() for account in holdout]))


def _account(definition, config, history, timestamp, colony_config=None):
    cls = _EmaAccount if definition['kind'] == 'ema' else _PassiveAccount
    return cls(definition, config, history, timestamp, colony_config)
