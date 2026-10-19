"""Literal prospective records and independently built legacy math fixtures.

No fixture is collected live or authenticated. The old synthetic history keeps
its original format; equality compares declared neutral mathematical/economic
fields, never a relabelled state or a claim of trading profitability.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from tests.test_prospective_source_v3 import mark, seal, OWNER, RUN, MARKET, PROCESS, ISSUER, PRINCIPAL, PACKAGE, RECEIPT, START, END
    from tests.test_provider_contract import raw_capture, raw_minutes
    from vonneumann.market import prospective_source_v3 as s, provider_acquisition_v3 as a, provider_derivation_v3 as d
    from vonneumann.research import prospective_ga_v3_policy as p, prospective_ga_v3_model as m
    from vonneumann.research import provider_portable_ga_model as legacy, numeric_wire as numbers
    from vonneumann.core.decision_inputs import DecisionInputs
    from vonneumann.core.decimal_execution import DecimalExecutionConfig


def new_inputs(event_us, monotonic_us, *, serial=0, generation=0, epoch=PROCESS):
    return p.V3Inputs(a.ClockBound(OWNER, RUN, MARKET, epoch, event_us, event_us, monotonic_us), event_us,
        tuple(str(UUID(int=300_000+serial*100+index)) for index in range(32)),
        tuple((generation, 'Literal-member-'+str(index)) for index in range(16)))


def inputs_for_mark(observation, *, serial, generation=0, offset=100_000):
    row = observation.to_dict(); original = row['original_observation_clock']
    event = int(row['reference']['available_at_upper_us'])+offset
    monotonic = int(original['monotonic_us'])+event-int(original['wall_lower_us'])
    return new_inputs(event, monotonic, serial=serial, generation=generation, epoch=row['acquisition_epoch'])


def old_inputs(value):
    # Only the unchanged old fixture receives its original float-mono API.
    at = datetime(1970, 1, 1, tzinfo=timezone.utc)+timedelta(seconds=value.math_second)
    return DecisionInputs(at, at, value.clock.monotonic_us/1_000_000, value.ids, value.names)


def fill_policy():
    return p.PaperFillPolicy('25', '10', '20', 'literal-offline-uncalibrated-costs',
        str(UUID(int=123)), hashlib.sha256(b'literal-fee25-spread10-slip20').hexdigest())


def subsecond_mark(prior, delta=500_000, *, epoch=PROCESS, mono_us=None, identity=500_000,
                   sequence=None, price=None, block=None, source_second=None):
    """Separate literal acquisition with explicit process/UTC clock provenance."""
    row = prior.to_dict(); ref = row['reference']; old_clock = row['original_observation_clock']
    accepted, available = int(ref['accepted_at_us'])+delta, int(ref['available_at_upper_us'])+delta
    original = row['record_pins'][0]
    wall, mono = int(original['received_wall_us'])+delta, int(original['received_monotonic_us'])+delta
    if mono_us is not None: mono=mono_us
    binding = a.IssuerBinding(OWNER,RUN,MARKET,epoch,ISSUER,
        (('jupiter-price-v3',str(UUID(int=21))),('solana-rpc',str(UUID(int=22)))))
    def capture(family, body, request, index):
        return a.capture_capsule(binding,record_id=str(UUID(int=identity+index)),provider_family=family,
            request=request,raw_body=body,http_status=200,started_wall_us=wall-100_000,received_wall_us=wall,
            started_monotonic_us=mono-100_000,received_monotonic_us=mono)
    price_text=row['price_decimal'] if price is None else price
    block_ref=int(row['block_ref']) if block is None else block
    price = capture('jupiter-price-v3',('{"'+a.MINT+'":{"usdPrice":'+price_text
        +',"blockId":'+str(block_ref)+',"decimals":9}}').encode(),a.public_request('jupiter-price-v3'),1)
    genesis = capture('solana-rpc',a.canonical({'jsonrpc':'2.0','id':1,'result':a.GENESIS}),
        a.public_request('solana-rpc',rpc_method='getGenesisHash',rpc_id=1),2)
    estimated=int(row['estimated_source_second']) if source_second is None else source_second
    block = capture('solana-rpc',a.canonical({'jsonrpc':'2.0','id':2,'result':estimated}),
        a.public_request('solana-rpc',rpc_method='getBlockTime',rpc_id=2,slot=block_ref),3)
    observed_mono=mono+int(old_clock['monotonic_us'])-int(original['received_monotonic_us'])
    observed_clock = a.ClockBound(OWNER,RUN,MARKET,epoch,int(old_clock['wall_lower_us'])+delta,
        int(old_clock['wall_upper_us'])+delta,observed_mono)
    observed = d.derive_observation(price,genesis,block,binding,observed_clock,observation_id=str(UUID(int=identity+4)))
    reference = s.RecordReference(OWNER,RUN,MARKET,epoch,str(UUID(int=identity+4)),observed.sha256,
        str(UUID(int=identity+5)),int(ref['ingest_sequence'])+1 if sequence is None else sequence,
        accepted,available,PRINCIPAL,PACKAGE,RECEIPT)
    return s.capture_mark(observed,reference)


class ProspectiveModelV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with deny_network():
            # A simulated contiguous corpus, not 15h15m of actual acquisition.
            cls.marks = tuple(mark(index, price='100') for index in range(915))
            cls.history = s.derive_sampled_history(seal(cls.marks))
            cls.series = s.derive_close_series(cls.history, expected_history_sha256=cls.history.sha256)
    def setUp(self):
        guard = deny_network(); guard.__enter__(); self.addCleanup(guard.__exit__, None, None, None)
        self.binding = p.SourceBinding(OWNER, RUN, MARKET, PROCESS, PRINCIPAL, PACKAGE)
        self.config = p.V3Config(OWNER, RUN, MARKET, self.binding, fill_policy())
        self.ledger = m.OfflineLedger(OWNER, RUN)
        self.initial_inputs = new_inputs((END+5)*1_000_000, 54_905_000_000)
    def bootstrap(self):
        candidate = m.bootstrap(self.config, self.history, self.series,
            expected_history_sha256=self.history.sha256, inputs=self.initial_inputs, ledger=self.ledger)
        return candidate, self.ledger.accept(candidate)
    def protective(self, state, observation, *, serial, generation=0):
        inputs = inputs_for_mark(observation, serial=serial, generation=generation)
        candidate = m.prepare_protective(state, observation, expected_mark_sha256=observation.sha256,
            inputs=inputs, ledger=self.ledger)
        return candidate, self.ledger.accept(candidate), inputs
    def decision(self, state, observation, inputs, **history):
        later = replace(inputs, clock=replace(inputs.clock, wall_lower_us=inputs.event_us+100_000,
            wall_upper_us=inputs.event_us+100_000, monotonic_us=inputs.clock.monotonic_us+100_000),
            event_us=inputs.event_us+100_000)
        candidate = m.prepare_decision(state, observation, expected_mark_sha256=observation.sha256,
            inputs=later, ledger=self.ledger, **history)
        return candidate, self.ledger.accept(candidate)
    def to_held_positions(self):
        _, state = self.bootstrap(); history = self.history; all_marks = list(self.marks)
        trajectory = ('100','80','120','100'); serial = 40
        for bar in range(4):
            history_args = {}
            if bar:
                added = tuple(mark(index,price=trajectory[bar-1])
                    for index in range(915+(bar-1)*15,915+bar*15));all_marks.extend(added)
                end = END+bar*900
                history = s.derive_sampled_history(seal(tuple(all_marks[-30:]),start=end-1800,end=end,
                    seal_id=str(UUID(int=100_000+bar))),previous=history,expected_previous_sha256=history.sha256)
                series = s.derive_close_series(history,expected_history_sha256=history.sha256)
                history_args = {'history':history,'series':series,'expected_history_sha256':history.sha256}
            for later in (False,True):
                observation=mark(915+bar*15+int(later),price=trajectory[bar])
                _, state, inputs=self.protective(state,observation,serial=serial,generation=1);serial+=1
                _, state=self.decision(state,observation,inputs,**({} if later else history_args))
        self.assertEqual(len(state.to_dict()['positions']),8)
        return state,inputs,history,series
    def test_required_cost_provenance_exact_config_and_authority_false(self):
        with self.assertRaises(TypeError): p.V3Config(OWNER, RUN, MARKET, self.binding)
        with self.assertRaises(TypeError): p.PaperFillPolicy()
        self.assertEqual(p.V3Config.from_dict(self.config.to_dict()), self.config)
        value = self.config.to_dict()
        self.assertEqual(value['paper_fill']['execution']['config'], {'fee_bps':'25','half_spread_bps':'10','slippage_bps':'20'})
        self.assertFalse(value['paper_fill']['calibrated']); self.assertFalse(value['paper_fill']['provenance']['authenticated'])
        for name in p.AUTHORITY: self.assertIs(value[name], False)
        for change in ({'native_admission': True}, {'population': True}, {'source_profile': legacy.PROFILE}, {'api_key':'not-a-key'}):
            with self.subTest(change=change), self.assertRaises((p.ModelError, ValueError, TypeError)):
                p.V3Config.from_dict({**value, **change})
        for costs in ((True,'0','0'),('0.0','0','0'),('10000','0','0')):
            with self.subTest(costs=costs), self.assertRaises((p.ModelError, ValueError)):
                p.PaperFillPolicy(*costs,'literal',str(UUID(int=123)),'a'*64)
    def test_fresh_sealed_bootstrap_retains_exact_source_refs_and_eight_members(self):
        candidate, state = self.bootstrap(); value = state.to_dict()
        self.assertEqual(value['version'], p.MODEL_FORMAT)
        self.assertEqual(len(value['accounts']), 8); self.assertEqual(len(value['engine']['members']), 8)
        self.assertEqual(value['engine']['ema']['count'], 61)
        self.assertEqual(value['source']['history_sha256'], self.history.sha256)
        self.assertEqual(value['source']['close_series_sha256'], self.series.sha256)
        self.assertLess(candidate.payload_bytes, p.MAX_PAYLOAD_BYTES)
        self.assertNotIn('minutes', value['source'])
        for name in p.AUTHORITY: self.assertIs(value[name], False)
        with self.assertRaises(p.ModelError): m.V3State(value)
        with self.assertRaises(AttributeError): state.revision = 99
        state.to_dict()['reserve'] = '0'; self.assertEqual(state.to_dict()['reserve'], '200')
    def test_typed_source_and_independent_hash_reject_dictionary_and_rehashed_forgery(self):
        for history, series, expected in ((self.history.to_dict(),self.series,self.history.sha256),
                (self.history,self.series.to_dict(),self.history.sha256), (self.history,self.series,'c'*64)):
            with self.subTest(expected=expected), self.assertRaises(p.ModelError):
                m.bootstrap(self.config,history,series,expected_history_sha256=expected,
                    inputs=self.initial_inputs,ledger=self.ledger)
        changed = self.series.to_dict(); changed['closes'][0]['close'] = '101'
        forged = object.__new__(s.SampledCloseSeries); object.__setattr__(forged,'_wire',a.canonical(changed))
        with self.assertRaises(p.ModelError):
            m.bootstrap(self.config,self.history,forged,expected_history_sha256=self.history.sha256,
                inputs=self.initial_inputs,ledger=self.ledger)
        self.assertIsNone(self.ledger._current)
    def test_current_original_mark_both_phases_and_same_floor_causal_protection(self):
        _, state = self.bootstrap(); first = mark(915, price='100')
        _, state, inputs = self.protective(state,first,serial=1)
        decision, state = self.decision(state,first,inputs)
        before = state.to_dict(); self.assertEqual(before['engine']['cohort']['phase'],'evaluating')
        with self.assertRaises(p.ModelError):
            m.prepare_decision(state,first,expected_mark_sha256=first.sha256,inputs=inputs,ledger=self.ledger)
        second = subsecond_mark(first)
        _, state, second_inputs = self.protective(state,second,serial=3)
        self.assertEqual(second_inputs.math_second, inputs.math_second)
        self.assertGreater(second_inputs.event_us, inputs.event_us)
        _, state = self.decision(state,second,second_inputs)
        self.assertEqual(state.to_dict()['engine']['ema']['count'], before['engine']['ema']['count'])
        self.assertEqual(state.to_dict()['engine']['generation'], 0)
        self.assertFalse(decision.running_authority)
    def test_clock_scope_freshness_future_and_same_process_monotonic_rejections(self):
        _, state = self.bootstrap(); observation = mark(915,price='100')
        valid = inputs_for_mark(observation,serial=1)
        for clock in (replace(valid.clock,owner_id=str(UUID(int=999))),
                replace(valid.clock,acquisition_epoch=str(UUID(int=999))),
                replace(valid.clock,wall_lower_us=valid.event_us+6_000_000,wall_upper_us=valid.event_us+6_000_000,
                    monotonic_us=valid.clock.monotonic_us+6_000_000)):
            bad = replace(valid,clock=clock,event_us=clock.wall_lower_us)
            with self.subTest(clock=clock),self.assertRaises(p.ModelError):
                m.prepare_protective(state,observation,expected_mark_sha256=observation.sha256,inputs=bad,ledger=self.ledger)
        _, state, valid = self.protective(state,observation,serial=2)
        regressed = replace(valid,clock=replace(valid.clock,monotonic_us=valid.clock.monotonic_us-1))
        with self.assertRaises(p.ModelError):
            m.prepare_decision(state,observation,expected_mark_sha256=observation.sha256,inputs=regressed,ledger=self.ledger)
    def test_pause_rollover_retains_history_aborts_unscored_and_never_creates_lease(self):
        _, state = self.bootstrap(); observation = mark(915,price='100')
        _, state, inputs = self.protective(state,observation,serial=1)
        _, state = self.decision(state,observation,inputs)
        successor = replace(self.binding,acquisition_epoch=str(UUID(int=99)))
        next_inputs = new_inputs(inputs.event_us+1_000_000,1000,serial=4,epoch=successor.acquisition_epoch)
        candidate = m.prepare_epoch_rollover(state,successor,next_inputs,ledger=self.ledger)
        current, original_history = state.to_dict(), self.ledger.history
        original_epochs = set(self.ledger._acquisition_epochs)
        self.assertEqual(original_epochs, {PROCESS})
        changed = numbers.decode(candidate._wire)
        # A supported typed candidate with forged economic operations cannot
        # publish a new epoch, identity, delta or after-state before full replay.
        changed['operations'].append({'kind':'birth','id':next_inputs.ids[0],'cash':'100',
            'lineage':{'unsupported':'forged economic operation'}})
        forged = replace(candidate, _wire=numbers.encode(changed))
        with self.assertRaises(p.ModelError): self.ledger.accept(forged)
        self.assertEqual(self.ledger._current, current); self.assertEqual(self.ledger.history, original_history)
        self.assertEqual(self.ledger._acquisition_epochs, original_epochs)
        accepted = self.ledger.accept(candidate); after = accepted.to_dict()
        self.assertEqual(self.ledger._acquisition_epochs, {PROCESS, successor.acquisition_epoch})
        epoch_snapshot = set(self.ledger._acquisition_epochs); history_snapshot = self.ledger.history
        reused = new_inputs(next_inputs.event_us+100_000,500,serial=6,epoch=PROCESS)
        with self.assertRaises(p.ModelError):
            m.prepare_epoch_rollover(accepted,self.binding,reused,ledger=self.ledger)
        self.assertEqual(self.ledger._current, after); self.assertEqual(self.ledger.history, history_snapshot)
        self.assertEqual(self.ledger._acquisition_epochs, epoch_snapshot)
        self.assertIs(self.ledger.accept(candidate), accepted)
        self.assertEqual(self.ledger.history, history_snapshot); self.assertEqual(self.ledger._acquisition_epochs, epoch_snapshot)
        self.assertEqual(after['status'],'paused'); self.assertEqual(after['source']['history_sha256'],self.history.sha256)
        self.assertEqual(after['engine']['config']['initial_binding'],self.binding.to_dict())
        self.assertEqual(after['source']['current_binding'],successor.to_dict())
        self.assertTrue(after['engine']['lifecycle']['restart_required'])
        self.assertEqual(len(candidate.history['assessments']),8)
        for assessment in candidate.history['assessments']:
            self.assertEqual(assessment['status'],'aborted'); self.assertFalse(assessment['selection_eligible'])
            self.assertIsNone(assessment['fitness_float64'])
        for name in p.AUTHORITY: self.assertIs(after[name],False)
    def test_same_package_epoch_rollover_retains_warmup_and_continues_with_new_original_records(self):
        state, prior_inputs, history, series = self.to_held_positions()
        before = state.to_dict(); old_members = [row['id'] for row in before['engine']['members']]
        old_used = set(self.ledger._identities)
        successor = replace(self.binding, acquisition_epoch=str(UUID(int=99)))
        rollover_inputs = new_inputs(prior_inputs.event_us+1_000_000, 1_000_000,
            serial=110, generation=1, epoch=successor.acquisition_epoch)
        # A package upgrade needs separate archived-decoder/native-registry work;
        # this same-package process restart must not reinterpret old anchors.
        with self.assertRaises(p.ModelError):
            m.prepare_epoch_rollover(state, replace(successor, recorder_package_sha256='c'*64),
                rollover_inputs, ledger=self.ledger)
        rollover = m.prepare_epoch_rollover(state, successor, rollover_inputs, ledger=self.ledger)
        state = self.ledger.accept(rollover); paused = state.to_dict()
        for key in ('positions', 'accounts', 'reserve'):
            self.assertEqual(paused[key], before[key])
        self.assertEqual(paused['source']['history_sha256'], history.sha256)
        self.assertEqual(paused['source']['bars'], before['source']['bars'])
        self.assertEqual(paused['engine']['ema'], before['engine']['ema'])
        self.assertTrue(old_used <= self.ledger._identities)
        self.assertEqual(paused['engine']['lifecycle']['last_monotonic_us'], 1_000_000)
        self.assertEqual(len(rollover.history['assessments']), 8)
        self.assertTrue(all(row['status']=='aborted' and not row['selection_eligible']
            and row['fitness_float64'] is None for row in rollover.history['assessments']))

        def acquired(index):
            return subsecond_mark(mark(index, price='101'), delta=0,
                epoch=successor.acquisition_epoch, mono_us=2_000_000+(index-962)*60_000_000,
                identity=600_000+(index-962)*10, sequence=1000+index-962)
        fresh = acquired(962); fresh_inputs = inputs_for_mark(fresh, serial=111, generation=1)
        old_mark = mark(961, price='100')
        resume_inputs = inputs_for_mark(fresh, serial=111, generation=1, offset=0)
        state = self.ledger.accept(m.prepare_control(state, 'resume', resume_inputs, ledger=self.ledger))
        with self.assertRaises(p.ModelError):
            m.prepare_protective(state, old_mark, expected_mark_sha256=old_mark.sha256,
                inputs=fresh_inputs, ledger=self.ledger)
        _, state, fresh_inputs = self.protective(state, fresh, serial=111, generation=1)
        later = acquired(963); _, state, inputs = self.protective(state, later, serial=112, generation=1)
        restart, state = self.decision(state, later, inputs)
        self.assertEqual(state.to_dict()['engine']['generation'], 1)
        self.assertEqual(state.to_dict()['engine']['lifecycle']['search_epoch'], 1)
        self.assertEqual(len(restart.history['closed_positions']), 8)
        self.assertEqual([row['genome']['parent_ids'] for row in restart.history['birth_members']],
            [[identity] for identity in old_members])
        self.assertIsNone(restart.history['selection'])
        self.assertEqual(state.to_dict()['source']['history_sha256'], history.sha256)

        overlap = tuple(mark(index, price='120') for index in range(945, 960))
        # The first two minutes were captured before the explicit rollover;
        # their original process epoch and bytes stay unchanged in the archive.
        preceding = tuple(mark(index, price='100') for index in range(960, 962))
        following = tuple(acquired(index) for index in range(962, 975))
        next_history = s.derive_sampled_history(seal(overlap+preceding+following,
            start=END+1800, end=END+3600, seal_id=str(UUID(int=100_110))),
            previous=history, expected_previous_sha256=history.sha256)
        next_series = s.derive_close_series(next_history, expected_history_sha256=next_history.sha256)
        archived = next_history.to_dict()['minutes']
        self.assertEqual(archived[:900], history.to_dict()['minutes'][15:])
        self.assertEqual([row['acquisition_epoch'] for row in archived[-15:-13]], [PROCESS, PROCESS])
        self.assertTrue(all(row['acquisition_epoch']==successor.acquisition_epoch for row in archived[-13:]))
        final_mark = acquired(975); _, state, inputs = self.protective(state, final_mark, serial=113, generation=1)
        continued, state = self.decision(state, final_mark, inputs, history=next_history,
            series=next_series, expected_history_sha256=next_history.sha256)
        after = state.to_dict()
        self.assertEqual(after['status'], 'running'); self.assertEqual(after['engine']['generation'], 1)
        self.assertEqual(after['engine']['ema']['count'], before['engine']['ema']['count']+1)
        self.assertEqual(after['source']['quote_sequence'], 1013)
        self.assertEqual(after['source']['history_sha256'], next_history.sha256)
        self.assertEqual(after['source']['current_binding'], successor.to_dict())
        self.assertEqual(after['engine']['config']['initial_binding'], self.binding.to_dict())
        self.assertTrue(old_used <= self.ledger._identities)
        self.assertFalse(continued.history['assessments']); self.assertFalse(continued.running_authority)
    def test_stop_preserves_source_and_never_fetches_or_fakes_liquidation(self):
        _, state = self.bootstrap()
        controls = new_inputs(self.initial_inputs.event_us+500_000,self.initial_inputs.clock.monotonic_us+500_000,serial=5)
        stop = m.prepare_control(state,'stop',controls,ledger=self.ledger)
        after = self.ledger.accept(stop).to_dict()
        self.assertEqual(after['status'],'stopped'); self.assertEqual(after['source'],state.to_dict()['source'])
        self.assertFalse(any(operation['kind'] in {'open','close'} for operation in stop.operations))
        self.assertFalse(after['running_authority'])
        for row in stop.history['assessments']:
            self.assertIsNone(row['window_started_us']); self.assertIsNone(row['window_ends_us'])
            self.assertEqual(row['finalized_event_us'], controls.event_us)
        self.assertTrue(all(row['event_us']==controls.event_us for row in stop.transition['events']))
    def test_held_stop_preserves_exact_positions_and_cash_with_eight_unscored_assessments(self):
        state,inputs,_,_=self.to_held_positions(); before=state.to_dict()
        # Source is deliberately stale by Stop time; no new quote is requested.
        controls=new_inputs(inputs.event_us+60_000_000,inputs.clock.monotonic_us+60_000_000,serial=85,generation=1)
        stop=m.prepare_control(state,'stop',controls,ledger=self.ledger)
        after=self.ledger.accept(stop).to_dict()
        self.assertEqual(after['status'],'stopped')
        for key in ('accounts','positions','reserve','source'):self.assertEqual(after[key],before[key])
        self.assertEqual(len(stop.history['assessments']),8)
        self.assertFalse(any(op['kind'] in {'close','open'} for op in stop.operations))
        for row in stop.history['assessments']:
            self.assertEqual(row['status'],'aborted');self.assertFalse(row['selection_eligible'])
            self.assertIsNone(row['roi_float64']);self.assertIsNone(row['fitness_float64'])
        with self.assertRaises(p.ModelError):m.prepare_control(stop.state,'resume',controls,ledger=self.ledger)
    def test_exact_risk_trip_ack_recovery_and_fresh_restart_clone(self):
        self.config=replace(self.config,account_loss_bps='49')
        state,_,history,series=self.to_held_positions(); old_ids=[row['id'] for row in state.to_dict()['engine']['members']]
        adverse=mark(962,price='97.5');risk,state,risk_inputs=self.protective(state,adverse,serial=90,generation=1)
        data=state.to_dict();self.assertEqual(data['status'],'risk_halted');self.assertEqual(len(data['positions']),8)
        trip=data['engine']['lifecycle']['risk']['trip_id'];self.assertTrue(self.ledger.used(trip))
        self.assertIn(trip,risk.history['allocated_ids'])
        self.assertEqual(data['engine']['lifecycle']['risk']['observed_us'], risk_inputs.event_us)
        self.assertEqual(data['engine']['lifecycle']['risk']['tripped_us'], risk_inputs.event_us)
        self.assertTrue(all(row['event_us']==risk_inputs.event_us for row in risk.transition['events']))
        self.assertEqual(len(risk.history['assessments']),8)
        for row in risk.history['assessments']:self.assertFalse(row['selection_eligible'])
        recovery_mark=mark(963,price='101');_,state,inputs=self.protective(state,recovery_mark,serial=91,generation=1)
        history_args={'history':history,'series':series,'expected_history_sha256':history.sha256}
        for bad_trip in (None,str(UUID(int=999))):
            with self.subTest(trip=bad_trip),self.assertRaises(p.ModelError):
                m.prepare_control(state,'recover',inputs,ledger=self.ledger,mark=recovery_mark,
                    expected_mark_sha256=recovery_mark.sha256,trip_id=bad_trip,**history_args)
        recovered=m.prepare_control(state,'recover',inputs,ledger=self.ledger,mark=recovery_mark,
            expected_mark_sha256=recovery_mark.sha256,trip_id=trip,**history_args)
        state=self.ledger.accept(recovered);self.assertEqual(state.to_dict()['status'],'running')
        self.assertEqual(state.to_dict()['engine']['lifecycle']['risk']['last_recovered_us'], inputs.event_us)
        later=mark(964,price='101');_,state,inputs=self.protective(state,later,serial=92,generation=1)
        restart,state=self.decision(state,later,inputs)
        self.assertEqual(state.to_dict()['engine']['generation'],1)
        self.assertEqual(state.to_dict()['engine']['lifecycle']['search_epoch'],1)
        self.assertEqual(len(restart.history['birth_members']),8)
        self.assertEqual(len(restart.history['closed_positions']),8)
        self.assertIsNone(restart.history['selection'])
        self.assertEqual([row['genome']['parent_ids'] for row in restart.history['birth_members']],[[identity] for identity in old_ids])
        self.assertTrue(all(self.ledger.used(identity) for identity in old_ids))
        self.assertFalse(state.running_authority)
    def test_early_terminal_cash_frozen_until_common_deadline_then_full_eight_selection(self):
        self.config=replace(self.config,account_loss_bps='9000')
        state,_,history,_=self.to_held_positions()
        original_ids=[member['id'] for member in state.to_dict()['engine']['members']]
        adverse=mark(962,price='20');terminal,state,terminal_inputs=self.protective(state,adverse,serial=95,generation=1)
        data=state.to_dict();self.assertEqual(data['status'],'running')
        self.assertEqual(len(data['positions']),0);self.assertEqual(len(terminal.history['closed_positions']),8)
        self.assertEqual(len(terminal.history['retired_accounts']),8)
        self.assertEqual(len(terminal.history['assessments']),0);self.assertIsNone(terminal.history['selection'])
        self.assertEqual(data['engine']['generation'],0)
        self.assertTrue(all(account['cash']=='0' and account['retired'] for account in data['accounts']))
        self.assertTrue(all(member['terminal'] is not None for member in data['engine']['members']))
        frozen_metrics=[member['assessment'] for member in data['engine']['members']]
        self.assertTrue(all(row['captured_event_us']==terminal_inputs.event_us for row in frozen_metrics))
        original_window_us=data['source']['cohort_start_us']
        overlap=tuple(mark(index,price='120') for index in range(945,960))
        new_minutes=tuple(mark(index,price='100' if index<962 else '20') for index in range(960,975))
        next_history=s.derive_sampled_history(seal(overlap+new_minutes,start=END+1800,end=END+3600,
            seal_id=str(UUID(int=100_004))),previous=history,expected_previous_sha256=history.sha256)
        next_series=s.derive_close_series(next_history,expected_history_sha256=next_history.sha256)
        fresh=mark(975,price='20');_,state,inputs=self.protective(state,fresh,serial=96,generation=1)
        completed,state=self.decision(state,fresh,inputs,history=next_history,series=next_series,
            expected_history_sha256=next_history.sha256)
        self.assertEqual(state.to_dict()['engine']['generation'],1)
        self.assertEqual(len(completed.history['assessments']),8)
        self.assertEqual([row['probe_id'] for row in completed.history['assessments']],original_ids)
        for row,metrics in zip(completed.history['assessments'],frozen_metrics):
            self.assertTrue(row['cohort_complete']);self.assertTrue(row['selection_eligible'])
            self.assertTrue(row['early_terminal_frozen']);self.assertEqual(row['metrics'],metrics)
            self.assertEqual(row['finalized_event_us'], inputs.event_us+100_000)
            self.assertGreater(row['finalized_event_us'], row['metrics']['captured_event_us'])
            self.assertEqual(row['window_started_us'], original_window_us)
            self.assertEqual(row['window_ends_us'], original_window_us+3_600_000_000)
        self.assertTrue(all(row['event_us']==inputs.event_us+100_000 for row in completed.transition['events']))
        self.assertEqual(len(completed.history['selection']['offspring']),8)
        self.assertTrue(all(self.ledger.used(identity) for identity in original_ids))
    def test_coarse_due_cannot_finish_one_hour_early_before_fresh_same_floor_original_mark(self):
        state, _, history, _ = self.to_held_positions(); before = state.to_dict()
        start_us = before['source']['cohort_start_us']; end_us = start_us+3_600_000_000
        original_members = [row['id'] for row in before['engine']['members']]
        overlap = tuple(mark(index, price='120') for index in range(945, 960))
        added = tuple(mark(index, price='100') for index in range(960, 975))
        next_history = s.derive_sampled_history(seal(overlap+added, start=END+1800,
            end=END+3600, seal_id=str(UUID(int=100_115))), previous=history,
            expected_previous_sha256=history.sha256)
        next_series = s.derive_close_series(next_history, expected_history_sha256=next_history.sha256)
        early = mark(975, price='100')
        early_inputs = inputs_for_mark(early, serial=115, generation=1, offset=0)
        self.assertEqual(early_inputs.event_us, end_us-100_000)
        # Both gates see the same original coarse second, but the logical
        # protected-action hour is not complete yet. No scores may be told.
        _, _, cohort = state._fork(); self.assertTrue(cohort.due(early_inputs.math_second))
        protected = m.prepare_protective(state, early, expected_mark_sha256=early.sha256,
            inputs=early_inputs, ledger=self.ledger); state = self.ledger.accept(protected)
        pending, state = self.decision(state, early, early_inputs, history=next_history,
            series=next_series, expected_history_sha256=next_history.sha256)
        held = state.to_dict()
        self.assertEqual(held['engine']['generation'], before['engine']['generation'])
        self.assertEqual([row['id'] for row in held['engine']['members']], original_members)
        self.assertEqual(held['engine']['cohort']['phase'], 'evaluating')
        self.assertEqual(held['engine']['optimizer'], before['engine']['optimizer'])
        self.assertEqual(pending.history['assessments'], []); self.assertIsNone(pending.history['selection'])
        self.assertFalse(any(op['kind']=='birth' for op in pending.operations))
        self.assertEqual(pending.transition['evidence']['inputs']['provider']['mark_sha256'], early.sha256)

        later = subsecond_mark(early, delta=200_000, identity=700_000)
        later_inputs = inputs_for_mark(later, serial=116, generation=1, offset=0)
        self.assertEqual(later_inputs.math_second, early_inputs.math_second)
        self.assertEqual(later_inputs.event_us, end_us+100_000)
        protected = m.prepare_protective(state, later, expected_mark_sha256=later.sha256,
            inputs=later_inputs, ledger=self.ledger); state = self.ledger.accept(protected)
        completed, state = self.decision(state, later, later_inputs)
        self.assertEqual(state.to_dict()['engine']['generation'], before['engine']['generation']+1)
        self.assertEqual([row['probe_id'] for row in completed.history['assessments']], original_members)
        self.assertEqual(len(completed.history['assessments']), 8)
        self.assertTrue(all(row['selection_eligible'] and row['cohort_complete']
            and row['window_started_us']==start_us and row['window_ends_us']==end_us
            for row in completed.history['assessments']))
        self.assertEqual(len(completed.history['selection']['offspring']), 8)
        self.assertEqual(completed.transition['evidence']['inputs']['provider']['mark_sha256'], later.sha256)
        self.assertEqual(sum(len(row['assessments']) for row in self.ledger.history), 8)
    def test_candidate_witness_is_immutable_and_original_replay_has_no_current_head_authority(self):
        initial,state=self.bootstrap()
        with self.assertRaises(TypeError):initial._witness['inputs']=self.initial_inputs
        observation=mark(915,price='100');_,current,_=self.protective(state,observation,serial=10)
        history_before=self.ledger.history
        self.assertIs(self.ledger.accept(initial),state)
        self.assertEqual(self.ledger.history,history_before)
        with self.assertRaises(p.ModelError):
            m.prepare_protective(state,mark(916,price='100'),expected_mark_sha256=mark(916,price='100').sha256,
                inputs=inputs_for_mark(mark(916,price='100'),serial=11),ledger=self.ledger)
        self.assertEqual(self.ledger._owned_current.to_dict(),current.to_dict())
    def test_unused_input_id_name_clock_and_seed_aliases_refuse(self):
        for changed in ({'ids':self.initial_inputs.ids[:-1]+(True,)},
                {'ids':self.initial_inputs.ids+(self.initial_inputs.ids[0],)},
                {'names':self.initial_inputs.names+((True,'unused'),)},
                {'names':self.initial_inputs.names+((0,' unused'),)},
                {'event_us':True}, {'event_us':float(self.initial_inputs.event_us)}):
            with self.subTest(changed=changed),self.assertRaises((p.ModelError,a.AcquisitionError,ValueError,TypeError)):
                replace(self.initial_inputs,**changed)
        for seed in (True,0,'00',str(2**64)):
            with self.subTest(seed=seed),self.assertRaises((p.ModelError,ValueError)):
                replace(self.config,search_seed=seed)
        maximum=replace(self.config,search_seed=str(2**64-1))
        self.assertEqual(p.V3Config.from_dict(maximum.to_dict()),maximum)
    def test_original_mark_hash_package_principal_and_body_changes_refuse_without_install(self):
        _,state=self.bootstrap();original=mark(915,price='100');inputs=inputs_for_mark(original,serial=1)
        before=state.to_dict();history_before=self.ledger.history
        for expected in ('c'*64,None):
            with self.subTest(expected=expected),self.assertRaises(p.ModelError):
                m.prepare_protective(state,original,expected_mark_sha256=expected,inputs=inputs,ledger=self.ledger)
        for change in ({'recorder_package_sha256':'c'*64},
                {'issuer_principal_binding_id':str(UUID(int=999))}):
            forged=mark(915,price='100',reference_changes=change)
            with self.subTest(change=change),self.assertRaises(p.ModelError):
                m.prepare_protective(state,forged,expected_mark_sha256=forged.sha256,inputs=inputs,ledger=self.ledger)
        self.assertEqual(self.ledger._current,before);self.assertEqual(self.ledger.history,history_before)
    def test_missing_completed_period_is_refused_and_protection_remains_available(self):
        _,state=self.bootstrap();observation=mark(930,price='100')
        _,state,inputs=self.protective(state,observation,serial=10,generation=1)
        before=state.to_dict();history_before=self.ledger.history
        with self.assertRaises(p.ModelError):
            m.prepare_decision(state,observation,expected_mark_sha256=observation.sha256,inputs=inputs,ledger=self.ledger)
        self.assertEqual(self.ledger._current,before);self.assertEqual(self.ledger.history,history_before)
        newer=mark(931,price='100');_,state,_=self.protective(state,newer,serial=11,generation=1)
        self.assertGreater(state.revision,before['revision'])
        self.assertEqual(state.to_dict()['engine']['generation'],0)
    def test_rehashed_history_package_change_refuses_with_original_overlap_and_prior_unchanged(self):
        _, state = self.bootstrap(); observation = mark(930, price='100')
        _, state, inputs = self.protective(state, observation, serial=114, generation=1)
        next_minutes = self.marks[-15:]+tuple(mark(index, price='100') for index in range(915, 930))
        following = s.derive_sampled_history(seal(next_minutes, start=END-900, end=END+900,
            seal_id=str(UUID(int=100_114))), previous=self.history,
            expected_previous_sha256=self.history.sha256)
        original_series = s.derive_close_series(following, expected_history_sha256=following.sha256)
        # A producer-valid same-package baseline makes the remaining binding
        # refusal independent of overlap/range, source age and typed grammar.
        expected = m.prepare_decision(state, observation, expected_mark_sha256=observation.sha256,
            inputs=inputs, ledger=self.ledger, history=following, series=original_series,
            expected_history_sha256=following.sha256)
        changed = following.to_dict(); changed['recorder_package_sha256'] = 'c'*64
        forged = object.__new__(s.SampledHistory); object.__setattr__(forged, '_wire', a.canonical(changed))
        forged_series = s.derive_close_series(forged, expected_history_sha256=forged.sha256)
        self.assertEqual(forged.to_dict()['minutes'][:900], self.history.to_dict()['minutes'][15:])
        self.assertEqual(forged.to_dict()['previous_history_sha256'], self.history.sha256)
        self.assertEqual(forged.to_dict()['range'], following.to_dict()['range'])
        self.assertEqual(forged_series.to_dict()['recorder_package_sha256'], 'c'*64)
        before = state.to_dict(); history_before = self.ledger.history
        with self.assertRaises(p.ModelError):
            m.prepare_decision(state, observation, expected_mark_sha256=observation.sha256,
                inputs=inputs, ledger=self.ledger, history=forged, series=forged_series,
                expected_history_sha256=forged.sha256)
        self.assertEqual(self.ledger._current, before); self.assertEqual(self.ledger.history, history_before)
        self.assertIs(self.ledger._history_witness, self.history)
        self.assertEqual(self.ledger.accept(expected).to_dict()['source']['history_sha256'], following.sha256)
    def test_legacy_models_configs_and_dictionary_states_cannot_be_cast(self):
        _,state=self.bootstrap();observation=mark(915,price='100');inputs=inputs_for_mark(observation,serial=1)
        for old in (state.to_dict(),object(),legacy.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=MARKET)):
            with self.subTest(kind=type(old).__name__),self.assertRaises(p.ModelError):
                m.prepare_protective(old,observation,expected_mark_sha256=observation.sha256,inputs=inputs,ledger=self.ledger)
        with self.assertRaises(p.ModelError):
            m.bootstrap(legacy.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',source_epoch=MARKET),self.history,self.series,
                expected_history_sha256=self.history.sha256,inputs=self.initial_inputs,ledger=m.OfflineLedger(OWNER,RUN))
    def test_original_economic_identity_reuse_refuses_without_publishing_partial_history(self):
        self.config=replace(self.config,account_loss_bps='49')
        state,_,_,_=self.to_held_positions();used=self.initial_inputs.ids[0]
        current=self.ledger._current;history_before=self.ledger.history
        self.assertTrue(self.ledger.used(used))
        adverse=mark(962,price='97.5');inputs=inputs_for_mark(adverse,serial=97,generation=1)
        reused=replace(inputs,ids=(used,)+inputs.ids[1:])
        with self.assertRaises(p.ModelError):
            m.prepare_protective(state,adverse,expected_mark_sha256=adverse.sha256,inputs=reused,ledger=self.ledger)
        self.assertEqual(self.ledger._current,current)
        self.assertEqual(self.ledger.history,history_before)
        self.assertFalse(self.ledger._current['engine']['lifecycle']['risk']['active'])
    def test_normalized_close_math_matches_original_two_full_cohorts_and_actual_mutation(self):
        new_candidate, new_state = self.bootstrap()
        old_config = legacy.GAConfig('genetic_algorithm',OWNER,RUN,asset='SOL/USD',
            execution=DecimalExecutionConfig('25','10','20'),source_epoch=MARKET)
        old_ledger = legacy.SimulationLedger(OWNER,RUN)
        old_history = legacy.source.build_history(raw_minutes(end=END,close='100',wall=END+5,mono=54_905),
            prior_bars=[],seed=True,wall_us=(END+5)*1_000_000,monotonic_us=54_905_000_000)
        old_candidate = legacy.bootstrap(old_config,old_history,old_inputs(self.initial_inputs),ledger=old_ledger)
        old_state = old_ledger.accept(old_candidate)
        self.assertEqual(new_state.to_dict()['engine']['members'],old_state.to_dict()['engine']['members'])
        self.assertEqual(new_state.to_dict()['engine']['ema'],old_state.to_dict()['engine']['ema'])
        history = self.history; all_marks = list(self.marks); serial = 10
        trajectory = ('100','80','120','100','120','80','120','100','120','80')
        for bar in range(9):
            if bar:
                start_index = 915+(bar-1)*15
                added = tuple(mark(index,price=trajectory[bar-1]) for index in range(start_index,start_index+15))
                all_marks.extend(added)
                end = END+bar*900
                frozen = seal(tuple(all_marks[-30:]),start=end-1800,end=end,
                    seal_id=str(UUID(int=100_000+bar)))
                history = s.derive_sampled_history(frozen,previous=history,expected_previous_sha256=history.sha256)
                series = s.derive_close_series(history,expected_history_sha256=history.sha256)
            for later in (False,True):
                index = 915+bar*15+int(later); observation = mark(index,price=trajectory[bar])
                generation = new_state.to_dict()['engine']['generation']+1
                inputs = inputs_for_mark(observation,serial=serial,generation=generation);serial += 1
                new_protect = m.prepare_protective(new_state,observation,expected_mark_sha256=observation.sha256,inputs=inputs,ledger=self.ledger)
                new_state = self.ledger.accept(new_protect)
                at = inputs.math_second; mono = inputs.clock.monotonic_us/1_000_000
                frame = legacy.source.make_frame(raw_capture(price=trajectory[bar],block=348004023+index,
                    source_second=at-2,wall=at-1,mono=mono-1),prior_source=old_state.to_dict()['source'],
                    epoch=MARKET,wall_now=at,monotonic_now=mono)
                old_protect = legacy.prepare_protective(old_state,frame,old_inputs(inputs),ledger=old_ledger)
                old_state = old_ledger.accept(old_protect)
                self.assertEqual(new_protect.operations,old_protect.operations)
                new_history_args = {}; old_next_history = None
                if bar and not later:
                    new_history_args = {'history':history,'series':series,'expected_history_sha256':history.sha256}
                    old_next_history = legacy.source.build_history(raw_minutes(end=END+bar*900,count=30,
                        closes=[trajectory[bar-2] if bar>1 else '100']*15+[trajectory[bar-1]]*15,
                        wall=at,mono=mono),prior_bars=old_state.to_dict()['source']['bars'],seed=False,
                        wall_us=at*1_000_000,monotonic_us=round(mono*1_000_000))
                # Use one declared source/action clock for the paired old math;
                # separate current bounds remain independently enforced above.
                new_decision = m.prepare_decision(new_state,observation,expected_mark_sha256=observation.sha256,
                    inputs=inputs,ledger=self.ledger,**new_history_args)
                new_state = self.ledger.accept(new_decision)
                old_decision = legacy.prepare_decision(old_state,frame,old_next_history,old_inputs(inputs),ledger=old_ledger)
                old_state = old_ledger.accept(old_decision)
                self.assertEqual(new_decision.operations,old_decision.operations)
                self.assertEqual(new_decision.history['selection'],old_decision.history['selection'])
                for field in ('reserve','accounts','positions'):
                    self.assertEqual(new_state.to_dict()[field],old_state.to_dict()[field])
                for field in ('generation','members','ema','optimizer'):
                    left,right=new_state.to_dict()['engine'][field],old_state.to_dict()['engine'][field]
                    if field=='members':
                        # New exact signal-us/assessment provenance is deliberate;
                        # compare all unchanged phenotype/economic ranking fields.
                        for member,prior in zip(left,right):
                            for name in ('id','genome','peak_equity','max_drawdown','num_trades','terminal'):
                                self.assertEqual(member[name],prior[name])
                    else:self.assertEqual(left,right)
                self.assertLess(new_decision.payload_bytes,p.MAX_PAYLOAD_BYTES)
        self.assertEqual(new_state.to_dict()['engine']['generation'],2)
        assessments = [item for row in self.ledger.history for item in row['assessments'] if item['status']=='completed']
        self.assertEqual(len(assessments),16)
        for item in assessments:
            self.assertFalse(item['authority']['profitability_authority'])
            self.assertTrue(item['selection_eligible']);self.assertTrue(item['cohort_complete'])
        self.assertEqual(new_state.to_dict()['engine']['config']['mutation_policy']['version'],'ema-period-triangular-integer-v1')


if __name__ == '__main__': unittest.main()
