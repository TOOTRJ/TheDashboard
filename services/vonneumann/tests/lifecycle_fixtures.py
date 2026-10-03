"""Complete real v4 command chains for offline and isolated PostgreSQL tests.

Every prepared state transition is returned, including quote protection and
empty-operation history changes. Owners/runs are supplied explicitly by each
test; no repository, transport, environment, or database is initialized here.
"""
from __future__ import annotations

from tests.test_exact_rehearsal import OWNER, RUN, inputs
from vonneumann.core import exact_lifecycle as life
from vonneumann.core.decimal_execution import DecimalExecutionConfig


def lifecycle_trace(kind, *, strategy='genetic_algorithm', owner_id=OWNER, run_id=RUN):
    """Return ``(config, candidates)`` with a consecutive revision chain.

    Supported endpoints: standard replacement, all-terminal replacement,
    recovery restart, pause/resume restart, paused stop retaining holdings,
    entry-fee halt, deadline-exit-fee halt, and stale-history restart.
    """
    kinds = {'replacement', 'terminal', 'recover', 'pause_resume', 'pause_stop',
             'entry_cost', 'deadline_cost', 'stale_restart'}
    if kind not in kinds:
        raise ValueError('unknown lifecycle fixture')
    loss = {'recover': '50', 'entry_cost': '1', 'deadline_cost': '10'}.get(kind, '3000')
    execution = DecimalExecutionConfig({'entry_cost': '100', 'deadline_cost': '35'}.get(kind, '0'))
    config = life.ExactLifecycleConfig(strategy, owner_id, run_id, execution=execution,
                                      account_loss_bps=loss)
    candidates = [life.bootstrap(config, inputs(0))]

    def append(candidate):
        candidates.append(candidate)
        return candidate

    def step(stamp, price='100', end=None, close=None):
        current = candidates[-1]
        generation = current.state.to_dict()['engine']['generation']
        protective = append(life.prepare_protective(current.state,
            life.ExactObservation(stamp, price), inputs(stamp, generation + 1)))
        return append(life.prepare_decision(protective.state,
            life.ExactObservation(stamp, price, end, close), inputs(stamp, generation + 1)))

    for bar in range(1, 63):
        step(bar * 900, end=bar * 900,
             close='100' if bar < 61 else '80' if bar == 61 else '120')
    step(55801)
    if kind == 'entry_cost':
        return config, candidates
    if kind == 'terminal':
        step(55802, '20')
        for bar in (63, 64, 65):
            step(bar * 900, end=bar * 900, close='120')
    elif kind in {'replacement', 'deadline_cost'}:
        for bar in (63, 64, 65):
            step(bar * 900, end=bar * 900,
                 close='120' if kind == 'deadline_cost' else '80')
            if bar == 63 and kind == 'replacement':
                step(56701, '99')
    elif kind == 'recover':
        step(55802, '97.5')
        current = append(life.prepare_protective(candidates[-1].state,
            life.ExactObservation(55803, '100'), inputs(55803)))
        trip = current.state.to_dict()['engine']['lifecycle']['risk']['trip_id']
        append(life.prepare_control(current.state, 'recover', inputs(55803),
            life.ExactObservation(55803, '100', 55800, '120'), trip_id=trip))
        step(55804, end=55800, close='120')
    else:
        current = append(life.prepare_control(candidates[-1].state, 'pause', inputs(55802)))
        if kind == 'pause_stop':
            append(life.prepare_control(current.state, 'stop', inputs(55803)))
        elif kind == 'pause_resume':
            append(life.prepare_control(current.state, 'resume', inputs(55803)))
            step(55804, end=55800, close='120')
        else:
            append(life.prepare_control(current.state, 'resume', inputs(58501)))
            step(58502)
            for stamp, end in ((58503, 56700), (58504, 57600), (58505, 58500)):
                step(stamp, end=end, close='100')
    return config, candidates
