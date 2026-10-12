"""Compare declared Linux worker-base math with owned PostgreSQL, offline only.

Synthetic boundaries are not reachable-seed or hosted-worker evidence. No network,
ports, application mounts/secrets, installation or production authority.
"""
import os,json,math,struct,subprocess,uuid,hashlib
from pathlib import Path
from tests.measure_gaussian_compatibility import cases
from tests.measure_provider_ga_research import literal
from tests.postgres.harness import IsolatedPostgres
IMAGE='python:3.12.14-slim-bookworm@sha256:1aaa65a85fda306ffb8b910824d4e93bdce61e212c7e87168123ea3073b41a1a'
CODE='''import sys,json,math,struct,platform
payload=json.load(sys.stdin);initial=len(payload);import random
rng=random.Random(283910)
for sigma,lo,hi in [(0.15*9,3,12),(0.15*45,15,60)]:
 for cached in (False,True):
  for a in [rng.random() for _ in range(128)]+[0.5336203798921629,0.9295600311517099]:
   component=math.sin(a*math.tau) if cached else math.cos(a*math.tau)
   for m in range(hi-lo):
    target=math.copysign(m+.5,component);radius=target/sigma/component
    if radius>8.55:continue
    ideal=1.0-math.exp(-radius*radius/2);nearest=round(ideal*2**53)
    for step in range(-3,4):
     q=min(2**53-1,max(0,nearest+step))
     payload.append([a,q/2**53,sigma,lo,hi,lo if component>=0 else hi,cached,'worker-boundary'])
out=[]
for a,b,sigma,lo,hi,old,cached,kind in payload:
 angle=a*math.tau;radius=math.sqrt(-2.0*math.log(1.0-b));z=(math.sin(angle) if cached else math.cos(angle))*radius
 noise=0.0+z*sigma;period=math.floor(min(hi,max(lo,old+noise))+.5)
 out.append([struct.pack('>d',noise).hex(),period])
print(json.dumps({'python':platform.python_version(),'machine':platform.machine(),'libc':platform.libc_ver(),'initial_cases':initial,'inputs':payload,'results':out}))'''

ROOT=Path(__file__).resolve().parents[1]


def measure():
    db=IsolatedPostgres()  # Fail before Docker operations without explicit opt-in.
    if (ROOT/'Dockerfile').read_text().splitlines()[0] != 'FROM '+IMAGE:
        raise RuntimeError('Reviewed worker-base pin changed')
    rows=cases('random')+cases('boundaries')
    env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','TMPDIR','LANG','LC_ALL')}
    cli=['/opt/homebrew/bin/docker','--host','unix:///Users/redjester/.colima/default/docker.sock']
    info=json.loads(subprocess.run(cli+['image','inspect',IMAGE],env=env,capture_output=True,text=True,check=True).stdout)[0]
    assert info['Id']==IMAGE.split('@')[1] and info['Architecture']=='amd64'
    token=uuid.uuid4().hex;name='dashboard-math-'+token;label='codex.dashboard.math-owner'
    try:
     r=subprocess.run(cli+['run','--interactive','--rm','--pull=never','--name',name,'--label',label+'='+token,'--network','none','--read-only','--user','65534:65534','--cap-drop=ALL','--security-opt','no-new-privileges','--pids-limit','32','--memory','512m','--cpus','1','--entrypoint','python',info['Id'],'-c',CODE],input=json.dumps(rows),env=env,capture_output=True,text=True,timeout=120,check=True)
     worker=json.loads(r.stdout);rows=worker['inputs']
    finally:
     check=subprocess.run(cli+['inspect',name],env=env,capture_output=True,text=True)
     if check.returncode==0:
      owned=json.loads(check.stdout)[0];assert owned['Config']['Labels'].get(label)==token
      subprocess.run(cli+['rm','--force',owned['Id']],env=env,capture_output=True,text=True,check=True)
    statements=[]
    for i,(a,b,sigma,lo,hi,old,cached,kind) in enumerate(rows):
     args=','.join([literal(repr(x))+'::float8' for x in (a,b,sigma)]+[str(lo),str(hi),str(old),'true' if cached else 'false'])
     statements.append("SELECT json_build_object('index',"+str(i)+",'result',pg_temp.gaussian("+args+"));")
    db=db.start()
    try:
     sql='''CREATE FUNCTION pg_temp.gaussian(a float8,b float8,sigma float8,lo integer,hi integer,old integer,cached boolean) RETURNS jsonb LANGUAGE plpgsql SET search_path=pg_catalog AS $f$
     DECLARE angle float8;radius float8;noise float8;
     BEGIN angle:=a*'6.283185307179586'::float8;radius:=sqrt('-2.0'::float8*ln('1.0'::float8-b));
     noise:=CASE WHEN cached THEN sin(angle) ELSE cos(angle) END*radius;noise:='0.0'::float8+noise*sigma;
     RETURN jsonb_build_object('noise_bits',encode(float8send(noise),'hex'),'period',floor(least(hi::float8,greatest(lo::float8,old::float8+noise))+'0.5'::float8)::integer);END $f$;'''
     output=db.sql(sql+'\n'+'\n'.join(statements),timeout=60).stdout.splitlines()
     bits=[];periods=[];mac_bits=[];mac_periods=[]
     for line in output:
      data=json.loads(line);i=data['index'];got=data['result'];expected=worker['results'][i]
      if got['noise_bits']!=expected[0]:bits.append({'index':i,'worker_bits':expected[0],'postgres_bits':got['noise_bits']})
      if got['period']!=expected[1]:periods.append({'index':i,'inputs':rows[i],'worker_period':expected[1],'postgres_period':got['period']})
      a,b,sigma,lo,hi,old,cached,_=rows[i];angle=a*math.tau;radius=math.sqrt(-2.0*math.log(1.0-b));z=(math.sin(angle) if cached else math.cos(angle))*radius
      noise=0.0+z*sigma;period=math.floor(min(hi,max(lo,old+noise))+.5)
      if struct.pack('>d',noise).hex()!=expected[0]:mac_bits.append(i)
      if period!=expected[1]:mac_periods.append(i)
     artifact={'date':'2026-10-12','cases':len(rows),'initial_cases':worker['initial_cases'],'worker_boundary_cases':len(rows)-worker['initial_cases'],'worker_base':{'reference':IMAGE,'image_id':info['Id'],'architecture':info['Architecture'],'python':worker['python'],'machine':worker['machine'],'libc':worker['libc']},'postgres':db.identity,'worker_postgres_noise_mismatches':len(bits),'worker_postgres_period_mismatches':len(periods),'mac_worker_noise_mismatches':len(mac_bits),'mac_worker_period_mismatches':len(mac_periods),'noise_examples':bits[:8],'period_examples':periods[:20],'scope':'exact installed worker base, not hosted Railway image/execution; synthetic inputs, not seed reachability','source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'input_generator_sha256':hashlib.sha256((Path(__file__).with_name('measure_gaussian_compatibility.py')).read_bytes()).hexdigest(),'dockerfile_sha256':hashlib.sha256((ROOT/'Dockerfile').read_bytes()).hexdigest()}
     (ROOT/'research/gaussian-worker-compatibility-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')
     print(json.dumps({k:artifact[k] for k in ('cases','worker_postgres_noise_mismatches','worker_postgres_period_mismatches','mac_worker_noise_mismatches','mac_worker_period_mismatches')}))
    finally:db.close()


if __name__=='__main__':
    measure()
