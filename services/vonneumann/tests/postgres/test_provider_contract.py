"""Raw-RPC v5 source binding with actual current-clock, isolated PostgreSQL.

Provider documents below are fabricated local JSON. The contract validates
worker-parsed records/manifests, not provider authenticity or raw derivation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import time
from uuid import uuid4

from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import identity, literal
from tests.postgres.test_decimal_lineage_contract import document
from tests.security_support import deny_network
from tests.test_birdeye_candles import row, body
from vonneumann.core.decision_inputs import DecisionInputs
from vonneumann.core.exact_lifecycle import ExactLifecycleConfig
from vonneumann.core import provider_lifecycle as core
from vonneumann.market import provider_contract as source
from vonneumann.market.exact_records import parse_candle_records, parse_price_record
from vonneumann.market.provider_evidence import ProviderDocument
from vonneumann.market.feed import QuoteEvidence
with deny_network():
    from vonneumann.market.jupiter_feed import PriceCapture


def decision_inputs(now=None, mono=None, *, second=None):
    now = time.time() if now is None else now
    mono = time.monotonic() if mono is None else mono
    wall = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=source.clock_us(now, upper=True))
    return DecisionInputs(datetime.fromtimestamp(int(now) if second is None else second, timezone.utc),
        wall, mono, tuple(identity() for _ in range(9)), tuple((0, f'Provider-{i}') for i in range(8)))


def seed_history(now, mono):
    end = int((now - 5) // 900) * 900
    start = end - 915 * 60
    params = {'address': source.MINT, 'type': '1m', 'mode': 'range', 'time_from': start,
        'time_to': end, 'currency': 'usd', 'chart_type': 'price', 'ui_amount_mode': 'raw', 'padding': 'false'}
    # The last seeded bar falls below the previous flat level, allowing the
    # first subsequent completed rising bar to produce real crossover signals.
    rows = [row(stamp, o=100, h=102, l=79, c=80 if stamp >= end-900 else 100)
            for stamp in range(start, end, 60)]
    raw = json.dumps(body(*rows), separators=(',', ':')).encode()
    doc = ProviderDocument.capture('birdeye-ohlcv-v3', params, raw, now-.01, mono-.01)
    records = parse_candle_records(doc, asset='SOL/USDC', mint=source.MINT)
    return source.build_history(records, prior_bars=[], seed=True,
        wall_us=source.clock_us(now, upper=True), monotonic_us=source.clock_us(mono, upper=True))


def quote_frame(state, now, mono, *, block=123456789, price='100', estimated=None):
    stamp = int(now)-1 if estimated is None else estimated
    raw = ('{"'+source.MINT+'":{"usdPrice":'+price+',"blockId":'+str(block)+',"decimals":9}}').encode()
    doc = ProviderDocument.capture('jupiter-price-v3', {'ids': source.MINT}, raw, now-1.1, mono-1.1)
    record = parse_price_record(doc, asset='SOL/USDC', mint=source.MINT)
    capture = PriceCapture(record, stamp, QuoteEvidence(block, doc.received_at,
        doc.received_monotonic, source_age_at_receipt=max(0, doc.received_at-stamp)))
    return source.make_frame(capture, prior_source=state.to_dict()['source'],
        epoch=state.to_dict()['source']['epoch'], wall_now=now, monotonic_now=mono)


class ProviderContractTests(PostgresContractTestCase):
    def setUp(self):
        self.owner, self.run, self.worker = identity(), identity(), identity()
        self.db.sql(f'INSERT INTO auth.users(id) VALUES ({literal(self.owner)});')

    def configuration(self, strategy='genetic_algorithm'):
        return core.ProviderLifecycleConfig(ExactLifecycleConfig(strategy, self.owner, self.run,
            asset='SOL/USD'), identity())

    def create(self, config, *, altered=None):
        return self.db.sql('SELECT vn_durability.create_run('+','.join((literal(self.owner),
            literal(self.run), literal(self.worker), literal(identity()),
            document(config.run_configuration() if altered is None else altered), literal(config.initial_cash),'120'))+');',
            role='service_role', check=altered is None)

    def payload(self, candidate):
        return {'version': 5, 'operations': candidate.operations, 'transition': candidate.transition}

    def sql(self, payload, command_id=None):
        before=payload['transition']['before']
        revision=1 if before is None else before['revision']
        return 'SELECT vn_durability.commit_command('+','.join((literal(self.owner),literal(self.run),
            literal(self.worker),'1',str(revision),literal(command_id or identity()),document(payload)))+');'

    def snapshot(self):
        tables=('runs','accounts','positions','commands','account_lineage','account_parents',
                'distributions','distribution_sources','lineage_sources','outbox_events','outbox_progress')
        # Aggregate digests keep diagnostics bounded even for retained source documents.
        return self.db.scalar('SELECT jsonb_build_array('+','.join(
            "(SELECT md5(coalesce(string_agg(to_jsonb(t)::text,',' ORDER BY to_jsonb(t)::text),'')) FROM vn_durability."+table+
            " t WHERE "+('id' if table=='runs' else 'run_id')+'='+literal(self.run)+')' for table in tables)+');')

    def prepare_bootstrap(self, strategy='genetic_algorithm'):
        config=self.configuration(strategy); self.create(config)
        now,mono=time.time(),time.monotonic()
        candidate=core.bootstrap(config,seed_history(now,mono),decision_inputs(now,mono))
        return config,candidate

    def install_bootstrap(self, strategy='genetic_algorithm'):
        config,candidate=self.prepare_bootstrap(strategy)
        self.db.sql(self.sql(self.payload(candidate)),role='service_role')
        return config,candidate

    def assert_rejected(self,payload,code=None):
        before=self.snapshot()
        result=self.db.sql(self.sql(payload),role='service_role',check=False)
        self.assertNotEqual(result.returncode,0,'raw altered source command unexpectedly committed')
        if code: self.assertIn(code,result.stderr)
        self.assertEqual(self.snapshot(),before,'rejected command changed economic/source/journal state')

    def test_real_seed_protect_decide_all_four_solvers_preserves_v5_and_outbox(self):
        for strategy in ('genetic_algorithm','differential_evolution','particle_swarm','cma_es'):
            with self.subTest(strategy=strategy):
                self.run,self.worker=identity(),identity()
                config,boot=self.install_bootstrap(strategy)
                now,mono=time.time(),time.monotonic()
                frame=quote_frame(boot.state,now,mono)
                protective=core.prepare_protective(boot.state,frame,decision_inputs(now,mono))
                self.db.sql(self.sql(self.payload(protective)),role='service_role')
                now,mono=time.time(),time.monotonic()
                decision=core.prepare_decision(protective.state,frame,None,
                    decision_inputs(now,mono,second=frame['decision_second']))
                self.db.sql(self.sql(self.payload(decision)),role='service_role')
                actual=json.loads(self.db.scalar('SELECT engine_state FROM vn_durability.runs WHERE id='+literal(self.run)+';'))
                self.assertEqual(actual,decision.state.to_dict())
                self.assertEqual(actual['source']['quote_sequence'],1)
                self.assertEqual(actual['engine']['cohort']['phase'],'evaluating')
                self.assertEqual(actual['engine']['ema']['count'],61)
                self.assertEqual(self.db.scalar('SELECT command_version FROM vn_durability.runs WHERE id='+literal(self.run)+';'),'5')
                self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_durability.outbox_events WHERE run_id='+literal(self.run)+';'),'9')
                read=json.loads(self.db.scalar('SELECT vn_durability.read_outbox('+','.join((literal(self.owner),literal(self.run),'4','50','65536'))+');',role='service_role'))
                self.assertEqual(len(read['events']),9)
                self.assertEqual(self.db.scalar("SELECT bool_and(request->'payload'->'version'='5'::jsonb AND request->'payload'->'transition'->'after' ? 'source') FROM vn_durability.commands WHERE kind='batch' AND run_id="+literal(self.run)+';'),'t')

    def test_config_requires_provider_policy_exact_asset_epoch_and_version(self):
        config=self.configuration();base=config.run_configuration()
        mutations=[lambda p:p.pop('source_policy'),lambda p:p['source_policy'].update(epoch=identity().upper()),
            lambda p:p['source_policy'].update(denomination='USDC'),lambda p:p['source_policy'].update(max_source_age_us=30000001),
            lambda p:p['rehearsal'].update(asset='SOL/USDC'),lambda p:p.update(durability_contract_version=4)]
        for mutate in mutations:
            altered=deepcopy(base);mutate(altered)
            self.assertNotEqual(self.create(config,altered=altered).returncode,0)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM vn_durability.runs WHERE id='+literal(self.run)+';'),'0')

    def test_raw_seed_manifest_history_and_fingerprint_tampering_is_atomic(self):
        _,candidate=self.prepare_bootstrap();base=self.payload(candidate)
        mutations=[
            lambda p:p['transition']['evidence'].pop('source'),
            lambda p:p['transition']['evidence']['source'].update(history=None),
            lambda p:p['transition']['evidence']['source']['history'].update(unscaled=False),
            lambda p:p['transition']['evidence']['source']['history']['minutes'][0].__setitem__(1,'100.000000000000000001'),
            lambda p:p['transition']['evidence']['source']['history']['minutes'][0].__setitem__(1,100),
            lambda p:p['transition']['evidence']['source']['history']['minutes'][1].__setitem__(0,p['transition']['evidence']['source']['history']['minutes'][0][0]),
            lambda p:p['transition']['evidence']['source']['history']['minutes'][0].__setitem__(2,1),
            lambda p:p['transition']['evidence']['source']['history']['documents'][0]['request']['parameters'].update(chart_type='market_cap'),
            lambda p:p['transition']['evidence']['source']['history']['documents'][0].update(response_sha256='G'*64),
            lambda p:p['transition']['evidence']['source']['history']['documents'][0].update(received_wall_us=True),
            lambda p:p['transition']['after']['source'].update(epoch=identity()),
            lambda p:p['transition']['after']['source']['bars'][0].__setitem__(2,'f'*64),
            lambda p:p['transition']['after']['engine']['ema']['values'].pop('2'),
            lambda p:p['transition']['evidence']['source'].update(wall_us=p['transition']['evidence']['source']['wall_us']+1),
        ]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                payload=deepcopy(base);mutate(payload);self.assert_rejected(payload)

    def test_raw_protection_quote_sequence_price_clock_and_epoch_binding(self):
        _,boot=self.install_bootstrap();now,mono=time.time(),time.monotonic()
        frame=quote_frame(boot.state,now,mono);candidate=core.prepare_protective(boot.state,frame,decision_inputs(now,mono))
        base=self.payload(candidate)
        mutations=[lambda p:p['transition']['evidence']['source']['frame']['quote'].update(price='100.000000000000000001'),
            lambda p:p['transition']['evidence']['source']['frame'].update(sequence=2),
            lambda p:p['transition']['evidence']['source']['frame']['quote'].update(block_ref=-1),
            lambda p:p['transition']['evidence']['source']['frame']['quote'].update(estimated_source_second=int(time.time())-31),
            lambda p:p['transition']['evidence']['source']['frame']['quote'].update(source_age_floor_us=30000001),
            lambda p:p['transition']['evidence']['source']['frame']['quote']['document']['request']['parameters'].update(ids='EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'),
            lambda p:p['transition']['after']['source'].update(quote_sequence=0),
            lambda p:p['transition']['before'].pop('source'),
            lambda p:p.update(version=4),
            lambda p:p['transition']['after']['engine']['ema']['closes'].__setitem__(0,'99'),
        ]
        for index,mutate in enumerate(mutations):
            with self.subTest(index=index):
                payload=deepcopy(base);mutate(payload);self.assert_rejected(payload)

    def test_old_seed_receipts_reject_before_any_effects(self):
        config=self.configuration();self.create(config)
        now,mono=time.time()-6,time.monotonic()-6
        candidate=core.bootstrap(config,seed_history(now,mono),decision_inputs(now,mono))
        self.assert_rejected(self.payload(candidate),'provider_receipt_expired')

    def test_source_receipt_expiring_during_effects_rolls_back_every_table(self):
        _,candidate=self.prepare_bootstrap()
        # Task-local fixture trigger delays only this run's first account write.
        # No clock override: the real server clock advances across both guards.
        function='provider_test_delay_'+uuid4().hex
        trigger='provider_test_delay_'+uuid4().hex
        self.db.sql('CREATE FUNCTION vn_durability.'+function+'() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER '
            "SET search_path=pg_catalog,vn_durability,pg_temp AS $$ BEGIN IF NEW.run_id="+literal(self.run)+
            "::uuid AND NOT EXISTS(SELECT 1 FROM vn_durability.accounts WHERE run_id=NEW.run_id) THEN "
            "PERFORM pg_sleep(5.05); END IF; RETURN NEW; END $$; CREATE TRIGGER "+trigger+
            ' BEFORE INSERT ON vn_durability.accounts FOR EACH ROW EXECUTE FUNCTION vn_durability.'+function+'();')
        try:
            self.assert_rejected(self.payload(candidate),'provider_receipt_expired')
        finally:
            self.db.sql('DROP TRIGGER '+trigger+' ON vn_durability.accounts; DROP FUNCTION vn_durability.'+function+'();')

    def test_original_command_replay_and_journal_survive_source_expiry(self):
        _,candidate=self.prepare_bootstrap();payload=self.payload(candidate);command=identity()
        first=json.loads(self.db.scalar(self.sql(payload,command),role='service_role'))
        before=self.snapshot()
        time.sleep(5.05)
        replay=json.loads(self.db.scalar(self.sql(payload,command),role='service_role'))
        self.assertEqual(replay,first)
        self.assertEqual(self.snapshot(),before)
        journal=json.loads(self.db.scalar('SELECT vn_durability.get_command('+','.join((literal(self.owner),literal(self.run),literal(command)))+');',role='service_role'))
        self.assertEqual(journal['request']['payload'],payload)
        self.assertEqual(journal['response'],first)
        self.assert_rejected(payload,'revision_conflict')

    def test_later_preparation_accepts_original_frame_without_rebasing_receipt(self):
        _,boot=self.install_bootstrap();now,mono=time.time(),time.monotonic()
        frame=quote_frame(boot.state,now,mono)
        time.sleep(.02)
        prepared_now,prepared_mono=time.time(),time.monotonic()
        candidate=core.prepare_protective(boot.state,frame,
            decision_inputs(prepared_now,prepared_mono,second=frame['decision_second']))
        self.assertGreater(candidate.transition['evidence']['source']['wall_us'],frame['decision_wall_us'])
        self.db.sql(self.sql(self.payload(candidate)),role='service_role')
        actual=json.loads(self.db.scalar('SELECT engine_state FROM vn_durability.runs WHERE id='+literal(self.run)+';'))
        self.assertEqual(actual['source']['last_quote'],frame)

    def test_server_wall_elapsed_consumes_carried_age_even_when_process_elapsed_shorter(self):
        _,boot=self.install_bootstrap();now,mono=time.time(),time.monotonic();block=123456789
        raw=(' {"'+source.MINT+'":{"usdPrice":100,"blockId":'+str(block)+',"decimals":9}}').encode()
        doc=ProviderDocument.capture('jupiter-price-v3',{'ids':source.MINT},raw,now-1.1,mono-.01)
        record=parse_price_record(doc,asset='SOL/USDC',mint=source.MINT)
        capture=PriceCapture(record,int(now)-1,QuoteEvidence(block,doc.received_at,doc.received_monotonic,
            source_age_at_receipt=29.9))
        frame=source.make_frame(capture,prior_source=boot.state.to_dict()['source'],epoch=boot.state.to_dict()['source']['epoch'],
            wall_now=now,monotonic_now=mono)
        candidate=core.prepare_protective(boot.state,frame,decision_inputs(now,mono))
        self.assert_rejected(self.payload(candidate),'provider_quote_stale')

    def test_history_increment_validator_enforces_complete_exact_fingerprints_and_cursor(self):
        # The helper is private; direct postgres-role validation isolates the
        # current15-minute history boundary without fast-forwarding server time.
        now,mono=time.time(),time.monotonic();seed=seed_history(now,mono)
        all_bars=source.derive_bars(seed)
        old_bars=[[end-900,close,fingerprint] for end,close,fingerprint in all_bars]
        bundle=deepcopy(seed);bundle['minutes']=bundle['minutes'][-15:]
        wall_us,mono_us=source.clock_us(now,upper=True),source.clock_us(mono,upper=True)
        def sql(value, prior=old_bars):
            return 'SELECT vn_durability.provider_history('+','.join((document(value),document(prior),'false',str(wall_us),str(mono_us)))+');'
        actual=json.loads(self.db.scalar(sql(bundle)))
        self.assertEqual(actual,(old_bars+source.derive_bars(bundle))[-64:])
        self.assertNotEqual(self.db.sql(sql(bundle),role='service_role',check=False).returncode,0)
        for mutation in (
            lambda b:b['minutes'].pop(),
            lambda b:b['minutes'][1].__setitem__(0,b['minutes'][0][0]),
            lambda b:b['minutes'][0].__setitem__(1,'0.0000000000000000001'),
            lambda b:b['documents'].append(deepcopy(b['documents'][0])),
            lambda b:b['documents'][0]['request']['parameters'].update(padding='true'),
            lambda b:b['documents'][0].update(received_monotonic_us=mono_us+1),
            lambda b:b['documents'][0].update(received_wall_us=all_bars[-1][0]*1000000+4999999),
        ):
            altered=deepcopy(bundle);mutation(altered)
            self.assertNotEqual(self.db.sql(sql(altered),check=False).returncode,0)
        skipped=[[end-900,close,fingerprint] for end,close,fingerprint in old_bars]
        self.assertNotEqual(self.db.sql(sql(bundle,skipped),check=False).returncode,0)

    def test_nonmarket_controls_keep_source_and_original_provider_policy(self):
        _,boot=self.install_bootstrap()
        candidate=core.prepare_control(boot.state,'pause',decision_inputs())
        self.db.sql(self.sql(self.payload(candidate)),role='service_role')
        self.assertEqual(candidate.state.to_dict()['source'],boot.state.to_dict()['source'])
        altered=self.payload(candidate);altered['transition']['after']['source']['bars'][0][1]='99'
        self.assert_rejected(altered)
        stopped=core.prepare_control(candidate.state,'stop',decision_inputs())
        self.db.sql(self.sql(self.payload(stopped)),role='service_role')
        actual=json.loads(self.db.scalar('SELECT engine_state FROM vn_durability.runs WHERE id='+literal(self.run)+';'))
        self.assertEqual(actual,stopped.state.to_dict())
        self.assertEqual(actual['status'],'stopped')

    def test_later_block_same_estimate_advances_once_and_cannot_reset_age_or_source(self):
        _,boot=self.install_bootstrap();now,mono=time.time(),time.monotonic()
        first=quote_frame(boot.state,now,mono)
        protective=core.prepare_protective(boot.state,first,decision_inputs(now,mono))
        self.db.sql(self.sql(self.payload(protective)),role='service_role')
        target=first['decision_second']+1.01
        if time.time()<target: time.sleep(target-time.time())
        now,mono=time.time(),time.monotonic()
        following=quote_frame(protective.state,now,mono,block=first['quote']['block_ref']+1,
            estimated=first['quote']['estimated_source_second'])
        candidate=core.prepare_protective(protective.state,following,decision_inputs(now,mono))
        base=self.payload(candidate)
        self.assertEqual(following['quote']['estimated_source_second'],first['quote']['estimated_source_second'])
        self.assertGreater(following['quote']['source_age_floor_us'],0)
        for name,value,code in (
            ('block_ref',first['quote']['block_ref'],'provider_source_regressed'),
            ('estimated_source_second',first['quote']['estimated_source_second']-1,'provider_source_regressed'),
            ('source_age_floor_us',0,'provider_age_floor_regressed'),
        ):
            payload=deepcopy(base)
            for frame in (payload['transition']['evidence']['source']['frame'],payload['transition']['after']['source']['last_quote']):
                frame['quote'][name]=value
            self.assert_rejected(payload,code)
        regressed=deepcopy(base)
        for frame in (regressed['transition']['evidence']['source']['frame'],regressed['transition']['after']['source']['last_quote']):
            frame['decision_monotonic_us']=first['decision_monotonic_us']-1
            frame['quote']['document']['received_monotonic_us']=first['decision_monotonic_us']-2
        self.assert_rejected(regressed,'provider_source_regressed')
        self.db.sql(self.sql(base),role='service_role')
        self.assertEqual(self.db.scalar("SELECT engine_state->'source'->'quote_sequence' FROM vn_durability.runs WHERE id="+literal(self.run)+';'),'2')

    def test_future_prepare_wall_rejects_without_source_or_economic_effects(self):
        _,boot=self.install_bootstrap();now,mono=time.time(),time.monotonic()
        frame=quote_frame(boot.state,now,mono)
        candidate=core.prepare_protective(boot.state,frame,decision_inputs(now,mono))
        payload=self.payload(candidate);envelope=payload['transition']['evidence']['source']
        envelope['wall_us']+=2000000
        dt=datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(microseconds=envelope['wall_us'])
        payload['transition']['evidence']['inputs']['wall_at']=dt.isoformat()
        self.assert_rejected(payload,'provider_decision_future')

    def test_private_clock_conversion_matches_exact_binary64_microsecond_edges(self):
        import math
        for value in (0.0,math.ulp(0.0),math.nextafter(1.0,0.0),1.0,
                      math.nextafter(1.0,math.inf),1e-6,1.000001,1e10):
            actual=self.db.scalar('SELECT vn_durability.provider_hex_us('+document(value.hex())+');')
            self.assertEqual(int(actual),source.clock_us(value,upper=True),value.hex())
        for value in (-1.0,math.nextafter(1e10,math.inf)):
            self.assertNotEqual(self.db.sql('SELECT vn_durability.provider_hex_us('+document(value.hex())+');',check=False).returncode,0)

    def test_document_request_boundaries_match_inclusive_rows_and_32_byte_mints(self):
        now,mono=time.time(),time.monotonic();seed=seed_history(now,mono)
        doc=deepcopy(seed['documents'][0]);params=doc['request']['parameters']
        params['time_from']=params['time_to']-300000
        result=self.db.sql("SELECT vn_durability.provider_document("+document(doc)+",'birdeye-ohlcv-v3');",check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('invalid_provider_request',result.stderr)
        params['time_from']+=60
        self.db.sql("SELECT vn_durability.provider_document("+document(doc)+",'birdeye-ohlcv-v3');")
        self.db.sql('SELECT vn_durability.provider_mint('+literal(source.MINT)+');')
        for mint in ('1'*33,'z'*44,'0'*32):
            result=self.db.sql('SELECT vn_durability.provider_mint('+literal(mint)+');',check=False)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('invalid_provider_mint',result.stderr)
        # The wire parser forbids minute0 independently of later cursor tests.
        seed['minutes'][0][0]=0
        result=self.db.sql('SELECT vn_durability.provider_history('+','.join((document(seed),'NULL','true',
            str(source.clock_us(now,upper=True)),str(source.clock_us(mono,upper=True))))+');',check=False)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('invalid_rehearsal_integer',result.stderr)
