"""Portable mutation proposal equality, independent SQL and no runtime grant."""
import hashlib
import json
import os
from pathlib import Path
import unittest

from tests.postgres.harness import OPT_IN
from tests.postgres import test_optimizer_transition as optimizer_tests
from tests.postgres.test_economic_transition import INSTALLER,AUDITOR
from tests.measure_provider_ga_research import literal
from vonneumann.research import numeric_wire as numbers
from vonneumann.research.portable_period_mutation import mutate_periods
from vonneumann.core import integer_period_mutation as versioned_mutation

ROOT=Path(__file__).resolve().parents[2]
SQL=ROOT/'db-contract/research/portable_period_mutation.sql'


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class PortablePeriodMutationSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        optimizer_tests.OptimizerTransitionSqlTests.setUpClass.__func__(cls)
        try:
            source=SQL.read_text(); denied=cls.db.sql(source,role=INSTALLER,check=False)
            if denied.returncode==0 or 'offline_portable_period_fixture_required' not in denied.stderr:
                raise AssertionError('Portable proposal installed without offline guard')
            cls.db.sql("BEGIN;SET dashboard.portable_period_fixture='offline-v1';"+source+'COMMIT;',role=INSTALLER)
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def test_complete_trace_matches_independent_sql(self):
        statements=[]; expected=[]; successes={'fast':0,'slow':0,'clamp':0,'negative':0,'positive':0}
        for seed in [str(i) for i in range(128)]+['18446744073709551615']:
            for epoch,event in ((0,0),(1,13)):
                for child in range(8):
                    for sexual in (False,True):
                        fast=3 if child%2 else 12;slow=15 if child%2 else 60
                        output=mutate_periods(fast,slow,seed=seed,epoch=epoch,event=event,child=child,sexual=sexual)
                        core=versioned_mutation.mutate_periods(fast,slow,seed=seed,epoch=epoch,event=event,child=child,sexual=sexual)
                        self.assertEqual(core['operator'],'ema-period-triangular-integer-v1')
                        self.assertEqual({k:v for k,v in core.items() if k!='operator'},
                            {k:v for k,v in output.items() if k not in ('operator','model_integration','restoration_authority')})
                        expected.append(numbers.encode(output).decode())
                        args=','.join((str(fast),str(slow),literal(seed),str(epoch),str(event),str(child),'true' if sexual else 'false'))
                        statements.append('SELECT vn_optimizer_research.portable_periods('+args+')::text;')
                        for i,record in enumerate(output['trace']):
                            if record['mutated']:successes['fast' if i==0 else 'slow']+=1
                            if record['delta']<0:successes['negative']+=1
                            if record['delta']>0:successes['positive']+=1
                            if record['before']+record['delta']!=record['after']:successes['clamp']+=1
        actual=[json.loads(line) for line in self.db.sql('\n'.join(statements),role=INSTALLER,timeout=60).stdout.splitlines()]
        self.assertEqual(actual,[json.loads(line) for line in expected]);self.assertEqual(len(actual),4128)
        self.assertTrue(all(n>0 for n in successes.values()))
        artifact={'date':'2026-10-12','identity':self.db.identity,'complete_python_sql_traces':len(actual),'coverage':successes,
            'operator':'ema-period-triangular-integer-research-v1','sql_sha256':hashlib.sha256(SQL.read_bytes()).hexdigest(),
            'python_sha256':hashlib.sha256((ROOT/'vonneumann/research/portable_period_mutation.py').read_bytes()).hexdigest(),
            'versioned_core_sha256':hashlib.sha256((ROOT/'vonneumann/core/integer_period_mutation.py').read_bytes()).hexdigest(),
            'model_integration':False,'production_grants_or_install':False,'restoration_authority':False,
            'scope':'bounded portable mutation prototype; not a replacement of legacy Gaussian semantics'}
        (ROOT/'research/portable-period-mutation-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')

    def test_bad_inputs_and_no_client_execution(self):
        for kwargs in ({'fast':True},{'fast':2},{'slow':61},{'child':8},{'sexual':1},{'event':-1},
                       {'epoch':2**31},{'event':2**31},{'seed':'18446744073709551616'},
                       {'seed':'01'},{'seed':'-1'},{'seed':''}):
            base={'fast':3,'slow':15,'seed':'0','epoch':0,'event':0,'child':0,'sexual':True};base.update(kwargs)
            with self.assertRaises(ValueError):mutate_periods(**base)
        for args in ("2,15,'0',0,0,0,true","3,61,'0',0,0,0,true","3,15,'0',0,0,8,true",
                     "3,15,'0',0,-1,0,true","3,15,'0',0,0,0,NULL",
                     "3,15,'0',2147483648,0,0,true","3,15,'0',0,2147483648,0,true",
                     "3,15,'18446744073709551616',0,0,0,true","3,15,'01',0,0,0,true",
                     "3,15,'-1',0,0,0,true","3,15,'',0,0,0,true"):
            self.assertNotEqual(self.db.sql('SELECT vn_optimizer_research.portable_periods('+args+');',role=INSTALLER,check=False).returncode,0)
        for role in ('anon','authenticated','service_role','vn_economic_relay',AUDITOR):
            self.assertNotEqual(self.db.sql("SELECT vn_optimizer_research.portable_periods(3,15,'0',0,0,0,true);",role=role,check=False).returncode,0)

    def test_maximum_counters_and_interior_periods(self):
        for child in range(8):
            for sexual in (False,True):
                expected=mutate_periods(7,33,seed='18446744073709551615',epoch=2**31-1,
                    event=2**31-1,child=child,sexual=sexual)
                args="7,33,'18446744073709551615',2147483647,2147483647,"+str(child)+','+str(sexual).lower()
                actual=json.loads(self.db.scalar('SELECT vn_optimizer_research.portable_periods('+args+')::text;',role=INSTALLER))
                self.assertEqual(actual,json.loads(numbers.encode(expected)))
