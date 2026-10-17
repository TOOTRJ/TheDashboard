"""Explicit owned offline native probe that waits for a genuine next bar.

This is never ordinary CI discovery, a provider call, or hosted activation. The
original v2 synthetic source label and every native guard remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
from uuid import UUID

from tests.postgres.harness import OPT_IN
from tests.postgres.test_portable_native import PortableNativeSqlTests,ACTOR,literal,ga,cp,numbers,OWNER,RUN,WORKER,EPOCH
from tests.test_provider_contract import raw_minutes,raw_capture,source_inputs


class ProbeOutputError(RuntimeError):
    def __init__(self):super().__init__('Owned probe output is unavailable or incompatible')


def _temporary_anchor():
    """Fixed OS anchors only; environment and tempfile defaults grant no rights."""
    if sys.platform=='darwin':return Path('/private/tmp')
    if sys.platform=='linux':return Path('/tmp')
    raise ProbeOutputError()


class _OwnedProbeOutput:
    """Exclusive private files beneath a fixed, pinned OS temporary anchor.

    Directory descriptors keep cleanup on the original parent after renames.
    Neither a caller filename nor a replaced file conveys cleanup authority.
    This is a trusted local operator boundary, not an OS sandbox against another
    malicious process running under the same user.
    """
    def __init__(self, raw):
        self.parent_fd=None;self.files={};self.published=False
        try:
            anchor=_temporary_anchor();self.anchor_depth=len(anchor.parts)-1
            if type(raw) is not str or '\x00' in raw:raise ProbeOutputError()
            output=Path(raw)
            if not output.is_absolute() or str(output)!=raw or any(p in ('.','..') for p in output.parts):
                raise ProbeOutputError()
            if anchor not in output.parents or output.suffix!='.json' or len(raw)>1024:
                raise ProbeOutputError()
            self.output=output;self.running=output.with_suffix('.running.json')
            self.parts=output.parent.parts[1:];self.parent_pins=[]
            self.parent_fd=self._open_parents(record=True)
            for name in (self.output.name,self.running.name):
                fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,
                    0o600,dir_fd=self.parent_fd)
                value=os.fstat(fd);self.files[name]=(fd,(value.st_dev,value.st_ino))
                if not stat.S_ISREG(value.st_mode) or stat.S_IMODE(value.st_mode)!=0o600 or value.st_uid!=os.geteuid():
                    raise ProbeOutputError()
            self._check_binding()
        except BaseException:
            self.close();raise ProbeOutputError() from None

    def _open_parents(self,*,record=False):
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            for index,part in enumerate(self.parts):
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
                os.close(fd);fd=child;value=os.fstat(fd)
                if not stat.S_ISDIR(value.st_mode) or (index>=self.anchor_depth and
                    (value.st_uid!=os.geteuid() or stat.S_IMODE(value.st_mode)&0o077)):
                    raise ProbeOutputError()
                identity=(value.st_dev,value.st_ino)
                if record:self.parent_pins.append(identity)
                elif identity!=self.parent_pins[index]:raise ProbeOutputError()
            return fd
        except BaseException:
            os.close(fd);raise

    def _is_owned(self,name):
        try:value=os.stat(name,dir_fd=self.parent_fd,follow_symlinks=False)
        except FileNotFoundError:return False
        return stat.S_ISREG(value.st_mode) and value.st_uid==os.geteuid() and (value.st_dev,value.st_ino)==self.files[name][1]

    def _check_binding(self):
        current=None
        try:
            current=self._open_parents()
            if os.fstat(current).st_ino!=os.fstat(self.parent_fd).st_ino or any(not self._is_owned(n) for n in self.files):
                raise ProbeOutputError()
            if any(stat.S_IMODE(os.stat(n,dir_fd=self.parent_fd,follow_symlinks=False).st_mode)!=0o600 for n in self.files):
                raise ProbeOutputError()
        except OSError:raise ProbeOutputError() from None
        finally:
            if current is not None:os.close(current)

    def write_running(self):
        self._check_binding()
        raw=(json.dumps({'pid':os.getpid(),'output':str(self.output),'scope':'owned portable native real-bar probe'})+'\n').encode()
        with os.fdopen(os.dup(self.files[self.running.name][0]),'wb') as stream:stream.write(raw);stream.flush()

    def publish(self,result):
        self._check_binding()
        raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
        with os.fdopen(os.dup(self.files[self.output.name][0]),'wb') as stream:stream.write(raw);stream.flush()
        self._check_binding();self.published=True

    def close(self):
        failed=False
        if self.parent_fd is not None:
            try:self._check_binding()
            except (ProbeOutputError,OSError):failed=True
            for name,(fd,_) in self.files.items():
                try:
                    if not self._is_owned(name):failed=True
                    elif name==self.running.name or not self.published:os.unlink(name,dir_fd=self.parent_fd)
                except OSError:failed=True
                finally:os.close(fd)
            self.files.clear();os.close(self.parent_fd);self.parent_fd=None
        return not failed


def run(*,maximum_seconds: int):
    if os.environ.get(OPT_IN)!='1' or os.environ.get('DASHBOARD_PORTABLE_NATIVE_REAL_BAR_PROBE')!='1':
        raise RuntimeError('Explicit owned PostgreSQL and real-bar probe opt-ins are both required')
    if not 30<=maximum_seconds<=970:
        raise ValueError('The genuine-clock probe deadline must be30..970seconds')
    started=time.monotonic();deadline=started+maximum_seconds;trace=[];heartbeats=0
    native_path=Path(__file__).parents[1]/'db-contract/research/portable_native.sql'
    native_sql_sha256=hashlib.sha256(native_path.read_bytes()).hexdigest()
    probe_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    PortableNativeSqlTests.setUpClass()
    fixture=PortableNativeSqlTests('test_actual_catalog_bound_bootstrap_journal_pins_and_readback')
    try:
        if hashlib.sha256(native_path.read_bytes()).hexdigest()!=native_sql_sha256:
            raise RuntimeError('Native package changed during owned fixture installation')
        fixture.setUp();fixture.create(lease=60)
        ledger=ga.SimulationLedger(OWNER,RUN)
        def clock():
            if time.monotonic()>=deadline:raise TimeoutError('Owned genuine-clock native probe deadline expired')
            return int(fixture.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp()));'))
        def utc(second):return datetime.fromtimestamp(second,timezone.utc).isoformat()
        def observe(stage,row):
            read=fixture.read(row)
            if not read['found'] or not read['receipt']['record_observed'] or read['receipt']['pending_until_commit']:
                raise AssertionError('Original command has not been independently observed')
            if read['original_command_wire'].encode()!=row[2]:raise AssertionError('Original wire differs')
            stamp=clock();entry={'stage':stage,'server_second':stamp,'server_utc':utc(stamp),
                'command_id':numbers.decode(row[2])['command_id'],'command_sha256':hashlib.sha256(row[2]).hexdigest(),
                'manifest_sha256':fixture.manifest_sha(row),'revision':str(row[0].state.revision),
                'guard_observed_at':read['receipt']['guard_observed_at'],
                'positions':len(row[0].state.to_dict()['positions'])}
            trace.append(entry);print(json.dumps(entry,sort_keys=True),flush=True)
            return ledger.accept(row[0])
        def capture(candidate,previous=None):
            active=cp.capture_owned_candidate(candidate)
            wire=cp.prepare_transport(candidate,active,command_id=str(UUID(int=96_100_000+candidate.state.revision)),
                previous=None if previous is None else previous[1])
            return candidate,active,wire,ledger
        now=clock();mono=time.monotonic();initial_end=(now//900)*900
        history=ga.source.build_history(raw_minutes(end=initial_end,count=915,close='80',wall=now,mono=mono),
            prior_bars=[],seed=True,wall_us=now*1_000_000,monotonic_us=ga.source.clock_us(mono,upper=True))
        row=capture(ga.bootstrap(ga.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH),
            history,source_inputs(now,mono=mono,serial=1100),ledger=ledger))
        fixture.commit(row[2]);state=observe('bootstrap',row)

        def protective(previous,*,price='100'):
            current=ledger.accept(previous[0]);old=current.to_dict()['source']['last_quote']
            now=clock()
            while old is not None and now<=old['decision_second']:
                time.sleep(.1);now=clock()
            mono=time.monotonic();block=100 if old is None else old['quote']['block_ref']+1
            frame=ga.source.make_frame(raw_capture(price=price,block=block,source_second=now-1,wall=now,mono=mono),
                prior_source=current.to_dict()['source'],epoch=EPOCH,wall_now=now,monotonic_now=mono)
            return capture(ga.prepare_protective(current,frame,
                source_inputs(now,mono=mono,serial=1100+current.revision),ledger=ledger),previous)

        def decision(previous,*,bar_end=None):
            current=ledger.accept(previous[0]);frame=current.to_dict()['source']['last_quote'];now=clock();mono=time.monotonic()
            history=None if bar_end is None else ga.source.build_history(
                raw_minutes(end=bar_end,count=15,close='120',wall=now,mono=mono),
                prior_bars=current.to_dict()['source']['bars'],seed=False,wall_us=now*1_000_000,
                monotonic_us=ga.source.clock_us(mono,upper=True))
            return capture(ga.prepare_decision(current,frame,history,
                source_inputs(frame['decision_second'],wall=now,mono=mono,serial=1100+current.revision),ledger=ledger),previous)

        row=protective(row);fixture.commit(row[2]);observe('warmup_quote',row)
        row=decision(row);fixture.commit(row[2]);state=observe('cohort_evaluating',row)
        if state._fork()[2].phase!='evaluating':
            raise AssertionError('The original v2 cohort must be evaluating before the next genuine bar')
        next_end=initial_end+900;ready_at=next_end+6;next_heartbeat=time.monotonic()+20
        print(json.dumps({'stage':'waiting_for_genuine_next_bar','target_server_second':next_end,
            'target_server_utc':utc(next_end),'completion_ready_server_second':ready_at,
            'completion_ready_server_utc':utc(ready_at),'bounded_maximum_seconds':maximum_seconds},sort_keys=True),flush=True)
        while clock()<ready_at:
            if time.monotonic()>=next_heartbeat:
                fixture.db.sql('SELECT vn_portable_native_research.heartbeat('+','.join((
                    literal(OWNER),literal(RUN),literal(WORKER),'1','60'))+');',role=ACTOR)
                heartbeats+=1;next_heartbeat=time.monotonic()+20
            time.sleep(min(2,max(.1,deadline-time.monotonic())))
        row=protective(row);fixture.commit(row[2]);observe('genuine_next_bar_quote',row)
        row=decision(row,bar_end=next_end);fixture.commit(row[2]);state=observe('genuine_next_bar_signal',row)
        if not any(m['pending'] is not None for m in state.to_dict()['engine']['members']):
            raise AssertionError('Original next-bar crossover must produce an entry signal')
        row=protective(row);fixture.commit(row[2]);observe('later_genuine_entry_quote',row)
        row=decision(row);fixture.commit(row[2]);state=observe('held_positions',row)
        holdings=state.to_dict()['positions'];accounts=state.to_dict()['accounts'];reserve=state.to_dict()['reserve']
        if len(holdings)!=8 or any(p['closed'] for p in holdings):
            raise AssertionError('The actual native trace must hold all eight original positions')
        now=clock();mono=time.monotonic()
        stop=capture(ga.prepare_control(state,'stop',source_inputs(now,mono=mono,serial=1200),ledger=ledger),row)
        if stop[0].state.to_dict()['positions']!=holdings or stop[0].state.to_dict()['accounts']!=accounts or stop[0].state.to_dict()['reserve']!=reserve:
            raise AssertionError('Data-free Stop must retain exact holdings and money')
        fixture.commit(stop[2]);stopped=observe('held_position_data_free_stop',stop)
        active=numbers.decode(fixture.db.scalar('SELECT resolved_wire FROM vn_portable_native_research.active_projection;').encode(),maximum=262144)
        if active!=stop[1].resolve():raise AssertionError('Native active projection differs from the original exact Stop checkpoint')
        before=fixture.snapshot();reply=json.loads(fixture.db.scalar(fixture.sql(stop[2]),role=ACTOR))
        if not reply['record_observed'] or fixture.snapshot()!=before:raise AssertionError('Original Stop replay changed state')
        stats=json.loads(fixture.db.scalar('''SELECT jsonb_build_object('commands',commands,'used_bytes',used_bytes,
          'status',status,'revision',revision,'lease_unexpired',lease_until>clock_timestamp()) FROM vn_portable_native_research.runs;'''))
        if stats['status']!='stopped' or not stats['lease_unexpired'] or stats['commands']!=8 or stats['used_bytes']>9707520:
            raise AssertionError('Stop status, lease or logical reserved budget differs')
        return {'format':'ga-portable-native-real-bar-offline-acceptance-lab-v1','accepted':True,
            'scope':'UUID-owned offline PostgreSQL fixture only; literal synthetic provider documents; no network/provider/account/process changes',
            'fixture':fixture.db.identity,'maximum_seconds':maximum_seconds,'elapsed_seconds':round(time.monotonic()-started,6),
            'native_sql_sha256':native_sql_sha256,'probe_source_sha256':probe_source_sha256,
            'genuine_bar_seconds':[initial_end,next_end],'genuine_bar_utc':[utc(initial_end),utc(next_end)],
            'heartbeats':heartbeats,'held_positions':len(holdings),'held_positions_sha256':hashlib.sha256(numbers.encode(holdings)).hexdigest(),
            'source_label':stopped.to_dict()['engine']['config']['source'],'trace':trace,'final_native_stats':stats,
            'source_relaxations':False,'accepted_trace_future_timestamps':False,'fixture_seeded_native_head':False,
            'authority':{'native_production_admission':False,'final_visible_instant_freshness':False,'restoration':False,'retention_deletion':False,'hosted':False}}
    finally:
        PortableNativeSqlTests.tearDownClass()


def main():
    # Check both guards before resolving/statting paths or creating any file.
    if os.environ.get(OPT_IN)!='1' or os.environ.get('DASHBOARD_PORTABLE_NATIVE_REAL_BAR_PROBE')!='1':
        raise RuntimeError('Explicit owned PostgreSQL and real-bar probe opt-ins are both required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maximum-seconds',type=int,default=970)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not 30<=args.maximum_seconds<=970:raise ValueError('The genuine-clock probe deadline must be30..970seconds')
    owned=_OwnedProbeOutput(args.output)
    # This exact PID record permits interrupting only this task's probe. The
    # default Python SIGINT handling runs the owned fixture's finally cleanup.
    try:
        owned.write_running();result=run(maximum_seconds=args.maximum_seconds);owned.publish(result)
    finally:
        if not owned.close():raise ProbeOutputError()
    print(json.dumps({'accepted':True,'output':str(owned.output),'elapsed_seconds':result['elapsed_seconds']},sort_keys=True),flush=True)


if __name__=='__main__':main()
