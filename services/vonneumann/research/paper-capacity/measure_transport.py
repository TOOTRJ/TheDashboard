#!/usr/bin/env python3
"""Measure actual read-only transport with deterministic synthetic HTTP bodies."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import select
import signal
import subprocess
import sys
import time
from unittest.mock import patch

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[2]
WORK = SCRIPT.parent
FILES = ('tests/security_support.py', 'tests/test_provider_recorded_transport_v3.py',
         'vonneumann/market/provider_acquisition_v3.py', 'vonneumann/market/provider_derivation_v3.py',
         'vonneumann/market/provider_recorded_transport_v3.py', 'requirements-dev.txt')
sys.path.insert(0, str(ROOT))
from tests.test_provider_recorded_transport_v3 import KEY, RPC_URL, a, deny_network, httpx, prepared, reply, t


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def stats(values):
    ordered = sorted(values)
    n = len(ordered)
    require(n > 0, 'missing observations')
    return {'n': n, **{f'p{k}_ns': ordered[(n*k+99)//100-1] for k in (50, 95, 99, 100)}}


def rss_bytes():
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    require(sys.platform in ('darwin','linux'), 'unsupported RSS units')
    return raw if sys.platform == 'darwin' else raw * 1024


BODY_PROFILES = {'tiny': (None,None,None), 'padded': (4096,1024,1024),
                 'max': (131072,65536,65536)}


class CounterTransport(httpx.AsyncBaseTransport):
    def __init__(self, sizes):
        self.sizes = sizes
        self.calls = Counter()
        self.body_bytes = 0

    async def handle_async_request(self, request):
        if request.method == 'GET':
            index = 0
            body = (f'{{"{a.MINT}":{{"usdPrice":100.123456789012345678,'
                    '"blockId":348004023,"decimals":9,"priceChange24h":null}}').encode()
            # Match exact source parser shape, including closing both objects.
        else:
            payload = json.loads(request.content)
            index = {'getGenesisHash': 1, 'getBlockTime': 2}[payload['method']]
            result = a.GENESIS if index == 1 else 1_800_000_000
            body = a.canonical({'jsonrpc':'2.0','id':payload['id'],'result':result})
        self.calls[('price','genesis','block_time')[index]] += 1
        size = self.sizes[index]
        if size is not None:
            require(size >= len(body), 'test body pad refused')
            body += b' ' * (size-len(body))
        self.body_bytes += len(body)
        return reply(request, body=body)


class MeasuredTransport(t.ProviderRecordedTransport):
    def __init__(self):
        self.phase_ns = defaultdict(list)
        self.packet_phases = 0
        super().__init__(KEY,RPC_URL,read_only_opt_in=True)

    async def _capture(self, *args, **kwargs):
        phase = ('price','genesis','block_time')[self.packet_phases % 3]
        start = time.perf_counter_ns()
        result = await super()._capture(*args, **kwargs)
        self.phase_ns[phase].append(time.perf_counter_ns()-start)
        self.packet_phases += 1
        return result


def make_transport(profile):
    fake = CounterTransport(BODY_PROFILES[profile])
    with patch.object(t,'_transport',return_value=fake):
        measured = MeasuredTransport()
    return measured, fake


def proof(result):
    return {'prepared_sha256':digest(result.prepared.wire),
            'original_capsule_sha256': [digest(cap.wire) for cap in result.capsules],
            'original_body_sha256': [digest(cap.raw_body) for cap in result.capsules],
            'completed':result.completed,
            'native_admission':result.native_admission}


async def profile(name, count):
    item,fake = make_transport(name)
    elapsed,charges = [],[]
    before_rss = rss_bytes()
    cpu_start = time.process_time_ns()
    refused = None
    try:
        for index in range(count):
            previous_bytes = item._retained_bytes
            start = time.perf_counter_ns()
            try:
                result = await item.collect(prepared(index))
            except t.RecordedTransportError as error:
                require(error.code=='retention_capacity', 'unexpected transport refusal')
                refused = index+1
                require(item._retained_bytes==previous_bytes, 'refusal changed bytes')
                break
            elapsed.append(time.perf_counter_ns()-start)
            require(result.completed and len(result.capsules)==3 and not result.native_admission,
                    'synthetic packet did not complete')
            charges.append(item._retained_bytes-previous_bytes)
        first, last = await item.collect(prepared(0)), await item.collect(prepared(len(elapsed)-1))
        require(len(fake.calls)==3 and all(x==len(elapsed) for x in fake.calls.values()), 'unexpected synthetic I/O')
        await item.close()
        require(await item.collect(prepared(0)) is first and await item.collect(prepared(len(elapsed)-1)) is last,
                'closed transport failed exact original replay')
        require(all(x==len(elapsed) for x in fake.calls.values()), 'replay repeated synthetic I/O')
        require(item._retained_bytes==sum(charges) and len(item._results)==len(elapsed), 'retained counter mismatch')
        return {'profile':name,'attempt_bound':count,'completed':len(elapsed),'capacity_refused_at':refused,
                'synthetic_call_counts':dict(fake.calls),'synthetic_body_bytes':fake.body_bytes,
                'retained_bytes':item._retained_bytes,'retained_ids':len(item._used_ids),
                'per_packet_charge_bytes':{'min':min(charges),'max':max(charges)},
                'remaining_before_pre_io_threshold':item._bounds.result_bytes_limit-t.PACKET_RESERVE_BYTES-item._retained_bytes,
                'phase_timing_ns':{**{k:stats(v) for k,v in item.phase_ns.items()},'collect':stats(elapsed)},
                'process_cpu_ns':time.process_time_ns()-cpu_start,'peak_rss_bytes_before_trace':before_rss,
                'peak_rss_bytes_after_trace':rss_bytes(),'closed_exact_replay':True,
                'sustained_real_time_or_provider_result':False}
    finally:
        await item.close()


async def child(original_hold):
    item,fake=make_transport('tiny')
    require(item._retained_bytes==0 and not item._results and not item._used_ids, 'fresh process unexpectedly owns records')
    plan=prepared(0)
    try:
        result=await item.collect(plan)
        require(result.completed and len(result.capsules)==3 and sum(fake.calls.values())==3, 'invalid synthetic result')
        print(json.dumps(proof(result),sort_keys=True),flush=True)
        if original_hold:
            signal.pause()
    finally:
        await item.close()


def abrupt_restart():
    args=[sys.executable,'-I','-B',str(SCRIPT)]
    env={'PATH':'/usr/bin:/bin','HOME':str(WORK),'PYTHON_DOTENV_DISABLED':'1'}
    with subprocess.Popen(args+['hold'],cwd=WORK,env=env,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True) as process:
        try:
            require(bool(select.select([process.stdout],[],[],10)[0]), 'owned child did not produce completion proof')
            raw=process.stdout.readline(8192)
            require(raw.endswith(b'\n'), 'bounded child proof unavailable')
            before=json.loads(raw)
            require(process.poll() is None, 'owned child exited before interruption')
            process.kill()
            require(process.wait(timeout=5)==-signal.SIGKILL, 'owned child SIGKILL not observed')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    after=json.loads(subprocess.check_output(args+['fresh'],cwd=WORK,env=env,timeout=10,stdin=subprocess.DEVNULL))
    require(before['prepared_sha256']==after['prepared_sha256'] and before['original_body_sha256']==after['original_body_sha256'],
            'restart fixture did not reuse identical synthetic inputs')
    require(before['original_capsule_sha256']!=after['original_capsule_sha256'], 'fresh process unexpectedly replayed old capsules')
    return {'owned_child_exit':'SIGKILL','same_prepared_identity':True,'same_synthetic_response_bodies':True,
            'new_receipts_on_deliberate_fake_resubmission':True,'native_recovery_proven':False,
            'meaning':'transport has no crash-persistent original lookup; do not resubmit uncertain identities'}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('profile','restart','hold','fresh'))
    p.add_argument('--body',choices=BODY_PROFILES,default='tiny')
    p.add_argument('--attempts',type=int,default=945)
    args=p.parse_args()
    require(1<=args.attempts<=945, 'attempt bound invalid')
    with deny_network():
        if args.action in ('hold','fresh'):
            asyncio.run(child(args.action=='hold'))
            return
        observation=asyncio.run(profile(args.body,args.attempts)) if args.action=='profile' else abrupt_restart()
    result={'kind':'actual-transport-with-in-memory-synthetic-http','observation':observation,
            'sources':{name:digest((ROOT/name).read_bytes()) for name in FILES},
            'harness_sha256':digest(SCRIPT.read_bytes()),'runtime':{'python':sys.version.split()[0],
            **{name:importlib.metadata.version(name) for name in ('httpx','httpcore','certifi')}}}
    print(json.dumps(result,sort_keys=True,indent=2))


if __name__=='__main__':
    main()
