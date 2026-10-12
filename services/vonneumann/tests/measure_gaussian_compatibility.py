"""Reproduce math portability research in an owned offline PostgreSQL fixture.

Uniform grid inputs are synthetic: this is not seed reachability, an accepted
command corpus, a production failure rate or native admission authority.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys
import platform

from tests.postgres.harness import IsolatedPostgres
from tests.measure_provider_ga_research import literal

ROOT=Path(__file__).resolve().parents[1]


def cases(profile):
    result=[];rng=random.Random(82591 if profile=='random' else 283910)
    for sigma,lo,hi in [(0.15*9,3,12),(0.15*45,15,60)]:
        for cached in (False,True):
            if profile=='random':
                for _ in range(1024):result.append((rng.random(),rng.random(),sigma,lo,hi,rng.randrange(lo,hi+1),cached,'random'))
                angles=[.25 if cached else 0.0]
            else:angles=[rng.random() for _ in range(128)]
            for a in angles:
                component=math.sin(a*math.tau) if cached else math.cos(a*math.tau)
                for m in range(hi-lo):
                    target=math.copysign(m+.5,component);radius=target/sigma/component
                    if radius>8.55:continue
                    ideal=1.0-math.exp(-radius*radius/2);nearest=round(ideal*2**53)
                    for step in range(-3,4):
                        q=min(2**53-1,max(0,nearest+step))
                        result.append((a,q/2**53,sigma,lo,hi,lo if component>=0 else hi,cached,'boundary'))
    return result


def measure(profile):
    rows=cases(profile);statements=[];expected=[]
    for i,(a,b,sigma,lo,hi,old,cached,kind) in enumerate(rows):
        angle=a*math.tau;radius=math.sqrt(-2.0*math.log(1.0-b))
        z=(math.sin(angle) if cached else math.cos(angle))*radius
        noise=0.0+z*sigma;period=math.floor(min(hi,max(lo,old+noise))+.5)
        expected.append((struct.pack('>d',noise).hex(),period))
        args=','.join([literal(repr(x))+'::float8' for x in (a,b,sigma)]+[str(lo),str(hi),str(old),'true' if cached else 'false'])
        statements.append('SELECT json_build_object(\'index\','+str(i)+',\'result\',pg_temp.gaussian('+args+'));')
    db=IsolatedPostgres().start()
    try:
        sql='''CREATE FUNCTION pg_temp.gaussian(a float8,b float8,sigma float8,lo integer,hi integer,old integer,cached boolean) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
        DECLARE angle float8;radius float8;noise float8;
        BEGIN angle:=a*'6.283185307179586'::float8;radius:=sqrt('-2.0'::float8*ln('1.0'::float8-b));
        noise:=CASE WHEN cached THEN sin(angle) ELSE cos(angle) END*radius;
        noise:='0.0'::float8+noise*sigma;
        RETURN jsonb_build_object('noise_bits',encode(float8send(noise),'hex'),'period',floor(least(hi::float8,greatest(lo::float8,old::float8+noise))+'0.5'::float8)::integer);
        END $f$;'''
        output=db.sql(sql+'\n'+'\n'.join(statements),timeout=60).stdout.splitlines()
        bits=[];periods=[]
        for line in output:
            row=json.loads(line);i=row['index'];result=row['result'];bit,period=expected[i]
            if result['noise_bits']!=bit:bits.append({'index':i,'kind':rows[i][-1],'cached':rows[i][-2],
                'python_bits':bit,'postgres_bits':result['noise_bits']})
            if result['period']!=period:periods.append({'index':i,'kind':rows[i][-1],'inputs':rows[i][:-1],
                'python_period':period,'postgres_period':result['period'],'python_bits':bit,'postgres_bits':result['noise_bits']})
        return {'date':'2026-10-12','identity':db.identity,'python':'.'.join(map(str,sys.version_info[:3])),
            'platform':{'system':platform.system(),'machine':platform.machine()},'profile':profile,
            'scope':'synthetic uniform inputs; numeric compatibility only; not owned command/seed reachability or native authority',
            'cases':len(rows),'random_cases':sum(c[-1]=='random' for c in rows),'boundary_cases':sum(c[-1]=='boundary' for c in rows),
            'noise_bit_mismatches':len(bits),'period_mismatches':len(periods),'bit_examples':bits[:8],'period_examples':periods[:20],
            'prototype_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    finally:db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('profile',choices=('random','boundaries'));args=parser.parse_args()
    artifact=measure(args.profile)
    name='gaussian-compatibility-measurements.json' if args.profile=='random' else 'gaussian-boundary-measurements.json'
    (ROOT/'research'/name).write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:artifact[key] for key in ('profile','cases','noise_bit_mismatches','period_mismatches','prototype_sha256')}))
