"""Original portable-v2 owned fixture traces; no relabeling or shared globals.

Reviewed forks of existing literal-provider fixture builders at PR103.
"""
from uuid import UUID
from tests.security_support import deny_network
from tests.test_provider_ga_components import provider_trace
from tests.test_provider_contract import OWNER,RUN,WORKER,EPOCH,WALL,MONO,END,source_inputs,seed_bundle,raw_capture,raw_minutes
from vonneumann.core.decimal_execution import DecimalExecutionConfig
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import portable_partitioned_checkpoint as cp, provider_portable_ga_model as ga


def extra_sequence(*,risk_bps='9000',cost=DecimalExecutionConfig(),death=False,controls=False):
    """Literal provider evidence, exact owned preparations and complete history."""
    rows=[]; previous=None
    ledger=ga.SimulationLedger(OWNER,RUN)
    def accept(candidate):
        nonlocal previous
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,
            command_id=str(UUID(int=50_000_000+candidate.state.revision)),previous=previous)
        rows.append((candidate,capture,wire))
        previous=capture
        return ledger.accept(candidate)
    with deny_network():
        state=accept(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',
            source_epoch=EPOCH,execution=cost,account_loss_bps=risk_bps),
            seed_bundle(last_close='80'),source_inputs(WALL),ledger=ledger))
        offsets=(1,900,901) if death or controls else (1,900,901,1800,1801,2700,2701,3600,3601)
        for serial,offset in enumerate(offsets,1):
            wall,mono=WALL+offset,MONO+offset
            frame=ga.source.make_frame(raw_capture(price='101.234567890123456789',
                block=100+serial,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial*2),ledger=ledger))
            history=None if offset%900 else ga.source.build_history(
                raw_minutes(end=END+offset,count=15,close='120' if offset//900%2 else '80',
                    wall=wall-1,mono=mono-1),prior_bars=state.to_dict()['source']['bars'],
                seed=False,wall_us=wall*1_000_000,monotonic_us=int(mono*1_000_000))
            state=accept(ga.prepare_decision(state,frame,history,
                source_inputs(wall,mono=mono,generation=state.to_dict()['engine']['generation']+1,serial=serial*2+1),ledger=ledger))
        if death:
            wall,mono=WALL+902,MONO+902
            frame=ga.source.make_frame(raw_capture(price='0.1',block=105,source_second=wall-2,
                wall=wall-1,mono=mono-1),prior_source=state.to_dict()['source'],epoch=EPOCH,
                wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=80),ledger=ledger))
        if controls:
            at=state.to_dict()['engine']['last_quote']['timestamp']
            state=accept(ga.prepare_control(state,'pause',source_inputs(at+1,serial=900),ledger=ledger))
            state=accept(ga.prepare_control(state,'resume',source_inputs(at+2,serial=901),ledger=ledger))
            wall,mono=at+3,MONO+905
            frame=ga.source.make_frame(raw_capture(price='101.234567890123456789',block=200,
                source_second=wall-2,wall=wall-1,mono=mono-1),prior_source=state.to_dict()['source'],
                epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=902),ledger=ledger))
            state=accept(ga.prepare_decision(state,frame,None,
                source_inputs(wall,mono=mono,generation=1,serial=903),ledger=ledger))
        at=state.to_dict()['engine']['last_quote']['timestamp']+1
        accept(ga.prepare_control(state,'stop',source_inputs(at,serial=904),ledger=ledger))
    return rows


def recovery_sequence():
    rows=[]; old=None; ledger=ga.SimulationLedger(OWNER,RUN)
    def accept(candidate):
        nonlocal old
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=80000000+candidate.state.revision)),previous=old)
        rows.append((candidate,capture,wire)); old=capture
        return ledger.accept(candidate)
    with deny_network():
        state=accept(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH,account_loss_bps='49'),
            seed_bundle(last_close='80'),source_inputs(WALL),ledger=ledger))
        for i,offset in enumerate((1,900,901),1):
            wall,mono=WALL+offset,MONO+offset
            frame=ga.source.make_frame(raw_capture(price='100',block=100+i,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=i*2),ledger=ledger))
            history=None if offset%900 else ga.source.build_history(raw_minutes(end=state.to_dict()['source']['bars'][-1][0]+900,
                count=15,close='120',wall=wall-1,mono=mono-1),prior_bars=state.to_dict()['source']['bars'],seed=False,
                wall_us=wall*1000000,monotonic_us=int(mono*1000000))
            state=accept(ga.prepare_decision(state,frame,history,source_inputs(wall,mono=mono,serial=i*2+1),ledger=ledger))
        if len(state.to_dict()['positions'])!=8: raise AssertionError('Recovery fixture did not hold eight positions')
        for i,price in ((902,'97.5'),(903,'101')):
            wall,mono=WALL+i,MONO+i
            frame=ga.source.make_frame(raw_capture(price=price,block=200+i,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=i),ledger=ledger))
        state=accept(ga.prepare_control(state,'recover',source_inputs(wall,mono=mono,serial=950),frame=frame,
            trip_id=state.to_dict()['engine']['lifecycle']['risk']['trip_id'],ledger=ledger))
        wall,mono=WALL+904,MONO+904
        frame=ga.source.make_frame(raw_capture(price='101',block=2000,source_second=wall-2,wall=wall-1,mono=mono-1),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
        state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=951),ledger=ledger))
        state=accept(ga.prepare_decision(state,frame,None,source_inputs(wall,mono=mono,generation=1,serial=952),ledger=ledger))
        accept(ga.prepare_control(state,'stop',source_inputs(wall+1,serial=953),ledger=ledger))
    return rows


def protective_boundary_sequence(prefix,price,serial):
    rows=list(prefix); ledger=ga.SimulationLedger(OWNER,RUN)
    with deny_network():
        for candidate,_,_ in prefix: state=ledger.accept(candidate)
        wall,mono=WALL+902,MONO+902
        frame=ga.source.make_frame(raw_capture(price=price,block=4000,source_second=wall-2,wall=wall-1,mono=mono-1),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
        for candidate in (ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial),ledger=ledger),):
            capture=cp.capture_owned_candidate(candidate)
            wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=90000000+serial)),previous=rows[-1][1])
            rows.append((candidate,capture,wire)); state=ledger.accept(candidate)
        stop=ga.prepare_control(state,'stop',source_inputs(wall+1,serial=serial+1),ledger=ledger)
        capture=cp.capture_owned_candidate(stop)
        rows.append((stop,capture,cp.prepare_transport(stop,capture,command_id=str(UUID(int=91000000+serial)),previous=rows[-1][1])))
    return rows


def expired_signal_sequence(prefix):
    rows=list(prefix); ledger=ga.SimulationLedger(OWNER,RUN)
    def accept(candidate):
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=92000000+candidate.state.revision)),previous=rows[-1][1])
        rows.append((candidate,capture,wire)); return ledger.accept(candidate)
    with deny_network():
        for candidate,_,_ in prefix: state=ledger.accept(candidate)
        wall,mono=WALL+1801,MONO+1801
        frame=ga.source.make_frame(raw_capture(price='100',block=5000,source_second=wall-2,wall=wall-1,mono=mono-1),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
        state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=1400),ledger=ledger))
        state=accept(ga.prepare_decision(state,frame,None,source_inputs(wall,mono=mono,serial=1401),ledger=ledger))
        accept(ga.prepare_control(state,'stop',source_inputs(wall+1,serial=1402),ledger=ledger))
    return rows


def frozen_completion_sequence():
    rows=extra_sequence(death=True)[:-1]
    ledger=ga.SimulationLedger(OWNER,RUN)
    for row in rows: state=ledger.accept(row[0])
    previous=rows[-1][1]
    def accept(candidate):
        nonlocal previous
        capture=cp.capture_owned_candidate(candidate)
        wire=cp.prepare_transport(candidate,capture,command_id=str(UUID(int=88_000_000+candidate.state.revision)),previous=previous)
        rows.append((candidate,capture,wire)); previous=capture
        return ledger.accept(candidate)
    with deny_network():
        for serial,offset in enumerate((1800,2700,3601),1700):
            wall,mono=WALL+offset,MONO+offset
            frame=ga.source.make_frame(raw_capture(price='101',block=serial,source_second=wall-2,wall=wall-1,mono=mono-1),
                prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
            state=accept(ga.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=serial*2),ledger=ledger))
            history=ga.source.build_history(raw_minutes(end=END+(offset//900)*900,count=15,close='100',wall=wall-1,mono=mono-1),
                prior_bars=state.to_dict()['source']['bars'],seed=False,wall_us=wall*1_000_000,monotonic_us=int(mono*1_000_000))
            state=accept(ga.prepare_decision(state,frame,history,source_inputs(wall,mono=mono,generation=1,serial=serial*2+1),ledger=ledger))
        accept(ga.prepare_control(state,'stop',source_inputs(wall+1,serial=1800),ledger=ledger))
    return rows
