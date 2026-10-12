"""Explicit portable model isolation, legacy byte continuity and real replacements."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import unittest
from uuid import UUID

from tests.security_support import OfflineTestMixin,deny_network
from tests.test_provider_ga_components import provider_trace
from tests.test_provider_contract import OWNER,RUN,WALL,MONO,EPOCH,seed_bundle,source_inputs,raw_capture
from vonneumann.core import integer_period_mutation as mutation
from vonneumann.db.command_protocol import CommandValidationError
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import provider_ga_model as legacy
from vonneumann.research import provider_checkpoint as old_cp
from vonneumann.research import provider_portable_ga_model as model
from vonneumann.research import portable_partitioned_checkpoint as cp

ROOT=Path(__file__).resolve().parents[1]


class PortableGAModelTests(OfflineTestMixin,unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.traces=[];cls.samples=[]
        for seed in ('0','1','18446744073709551615'):
            samples=[]
            metrics,last,capture,ledger=provider_trace(True,windows=4,model=model,checkpoint=cp,
                search_seed=seed,observer=lambda c,p,w:samples.append((c,p,w)))
            cls.traces.append((seed,metrics,last,capture,ledger,samples));cls.samples.extend(samples)
        if os.environ.get('DASHBOARD_PORTABLE_MODEL_MEASURE')=='1':
            files=('vonneumann/core/integer_period_mutation.py','vonneumann/core/strategies/genetic_algorithm.py',
                'vonneumann/research/exact_configuration.py',
                'vonneumann/research/provider_portable_ga_model.py','vonneumann/research/provider_portable_checkpoint.py','vonneumann/research/portable_partitioned_checkpoint.py')
            artifact={'date':'2026-10-12','model':model.MODEL_FORMAT,'operator':mutation.VERSION,
                'transport':cp.TRANSPORT_FORMAT,'scope':'three seeds/four synthetic windows each; owned in-process model and capture only',
                'previous_measurement_sha256':hashlib.sha256((ROOT/'research/portable-ga-model-measurements.json').read_bytes()).hexdigest(),
                'repair':'PAPER-COMPACT-TYPE1; configuration validation only; canonical model/operator/wire policies unchanged',
                'traces':[{'seed':seed,'metrics':metrics} for seed,metrics,*_ in cls.traces],
                'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
                'independent_complete_sql_validation':False,'native_admission':False,'restoration_authority':False,
                'hosted_activation':False,'performance_calibration':False}
            (ROOT/'research/portable-ga-model-type-repair-measurements.json').write_text(json.dumps(artifact,indent=2,sort_keys=True)+'\n')

    def test_ordinary_ga_import_does_not_load_the_portable_operator(self):
        env={'PATH':os.environ['PATH'],'PYTHONPATH':str(ROOT),'PYTHON_DOTENV_DISABLED':'1','PYTHONDONTWRITEBYTECODE':'1'}
        code="from tests.security_support import deny_network\nwith deny_network():\n import vonneumann.core.strategies.genetic_algorithm\n import sys\n assert 'vonneumann.core.integer_period_mutation' not in sys.modules\n"
        result=subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_legacy_sparse_dense_full_and_compact_wires_are_identical(self):
        baseline=json.loads((ROOT/'research/legacy-ga-portable-integration-baseline.json').read_text())
        for row in baseline['traces']:
            actual=[]
            provider_trace(row['dense'],windows=2,observer=lambda c,p,w:actual.append({
                'candidate_sha256':hashlib.sha256(c._wire).hexdigest(),
                'compact_sha256':hashlib.sha256(w).hexdigest(),'phase':c.transition['evidence']['kind']}))
            self.assertEqual(actual,row['commands'])
        self.assertEqual(sum(len(t['commands']) for t in baseline['traces']),70)
        repair=json.loads((ROOT/'research/configuration-type-repair-measurements.json').read_text())
        for name in ('provider_ga_model.py','provider_checkpoint.py','partitioned_checkpoint.py'):
            path='vonneumann/research/'+name
            expected=baseline['source_before'][path]
            if name=='provider_ga_model.py':
                # The original artifact stays historical. Only the exactly
                # source-bound TYPE1 rejection repair may replace this validator.
                self.assertEqual(repair['source_before'][path],expected)
                self.assertEqual(repair['compatibility_decision'],'same_versions_canonical_wires_unchanged_stricter_rejection_only')
                expected=repair['source_sha256'][path]
            self.assertEqual(hashlib.sha256((ROOT/'vonneumann/research'/name).read_bytes()).hexdigest(),
                expected)

    def test_three_seeds_four_complete_windows_have_fixed_genes_and_actual_parentage(self):
        operations=set();total=0
        for seed,metrics,last,capture,ledger,samples in self.traces:
            self.assertEqual(metrics['final_generation'],4);self.assertEqual(metrics['assessments'],32)
            self.assertLess(metrics['max_compact_command_bytes'],cp.ORDINARY_COMMAND_BYTES)
            self.assertLess(metrics['max_resolved_bytes'],cp.MAX_RESOLVED_BYTES)
            for candidate,checkpoint,wire in samples:
                data=candidate.state.to_dict();config=data['engine']['config']
                self.assertEqual(config['mutation_policy'],mutation.policy())
                self.assertEqual(numbers.decode(wire)['format'],cp.TRANSPORT_FORMAT)
                for member in data['engine']['members']:
                    genome=model.base._genome(member['genome'],model._configuration(data).colony_config())
                    model._configuration(data).colony_config().assert_profile_genome(genome)
                    self.assertTrue(3<=genome.ema_fast<=12 and 15<=genome.ema_slow<=60)
                    self.assertEqual(genome.assets,['SOL/USD'])
                selection=candidate.history['selection']
                if selection is not None:
                    self.assertEqual(selection['mutation_operator'],mutation.VERSION)
                    total+=len(selection['offspring'])
                    for child,record in zip(candidate.history['birth_members'],selection['offspring']):
                        operations.add(record['operation'])
                        self.assertEqual(child['genome']['parent_ids'],record['parent_ids'])
                        self.assertEqual(len(record['parent_ids']),2 if record['operation']=='crossover_mutation' else 1)
                    self.assertEqual(candidate.history['assessments'][0]['format'],model.ASSESSMENT_FORMAT)
            state,_,_=last.state._fork()
            self.assertEqual(state['engine']['config']['search_seed'],seed)
        self.assertEqual(total,96)
        self.assertEqual(operations,{'crossover_mutation','clone_mutation'})

    def test_common_founders_and_first_window_selection_stream_stay_identical(self):
        for seed in ('0','1'):
            snapshots=[];legacy_snapshots=[]
            _,new,_,_=provider_trace(False,windows=1,model=model,checkpoint=cp,search_seed=seed,
                observer=lambda c,p,w:snapshots.append(c))
            _,old,_,_=provider_trace(False,windows=1,search_seed=seed,
                observer=lambda c,p,w:legacy_snapshots.append(c))
            self.assertEqual([m['genome'] for m in snapshots[0].state.to_dict()['engine']['members']],
                [m['genome'] for m in legacy_snapshots[0].state.to_dict()['engine']['members']])
            _,new_strategy,_=new.state._fork();_,old_strategy,_=old.state._fork()
            self.assertEqual(new_strategy._rng.getstate(),old_strategy._rng.getstate())
            new_selection=[c.history['selection'] for c in snapshots if c.history['selection'] is not None][0]
            old_selection=[c.history['selection'] for c in legacy_snapshots if c.history['selection'] is not None][0]
            new_selection.pop('mutation_operator');self.assertEqual(new_selection,old_selection)

    def test_quote_and_replacement_keep_stable_candle_indicator_dependencies(self):
        replacements=0
        for _,_,_,_,_,samples in self.traces:
            previous=None
            for candidate,capture,wire in samples:
                self.assertEqual(len(capture.components),13)
                stable={r['kind']:r for r in capture.to_dict()['components'] if r['kind'] in ('source_bars','ema')}
                self.assertEqual(set(stable),{'source_bars','ema'})
                self.assertTrue(all(r['generation']==0 for r in stable.values()))
                body=numbers.decode(wire)
                if previous is not None and candidate.transition['evidence']['inputs']['provider']['history'] is None:
                    self.assertEqual(stable,previous)
                    self.assertFalse(any(c['kind'] in ('source_bars','ema') for c in body['components']))
                    if candidate.history['selection'] is not None:replacements+=1
                previous=stable
        self.assertEqual(replacements,12)

    def test_versions_and_owned_classes_cannot_mix(self):
        new,new_cp,_=self.samples[0]
        old_ledger=legacy.SimulationLedger(OWNER,RUN)
        old=legacy.bootstrap(legacy.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH),
            seed_bundle(last_close='80'),source_inputs(WALL),ledger=old_ledger)
        for function,arg in ((cp.capture_owned_candidate,old),(old_cp.capture_owned_candidate,new),
                             (old_ledger.accept,new),(model.SimulationLedger(OWNER,RUN).accept,old)):
            with self.assertRaises((CommandValidationError,model.ExactRehearsalError)):function(arg)
        with self.assertRaises(model.ExactRehearsalError):
            model.bootstrap(legacy.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH),
                seed_bundle(),source_inputs(WALL),ledger=model.SimulationLedger(OWNER,RUN))
        with self.assertRaises(CommandValidationError):old_cp.TypedComponent(new_cp.components[0]._wire)
        with self.assertRaises(CommandValidationError):cp.ActiveCheckpoint(new_cp.to_dict())
        with self.assertRaises(model.ExactRehearsalError):model.GAState(new.state.to_dict())

    def test_rehashed_configuration_and_operator_headers_cannot_change(self):
        candidate,capture,_=self.samples[0]
        for alter in (lambda c:c['mutation_policy'].update(sexual_rate_per_million=200001),
                      lambda c:c.pop('mutation_policy'),lambda c:c.update(code_version=legacy.CODE_VERSION),
                      lambda c:c.update(search_seed='01'),lambda c:c.update(population=7),
                      lambda c:c['counter_policy'].update(maximum='10')):
            manifest=capture.to_dict();components=[]
            for component in capture.components:
                item=component.to_dict()
                if item['kind']=='configuration':
                    alter(item['body']);following=cp.TypedComponent.make(OWNER,RUN,'configuration','configuration',0,item['body'])
                    manifest['components']=[following.reference() if r['kind']=='configuration' else r for r in manifest['components']]
                    components.append(following)
                else:components.append(component)
            with self.assertRaises(CommandValidationError):
                cp.resolve_manifest(manifest,tuple(components),owner_id=OWNER,run_id=RUN,revision=candidate.state.revision)
        policy=mutation.policy();policy['radii']['ema_fast']=4
        with patch.object(mutation,'policy',return_value=policy),self.assertRaises(model.ExactRehearsalError):
            model.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=EPOCH)

    def test_pause_resume_restart_and_data_free_stop_preserve_version(self):
        ledger=model.SimulationLedger(OWNER,RUN)
        state=ledger.accept(model.bootstrap(model.GAConfig('genetic_algorithm',OWNER,RUN,
            asset='SOL/USD',source_epoch=EPOCH),seed_bundle(last_close='80'),source_inputs(WALL),ledger=ledger))
        original=[m['genome'] for m in state.to_dict()['engine']['members']]
        state=ledger.accept(model.prepare_control(state,'pause',source_inputs(WALL+1,mono=MONO+1,serial=1),ledger=ledger))
        self.assertTrue(state.to_dict()['engine']['lifecycle']['restart_required'])
        state=ledger.accept(model.prepare_control(state,'resume',source_inputs(WALL+2,mono=MONO+2,serial=2),ledger=ledger))
        wall=WALL+3;mono=MONO+3
        frame=model.source.make_frame(raw_capture(block=103,source_second=wall-2,wall=wall-1,mono=mono-1),
            prior_source=state.to_dict()['source'],epoch=EPOCH,wall_now=wall,monotonic_now=mono)
        state=ledger.accept(model.prepare_protective(state,frame,source_inputs(wall,mono=mono,serial=6),ledger=ledger))
        state=ledger.accept(model.prepare_decision(state,frame,None,
            source_inputs(wall,mono=mono,generation=1,serial=7),ledger=ledger))
        data,strategy,_=state._fork()
        self.assertEqual(data['engine']['generation'],1);self.assertEqual(strategy._search_epoch,1)
        self.assertEqual(strategy._mutation_event,0)
        for old,member in zip(original,data['engine']['members']):
            expected=dict(old);expected.update(generation=1,parent_ids=member['genome']['parent_ids'])
            self.assertEqual(member['genome'],expected)
        stopped=model.prepare_control(state,'stop',source_inputs(wall+1,mono=mono+1,serial=9),ledger=ledger)
        self.assertIsNone(stopped.transition['evidence']['inputs']['provider']['frame'])
        checkpoint=cp.capture_owned_candidate(stopped)
        self.assertEqual(checkpoint.resolve()['source_model_version'],model.MODEL_FORMAT)
        self.assertEqual(ledger.accept(stopped).to_dict()['status'],'stopped')

    def test_selector_and_fractional_periods_fail_without_rng_advance(self):
        _,_,last,_,_,_=self.traces[0]
        data,strategy,_=last.state._fork();config=model._configuration(data).colony_config()
        before=strategy._rng.getstate()
        for version in ('unknown',True,1):
            with self.assertRaises(ValueError):strategy.evolve([],[],config,period_operator=version)
        self.assertEqual(strategy._rng.getstate(),before)
        strategy._mutation_event=2**31-1
        with patch.object(strategy._cohort,'results',side_effect=AssertionError('Admission reached cohort')):
            with self.assertRaises(ValueError):strategy.evolve([],[],config,period_operator=mutation.VERSION)
        self.assertEqual(strategy._rng.getstate(),before)
        for label in ('search epoch','mutation event'):
            model._counter(2**31-2,label)
            with self.assertRaises(model.base.ExactCapacityError):model._counter(2**31-1,label)
        for value in (7.5,True,float('nan'),float('inf')):
            with self.assertRaises((ValueError,OverflowError)):mutation._genome_period(value)
        self.assertEqual(mutation._genome_period(7.0),7)
