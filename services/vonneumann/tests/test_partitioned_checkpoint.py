"""Lossless stable partition and complete-command boundaries; no runtime writes."""
from copy import deepcopy
import hashlib
import unittest
from uuid import UUID

from tests.security_support import OfflineTestMixin
from tests.test_provider_contract import OWNER, RUN, WORKER, source_inputs, WALL
from tests.test_provider_ga_components import provider_trace
from vonneumann.db.command_protocol import CommandValidationError, canonical_json
from vonneumann.research import provider_checkpoint as old
from vonneumann.research import partitioned_checkpoint as cp
from vonneumann.research import numeric_wire as numbers
from vonneumann.research import provider_ga_model as ga


def partition_trace(dense, windows=2, observer=None, driver=provider_trace):
    previous, samples = None, []
    metrics = {'windows': windows, 'dense': dense, 'candidates': 0,
        'total_v1_wire_bytes': 0, 'total_v2_wire_bytes': 0,
        'max_manifest_bytes': 0, 'max_command_bytes': 0, 'max_resolved_bytes': 0,
        'changed_blocks_by_phase': {}, 'unique_components': 0, 'unique_component_bytes': 0,
        'quote_only': {'protective': [], 'decision': []}}
    seen = set()
    def observe(candidate, original_capture, original_wire):
        nonlocal previous
        capture = cp.capture_owned_candidate(candidate, legacy_capture=original_capture)
        resolved = capture.resolve()
        original = original_capture.resolve(); original['format'] = cp.FORMAT
        if canonical_json(resolved) != canonical_json(original):
            raise AssertionError('Partition changed complete original evidence')
        command_id = str(UUID(int=40_000_000 + candidate.state.revision))
        wire = cp.prepare_transport(candidate, capture, command_id=command_id, previous=previous)
        body, old_body = numbers.decode(wire), numbers.decode(original_wire)
        for key in ('command_id','owner_id','run_id','operations','history','evidence','events'):
            if numbers.encode(body[key]) != numbers.encode(old_body[key]):
                raise AssertionError('Partition altered original command evidence')
        phase = body['evidence']['kind']
        counts = metrics['changed_blocks_by_phase'].setdefault(phase, {})
        count = str(len(body['components'])); counts[count] = counts.get(count, 0) + 1
        for block in capture.components:
            if block.identity not in seen:
                seen.add(block.identity); metrics['unique_component_bytes'] += len(block._wire)
        metrics['candidates'] += 1
        metrics['total_v1_wire_bytes'] += len(original_wire)
        metrics['total_v2_wire_bytes'] += len(wire)
        for key, size in (('manifest', capture.manifest_bytes), ('command',len(wire)),
                          ('resolved',capture.resolved_bytes)):
            metrics['max_' + key + '_bytes'] = max(metrics['max_' + key + '_bytes'],size)
        if phase in metrics['quote_only'] and not body['components'] and body['evidence']['inputs']['provider']['history'] is None:
            metrics['quote_only'][phase].append({'v1':len(original_wire),'v2':len(wire)})
        if len(samples) < 5: samples.append((candidate, capture, wire, original_capture))
        if observer is not None: observer(candidate, original_capture, original_wire, capture, wire)
        previous = capture
    trace, candidate, _, ledger = driver(dense, windows=windows, observer=observe)
    metrics.update(unique_components=len(seen), final_generation=trace['final_generation'],
                   assessments=trace['assessments'], closed_positions=trace['closed_positions'])
    return metrics, samples, candidate, previous, ledger


class PartitionedCheckpointTests(OfflineTestMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics, cls.samples, cls.last, cls.capture, cls.ledger = partition_trace(True)

    def reject(self, manifest, blocks):
        with self.assertRaises(CommandValidationError):
            cp.resolve_manifest(manifest, blocks, owner_id=OWNER, run_id=RUN, revision=manifest['revision'])

    def test_complete_state_and_command_evidence_survive_two_replacements(self):
        self.assertEqual(self.metrics['final_generation'], 2)
        self.assertEqual(self.metrics['assessments'], 16)
        self.assertEqual(self.metrics['candidates'], 35)
        self.assertLess(self.metrics['max_command_bytes'], cp.ORDINARY_COMMAND_BYTES)
        self.assertLess(self.metrics['total_v2_wire_bytes'], self.metrics['total_v1_wire_bytes'])
        self.assertEqual(len(self.capture.components), 13)
        self.assertEqual(self.capture.resolve()['engine']['optimizer'], self.last.state.to_dict()['engine']['optimizer'])

    def test_quote_reuses_stable_components_without_claiming_retention(self):
        first, quote = self.samples[0][1], self.samples[1][1]
        self.assertEqual(cp.component_updates(first,quote), ())
        self.assertEqual(quote.resolve(),cp.resolve_manifest(quote.to_dict(),first.components,
            owner_id=OWNER,run_id=RUN,revision=quote.to_dict()['revision']))
        self.reject(quote.to_dict(), ())

    def test_completed_candle_changes_both_stable_blocks_and_stop_preserves_them(self):
        samples=[]
        partition_trace(False,windows=1,observer=lambda c,o,ow,p,w:samples.append((c,p,numbers.decode(w))))
        candle=[r for r in samples if r[2]['evidence']['inputs']['provider']['history'] is not None][1]
        self.assertTrue({'source_bars','ema'} <= {b['kind'] for b in candle[2]['components']})
        state=self.ledger._owned_current
        stopped=ga.prepare_control(state,'stop',source_inputs(WALL+9000,serial=600),ledger=self.ledger)
        capture=cp.capture_owned_candidate(stopped)
        wire=cp.prepare_transport(stopped,capture,command_id=str(UUID(int=91)),previous=self.capture)
        body=numbers.decode(wire)
        self.assertEqual(capture.resolve()['status'],'stopped')
        self.assertEqual(body['evidence']['control']['action'],'stop')
        stable=lambda c:{b.to_dict()['kind']:b.identity for b in c.components if b.to_dict()['kind'] in cp._STABLE}
        self.assertEqual(stable(self.capture),stable(capture))
        self.assertTrue(body['history']['assessments'])
        self.assertLess(len(wire),cp.MAX_RESOLVED_BYTES)

    def test_generation_change_does_not_rewrite_unchanged_stable_blocks(self):
        samples=[]
        partition_trace(False,windows=1,observer=lambda c,o,ow,p,w:samples.append((c,p,numbers.decode(w))))
        for index,(candidate,capture,body) in enumerate(samples[1:],1):
            if candidate.history['assessments']:
                previous=samples[index-1][1]
                self.assertEqual({b.to_dict()['kind'] for b in cp.component_updates(previous,capture)},
                                 {'optimizer','cohort','genome'})
                self.assertTrue(all(b.to_dict()['generation']==0 for b in capture.components
                                   if b.to_dict()['kind'] in cp._STABLE))
                return
        self.fail('Fixture did not replace a complete cohort')

    def test_stop_retains_held_positions_and_unscored_history_without_fabricating_exits(self):
        prefix=[]
        def observe(candidate,original,old_wire,capture,wire):
            if not prefix or not prefix[-1][0].state.to_dict()['positions']:
                prefix.append((candidate,capture))
        partition_trace(True,windows=1,observer=observe)
        ledger=ga.SimulationLedger(OWNER,RUN)
        for candidate,_ in prefix: state=ledger.accept(candidate)
        self.assertTrue(state.to_dict()['positions'])
        prior=prefix[-1][1]
        at=state.to_dict()['engine']['last_quote']['timestamp']+1
        stopped=ga.prepare_control(state,'stop',source_inputs(at,serial=700),ledger=ledger)
        capture=cp.capture_owned_candidate(stopped)
        body=numbers.decode(cp.prepare_transport(stopped,capture,
            command_id=str(UUID(int=701)),previous=prior))
        self.assertEqual(capture.resolve()['positions'],state.to_dict()['positions'])
        self.assertEqual(body['history']['closed_positions'],[])
        self.assertTrue(body['history']['assessments'])
        self.assertTrue(all(a['status']=='aborted' and a['fitness_float64'] is None
                            for a in body['history']['assessments']))
        self.assertTrue(all(a['metrics']['has_open_position'] for a in body['history']['assessments']))
        self.assertFalse({'source_bars','ema'} & {b['kind'] for b in body['components']})
        ledger.accept(stopped)

    def test_missing_foreign_duplicate_and_wrong_format_blocks_fail_closed(self):
        capture=self.samples[1][1]; blocks=capture.components; manifest=capture.to_dict()
        foreign=cp.TypedComponent.make(WORKER,RUN,'ema','ema',0,blocks[-1].to_dict()['body'])
        for changed in (blocks[:-1],blocks+(blocks[-1],),(blocks[0],)*13,
                        blocks[:-1]+(foreign,),blocks[:-2]+self.samples[1][3].components[-2:]):
            self.reject(manifest,changed)
        for field,value in (('format',old.FORMAT),('source_model_version','native-v6'),('revision',True)):
            altered=deepcopy(manifest); altered[field]=value; self.reject(altered,blocks)
        with self.assertRaises(CommandValidationError):
            old.resolve_manifest(manifest,blocks,owner_id=OWNER,run_id=RUN,revision=manifest['revision'])

    def test_rehashed_source_and_indicator_substitution_is_rejected(self):
        capture=self.samples[1][1]
        for kind in ('source_bars','ema'):
            blocks=list(capture.components); manifest=capture.to_dict()
            i=next(i for i,b in enumerate(blocks) if b.to_dict()['kind']==kind)
            body=blocks[i].to_dict()['body']
            if kind=='source_bars': body['bars'][-1][1]='81'
            else: body['last_end']+=900
            blocks[i]=cp.TypedComponent.make(OWNER,RUN,kind,kind,0,body)
            manifest['components'][i]=blocks[i].reference()
            self.reject(manifest,tuple(blocks))

    def test_slot_scope_and_duplicate_references_are_explicit(self):
        capture=self.samples[1][1]; manifest=capture.to_dict()
        manifest['components'][-1]=manifest['components'][-2]
        self.reject(manifest,capture.components)
        for generation in (True,1,-1):
            with self.assertRaises(CommandValidationError):
                cp.TypedComponent.make(OWNER,RUN,'ema','ema',generation,{})
        manifest=capture.to_dict(); manifest['engine']['ema']={}
        self.reject(manifest,capture.components)
        manifest=capture.to_dict(); manifest['source']['bars']=[]
        self.reject(manifest,capture.components)

    def test_full_dependency_budget_is_charged_even_if_changed_blocks_are_small(self):
        capture=self.samples[1][1]; manifest=capture.to_dict(); blocks=list(capture.components)
        body={'padding':['x'*14000]*10}
        for i,kind in ((11,'source_bars'),(12,'ema')):
            blocks[i]=cp.TypedComponent.make(OWNER,RUN,kind,kind,0,body)
            manifest['components'][i]=blocks[i].reference()
        self.reject(manifest,tuple(blocks))

    def test_prior_original_uuid_detachment_and_format_boundary(self):
        c,p,w,o=self.samples[1]; before=self.samples[0][1]
        self.assertEqual(cp.prepare_transport(c,p,command_id=str(UUID(int=40_000_000+c.state.revision)),previous=before),w)
        value=numbers.decode(w)
        self.assertEqual(value['prior']['sha256'],hashlib.sha256(numbers.encode(before.to_dict())).hexdigest())
        for previous in (None,o,p):
            with self.assertRaises(CommandValidationError): cp.prepare_transport(c,p,command_id=str(UUID(int=99)),previous=previous)
        copied=p.to_dict(); copied['revision']=999
        self.assertNotEqual(p.to_dict()['revision'],999)
        with self.assertRaises(CommandValidationError): cp.capture_owned_candidate(c,legacy_capture=self.samples[0][3])
        self.assertFalse(hasattr(cp,'decode_state'))
        from vonneumann.db.command_protocol import PreparedCommand
        with self.assertRaises(ValueError):
            PreparedCommand.batch(OWNER,RUN,WORKER,1,1,c.operations,version=6,transition=c.transition)
