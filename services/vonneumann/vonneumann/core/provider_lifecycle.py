"""Provider-bound v5 wrapper around the unchanged exact lifecycle model.

Only owned solver state can advance. Historical bars seed indicators at the
actual startup clock; they never create retrospective trades or evaluations.
This contract is an isolated paper model, not a live transaction adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from . import exact_lifecycle as kernel
from . import exact_rehearsal as base
from .decision_inputs import DecisionInputs
from ..market import provider_contract as source


@dataclass(frozen=True, slots=True)
class ProviderLifecycleConfig:
    kernel: kernel.ExactLifecycleConfig
    epoch: str

    def __post_init__(self):
        if type(self.kernel) is not kernel.ExactLifecycleConfig or self.kernel.asset != 'SOL/USD':
            raise base.ExactRehearsalError('provider lifecycle requires the exact SOL/USD model')
        self.kernel.__post_init__()
        source.source_policy(self.epoch)

    @property
    def owner_id(self):
        return self.kernel.owner_id

    @property
    def run_id(self):
        return self.kernel.run_id

    @property
    def initial_cash(self):
        return self.kernel.initial_cash

    def run_configuration(self):
        self.__post_init__()
        result = self.kernel.run_configuration()
        result.update(durability_contract_version=5, source_policy=source.source_policy(self.epoch))
        return result


def evidence_clocks(inputs):
    base._inputs(inputs)
    delta = inputs.wall_at - datetime(1970, 1, 1, tzinfo=timezone.utc)
    wall = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    if not 0 <= wall <= 10**16:
        raise source.ProviderSourceError()
    return wall, source.clock_us(inputs.monotonic_at, upper=True)


def _model(state):
    if type(state) is not base.ExactState:
        raise base.ExactRehearsalError('owned provider state required')
    data, strategy, cohort = state._fork()
    if 'source' not in data:
        raise base.ExactRehearsalError('provider source state required')
    data.pop('source')
    return base.ExactState._seal(data, strategy, cohort)


def _source_after(before, *, epoch=None, frame=None, history=None):
    result = ({'version': 1, 'epoch': epoch, 'quote_sequence': 0,
               'last_quote': None, 'bars': []} if before is None
              else json.loads(base._json(before['source'])))
    if frame is not None:
        result.update(quote_sequence=frame['sequence'], last_quote=frame)
    if history is not None:
        result['bars'] = (result['bars'] + source.derive_bars(history))[-64:]
    return result


def _wrap(candidate, before, source_state, inputs, phase, frame=None, history=None, *, seeded=False):
    from ..db.provider_protocol import validate_transition
    data, strategy, cohort = candidate.state._fork()
    if seeded:
        at = int(inputs.event_at.timestamp())
        for end, close, _ in source_state['bars']:
            base._append_candle(data['engine'], base.ExactObservation(at, close, end, close))
    data['source'] = source_state
    transition = candidate.transition
    transition.update(before=before, after=data)
    wall, mono = evidence_clocks(inputs)
    transition['evidence']['source'] = {'version': 1, 'phase': phase, 'frame': frame,
                                      'history': history, 'wall_us': wall, 'monotonic_us': mono}
    validate_transition(transition, candidate.operations, data['owner_id'], data['run_id'],
                        data['revision'] - 1)
    payload = {'version': 5, 'operations': candidate.operations, 'transition': transition}
    wire = base._json(payload)
    size = len(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(', ', ': ')).encode('utf-8'))
    return base.ExactCandidate(base.ExactState._seal(data, strategy, cohort), wire, size)


def bootstrap(config: ProviderLifecycleConfig, history, inputs: DecisionInputs):
    if type(config) is not ProviderLifecycleConfig:
        raise base.ExactRehearsalError('fresh provider lifecycle configuration required')
    config.__post_init__()
    wall, mono = evidence_clocks(inputs)
    source.validate_history(history, prior_bars=[], seed=True, wall_us=wall, monotonic_us=mono)
    original = kernel.bootstrap(config.kernel, inputs)
    return _wrap(original, None, _source_after(None, epoch=config.epoch, history=history),
                 inputs, 'bootstrap', history=history, seeded=True)


def prepare_protective(state, frame, inputs):
    before = state.to_dict()
    wall, mono = evidence_clocks(inputs)
    source.check_frame(frame, wall_us=wall, monotonic_us=mono)
    observation = base.ExactObservation(frame['decision_second'], frame['quote']['price'])
    original = kernel.prepare_protective(_model(state), observation, inputs)
    return _wrap(original, before, _source_after(before, frame=frame), inputs,
                 'protective', frame=frame)


def _observation(before, frame, history, inputs, *, recovery=False):
    wall, mono = evidence_clocks(inputs)
    source.check_frame(frame, wall_us=wall, monotonic_us=mono)
    bars = before['source']['bars']
    if history is not None:
        source.validate_history(history, prior_bars=bars, seed=False, wall_us=wall, monotonic_us=mono)
        bars = source.derive_bars(history)
    bar = bars[-1] if recovery or history is not None else None
    return base.ExactObservation(frame['decision_second'], frame['quote']['price'],
                                 None if bar is None else bar[0], None if bar is None else bar[1])


def prepare_decision(state, frame, history, inputs):
    before = state.to_dict()
    if history is not None and before['engine']['lifecycle']['risk']['active']:
        raise source.ProviderSourceError()
    observation = _observation(before, frame, history, inputs)
    original = kernel.prepare_decision(_model(state), observation, inputs)
    return _wrap(original, before, _source_after(before, history=history), inputs,
                 'decision', frame=frame, history=history)


def prepare_control(state, action, inputs, *, frame=None, history=None, trip_id=None):
    before = state.to_dict()
    if action != 'recover' and (frame is not None or history is not None):
        raise source.ProviderSourceError()
    observation = (_observation(before, frame, history, inputs, recovery=True)
                   if action == 'recover' else None)
    original = kernel.prepare_control(_model(state), action, inputs, observation, trip_id)
    return _wrap(original, before, _source_after(before, history=history), inputs,
                 'control', frame=frame, history=history)
