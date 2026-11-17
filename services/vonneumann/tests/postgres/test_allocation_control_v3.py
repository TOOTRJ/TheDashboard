"""Private first-slice B2 native cases. Not executed/accepted by source creation.

The opt-in applies only to the current UUID-owned network-none harness. All
arrangement writes are trusted fixture setup. Actor calls preserve one original
wire, one submission, and independently committed readback; no rebased request.
"""
from __future__ import annotations
import copy
import json
import os
import time
import unittest
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres, OPT_IN
from tests.postgres.allocation_control_v3_fixture import (
    AllocationControlWindowRetirementPostgres, AllocationDeadlineRetirementPostgres,
    AllocationDeadlineScramPostgres, AllocationFixture, AllocationReaderWindowRetirementPostgres,
    AllocationHandoffPostgres, SUCCESSOR_RECORDER,
    AllocationScramPostgres, A, N, ANCHOR_OWNER, OWNER, CREATOR, BEGIN, SETTINGS, canonical, literal, sha,
)



# These are observations of materialized rows in the finite fixture. They are not
# PostgreSQL physical tuple/index/WAL measurements or a new transport protocol.
def scoped_rows(fixture,scope):
    sw=canonical(scope);answer={}
    for namespace,name,entries in fixture.snapshot():
        if name in answer:raise AssertionError('b2_duplicate_observed_table')
        answer[name]=[entry['row'] for entry in entries if entry['row']['scope_wire']==sw]
    if set(answer)!={'package_inputs','actor_bindings','scope_state','original_operations',
                     'journal_entries','identities','domain_facts','dependency_associations'}:
        raise AssertionError('b2_observed_table_inventory')
    return answer


def decimal_text(value):
    if type(value) not in (int,str) or type(value) is bool:
        raise AssertionError('b2_observed_counter_type')
    text=str(value)
    if not text.isascii() or not text.isdecimal() or str(int(text))!=text:
        raise AssertionError('b2_observed_counter_shape')
    return text


def observed_row_charge(table,row,scope):
    """Policy representation of actual values, not the SQL upper calculator.

    TEXT wires are charged as raw UTF8 once per stored occurrence. Closed logical
    metadata and declared key arrays are separately canonical-encoded. This reads
    actual committed observations and counters instead of invented upper padding.
    """
    size=lambda value:len(canonical(value).encode('utf8'))
    wires=[];metadata={'scope':scope}
    if table=='package_inputs':
        wires=[row[k] for k in ('package_wire','actor_manifest_wire','genesis_wire')]
        metadata.update(installation_id=row['installation_id'],expected_catalog_sha256=row['expected_catalog_sha256'],
          **{k+'_bytes':str(len(row[k].encode('utf8'))) for k in ('package_wire','actor_manifest_wire','genesis_wire')})
        keys=[['scope']]
    elif table=='actor_bindings':
        wires=[row['binding_wire']]
        metadata.update(binding_id=row['binding_id'],session_oid=decimal_text(row['session_oid']),
          session_name=row['session_name'],capabilities=row['capabilities'],binding_wire_bytes=str(len(wires[0].encode('utf8'))))
        keys=[['binding_id'],['session_oid','session_name']]
    elif table=='scope_state':
        wires=[row['head_wire'],row['accounting_wire']]
        metadata.update(head_sha256=sha(wires[0]),head_bytes=str(len(wires[0].encode('utf8'))),accounting_bytes=str(len(wires[1].encode('utf8'))))
        keys=[['scope']]
    elif table=='original_operations':
        wires=[row[k] for k in ('command_wire','result_wire','receipt_wire') if row[k] is not None]
        metadata.update(action_id=row['action_id'],action_kind=row['action_kind'],native_sequence=decimal_text(row['native_sequence']),
          command_sha256=row['command_sha256'],result_sha256=row['result_sha256'],receipt_sha256=row['receipt_sha256'],
          command_bytes=str(len(row['command_wire'].encode('utf8'))),result_bytes=str(len(row['result_wire'].encode('utf8'))),
          receipt_bytes='0' if row['receipt_wire'] is None else str(len(row['receipt_wire'].encode('utf8'))),
          writer_xid8=decimal_text(row['writer_xid8']),writer_principal_binding_id=row['writer_binding_id'],
          finalized=row['finalized'],final_function_observation=row['final_function_observation'])
        keys=[['action_id'],['scope','native_sequence'],['writer_xid8']]
    elif table=='journal_entries':
        wires=[row['journal_wire']]
        metadata.update(action_id=row['action_id'],native_sequence=decimal_text(row['native_sequence']),
          journal_sha256=row['journal_sha256'],journal_bytes=str(len(wires[0].encode('utf8'))))
        keys=[['scope','native_sequence'],['action_id']]
    elif table=='identities':
        wires=[row['record_wire']]
        metadata.update(original_id=row['original_id'],wire_bytes=str(len(wires[0].encode('utf8'))))
        keys=[['original_id'],['scope','original_id']]
    elif table=='domain_facts':
        wires=[row['original_wire']]
        metadata.update(semantic_kind=row['semantic_kind'],original_id=row['original_id'],wire_sha256=row['wire_sha256'],
          native_sequence=decimal_text(row['native_sequence']),wire_bytes=str(len(wires[0].encode('utf8'))))
        keys=[['semantic_kind','original_id','wire_sha256'],['scope','native_sequence','semantic_kind','original_id','wire_sha256']]
    elif table=='dependency_associations':
        metadata.update(action_id=row['action_id'],semantic_kind=row['semantic_kind'],original_id=row['original_id'],
          wire_sha256=row['wire_sha256'],wire_bytes=decimal_text(row['wire_bytes']),ordinal=decimal_text(row['ordinal']))
        keys=[['action_id','semantic_kind','original_id','wire_sha256'],['semantic_kind','original_id','wire_sha256','action_id']]
    else:raise AssertionError('b2_unknown_observed_table')
    if any(type(v) is not str for v in wires):raise AssertionError('b2_observed_wire_type')
    raw=sum(len(v.encode('utf8')) for v in wires)
    key_bytes=sum(size([metadata[field] for field in key]) for key in keys)
    return dict(bytes=raw+size(metadata)+key_bytes,keys=len(keys))


def observed_pin(kind,identity,wire):
    return dict(semantic_kind=kind,original_id=identity,original_wire=wire,
                wire_sha256=sha(wire),wire_bytes=str(len(wire.encode('utf8'))))


def ordered_pins(pins):
    keys=[(p['semantic_kind'],p['original_id'],p['wire_sha256']) for p in pins]
    if len(keys)!=len(set(keys)):raise AssertionError('b2_duplicate_expected_pin')
    return sorted(pins,key=lambda p:(p['semantic_kind'],p['original_id'],p['wire_sha256']))


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationControlNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=IsolatedPostgres().start()
        try:cls.fixture=AllocationFixture(cls.db)
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def setUp(self):
        self.f=self.fixture;self.f.reset();self.s=self.f.scopes[0];self.other=self.f.scopes[1]

    def submit(self,c,profile=None):
        s=next(s for s in self.f.scopes if s['scope']==c['scope'])
        role=s['actors'][profile or ('installer' if c['action_kind']=='installation' else 'control')]
        writer=self.f.writer(role)
        try:
            writer.send(self.f.call('submit',c,role));provisional=json.loads(writer.line())
            writer.finish()  # Original COMMIT once; no return value is receipt.
        finally:writer.close()
        return provisional

    def refusal(self,c,marker,*,profile='installer',prefix='',suffix='COMMIT;\n'):
        before=self.f.snapshot()
        result=self.db.sql(BEGIN+SETTINGS+prefix+self.f.call('submit',c,self.s['actors'][profile])+suffix,role=self.s['actors'][profile],check=False)
        self.assertNotEqual(0,result.returncode)
        self.assertIn(marker,result.stderr)
        self.assertEqual(before,self.f.snapshot())
        return result

    def assert_committed(self,c,reply,expected_sequence):
        self.assertEqual('ga-jupiter-b2-original-reply-research-v3-v1',reply['format'])
        self.assertEqual(canonical(c),reply['original_command_wire'])
        result=json.loads(reply['original_result_wire']);receipt=json.loads(reply['original_receipt_wire'])
        self.assertEqual(sha(canonical(c)),result['original_command_sha256'])
        self.assertEqual(sha(reply['original_result_wire']),receipt['result_sha256'])
        self.assertEqual(str(expected_sequence),result['native_sequence'])
        self.assertEqual(c['action_id'],receipt['action_id'])
        self.assertEqual(c['scope'],receipt['scope'])
        self.assertIsNone(receipt['admission_observation'])
        self.assertTrue(all(value is False for value in receipt['limits'].values()))
        a,b=receipt['final_function_observation'],receipt['commit_processing_observation']
        self.assertLessEqual(int(a['observed_at_us']),int(b['observed_at_us']))
        for observation in (a,b):
            self.assertEqual(observation['wall_lower_us'],observation['observed_at_us'])
            self.assertEqual(observation['wall_upper_us'],observation['observed_at_us'])
        journal=dict(native_sequence=str(expected_sequence),action_id=c['action_id'],action_kind=c['action_kind'],original_command_sha256=sha(canonical(c)),original_result_sha256=sha(reply['original_result_wire']),original_receipt_sha256=sha(reply['original_receipt_wire']),previous_native_head_sha256=c['expected_head']['native_head_sha256'])
        actual=json.loads(self.db.scalar(f'SELECT journal_wire FROM {N}.journal_entries WHERE action_id={literal(c["action_id"])};'))
        self.assertEqual(journal,actual)
        if self.f.head(next(s for s in self.f.scopes if s['scope']==c['scope']))['native_sequence']==str(expected_sequence):
            self.assertEqual(sha(canonical(journal)),reply['observed_head']['native_head_sha256'])
        for pin in result['dependencies']+reply['dependencies']:
            self.assertEqual(sha(pin['original_wire']),pin['wire_sha256'])
            self.assertEqual(str(len(pin['original_wire'].encode())),pin['wire_bytes'])
        return result,receipt

    def test_original_provisional_independent_absence_then_committed_getter(self):
        c=self.f.command(self.s);role=self.s['actors']['installer'];writer=self.f.writer(role)
        try:
            writer.send(self.f.call('submit',c,role));provisional=json.loads(writer.line())
            self.assertTrue(provisional['pending_commit'])
            self.assertNotIn('original_receipt_wire',provisional)
            self.assertNotIn('commit_processing_observation',provisional)
            absent=self.f.get(c,self.s['actors']['reader'])
            self.assertEqual('observed_absent_unknown',absent['resolution'])
            self.assertIsNone(absent['original_operation_pin'])
            self.assertEqual('0',self.f.head(self.s)['native_sequence'])
            writer.finish()  # No re-submit even though function output provisional.
        finally:writer.close()
        before=self.f.snapshot()
        reply=self.f.get(c,self.s['actors']['reader'])
        self.assert_committed(c,reply,1)
        self.assertEqual(before,self.f.snapshot())

    def test_installation_then_reserved_Stop_and_exact_original_replays(self):
        install=self.f.command(self.s);self.submit(install)
        first=self.f.get(install,self.s['actors']['reader']);self.assert_committed(install,first,1)
        stop=self.f.command(self.s,'source_stop')
        self.assertEqual('observed_absent_unknown',self.f.get(stop,self.s['actors']['reader'])['resolution'])
        self.submit(stop)
        before=self.f.snapshot();reply=self.f.get(stop,self.s['actors']['reader'])
        result,_=self.assert_committed(stop,reply,2)
        self.assertEqual(4,len(result['dependencies']))
        self.assertEqual(6,len(reply['dependencies']))  # Three facts+ancestor trio.
        self.assertEqual('stopped',self.f.head(self.s)['source_mode'])
        self.assertEqual(before,self.f.snapshot())
        # Replay only reads: control can replay installation through read_original
        # without gaining fresh install capability; original bytes stay unchanged.
        for original in (install,stop):
            replay=self.submit(original,profile='control')
            self.assertEqual('ga-jupiter-b2-original-reply-research-v3-v1',replay['format'])
            self.assertEqual(canonical(original),replay['original_command_wire'])
            self.assertEqual(before,self.f.snapshot())
        changed=copy.deepcopy(stop);changed['body']['expected_mode']='stopped'
        self.refusal(changed,'b2_original_conflict',profile='control')

    def test_provisional_rollback_removes_all_staged_rows(self):
        c=self.f.command(self.s);before=self.f.snapshot();role=self.s['actors']['installer']
        writer=self.f.writer(role)
        try:
            writer.send(self.f.call('submit',c,role));self.assertTrue(json.loads(writer.line())['pending_commit'])
            writer.finish('ROLLBACK;')
        finally:writer.close()
        self.assertEqual(before,self.f.snapshot())
        self.assertEqual('observed_absent_unknown',self.f.get(c,self.s['actors']['reader'])['resolution'])

    def test_same_writer_getter_is_not_commit_evidence(self):
        c=self.f.command(self.s);before=self.f.snapshot();role=self.s['actors']['installer']
        result=self.db.sql(BEGIN+SETTINGS+self.f.call('submit',c,role)+self.f.call('get_original',self.f.query(c),role)+'COMMIT;\n',role=role,check=False)
        self.assertNotEqual(0,result.returncode);self.assertIn('b2_writer_transaction',result.stderr)
        self.assertEqual(before,self.f.snapshot())

    def test_early_constraints_and_second_new_operation_roll_back(self):
        c=self.f.command(self.s)
        self.refusal(c,'b2_commit_form_refused',suffix='SET CONSTRAINTS ALL IMMEDIATE;\nCOMMIT;\n')
        second=copy.deepcopy(c);second['action_id']=str(UUID(int=999999))
        self.refusal(c,'b2_one_new_operation',suffix=self.f.call('submit',second,self.s['actors']['installer'])+'COMMIT;\n')

    def test_every_other_kind_refuses_without_any_table_write(self):
        for kind in ('epoch_registration','epoch_rollover','reader_epoch_registration','fence_release','source_pause','packet_reservation','capture_retention','source_admission','availability_retention','terminal_closure','inventory_seal'):
            with self.subTest(kind=kind):
                self.refusal(self.f.command(self.s,kind,action_id=str(UUID(int=999990))),'b2_kind_not_implemented',profile='reader')

    def test_foreign_originals_and_wrong_scope_never_borrow_authority(self):
        c=self.f.command(self.s);self.submit(c)
        q=self.f.query(c);q['scope']=self.other['scope']
        row=self.db.scalar(SETTINGS+self.f.call('get_original',q,self.other['actors']['reader']),role=self.other['actors']['reader'])
        self.assertEqual('observed_absent_unknown',json.loads(row)['resolution'])
        q['target_id']=str(UUID(int=999999));q['correlation']['id']=q['target_id']
        missing=json.loads(self.db.scalar(SETTINGS+self.f.call('get_original',q,self.other['actors']['reader']),role=self.other['actors']['reader']))
        self.assertEqual('observed_absent_unknown',missing['resolution'])
        before=self.f.snapshot()
        wrong=self.db.sql(SETTINGS+self.f.call('get_original',self.f.query(c),self.other['actors']['reader']),role=self.other['actors']['reader'],check=False)
        self.assertNotEqual(0,wrong.returncode);self.assertIn('b2_actor_scope_refused',wrong.stderr)
        self.assertEqual(before,self.f.snapshot())

    def test_null_capability_anchor_is_refused_by_closed_constructor(self):
        before=self.f.snapshot()
        result=self.db.sql(f"UPDATE {A}.actor_bindings SET capabilities=ARRAY[NULL]::text[] WHERE binding_id={literal(self.s['bindings']['installer'])};",check=False)
        self.assertNotEqual(0,result.returncode)
        self.assertIn('23514',result.stderr)
        self.assertEqual(before,self.f.snapshot())
        # The nullable ANY comparison is additionally closed in _auth, even
        # though this constructor prevents storing that malformed array.

    def test_null_and_mismatched_genesis_identity_refuse_before_staging(self):
        for role,value in (('owner_id',str(UUID(int=999991))),('run_id',str(UUID(int=999992))),('market_epoch',str(UUID(int=999993))),('installation_id',str(UUID(int=999994))),('owner_id',None)):
            with self.subTest(role=role,value=value):
                changed=copy.deepcopy(self.s['genesis'])
                target=next(x for x in changed['identity_specs'] if x['identity_role']==role)
                if value is None:target['identity_role']=None
                else:target['original_id']=value
                self.db.sql(f'UPDATE {A}.package_inputs SET genesis_wire={literal(canonical(changed))} WHERE scope_wire={literal(canonical(self.s["scope"]))};')
                c=self.f.command(self.s);c['body']['genesis_registry_sha256']=sha(canonical(changed))
                self.refusal(c,'b2_genesis_refused')
                self.db.sql(f'UPDATE {A}.package_inputs SET genesis_wire={literal(canonical(self.s["genesis"]))} WHERE scope_wire={literal(canonical(self.s["scope"]))};')

    def test_consistent_wrong_database_binding_refuses_without_state_DML(self):
        manifest=copy.deepcopy(self.s['manifest'])
        binding=next(x for x in manifest['bindings'] if x['principal_binding_id']==self.s['bindings']['installer'])
        binding['database_identity_sha256']=sha('a-different-owned-database')
        package=copy.deepcopy(self.s['package']);package['actor_manifest_sha256']=sha(canonical(manifest))
        self.db.sql(f"BEGIN; UPDATE {A}.package_inputs SET actor_manifest_wire={literal(canonical(manifest))},package_wire={literal(canonical(package))} WHERE scope_wire={literal(canonical(self.s['scope']))}; UPDATE {A}.actor_bindings SET binding_wire={literal(canonical(binding))} WHERE binding_id={literal(binding['principal_binding_id'])}; COMMIT;")
        self.refusal(self.f.command(self.s),'b2_actor_scope_refused')
        self.db.sql(f"UPDATE {A}.actor_bindings SET binding_wire={literal(canonical(next(x for x in self.s['manifest']['bindings'] if x['principal_binding_id']==self.s['bindings']['installer'])))} WHERE binding_id={literal(self.s['bindings']['installer'])};")

    def test_malformed_package_digest_refuses_before_known_finalization_cost(self):
        changed=copy.deepcopy(self.s['package']);changed['native_package_sha256']='a'*5000
        self.db.sql(f'UPDATE {A}.package_inputs SET package_wire={literal(canonical(changed))} WHERE scope_wire={literal(canonical(self.s["scope"]))};')
        self.refusal(self.f.command(self.s),'b2_package_refused')

    def test_original_aliases_cannot_overwrite_allocated_scope_or_Stop_ids(self):
        for identity in (self.s['stop_id'],self.s['scope']['owner_id'],self.s['installation_id']):
            c=self.f.command(self.s,action_id=identity)
            self.refusal(c,'b2_identity_conflict')
        install=self.f.command(self.s);self.submit(install)
        stale=self.f.command(self.s,'source_stop');stale['expected_head']=install['expected_head']
        self.refusal(stale,'b2_stale_head',profile='control')

    def test_autocommit_and_sync_off_are_unsupported_and_leave_no_original(self):
        c=self.f.command(self.s);before=self.f.snapshot();role=self.s['actors']['installer']
        result=self.db.sql(SETTINGS+self.f.call('submit',c,role),role=role,check=False)
        self.assertNotEqual(0,result.returncode);self.assertIn('b2_commit_form_refused',result.stderr)
        self.assertEqual(before,self.f.snapshot())
        self.refusal(c,'b2_session_refused',prefix="SET LOCAL synchronous_commit='off';\n")

    def test_actual_Stop_retained_rows_and_row_DML_include_deferred_update(self):
        self.assertEqual(1,self.f.arrangements,'b2_fresh_class_measurement_required')
        self.assertEqual('0',self.f.head(self.s)['native_sequence'])
        self.submit(self.f.command(self.s))
        def stats():
            return json.loads(self.db.scalar(f"SELECT pg_stat_clear_snapshot(); SELECT coalesce(jsonb_object_agg(relname,jsonb_build_array(n_tup_ins,n_tup_upd,n_tup_del)),'{{}}') FROM pg_stat_user_tables WHERE schemaname={literal(N)};"))
        # This is the first sorted native method in the whole-module fresh-
        # class launch. Require its complete known setup/installation vector;
        # do not take an immediate, potentially unflushed baseline. A different
        # execution arrangement refuses this measurement rather than guessing.
        expected_before=dict(original_operations=[1,1,0],journal_entries=[1,0,0],
          dependency_associations=[3,0,0],identities=[15,0,0],domain_facts=[3,0,0],
          scope_state=[4,1,2])
        def settled(expected):
            deadline=time.monotonic()+2
            while True:
                observed=stats()
                if observed==expected:return observed
                if time.monotonic()>=deadline:self.fail('b2_owned_complete_DML_statistics_unobserved')
                time.sleep(.02)
        before=settled(expected_before)
        c=self.f.command(self.s,'source_stop');self.submit(c)
        expected_delta=dict(original_operations=[1,1,0],journal_entries=[1,0,0],
          dependency_associations=[4,0,0],identities=[0,0,0],domain_facts=[0,0,0],
          scope_state=[0,1,0])
        after=settled({key:[before[key][i]+expected_delta[key][i] for i in range(3)] for key in before})
        delta={key:[after[key][i]-before[key][i] for i in range(3)] for key in before}
        self.assertEqual([1,1,0],delta['original_operations'])
        self.assertEqual([1,0,0],delta['journal_entries'])
        self.assertEqual([0,1,0],delta['scope_state'])
        self.assertEqual([4,0,0],delta['dependency_associations'])
        self.assertEqual([0,0,0],delta['identities']);self.assertEqual([0,0,0],delta['domain_facts'])
        self.assertEqual(8,sum(sum(row[:2]) for row in delta.values()))  # Four-pin path.
        self.assert_committed(c,self.f.get(c,self.s['actors']['reader']),2)
        a=json.loads(self.db.scalar(f'SELECT accounting_wire FROM {N}.scope_state WHERE scope_wire={literal(canonical(self.s["scope"]))};'))
        self.assertTrue(a['Stop_reserve_consumed'])
        self.assertEqual('2',a['committed_positions'])


    def test_broker_direct_actor_execute_is_denied(self):
        before=self.f.snapshot()
        for s in self.f.scopes:
            for role in s['actors'].values():
                for resume_lock in ('false','true'):
                    result=self.db.sql(SETTINGS+f"SELECT {A}._lock_inputs({literal(canonical(s['scope']))},{resume_lock});",role=role,check=False)
                    self.assertNotEqual(0,result.returncode)
                    self.assertIn('42501',result.stderr)
        self.assertEqual(before,self.f.snapshot())

    def test_broker_native_owner_cannot_update_anchor_rows(self):
        before=self.f.snapshot();sw=literal(canonical(self.s['scope']))
        for table,column in (('package_inputs','package_wire'),('actor_bindings','binding_wire')):
            result=self.db.sql(f'BEGIN; SET LOCAL ROLE vn_jupiter_b2_sealed_owner; UPDATE {A}.{table} SET {column}={column} WHERE scope_wire={sw}; ROLLBACK;',check=False)
            self.assertNotEqual(0,result.returncode)
            self.assertIn('42501',result.stderr)
        self.assertEqual(before,self.f.snapshot())

    def test_broker_anchor_updates_block_until_transaction_end(self):
        c=self.f.command(self.s);writer=self.f.writer(self.s['actors']['installer'])
        updates=[]
        try:
            writer_pid=writer.backend_pid()
            writer.send(self.f.call('submit',c,self.s['actors']['installer']))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            for table,column in (('package_inputs','package_wire'),('actor_bindings','binding_wire')):
                update=self.f.anchor_session();updates.append(update)
                pid=update.backend_pid()
                predicate=f"scope_wire={literal(canonical(self.s['scope']))}"
                if table=='actor_bindings':predicate+=f" AND binding_id={literal(self.s['bindings']['installer'])}"
                update.send(f"UPDATE {A}.{table} SET {column}={column} WHERE {predicate} RETURNING 'released';\n")
                self.f.wait_for_blocker(pid,writer_pid)
            writer.finish('ROLLBACK;')
            for update in updates:
                self.assertEqual('released',update.line())
                update.finish()
        finally:
            writer.close()
            for update in updates:update.close()
        self.assertEqual('0',self.f.head(self.s)['native_sequence'])
        self.assertEqual('observed_absent_unknown',self.f.get(c,self.s['actors']['reader'])['resolution'])

    def test_broker_postlock_reauthorization_refuses_changed_trusted_input(self):
        c=self.f.command(self.s);before=[r for r in self.f.snapshot() if r[0]==N]
        trusted=self.f.anchor_session();writer=self.f.writer(self.s['actors']['installer'])
        changed=copy.deepcopy(self.s['package']);changed['native_package_sha256']='a'*64
        try:
            trusted_pid=trusted.backend_pid();writer_pid=writer.backend_pid()
            trusted.send(f"UPDATE {A}.package_inputs SET package_wire={literal(canonical(changed))} WHERE scope_wire={literal(canonical(self.s['scope']))} RETURNING 'held';\n")
            self.assertEqual('held',trusted.line())
            writer.send(self.f.call('submit',c,self.s['actors']['installer']))
            self.f.wait_for_blocker(writer_pid,trusted_pid)
            trusted.finish()
            with self.assertRaisesRegex(RuntimeError,'b2_package_refused'):writer.line()
        finally:
            writer.close();trusted.close()
            self.db.sql(f"UPDATE {A}.package_inputs SET package_wire={literal(canonical(self.s['package']))} WHERE scope_wire={literal(canonical(self.s['scope']))};")
        self.assertEqual(before,[r for r in self.f.snapshot() if r[0]==N])
        self.assertEqual('observed_absent_unknown',self.f.get(c,self.s['actors']['reader'])['resolution'])

    def test_broker_locking_preserves_anchor_rows_and_releases_on_rollback(self):
        before=self.f.snapshot();anchors=[r for r in before if r[0]==A]
        c=self.f.command(self.s);writer=self.f.writer(self.s['actors']['installer'])
        queries=[]
        for table in ('package_inputs','actor_bindings'):
            predicate=f"scope_wire={literal(canonical(self.s['scope']))}"
            if table=='actor_bindings':predicate+=f" AND binding_id={literal(self.s['bindings']['installer'])}"
            queries.append(f'SELECT scope_wire FROM {A}.{table} WHERE {predicate} FOR UPDATE NOWAIT;')
        try:
            writer.send(self.f.call('submit',c,self.s['actors']['installer']))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            self.assertEqual(anchors,[r for r in self.f.snapshot() if r[0]==A])
            for query in queries:
                result=self.db.sql('BEGIN; '+query+' ROLLBACK;',check=False)
                self.assertNotEqual(0,result.returncode);self.assertIn('55P03',result.stderr)
            writer.finish('ROLLBACK;')
        finally:writer.close()
        for query in queries:self.db.sql('BEGIN; '+query+' ROLLBACK;')
        self.assertEqual(before,self.f.snapshot())


    def test_bound_accounting_component_envelope_covers_both_boolean_widths(self):
        # A symbolic component boundary, not a fabricated native business state.
        import re
        caps=self.f.policy['finite_caps_per_scope']
        maximum=dict(committed_positions=str(caps['committed_events']),
          logical_UTF8_bytes=str(caps['logical_UTF8_bytes_charged']),
          identity_rows=str(caps['retained_identity_rows']),
          domain_rows=str(self.f.policy['logical_storage']['row_caps_per_scope']['domain_facts']),
          dependency_rows=str(caps['dependency_association_rows']),retained_rows=str(caps['logical_retained_rows']),
          row_writes=str(caps['logical_row_writes_charged']),index_entries=str(caps['logical_index_entries_charged']),
          Stop_reserve_consumed=False)
        body=next(row['body'] for row in self.f.source.functions() if row['name']=='_cost')
        matches=re.findall(r"\bac:='([^']+)'::jsonb;\s+aw:=",body)
        self.assertEqual(1,len(matches),'b2_accounting_literal_review_required')
        declared=json.loads(matches[0])
        self.assertEqual(set(maximum),set(declared))
        declared_bytes=len(canonical(declared).encode('utf8'))
        for consumed in (False,True):
            candidate=maximum|dict(Stop_reserve_consumed=consumed)
            self.assertGreaterEqual(declared_bytes,len(canonical(candidate).encode('utf8')))
        self.assertEqual(1,len(canonical(maximum).encode('utf8'))-len(canonical(maximum|dict(Stop_reserve_consumed=True)).encode('utf8')))
        # Independently verify the encoded component with PostgreSQL's serializer.
        observed=self.db.sql(SETTINGS+f"SELECT {N}._c14n({literal(canonical(maximum))}::jsonb);")
        self.assertEqual(canonical(maximum)+'\n',observed.stdout)

    def test_first_path_observed_bytes_and_complete_counter_vectors(self):
        scope=self.s['scope'];policy=self.f.policy
        declared_keys=policy['logical_storage']['index_keys']
        actual_keys=json.loads(self.db.scalar(f"SELECT jsonb_object_agg(c.relname,(SELECT count(*) FROM pg_index i WHERE i.indrelid=c.oid)) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN({literal(A)},{literal(N)}) AND c.relkind='r';"))
        self.assertEqual(declared_keys,actual_keys)
        before=scoped_rows(self.f,scope)
        self.assertEqual(6,sum(map(len,before.values())))
        install=self.f.command(self.s);self.submit(install)
        installed=scoped_rows(self.f,scope)
        expected_install=dict(package_inputs=1,actor_bindings=4,scope_state=1,original_operations=1,
          journal_entries=1,identities=15,domain_facts=3,dependency_associations=3)
        self.assertEqual(expected_install,{name:len(rows) for name,rows in installed.items()})
        a1=json.loads(installed['scope_state'][0]['accounting_wire'])
        self.assertEqual(dict(committed_positions='1',identity_rows='15',domain_rows='3',dependency_rows='3',
          retained_rows='29',row_writes='24',index_entries='48',Stop_reserve_consumed=False),
          {key:value for key,value in a1.items() if key!='logical_UTF8_bytes'})
        install_bytes=sum(observed_row_charge(name,row,scope)['bytes'] for name,rows in installed.items() for row in rows)
        self.assertGreaterEqual(int(a1['logical_UTF8_bytes']),install_bytes)
        self.assertLessEqual(int(a1['logical_UTF8_bytes'])+policy['Stop_reserve_vector']['logical_UTF8_bytes'],
                             policy['finite_caps_per_scope']['logical_UTF8_bytes_charged'])
        stop=self.f.command(self.s,'source_stop');self.submit(stop)
        stopped=scoped_rows(self.f,scope)
        expected_final=expected_install|dict(original_operations=2,journal_entries=2,dependency_associations=7)
        self.assertEqual(expected_final,{name:len(rows) for name,rows in stopped.items()})
        self.assertEqual(35,sum(map(len,stopped.values())))
        a2=json.loads(stopped['scope_state'][0]['accounting_wire'])
        self.assertEqual(dict(committed_positions='2',identity_rows='15',domain_rows='3',dependency_rows='7',
          retained_rows='35',row_writes='31',index_entries='62',Stop_reserve_consumed=True),
          {key:value for key,value in a2.items() if key!='logical_UTF8_bytes'})
        changed={'scope_state':stopped['scope_state']}
        for name in ('original_operations','journal_entries','dependency_associations'):
            changed[name]=[row for row in stopped[name] if row['action_id']==stop['action_id']]
        stop_bytes=sum(observed_row_charge(name,row,scope)['bytes'] for name,rows in changed.items() for row in rows)
        self.assertGreaterEqual(int(a2['logical_UTF8_bytes'])-int(a1['logical_UTF8_bytes']),stop_bytes)
        self.assertLessEqual(int(a2['logical_UTF8_bytes']),policy['finite_caps_per_scope']['logical_UTF8_bytes_charged'])
        # Derive writes/keys from new retained row counts and the one updated
        # scope key, then separately account the provisional original's extra DML.
        observed_vectors=[]
        for left,right in ((before,installed),(installed,stopped)):
            inserts={name:len(right[name])-len(left[name]) for name in right if name not in ('package_inputs','actor_bindings','scope_state')}
            logical_writes=sum(inserts.values())+1
            keys=sum(count*actual_keys[name] for name,count in inserts.items())+actual_keys['scope_state']
            observed_vectors.append((logical_writes,keys,logical_writes+inserts['original_operations'],keys+inserts['original_operations']*actual_keys['original_operations']))
        self.assertEqual([(24,48,25,51),(7,14,8,17)],observed_vectors)
        self.assertEqual((31,62,33,68),tuple(sum(v[i] for v in observed_vectors) for i in range(4)))
        # Reconstruct the declared pending image from the retained immutable row;
        # this is selected logical encoding, not observation of WAL/physical DML.
        pending=0
        for row in stopped['original_operations']:
            image=row|dict(receipt_wire=None,receipt_sha256=None,finalized=False)
            pending+=observed_row_charge('original_operations',image,scope)['bytes']
        self.assertLessEqual(install_bytes+stop_bytes+pending,policy['finite_caps_per_scope']['encoded_row_DML_UTF8_upper_charged'])

    def test_getter_exact_pin_closures_and_nested_scalar_encoding(self):
        install=self.f.command(self.s);self.submit(install)
        def capture(command):
            result=self.db.sql(SETTINGS+self.f.call('get_original',self.f.query(command),self.s['actors']['reader']),role=self.s['actors']['reader'])
            value=json.loads(result.stdout)
            self.assertEqual(canonical(value)+'\n',result.stdout)
            self.assertEqual(1,result.stdout.count('\n'))
            self.assertLessEqual(len(result.stdout.encode('utf8')),self.f.policy['transport_budget']['new_B2_native_fixture_response_bytes_limit'])
            self.assertGreater(len(result.stdout.encode('utf8')),sum(len(value[k].encode('utf8')) for k in ('original_command_wire','original_result_wire','original_receipt_wire'))+1)
            return value
        first=capture(install);self.assert_committed(install,first,1)
        command_sha=sha(canonical(install));g=self.s['genesis'];scope=self.s['scope']
        epoch=g['initial_acquisition_spec']|dict(scope=scope,ordinal='1',original_command_sha256=command_sha)
        terminal=dict(format='ga-jupiter-b2-terminal-allocation-research-v3-v1',scope=scope,
          installation_id=self.s['installation_id'],stop_action_id=self.s['stop_id'],
          allocation_command_sha256=command_sha,first_native_sequence='1')
        facts=ordered_pins([observed_pin('native_genesis_input',self.s['installation_id'],canonical(g)),
          observed_pin('native_epoch_registration',epoch['registration_id'],canonical(epoch)),
          observed_pin('native_terminal_allocation',self.s['stop_id'],canonical(terminal))])
        self.assertEqual(facts,first['dependencies'])
        self.assertEqual(facts,json.loads(first['original_result_wire'])['dependencies'])
        stop=self.f.command(self.s,'source_stop');self.submit(stop)
        second=capture(stop);self.assert_committed(stop,second,2)
        ancestor=[observed_pin(kind,install['action_id'],first[field]) for kind,field in
          (('native_command','original_command_wire'),('native_result','original_result_wire'),('native_receipt','original_receipt_wire'))]
        self.assertEqual(ordered_pins(facts+ancestor),second['dependencies'])
        self.assertEqual(ordered_pins(facts+[observed_pin('native_command',install['action_id'],canonical(install))]),
                         json.loads(second['original_result_wire'])['dependencies'])
        self.assertEqual(3,len(first['dependencies']));self.assertEqual(6,len(second['dependencies']))
        caps=self.f.policy['wire_caps_UTF8']
        for c,reply in ((install,first),(stop,second)):
            self.assertLessEqual(len(canonical(c).encode('utf8')),caps['command'])
            for field,cap in (('original_result_wire','result'),('original_receipt_wire','receipt')):
                self.assertLessEqual(len(reply[field].encode('utf8')),caps[cap])
        # Serializer vectors exercise escaping, not expanded business admission.
        vectors=[dict(text='quote" backslash\\ slash/\n\t\b\f\r',unicode='é😀\u2028'),
                 dict(original_wire=canonical(dict(text='"\\\n',unicode='é😀')))]
        for value in vectors:
            wire=canonical(value)
            native=self.db.sql(SETTINGS+f'SELECT {N}._c14n({literal(wire)}::jsonb);')
            self.assertEqual(wire+'\n',native.stdout)

    def test_concurrent_same_original_waiter_reconciles_without_new_action(self):
        c=self.f.command(self.s);role=self.s['actors']['installer']
        winner=self.f.writer(role);waiter=self.f.writer(role)
        try:
            winner_pid=winner.backend_pid();waiter_pid=waiter.backend_pid()
            winner.send(self.f.call('submit',c,role));self.assertTrue(json.loads(winner.line())['pending_commit'])
            waiter.send(self.f.call('submit',c,role))
            self.f.wait_for_blocker(waiter_pid,winner_pid)
            winner.finish()
            with self.assertRaisesRegex(RuntimeError,'b2_stale_head'):waiter.line()
        finally:winner.close();waiter.close()
        before=self.f.snapshot()
        reply=self.f.get(c,self.s['actors']['reader']);self.assert_committed(c,reply,1)
        self.assertEqual(before,self.f.snapshot())
        rows=scoped_rows(self.f,self.s['scope'])
        self.assertEqual([c['action_id']],[row['action_id'] for row in rows['original_operations']])
        self.assertEqual('1',self.f.head(self.s)['native_sequence'])

    def test_getter_parent_statement_snapshot_stays_before_concurrent_commit(self):
        # The barrier is an owned coordinator lock in a private test statement,
        # not an installed source hook or a production executor protocol change.
        c=self.f.command(self.s);role=self.s['actors']['installer']
        writer=self.f.writer(role);reader=self.f.writer(self.s['actors']['reader']);gate=self.f.anchor_session()
        key=int(UUID(self.s['scope']['run_id'])) & 0x7fffffff
        try:
            writer.send(self.f.call('submit',c,role));self.assertTrue(json.loads(writer.line())['pending_commit'])
            gate_pid=gate.backend_pid();reader_pid=reader.backend_pid()
            gate.send(f'SELECT pg_catalog.pg_advisory_xact_lock(1275068433,{key});\n')
            self.assertEqual('',gate.line())
            query=literal(canonical(self.f.query(c)))
            reader.send(f'SELECT {N}.get_original({query}) FROM (SELECT pg_catalog.pg_advisory_xact_lock(1275068433,{key})) AS owned_gate;\n')
            self.f.wait_for_blocker(reader_pid,gate_pid)
            writer.finish()
            gate.finish('ROLLBACK;')
            old=json.loads(reader.line());reader.finish('ROLLBACK;')
            self.assertEqual('observed_absent_unknown',old['resolution'])
            self.assertEqual(c['expected_head'],old['observed_head'])
            self.assertIsNone(old['original_operation_pin'])
        finally:writer.close();reader.close();gate.close()
        current=self.f.get(c,self.s['actors']['reader']);self.assert_committed(c,current,1)
        self.assertEqual('1',current['observed_head']['native_sequence'])


    def acquire_command(self,*,action_number=993001,fence_number=993002):
        c=self.f.command(self.s,'fence_acquire',action_id=str(UUID(int=action_number)))
        c['body']=dict(fence_id=str(UUID(int=fence_number)),acquisition_epoch=self.s['epoch'],
            holder_principal_binding_id=self.s['bindings']['recorder'],requested_duration_us='60000000')
        return c

    def test_fence_acquire_original_clock_active_head_and_observed_charge(self):
        install=self.f.command(self.s);self.submit(install)
        reader=self.s['actors']['reader'];recorder=self.s['actors']['recorder'];scope=self.s['scope']
        installed=self.f.get(install,reader)
        initial=scoped_rows(self.f,scope)
        c=self.acquire_command()
        before=self.f.get(c,reader)
        self.assertEqual('observed_absent_unknown',before['resolution'])
        self.assertEqual(c['expected_head'],before['observed_head'])
        writer=self.f.writer(recorder)
        try:
            writer.send(self.f.call('submit',c,recorder))
            pending=json.loads(writer.line())
            self.assertTrue(pending['pending_commit'])
            self.assertEqual(sha(canonical(c)),pending['original_command_sha256'])
            self.assertTrue(all(value is False for value in pending['limits'].values()))
            self.assertEqual(before,self.f.get(c,reader))
            writer.finish()  # Command completion is not treated as the receipt.
        finally:writer.close()
        reply=self.f.get(c,reader);result,receipt=self.assert_committed(c,reply,2)
        fence=result['result_body']['original_fence_record']
        issued=int(fence['issued_at_us']);expires=int(fence['expires_at_us'])
        self.assertGreaterEqual(issued,0)
        self.assertEqual(dict(fence_id=c['body']['fence_id'],scope=scope,
            holder_principal_binding_id=self.s['bindings']['recorder'],acquisition_epoch=self.s['epoch'],
            revision='1',issued_at_us=str(issued),expires_at_us=str(issued+60_000_000),
            original_command_sha256=sha(canonical(c)),native_sequence='2'),fence)
        self.assertLessEqual(issued,int(receipt['final_function_observation']['observed_at_us']))
        self.assertLess(int(receipt['commit_processing_observation']['observed_at_us']),expires)
        h=self.f.head(self.s)
        self.assertEqual(('paused',self.s['epoch'],fence['fence_id'],'1','2'),
            tuple(h[key] for key in ('source_mode','active_acquisition_epoch','active_fence_id','fence_revision','native_sequence')))
        fence_pin=observed_pin('native_fence_record',fence['fence_id'],canonical(fence))
        install_pin=observed_pin('native_command',install['action_id'],canonical(install))
        expected=ordered_pins(installed['dependencies']+[install_pin,fence_pin])
        self.assertEqual(5,len(expected));self.assertEqual(expected,result['dependencies'])
        expected=ordered_pins(expected+[observed_pin(kind,install['action_id'],installed[field])
          for kind,field in (('native_result','original_result_wire'),('native_receipt','original_receipt_wire'))])
        self.assertEqual(7,len(expected));self.assertEqual(expected,reply['dependencies'])
        raw=self.db.sql(SETTINGS+self.f.call('get_original',self.f.query(c),reader),role=reader).stdout
        self.assertEqual(canonical(reply)+'\n',raw)
        self.assertLessEqual(len(raw.encode('utf8')),8388608)
        current=scoped_rows(self.f,scope)
        a1=json.loads(initial['scope_state'][0]['accounting_wire'])
        a2=json.loads(current['scope_state'][0]['accounting_wire'])
        self.assertEqual(39,sum(map(len,current.values())))
        self.assertEqual(dict(committed_positions='2',identity_rows='17',domain_rows='4',dependency_rows='8',
          retained_rows='39',row_writes='35',index_entries='70',Stop_reserve_consumed=False),
          {key:value for key,value in a2.items() if key!='logical_UTF8_bytes'})
        changed={'scope_state':current['scope_state']}
        for name in ('original_operations','journal_entries','dependency_associations'):
            changed[name]=[row for row in current[name] if row['action_id']==c['action_id']]
        changed['identities']=[row for row in current['identities'] if row['original_id'] in (c['action_id'],fence['fence_id'])]
        changed['domain_facts']=[row for row in current['domain_facts'] if row['original_id']==fence['fence_id']]
        self.assertEqual(1,len(changed['domain_facts']))
        self.assertEqual(canonical(fence),changed['domain_facts'][0]['original_wire'])
        self.assertEqual(2,len(changed['identities']))
        for row in changed['identities']:
            identity=row['original_id']
            self.assertEqual(dict(original_id=identity,identity_role='fence_id' if identity==fence['fence_id'] else 'native_operation_id',
                association=scope|dict(packet_reservation_id=None),original_allocation_sha256=sha(canonical(c)),first_native_sequence='2'),json.loads(row['record_wire']))
        selected=[observed_row_charge(name,row,scope) for name,rows in changed.items() for row in rows]
        self.assertEqual((11,22),(len(selected),sum(row['keys'] for row in selected)))
        self.assertGreaterEqual(int(a2['logical_UTF8_bytes'])-int(a1['logical_UTF8_bytes']),sum(row['bytes'] for row in selected))
        self.assertLessEqual(int(a2['logical_UTF8_bytes'])+self.f.policy['Stop_reserve_vector']['logical_UTF8_bytes'],
          self.f.policy['finite_caps_per_scope']['logical_UTF8_bytes_charged'])
        unchanged=self.f.snapshot()
        replay=json.loads(self.db.scalar(SETTINGS+self.f.call('submit',c,reader),role=reader))
        self.assertEqual(reply,replay);self.assertEqual(unchanged,self.f.snapshot())
        historical=self.f.get(install,reader)
        self.assertEqual(installed['original_result_wire'],historical['original_result_wire'])
        self.assertEqual(installed['dependencies'],historical['dependencies'])

    def test_fence_acquire_requires_installed_recorder_and_closed_exact_duration(self):
        self.refusal(self.acquire_command(),'b2_fence_acquire_refused',profile='recorder')
        self.submit(self.f.command(self.s));c=self.acquire_command()
        for profile in ('control','installer','reader'):
            with self.subTest(profile=profile):self.refusal(c,'b2_actor_scope_refused',profile=profile)
        before=self.f.snapshot();foreign=self.other['actors']['recorder']
        result=self.db.sql(BEGIN+SETTINGS+self.f.call('submit',c,foreign)+'COMMIT;\n',role=foreign,check=False)
        self.assertNotEqual(0,result.returncode);self.assertIn('b2_actor_scope_refused',result.stderr)
        self.assertEqual(before,self.f.snapshot())
        for field,value in (('requested_duration_us',60000000),('requested_duration_us','60000001'),
             ('holder_principal_binding_id',self.s['bindings']['control']),('acquisition_epoch',self.other['epoch']),
             ('issued_at_us','0')):
            with self.subTest(field=field,value=value):
                bad=copy.deepcopy(c);bad['body'][field]=value
                self.refusal(bad,'b2_fence_acquire_refused',profile='recorder')

    def test_fence_acquire_identity_stale_and_active_hold_refuse(self):
        self.submit(self.f.command(self.s));self.submit(self.f.command(self.other))
        c=self.acquire_command()
        for identity in (c['action_id'],self.s['stop_id'],self.other['epoch']):
            with self.subTest(identity=identity):
                bad=copy.deepcopy(c);bad['body']['fence_id']=identity
                self.refusal(bad,'b2_identity_conflict',profile='recorder')
        alias=copy.deepcopy(c);alias['action_id']=self.s['stop_id']
        self.refusal(alias,'b2_identity_conflict',profile='recorder')
        self.submit(c,'recorder')
        altered=copy.deepcopy(c);altered['body']['requested_duration_us']='60000001'
        self.refusal(altered,'b2_original_conflict',profile='recorder')
        fresh=self.acquire_command(action_number=993011,fence_number=993012)
        stale=copy.deepcopy(fresh);stale['expected_head']=c['expected_head']
        self.refusal(stale,'b2_stale_head',profile='recorder')
        self.refusal(fresh,'b2_fence_acquire_refused',profile='recorder')

    def test_fence_acquire_provisional_rollback_and_early_guard_leave_no_facts(self):
        self.submit(self.f.command(self.s));c=self.acquire_command();role=self.s['actors']['recorder']
        before=self.f.snapshot()
        writer=self.f.writer(role)
        try:
            writer.send(self.f.call('submit',c,role));self.assertTrue(json.loads(writer.line())['pending_commit'])
            writer.finish('ROLLBACK;')
        finally:writer.close()
        self.assertEqual(before,self.f.snapshot())
        self.assertEqual('observed_absent_unknown',self.f.get(c,self.s['actors']['reader'])['resolution'])
        # Separate original ID after a proved rollback; no uncertain command reissue.
        other=self.acquire_command(action_number=993021,fence_number=993022)
        self.refusal(other,'b2_commit_form_refused',profile='recorder',suffix='SET CONSTRAINTS ALL IMMEDIATE;\nCOMMIT;\n')
        stop=self.f.command(self.s,'source_stop');self.submit(stop)
        self.assert_committed(stop,self.f.get(stop,self.s['actors']['reader']),2)
        self.assertIsNone(self.f.head(self.s)['active_fence_id'])

    def test_original_reserved_stop_after_acquire_retains_fence_and_exact_closure(self):
        install=self.f.command(self.s);self.submit(install)
        c=self.acquire_command();self.submit(c,'recorder')
        reader=self.s['actors']['reader'];scope=self.s['scope']
        i=self.f.get(install,reader);a=self.f.get(c,reader)
        result,_=self.assert_committed(c,a,2)
        fence=result['result_body']['original_fence_record']
        before=scoped_rows(self.f,scope)
        stop=self.f.command(self.s,'source_stop')
        self.assertEqual(self.s['stop_id'],stop['action_id'])
        self.refusal(stop,'b2_actor_scope_refused',profile='recorder')
        self.submit(stop);reply=self.f.get(stop,reader)
        stopped,_=self.assert_committed(stop,reply,3)
        self.assertEqual(dict(previous_mode='paused',resulting_mode='stopped',previous_control_sha256=None,
          resulting_fence_revision='2'),stopped['result_body'])
        expected=ordered_pins(result['dependencies']+[observed_pin('native_command',c['action_id'],canonical(c))])
        self.assertEqual(6,len(expected));self.assertEqual(expected,stopped['dependencies'])
        ancestors=[observed_pin(kind,source['action_id'],saved[field]) for source,saved in ((install,i),(c,a))
          for kind,field in (('native_command','original_command_wire'),('native_result','original_result_wire'),('native_receipt','original_receipt_wire'))]
        expected=ordered_pins(i['dependencies']+[observed_pin('native_fence_record',fence['fence_id'],canonical(fence))]+ancestors)
        self.assertEqual(10,len(expected));self.assertEqual(expected,reply['dependencies'])
        h=self.f.head(self.s)
        self.assertEqual(('stopped',None,'2','3'),tuple(h[key] for key in ('source_mode','active_fence_id','fence_revision','native_sequence')))
        after=scoped_rows(self.f,scope)
        self.assertEqual(before['domain_facts'],after['domain_facts'])
        self.assertEqual(before['identities'],after['identities'])
        self.assertEqual(47,sum(map(len,after.values())))
        a3=json.loads(after['scope_state'][0]['accounting_wire'])
        self.assertEqual(dict(committed_positions='3',identity_rows='17',domain_rows='4',dependency_rows='14',
          retained_rows='47',row_writes='44',index_entries='88',Stop_reserve_consumed=True),
          {key:value for key,value in a3.items() if key!='logical_UTF8_bytes'})
        # The original UPDATE adds one DML and its three declared key touches per operation.
        self.assertEqual((47,97),(int(a3['row_writes'])+len(after['original_operations']),
          int(a3['index_entries'])+3*len(after['original_operations'])))
        before_accounting=json.loads(before['scope_state'][0]['accounting_wire'])
        chosen=[observed_row_charge('scope_state',after['scope_state'][0],scope)]
        chosen += [observed_row_charge(name,row,scope) for name in ('original_operations','journal_entries','dependency_associations')
          for row in after[name] if row['action_id']==stop['action_id']]
        self.assertEqual((9,18),(len(chosen),sum(row['keys'] for row in chosen)))
        self.assertGreaterEqual(int(a3['logical_UTF8_bytes'])-int(before_accounting['logical_UTF8_bytes']),sum(row['bytes'] for row in chosen))
        # Reconstruct the three pending row images from retained exact C/R and
        # final-function metadata; this is a separate selected logical charge.
        pending=sum(observed_row_charge('original_operations',
          row|dict(receipt_wire=None,receipt_sha256=None,finalized=False),scope)['bytes']
          for row in after['original_operations'])
        self.assertLessEqual(int(a3['logical_UTF8_bytes'])+pending,
          self.f.policy['finite_caps_per_scope']['encoded_row_DML_UTF8_upper_charged'])
        immutable=self.f.snapshot()
        self.assertEqual(reply,json.loads(self.db.scalar(SETTINGS+self.f.call('submit',stop,reader),role=reader)))
        self.assertEqual(a['original_result_wire'],self.f.get(c,reader)['original_result_wire'])
        self.assertEqual(immutable,self.f.snapshot())
        self.refusal(self.acquire_command(action_number=993031,fence_number=993032),'b2_fence_acquire_refused',profile='recorder')


    def resume_command(self, *, action_number=994001):
        command=self.f.command(self.s,'source_resume',action_id=str(UUID(int=action_number)))
        head=self.f.head(self.s)
        command['expected_fence_id']=head['active_fence_id']
        command['expected_fence_revision']=head['fence_revision']
        return command

    def open_stop_command(self, resume):
        command=self.f.command(self.s,'source_stop')
        command['body']=dict(expected_control_sha256=sha(canonical(resume)),expected_mode='open')
        return command

    def install_and_acquire_for_resume(self):
        install=self.f.command(self.s)
        self.submit(install)
        acquire=self.acquire_command()
        self.submit(acquire,'recorder')
        return install,acquire

    def test_resume_open_stop_exact_originals_and_observed_accounting(self):
        install,acquire=self.install_and_acquire_for_resume()
        resume=self.resume_command()
        reader=self.s['actors']['reader']
        control=self.s['actors']['control']
        scope=self.s['scope']
        installed=self.f.get(install,reader)
        acquired=self.f.get(acquire,reader)
        acquired_result=json.loads(acquired['original_result_wire'])
        fence=acquired_result['result_body']['original_fence_record']
        before_resume=scoped_rows(self.f,scope)
        absent=self.f.get(resume,reader)
        self.assertEqual('observed_absent_unknown',absent['resolution'])
        writer=self.f.writer(control)
        try:
            writer.send(self.f.call('submit',resume,control))
            provisional=json.loads(writer.line())
            self.assertTrue(provisional['pending_commit'])
            self.assertEqual(sha(canonical(resume)),provisional['original_command_sha256'])
            self.assertEqual(absent,self.f.get(resume,reader))
            writer.finish()
        finally:
            writer.close()
        reply=self.f.get(resume,reader)
        result,receipt=self.assert_committed(resume,reply,3)
        self.assertEqual(dict(previous_mode='paused',resulting_mode='open',previous_control_sha256=None,
            resulting_fence_revision='1'),result['result_body'])
        self.assertLessEqual(int(fence['issued_at_us']),int(receipt['final_function_observation']['observed_at_us']))
        self.assertLess(int(receipt['commit_processing_observation']['observed_at_us']),int(fence['expires_at_us']))
        head=self.f.head(self.s)
        self.assertEqual(('open',fence['fence_id'],'1','3'),
            tuple(head[key] for key in ('source_mode','active_fence_id','fence_revision','native_sequence')))
        acquire_command_pin=observed_pin('native_command',acquire['action_id'],canonical(acquire))
        direct=ordered_pins(acquired_result['dependencies']+[acquire_command_pin])
        self.assertEqual(6,len(direct))
        self.assertEqual(direct,result['dependencies'])
        wire_fields=(('native_command','original_command_wire'),('native_result','original_result_wire'),
            ('native_receipt','original_receipt_wire'))
        closure=ordered_pins(acquired['dependencies']+
            [observed_pin(kind,acquire['action_id'],acquired[field]) for kind,field in wire_fields])
        self.assertEqual(10,len(closure))
        self.assertEqual(closure,reply['dependencies'])
        after_resume=scoped_rows(self.f,scope)
        self.assertEqual(before_resume['domain_facts'],after_resume['domain_facts'])
        identities=[row for row in after_resume['identities'] if row['original_id']==resume['action_id']]
        self.assertEqual(1,len(identities))
        self.assertEqual(dict(original_id=resume['action_id'],identity_role='control_action_id',
            association=scope|dict(packet_reservation_id=None),original_allocation_sha256=sha(canonical(resume)),
            first_native_sequence='3'),json.loads(identities[0]['record_wire']))
        self.assertEqual(48,sum(map(len,after_resume.values())))

        stop=self.open_stop_command(resume)
        self.assertEqual(self.s['stop_id'],stop['action_id'])
        for key,value in (('expected_mode','paused'),('expected_control_sha256','f'*64)):
            with self.subTest(key=key):
                altered=copy.deepcopy(stop)
                altered['body'][key]=value
                self.refusal(altered,'b2_Stop_refused',profile='control')
        self.submit(stop)
        stop_reply=self.f.get(stop,reader)
        stopped,_=self.assert_committed(stop,stop_reply,4)
        self.assertEqual(dict(previous_mode='open',resulting_mode='stopped',
            previous_control_sha256=sha(canonical(resume)),resulting_fence_revision='2'),stopped['result_body'])
        stop_direct=ordered_pins(acquired_result['dependencies']+
            [observed_pin('native_command',resume['action_id'],canonical(resume))])
        self.assertEqual(6,len(stop_direct))
        self.assertEqual(stop_direct,stopped['dependencies'])
        stop_closure=ordered_pins(closure+
            [observed_pin(kind,resume['action_id'],reply[field]) for kind,field in wire_fields])
        self.assertEqual(13,len(stop_closure))
        self.assertEqual(stop_closure,stop_reply['dependencies'])
        raw=self.db.sql(SETTINGS+self.f.call('get_original',self.f.query(stop),reader),role=reader).stdout
        self.assertEqual(canonical(stop_reply)+'\n',raw)
        self.assertLessEqual(len(raw.encode('utf8')),8388608)
        head=self.f.head(self.s)
        self.assertEqual(('stopped',None,'2','4'),
            tuple(head[key] for key in ('source_mode','active_fence_id','fence_revision','native_sequence')))
        after_stop=scoped_rows(self.f,scope)
        self.assertEqual(after_resume['domain_facts'],after_stop['domain_facts'])
        self.assertEqual(after_resume['identities'],after_stop['identities'])
        self.assertEqual(56,sum(map(len,after_stop.values())))
        final=json.loads(after_stop['scope_state'][0]['accounting_wire'])
        self.assertEqual(dict(committed_positions='4',identity_rows='18',domain_rows='4',dependency_rows='20',
            retained_rows='56',row_writes='54',index_entries='108',Stop_reserve_consumed=True),
            {key:value for key,value in final.items() if key!='logical_UTF8_bytes'})
        self.assertEqual((58,120),(int(final['row_writes'])+len(after_stop['original_operations']),
            int(final['index_entries'])+3*len(after_stop['original_operations'])))
        for command,before,after,writes,keys in ((resume,before_resume,after_resume,10,20),(stop,after_resume,after_stop,9,18)):
            selected=[observed_row_charge('scope_state',after['scope_state'][0],scope)]
            selected += [observed_row_charge(name,row,scope)
                for name in ('original_operations','journal_entries','dependency_associations')
                for row in after[name] if row['action_id']==command['action_id']]
            selected += [observed_row_charge('identities',row,scope)
                for row in after['identities'] if row['original_id']==command['action_id'] and command is resume]
            self.assertEqual((writes,keys),(len(selected),sum(row['keys'] for row in selected)))
            prior=json.loads(before['scope_state'][0]['accounting_wire'])
            updated=json.loads(after['scope_state'][0]['accounting_wire'])
            self.assertGreaterEqual(int(updated['logical_UTF8_bytes'])-int(prior['logical_UTF8_bytes']),
                sum(row['bytes'] for row in selected))
        pending=sum(observed_row_charge('original_operations',row|dict(receipt_wire=None,receipt_sha256=None,finalized=False),
            scope)['bytes'] for row in after_stop['original_operations'])
        self.assertLessEqual(int(final['logical_UTF8_bytes'])+pending,
            self.f.policy['finite_caps_per_scope']['encoded_row_DML_UTF8_upper_charged'])
        intermediate=json.loads(after_resume['scope_state'][0]['accounting_wire'])
        self.assertFalse(intermediate['Stop_reserve_consumed'])
        self.assertLessEqual(int(intermediate['logical_UTF8_bytes'])+self.f.policy['Stop_reserve_vector']['logical_UTF8_bytes'],
            self.f.policy['finite_caps_per_scope']['logical_UTF8_bytes_charged'])
        immutable=self.f.snapshot()
        for command,old in ((install,installed),(acquire,acquired),(resume,reply),(stop,stop_reply)):
            saved=self.f.get(command,reader)
            for field in ('original_command_wire','original_result_wire','original_receipt_wire','dependencies'):
                self.assertEqual(old[field],saved[field])
            replay=json.loads(self.db.scalar(SETTINGS+self.f.call('submit',command,reader),role=reader))
            self.assertEqual(saved,replay)
        self.assertEqual(immutable,self.f.snapshot())

    def test_resume_refuses_wrong_actor_hold_body_identity_and_mode(self):
        self.submit(self.f.command(self.s))
        self.refusal(self.resume_command(),'b2_Resume_refused',profile='control')
        acquire=self.acquire_command()
        self.submit(acquire,'recorder')
        resume=self.resume_command()
        for profile in ('installer','recorder','reader'):
            self.refusal(resume,'b2_actor_scope_refused',profile=profile)
        foreign=self.other['actors']['control']
        before=self.f.snapshot()
        result=self.db.sql(BEGIN+SETTINGS+self.f.call('submit',resume,foreign)+'COMMIT;\n',role=foreign,check=False)
        self.assertNotEqual(0,result.returncode)
        self.assertIn('b2_actor_scope_refused',result.stderr)
        self.assertEqual(before,self.f.snapshot())
        for field,value in (('expected_fence_id',None),('expected_fence_id',self.other['epoch']),
            ('expected_fence_revision',1),('expected_fence_revision','0'),('expected_head',acquire['expected_head'])):
            with self.subTest(field=field,value=value):
                altered=copy.deepcopy(resume)
                altered[field]=value
                self.refusal(altered,'b2_stale_head',profile='control')
        for field,value in (('expected_control_sha256','a'*64),('expected_mode','open'),('holder_principal_binding_id',self.s['bindings']['recorder'])):
            with self.subTest(field=field):
                altered=copy.deepcopy(resume)
                altered['body'][field]=value
                self.refusal(altered,'b2_Resume_refused',profile='control')
        reserved=copy.deepcopy(resume)
        reserved['action_id']=self.s['stop_id']
        self.refusal(reserved,'b2_identity_conflict',profile='control')
        self.submit(resume)
        self.refusal(self.resume_command(action_number=994002),'b2_Resume_refused',profile='control')
        self.submit(self.open_stop_command(resume))
        self.refusal(self.resume_command(action_number=994003),'b2_Resume_refused',profile='control')

    def test_resume_locks_recorder_binding_and_rolls_back_but_open_stop_does_not_wait(self):
        self.install_and_acquire_for_resume()
        resume=self.resume_command()
        role=self.s['actors']['control']
        scope_wire=literal(canonical(self.s['scope']))
        binding=literal(self.s['bindings']['recorder'])
        predicate=f'scope_wire={scope_wire} AND binding_id={binding}'
        before=self.f.snapshot()
        writer=self.f.writer(role)
        recorder_lock=self.f.anchor_session()
        try:
            writer_pid=writer.backend_pid()
            waiter_pid=recorder_lock.backend_pid()
            writer.send(self.f.call('submit',resume,role))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            recorder_lock.send(f"SELECT 'locked' FROM {A}.actor_bindings WHERE {predicate} FOR UPDATE;\n")
            self.f.wait_for_blocker(waiter_pid,writer_pid)
            writer.finish('ROLLBACK;')
            self.assertEqual('locked',recorder_lock.line())
            recorder_lock.finish('ROLLBACK;')
        finally:
            writer.close()
            recorder_lock.close()
        self.assertEqual(before,self.f.snapshot())
        self.assertEqual('observed_absent_unknown',self.f.get(resume,self.s['actors']['reader'])['resolution'])
        staged=self.resume_command(action_number=994011)
        self.refusal(staged,'b2_commit_form_refused',profile='control',suffix='SET CONSTRAINTS ALL IMMEDIATE;\nCOMMIT;\n')
        next_resume=self.resume_command(action_number=994012)
        self.submit(next_resume)
        stop=self.open_stop_command(next_resume)
        recorder_lock=self.f.anchor_session()
        try:
            recorder_lock.send(f"SELECT 'locked' FROM {A}.actor_bindings WHERE {predicate} FOR UPDATE;\n")
            self.assertEqual('locked',recorder_lock.line())
            self.submit(stop)
            recorder_lock.finish('ROLLBACK;')
        finally:
            recorder_lock.close()
        self.assert_committed(stop,self.f.get(stop,self.s['actors']['reader']),4)

    def test_resume_rechecks_recorder_binding_after_lock_wait(self):
        self.install_and_acquire_for_resume()
        resume=self.resume_command()
        role=self.s['actors']['control']
        predicate=f"scope_wire={literal(canonical(self.s['scope']))} AND binding_id={literal(self.s['bindings']['recorder'])}"
        before=[row for row in self.f.snapshot() if row[0]==N]
        trusted=self.f.anchor_session()
        writer=self.f.writer(role)
        try:
            blocker_pid=trusted.backend_pid()
            writer_pid=writer.backend_pid()
            trusted.send(f"UPDATE {A}.actor_bindings SET capabilities=ARRAY['read_original'] WHERE {predicate} RETURNING 'held';\n")
            self.assertEqual('held',trusted.line())
            writer.send(self.f.call('submit',resume,role))
            self.f.wait_for_blocker(writer_pid,blocker_pid)
            trusted.finish()
            with self.assertRaisesRegex(RuntimeError,'b2_actor_scope_refused'):
                writer.line()
        finally:
            writer.close()
            trusted.close()
            self.db.sql(f"UPDATE {A}.actor_bindings SET capabilities=ARRAY['reserve','fence_manage','read_original'] WHERE {predicate};")
        self.assertEqual(before,[row for row in self.f.snapshot() if row[0]==N])
        self.assertEqual('observed_absent_unknown',self.f.get(resume,self.s['actors']['reader'])['resolution'])

    def test_resume_real_expiry_refuses_commit_and_fresh_resume_but_preserves_stop(self):
        _,acquire=self.install_and_acquire_for_resume()
        reader=self.s['actors']['reader']
        role=self.s['actors']['control']
        acquired=json.loads(self.f.get(acquire,reader)['original_result_wire'])
        expiry=int(acquired['result_body']['original_fence_record']['expires_at_us'])
        resume=self.resume_command()
        before=self.f.snapshot()
        # This read waits for the actual accepted database-clock deadline with
        # margin for the existing transaction and idle bounds. No clock or
        # fence record is overridden. The ordinary writer has its same limits.
        self.db.scalar(f"SELECT pg_catalog.pg_sleep_until(pg_catalog.to_timestamp(({expiry}-4500000)::numeric/1000000));",timeout=60)
        writer=self.f.writer(role)
        try:
            writer.send(self.f.call('submit',resume,role))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            self.db.scalar(f"SELECT pg_catalog.pg_sleep_until(pg_catalog.to_timestamp(({expiry}+100000)::numeric/1000000));",timeout=8)
            code,stderr=writer.finish(check=False)
            self.assertNotEqual(0,code)
            self.assertIn('b2_fence_clock_refused',stderr)
        finally:
            writer.close()
        self.assertEqual(before,self.f.snapshot())
        self.assertEqual('observed_absent_unknown',self.f.get(resume,reader)['resolution'])
        fresh=self.resume_command(action_number=994021)
        self.refusal(fresh,'b2_fence_clock_refused',profile='control')
        stop=self.f.command(self.s,'source_stop')
        self.submit(stop)
        self.assert_committed(stop,self.f.get(stop,reader),3)


    def test_renew_versions_same_identity_and_stop_uses_seven_direct_pins(self):
        install,acquire=self.install_and_acquire_for_resume()
        resume=self.resume_command()
        self.submit(resume)
        reader=self.s['actors']['reader']
        recorder=self.s['actors']['recorder']
        scope=self.s['scope']
        installed=self.f.get(install,reader)
        acquired=self.f.get(acquire,reader)
        resumed=self.f.get(resume,reader)
        acquire_result=json.loads(acquired['original_result_wire'])
        resume_receipt=json.loads(resumed['original_receipt_wire'])
        old_fence=acquire_result['result_body']['original_fence_record']
        old_pin=observed_pin('native_fence_record',old_fence['fence_id'],canonical(old_fence))
        renew=self.f.command(self.s,'fence_renew',action_id=str(UUID(int=995001)))
        renew['expected_fence_id']=old_fence['fence_id']
        renew['expected_fence_revision']='1'
        renew['body']=dict(fence_id=old_fence['fence_id'],expected_revision='1',requested_duration_us='60000000')
        before=self.f.snapshot()
        reused=copy.deepcopy(renew)
        reused['action_id']=old_fence['fence_id']
        wrong_revision=copy.deepcopy(renew)
        wrong_revision['body']['expected_revision']=1
        for command,role,reason in (
            (renew,self.s['actors']['control'],'b2_actor_scope_refused'),
            (reused,recorder,'b2_identity_conflict'),
            (wrong_revision,recorder,'b2_fence_renew_refused'),
        ):
            outcome=self.db.sql(BEGIN+SETTINGS+self.f.call('submit',command,role)+'COMMIT;\n',role=role,check=False)
            self.assertNotEqual(0,outcome.returncode)
            self.assertIn(reason,outcome.stderr)
        self.assertEqual(before,self.f.snapshot())
        before_renew=scoped_rows(self.f,scope)
        writer=self.f.writer(recorder)
        try:
            writer.send(self.f.call('submit',renew,recorder))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            self.assertEqual('observed_absent_unknown',self.f.get(renew,reader)['resolution'])
            writer.finish()
        finally:
            writer.close()
        renewed=self.f.get(renew,reader)
        result,receipt=self.assert_committed(renew,renewed,4)
        new_fence=result['result_body']['original_fence_record']
        issued=int(new_fence['issued_at_us'])
        self.assertEqual(dict(fence_id=old_fence['fence_id'],scope=scope,
            holder_principal_binding_id=self.s['bindings']['recorder'],acquisition_epoch=self.s['epoch'],
            revision='2',issued_at_us=str(issued),expires_at_us=str(issued+60_000_000),
            original_command_sha256=sha(canonical(renew)),native_sequence='4'),new_fence)
        self.assertEqual(old_pin['wire_sha256'],result['result_body']['previous_fence_sha256'])
        self.assertLessEqual(int(resume_receipt['commit_processing_observation']['observed_at_us']),issued)
        self.assertLessEqual(issued,int(receipt['final_function_observation']['observed_at_us']))
        self.assertLess(int(receipt['commit_processing_observation']['observed_at_us']),int(old_fence['expires_at_us']))
        new_pin=observed_pin('native_fence_record',new_fence['fence_id'],canonical(new_fence))
        self.assertNotEqual(old_pin['wire_sha256'],new_pin['wire_sha256'])
        install_pin=observed_pin('native_command',install['action_id'],canonical(install))
        resume_pin=observed_pin('native_command',resume['action_id'],canonical(resume))
        renew_pin=observed_pin('native_command',renew['action_id'],canonical(renew))
        expected=ordered_pins(installed['dependencies']+[install_pin,resume_pin,old_pin,new_pin])
        self.assertEqual(7,len(expected))
        self.assertEqual(expected,result['dependencies'])
        fields=(('native_command','original_command_wire'),('native_result','original_result_wire'),
            ('native_receipt','original_receipt_wire'))
        closure=ordered_pins(resumed['dependencies']+[new_pin]+
            [observed_pin(kind,resume['action_id'],resumed[field]) for kind,field in fields])
        self.assertEqual(14,len(closure))
        self.assertEqual(closure,renewed['dependencies'])
        head=self.f.head(self.s)
        self.assertEqual(('open',old_fence['fence_id'],'2','4'),
            tuple(head[key] for key in ('source_mode','active_fence_id','fence_revision','native_sequence')))
        after_renew=scoped_rows(self.f,scope)
        self.assertEqual(59,sum(map(len,after_renew.values())))
        by_id=lambda rows,identity:[row for row in rows['identities'] if row['original_id']==identity]
        self.assertEqual(by_id(before_renew,old_fence['fence_id']),by_id(after_renew,new_fence['fence_id']))
        self.assertEqual(1,len(by_id(after_renew,new_fence['fence_id'])))
        identity,=by_id(after_renew,renew['action_id'])
        self.assertEqual(dict(original_id=renew['action_id'],identity_role='native_operation_id',
            association=scope|dict(packet_reservation_id=None),original_allocation_sha256=sha(canonical(renew)),
            first_native_sequence='4'),json.loads(identity['record_wire']))
        facts=[row for row in after_renew['domain_facts'] if row['original_id']==new_fence['fence_id']]
        self.assertEqual({('2',old_pin['wire_sha256'],old_pin['original_wire']),
            ('4',new_pin['wire_sha256'],new_pin['original_wire'])},
            {(str(row['native_sequence']),row['wire_sha256'],row['original_wire']) for row in facts})
        accounting=json.loads(after_renew['scope_state'][0]['accounting_wire'])
        reserve=self.f.policy['Stop_reserve_vector']
        caps=self.f.policy['finite_caps_per_scope']
        self.assertFalse(accounting['Stop_reserve_consumed'])
        dimensions=(
            ('committed_positions','native_position_increments','committed_events'),
            ('logical_UTF8_bytes','logical_UTF8_bytes','logical_UTF8_bytes_charged'),
            ('retained_rows','new_retained_rows','logical_retained_rows'),
            ('dependency_rows','new_dependency_associations','dependency_association_rows'),
            ('row_writes','logical_row_writes','logical_row_writes_charged'),
            ('index_entries','logical_index_entries','logical_index_entries_charged'),
        )
        for field,margin,cap in dimensions:
            self.assertLessEqual(int(accounting[field])+reserve[margin],caps[cap])
        self.assertLessEqual(int(accounting['row_writes'])+4+reserve['row_DML_touches'],caps['row_DML_touches_charged'])
        self.assertLessEqual(int(accounting['index_entries'])+12+reserve['declared_index_key_touches'],
            caps['declared_index_key_touches_charged'])

        stop=self.open_stop_command(resume)
        self.assertEqual(self.s['stop_id'],stop['action_id'])
        self.submit(stop)
        stopped=self.f.get(stop,reader)
        stop_result,_=self.assert_committed(stop,stopped,5)
        self.assertEqual(dict(previous_mode='open',resulting_mode='stopped',
            previous_control_sha256=sha(canonical(resume)),resulting_fence_revision='3'),stop_result['result_body'])
        stop_expected=ordered_pins(installed['dependencies']+[install_pin,resume_pin,renew_pin,new_pin])
        self.assertEqual(7,len(stop_expected))
        self.assertEqual(stop_expected,stop_result['dependencies'])
        stop_closure=ordered_pins(closure+
            [observed_pin(kind,renew['action_id'],renewed[field]) for kind,field in fields])
        self.assertEqual(17,len(stop_closure))
        self.assertEqual(stop_closure,stopped['dependencies'])
        raw=self.db.sql(SETTINGS+self.f.call('get_original',self.f.query(stop),reader),role=reader).stdout
        self.assertEqual(canonical(stopped)+'\n',raw)
        self.assertLessEqual(len(raw.encode('utf8')),8388608)
        head=self.f.head(self.s)
        self.assertEqual(('stopped',None,'3','5'),
            tuple(head[key] for key in ('source_mode','active_fence_id','fence_revision','native_sequence')))
        after_stop=scoped_rows(self.f,scope)
        self.assertEqual(after_renew['domain_facts'],after_stop['domain_facts'])
        self.assertEqual(after_renew['identities'],after_stop['identities'])
        self.assertEqual(68,sum(map(len,after_stop.values())))
        final=json.loads(after_stop['scope_state'][0]['accounting_wire'])
        self.assertEqual(dict(committed_positions='5',identity_rows='19',domain_rows='5',dependency_rows='28',
            retained_rows='68',row_writes='67',index_entries='134',Stop_reserve_consumed=True),
            {key:value for key,value in final.items() if key!='logical_UTF8_bytes'})
        self.assertEqual((72,149),(int(final['row_writes'])+len(after_stop['original_operations']),
            int(final['index_entries'])+3*len(after_stop['original_operations'])))
        for command,prior_rows,current_rows,logical_rows,logical_keys in (
            (renew,before_renew,after_renew,12,24),(stop,after_renew,after_stop,10,20),
        ):
            selected=[observed_row_charge('scope_state',current_rows['scope_state'][0],scope)]
            selected.extend(observed_row_charge(name,row,scope)
                for name in ('original_operations','journal_entries','dependency_associations')
                for row in current_rows[name] if row['action_id']==command['action_id'])
            if command is renew:
                selected.append(observed_row_charge('identities',identity,scope))
                selected.append(observed_row_charge('domain_facts',next(row for row in facts if
                    row['wire_sha256']==new_pin['wire_sha256']),scope))
            self.assertEqual((logical_rows,logical_keys),(len(selected),sum(row['keys'] for row in selected)))
            old_accounting=json.loads(prior_rows['scope_state'][0]['accounting_wire'])
            new_accounting=json.loads(current_rows['scope_state'][0]['accounting_wire'])
            logical=int(new_accounting['logical_UTF8_bytes'])-int(old_accounting['logical_UTF8_bytes'])
            self.assertGreaterEqual(logical,sum(row['bytes'] for row in selected))
            if command is stop:
                pending,=(row for row in current_rows['original_operations'] if row['action_id']==stop['action_id'])
                stage=observed_row_charge('original_operations',
                    pending|dict(receipt_wire=None,receipt_sha256=None,finalized=False),scope)
                self.assertLessEqual(logical,reserve['logical_UTF8_bytes'])
                self.assertLessEqual(logical+stage['bytes'],reserve['encoded_row_DML_UTF8_upper'])
        immutable=self.f.snapshot()
        for command,saved in ((install,installed),(acquire,acquired),(resume,resumed),(renew,renewed),(stop,stopped)):
            replay=json.loads(self.db.scalar(SETTINGS+self.f.call('submit',command,reader),role=reader))
            for field in ('original_command_wire','original_result_wire','original_receipt_wire','dependencies'):
                self.assertEqual(saved[field],replay[field])
        self.assertEqual(immutable,self.f.snapshot())


    def test_renew_late_commit_refuses_old_expiry_before_new_expiry_and_open_stop_succeeds(self):
        _,acquire=self.install_and_acquire_for_resume()
        reader=self.s['actors']['reader']
        recorder=self.s['actors']['recorder']
        acquired=json.loads(self.f.get(acquire,reader)['original_result_wire'])
        old_fence=acquired['result_body']['original_fence_record']
        old_issued=int(old_fence['issued_at_us'])
        old_expiry=int(old_fence['expires_at_us'])
        duration=60_000_000
        self.assertEqual(old_issued+duration,old_expiry)

        def database_clock_us(*, wait_until_us=None, timeout=10):
            # This trusted test read samples the actual clock used by the
            # owned PostgreSQL engine. It never supplies a clock to submit.
            wait=''
            if wait_until_us is not None:
                wait=f"SELECT pg_catalog.pg_sleep_until(pg_catalog.to_timestamp({wait_until_us}::numeric/1000000));\n"
            sample="SELECT pg_catalog.floor(EXTRACT(epoch FROM pg_catalog.clock_timestamp())*1000000)::bigint;"
            return int(self.db.scalar(wait+sample,timeout=timeout))

        resume_after=old_issued+10_000_000
        self.assertGreaterEqual(database_clock_us(wait_until_us=resume_after,timeout=20),resume_after)
        resume=self.resume_command()
        self.submit(resume)
        resume_reply=self.f.get(resume,reader)
        _,resume_receipt=self.assert_committed(resume,resume_reply,3)
        resume_commit=int(resume_receipt['commit_processing_observation']['observed_at_us'])
        self.assertLessEqual(resume_after,resume_commit)
        self.assertLess(resume_commit,old_expiry)

        # V16 accepts a provisional Renew only when its issuance is at or
        # after this exact Resume COMMIT observation. Its duration is fixed.
        # This lower bound requires no read of the writer's staged fence.
        earliest_new_expiry=resume_commit+duration
        renew=self.f.command(self.s,'fence_renew',action_id=str(UUID(int=996001)))
        renew['expected_fence_id']=old_fence['fence_id']
        renew['expected_fence_revision']='1'
        renew['body']=dict(fence_id=old_fence['fence_id'],expected_revision='1',requested_duration_us=str(duration))
        before=self.f.snapshot()
        absent=self.f.get(renew,reader)
        self.assertEqual('observed_absent_unknown',absent['resolution'])
        self.assertIsNone(absent['original_operation_pin'])
        self.assertEqual(renew['expected_head'],absent['observed_head'])

        stage_after=old_expiry-5_500_000
        self.assertLess(database_clock_us(wait_until_us=stage_after,timeout=60),old_expiry)
        writer=self.f.writer(recorder)
        try:
            before_submit=database_clock_us()
            self.assertLessEqual(stage_after,before_submit)
            self.assertLess(before_submit,old_expiry)
            writer.send(self.f.call('submit',renew,recorder))
            pending=json.loads(writer.line())
            self.assertTrue(pending['pending_commit'])
            self.assertEqual(sha(canonical(renew)),pending['original_command_sha256'])
            self.assertEqual(absent,self.f.get(renew,reader))
            after_provisional=database_clock_us()
            self.assertLessEqual(before_submit,after_provisional)
            self.assertLess(after_provisional,old_expiry)

            before_commit=database_clock_us(wait_until_us=old_expiry+100_000,timeout=8)
            self.assertGreaterEqual(before_commit,old_expiry+100_000)
            self.assertLess(before_commit,earliest_new_expiry)
            code,stderr=writer.finish(check=False)
            after_commit=database_clock_us()
            self.assertLessEqual(before_commit,after_commit)
            self.assertLess(after_commit,earliest_new_expiry)
            self.assertNotEqual(0,code)
            self.assertRegex(stderr,r'(?m)^ERROR:\s+P0001: b2_fence_clock_refused\s*$')
            self.assertIn('._commit_guard()',stderr)
        finally:
            writer.close()

        self.assertEqual(before,self.f.snapshot())
        self.assertEqual(absent,self.f.get(renew,reader))
        fresh=copy.deepcopy(renew)
        fresh['action_id']=str(UUID(int=996002))
        refusal=self.refusal(fresh,'b2_fence_clock_refused',profile='recorder')
        self.assertRegex(refusal.stderr,r'(?m)^ERROR:\s+P0001: b2_fence_clock_refused\s*$')
        self.assertEqual('',refusal.stdout.strip())
        self.assertEqual('observed_absent_unknown',self.f.get(fresh,reader)['resolution'])

        stop=self.open_stop_command(resume)
        self.assertEqual(self.s['stop_id'],stop['action_id'])
        self.submit(stop)
        result,_=self.assert_committed(stop,self.f.get(stop,reader),4)
        self.assertEqual(dict(previous_mode='open',resulting_mode='stopped',
            previous_control_sha256=sha(canonical(resume)),resulting_fence_revision='2'),result['result_body'])
        head=self.f.head(self.s)
        self.assertEqual(('stopped',None,'2','4'),
            tuple(head[key] for key in ('source_mode','active_fence_id','fence_revision','native_sequence')))
        self.assertEqual('observed_absent_unknown',self.f.get(renew,reader)['resolution'])


    def test_repeated_renew_reaches_position_reserve_and_original_stop_16(self):
        install,acquire=self.install_and_acquire_for_resume()
        resume=self.resume_command()
        self.submit(resume)
        reader=self.s['actors']['reader']
        recorder=self.s['actors']['recorder']
        scope=self.s['scope']
        installed=self.f.get(install,reader)
        acquired=self.f.get(acquire,reader)
        resumed=self.f.get(resume,reader)
        old_fence=json.loads(acquired['original_result_wire'])['result_body']['original_fence_record']
        fence_id=old_fence['fence_id']
        previous_fence=old_fence
        previous_commit=int(json.loads(resumed['original_receipt_wire'])['commit_processing_observation']['observed_at_us'])
        previous_command=resume
        fields=(('native_command','original_command_wire'),('native_result','original_result_wire'),
            ('native_receipt','original_receipt_wire'))
        fixed=installed['dependencies']
        installation_pin=observed_pin('native_command',install['action_id'],canonical(install))
        resume_pin=observed_pin('native_command',resume['action_id'],canonical(resume))
        prior_pins=[observed_pin(kind,command['action_id'],reply[field])
            for command,reply in ((install,installed),(acquire,acquired),(resume,resumed)) for kind,field in fields]
        fence_pins=[observed_pin('native_fence_record',fence_id,canonical(old_fence))]
        originals=[]

        def renew_command(position, fence):
            command=self.f.command(self.s,'fence_renew',action_id=str(UUID(int=997000+position)))
            command['expected_fence_id']=fence_id
            command['expected_fence_revision']=fence['revision']
            command['body']=dict(fence_id=fence_id,expected_revision=fence['revision'],requested_duration_us='60000000')
            return command

        for position in range(4,16):
            with self.subTest(position=position):
                command=renew_command(position,previous_fence)
                provisional=self.submit(command,'recorder')
                self.assertTrue(provisional['pending_commit'])
                self.assertEqual(sha(canonical(command)),provisional['original_command_sha256'])
                reply=self.f.get(command,reader)
                self.assertEqual(canonical(command),reply['original_command_wire'])
                result=json.loads(reply['original_result_wire'])
                receipt=json.loads(reply['original_receipt_wire'])
                self.assertEqual((command['action_id'],str(position),sha(canonical(command))),
                    (result['action_id'],result['native_sequence'],result['original_command_sha256']))
                self.assertEqual(sha(reply['original_result_wire']),receipt['result_sha256'])
                self.assertEqual(command['expected_head']['native_head_sha256'],receipt['previous_native_head_sha256'])
                fence=result['result_body']['original_fence_record']
                issued=int(fence['issued_at_us'])
                self.assertEqual(dict(fence_id=fence_id,scope=scope,
                    holder_principal_binding_id=self.s['bindings']['recorder'],acquisition_epoch=self.s['epoch'],
                    revision=str(position-2),issued_at_us=str(issued),expires_at_us=str(issued+60_000_000),
                    original_command_sha256=sha(canonical(command)),native_sequence=str(position)),fence)
                final=int(receipt['final_function_observation']['observed_at_us'])
                commit=int(receipt['commit_processing_observation']['observed_at_us'])
                self.assertLessEqual(previous_commit,issued)
                self.assertLessEqual(issued,final)
                self.assertLessEqual(final,commit)
                self.assertLess(commit,int(previous_fence['expires_at_us']))
                new_pin=observed_pin('native_fence_record',fence_id,canonical(fence))
                self.assertEqual(fence_pins[-1]['wire_sha256'],result['result_body']['previous_fence_sha256'])
                prior_pin=observed_pin('native_command',previous_command['action_id'],canonical(previous_command))
                self.assertEqual(ordered_pins(fixed+[installation_pin,prior_pin,fence_pins[-1],new_pin]),
                    result['dependencies'])
                fence_pins.append(new_pin)
                self.assertEqual(ordered_pins(fixed+fence_pins+prior_pins),reply['dependencies'])
                self.assertEqual(str(position),reply['observed_head']['native_sequence'])
                prior_pins.extend(observed_pin(kind,command['action_id'],reply[field]) for kind,field in fields)
                originals.append((command,reply))
                previous_fence=fence
                previous_commit=commit
                previous_command=command
        self.assertEqual(12,len(originals))
        self.assertEqual(58,len(originals[-1][1]['dependencies']))
        self.assertEqual(13,len({pin['wire_sha256'] for pin in fence_pins}))

        before_stop=scoped_rows(self.f,scope)
        accounting=json.loads(before_stop['scope_state'][0]['accounting_wire'])
        self.assertEqual(dict(committed_positions='15',identity_rows='30',domain_rows='16',dependency_rows='98',
            retained_rows='180',row_writes='189',index_entries='378',Stop_reserve_consumed=False),
            {key:value for key,value in accounting.items() if key!='logical_UTF8_bytes'})
        self.assertEqual(180,sum(map(len,before_stop.values())))
        self.assertEqual(1,sum(row['original_id']==fence_id for row in before_stop['identities']))
        actual_versions={(row['wire_sha256'],row['original_wire']) for row in before_stop['domain_facts']
            if row['original_id']==fence_id}
        self.assertEqual({(pin['wire_sha256'],pin['original_wire']) for pin in fence_pins},actual_versions)

        # Independent projected ordinary Renew row vector. A second slot for
        # original Stop is the sole failing predicate in the frozen budget.
        caps=self.f.policy['finite_caps_per_scope']
        reserve=self.f.policy['Stop_reserve_vector']
        def projected(field, ordinary, terminal, cap):
            self.assertLessEqual(int(accounting[field])+ordinary+terminal,caps[cap])

        projected('retained_rows',11,reserve['new_retained_rows'],'logical_retained_rows')
        projected('identity_rows',1,0,'retained_identity_rows')
        self.assertLessEqual(int(accounting['domain_rows'])+1,25)
        self.assertLessEqual(len(fence_pins)+1,caps['fence_record_versions'])
        projected('dependency_rows',7,reserve['new_dependency_associations'],'dependency_association_rows')
        self.assertEqual(112,int(accounting['dependency_rows'])+7+reserve['new_dependency_associations'])
        projected('row_writes',12,reserve['logical_row_writes'],'logical_row_writes_charged')
        projected('index_entries',24,reserve['logical_index_entries'],'logical_index_entries_charged')
        projected('row_writes',15+13,reserve['row_DML_touches'],'row_DML_touches_charged')
        projected('index_entries',3*15+27,reserve['declared_index_key_touches'],'declared_index_key_touches_charged')
        wire_caps=self.f.policy['wire_caps_UTF8']
        # Each closed row's metadata and key encodings (and the single
        # identity wire) fit 4 KiB. Separate raw C/R/T/journal/head/accounting
        # and the new fence charge are conservatively paid at their wire caps.
        row_overhead=4096
        new_logical_upper=12*row_overhead+sum(wire_caps[key] for key in (
            'command','result','receipt','journal','scope_head','accounting','native_fence_record'))
        stage_upper=wire_caps['command']+wire_caps['result']+row_overhead
        projected('logical_UTF8_bytes',new_logical_upper,reserve['logical_UTF8_bytes'],'logical_UTF8_bytes_charged')
        projected('logical_UTF8_bytes',new_logical_upper+16*stage_upper,reserve['encoded_row_DML_UTF8_upper'],
            'encoded_row_DML_UTF8_upper_charged')
        self.assertEqual(17,int(accounting['committed_positions'])+1+reserve['native_position_increments'])
        self.assertEqual(16,caps['committed_events'])

        over=renew_command(16,previous_fence)
        self.assertEqual('15',over['expected_head']['native_sequence'])
        self.assertEqual('13',over['expected_fence_revision'])
        clock_sql="SELECT pg_catalog.floor(EXTRACT(epoch FROM pg_catalog.clock_timestamp())*1000000)::bigint;"
        expiry=int(previous_fence['expires_at_us'])
        self.assertLess(int(self.db.scalar(clock_sql)),expiry)
        rejected=self.refusal(over,'b2_budget_refused',profile='recorder')
        self.assertRegex(rejected.stderr,r'(?m)^ERROR:\s+P0001: b2_budget_refused\s*$')
        self.assertLess(int(self.db.scalar(clock_sql)),expiry)
        absent=self.f.get(over,reader)
        self.assertEqual('observed_absent_unknown',absent['resolution'])
        self.assertEqual(over['expected_head'],absent['observed_head'])
        self.assertIsNone(absent['original_operation_pin'])

        stop=self.open_stop_command(resume)
        self.assertEqual(self.s['stop_id'],stop['action_id'])
        self.assertEqual(over['expected_head'],stop['expected_head'])
        self.submit(stop)
        stopped=self.f.get(stop,reader)
        result,_=self.assert_committed(stop,stopped,16)
        self.assertEqual(dict(previous_mode='open',resulting_mode='stopped',
            previous_control_sha256=sha(canonical(resume)),resulting_fence_revision='14'),result['result_body'])
        latest_renew_pin=observed_pin('native_command',previous_command['action_id'],canonical(previous_command))
        direct=ordered_pins(fixed+[installation_pin,resume_pin,latest_renew_pin,fence_pins[-1]])
        self.assertEqual(7,len(direct))
        self.assertEqual(direct,result['dependencies'])
        self.assertEqual(61,len(stopped['dependencies']))
        self.assertEqual(ordered_pins(fixed+fence_pins+prior_pins),stopped['dependencies'])
        wire=self.db.sql(SETTINGS+self.f.call('get_original',self.f.query(stop),reader),role=reader).stdout
        self.assertEqual(canonical(stopped)+'\n',wire)
        self.assertLessEqual(len(wire.encode('utf8')),caps['getter_reply_UTF8_bytes'])
        head=self.f.head(self.s)
        self.assertEqual(('stopped',None,'14','16'),
            tuple(head[key] for key in ('source_mode','active_fence_id','fence_revision','native_sequence')))

        after_stop=scoped_rows(self.f,scope)
        self.assertEqual(before_stop['identities'],after_stop['identities'])
        self.assertEqual(before_stop['domain_facts'],after_stop['domain_facts'])
        self.assertEqual(189,sum(map(len,after_stop.values())))
        final=json.loads(after_stop['scope_state'][0]['accounting_wire'])
        self.assertEqual(dict(committed_positions='16',identity_rows='30',domain_rows='16',dependency_rows='105',
            retained_rows='189',row_writes='199',index_entries='398',Stop_reserve_consumed=True),
            {key:value for key,value in final.items() if key!='logical_UTF8_bytes'})
        self.assertEqual((215,446),(int(final['row_writes'])+len(after_stop['original_operations']),
            int(final['index_entries'])+3*len(after_stop['original_operations'])))
        selected=[observed_row_charge('scope_state',after_stop['scope_state'][0],scope)]
        selected.extend(observed_row_charge(table,row,scope)
            for table in ('original_operations','journal_entries','dependency_associations')
            for row in after_stop[table] if row['action_id']==stop['action_id'])
        self.assertEqual((10,20),(len(selected),sum(row['keys'] for row in selected)))
        logical=int(final['logical_UTF8_bytes'])-int(accounting['logical_UTF8_bytes'])
        self.assertGreaterEqual(logical,sum(row['bytes'] for row in selected))
        self.assertLessEqual(logical,reserve['logical_UTF8_bytes'])
        pending,=(row for row in after_stop['original_operations'] if row['action_id']==stop['action_id'])
        stage=observed_row_charge('original_operations',
            pending|dict(receipt_wire=None,receipt_sha256=None,finalized=False),scope)
        self.assertLessEqual(logical+stage['bytes'],reserve['encoded_row_DML_UTF8_upper'])
        self.assertFalse(any(row['original_id']==over['action_id'] for row in after_stop['identities']))

        immutable=self.f.snapshot()
        replayed=json.loads(self.db.scalar(SETTINGS+self.f.call('submit',stop,reader),role=reader))
        self.assertEqual(stopped,replayed)
        for command,saved in (originals[0],originals[-1]):
            historical=self.f.get(command,reader)
            for field in ('original_command_wire','original_result_wire','original_receipt_wire','dependencies'):
                self.assertEqual(saved[field],historical[field])
        self.assertEqual(immutable,self.f.snapshot())
    def test_reader_exact_original_survives_one_writer_nologin_only(self):
        installer=self.s['actors']['installer']
        recorder=self.s['actors']['recorder']
        reader=self.s['actors']['reader']
        control=self.s['actors']['control']
        self.assertEqual((installer,recorder,reader,control),
            ('vn_jupiter_b2_0_installer','vn_jupiter_b2_0_recorder','vn_jupiter_b2_0_reader','vn_jupiter_b2_0_control'))
        self.assertEqual(self.db.identity['network'],'none')
        install=self.f.command(self.s)
        self.submit(install)
        installed=self.f.get(install,reader)
        installed_rows=self.f.snapshot()
        try:
            self.db.sql('ALTER ROLE vn_jupiter_b2_0_installer NOLOGIN;')
            self.assertEqual(installed,self.f.get(install,reader))
            self.assertEqual(installed_rows,self.f.snapshot())
        finally:
            self.db.sql('ALTER ROLE vn_jupiter_b2_0_installer LOGIN;')

        acquire=self.acquire_command()
        self.submit(acquire,'recorder')
        resume=self.resume_command()
        self.submit(resume)
        accepted=self.f.get(acquire,reader)
        stored=self.f.snapshot()
        hold=self.f.head(self.s)
        renew=self.f.command(self.s,'fence_renew',action_id=str(UUID(int=998901)))
        renew['expected_fence_id']=hold['active_fence_id']
        renew['expected_fence_revision']=hold['fence_revision']
        renew['body']=dict(fence_id=hold['active_fence_id'],expected_revision=hold['fence_revision'],requested_duration_us='60000000')
        query=self.f.query(acquire)
        staged=self.f.writer(recorder)
        held=self.f.writer(recorder)
        try:
            held.backend_pid()
            staged.send(self.f.call('submit',renew,recorder))
            pending=json.loads(staged.line())
            self.assertTrue(pending['pending_commit'])
            self.assertEqual(sha(canonical(renew)),pending['original_command_sha256'])
            self.assertEqual('observed_absent_unknown',self.f.get(renew,reader)['resolution'])
            self.db.sql('ALTER ROLE vn_jupiter_b2_0_recorder NOLOGIN;')
            self.assertEqual('f',self.db.scalar("SELECT rolcanlogin FROM pg_catalog.pg_roles WHERE rolname="+literal(recorder)+";"))
            code,stderr=staged.finish(check=False)
            self.assertNotEqual(0,code)
            self.assertIn('b2_actor_scope_refused',stderr)
            self.assertIn('._commit_guard()',stderr)
            self.assertEqual(stored,self.f.snapshot())

            next_original=copy.deepcopy(renew)
            next_original['action_id']=str(UUID(int=998902))
            held.send(self.f.call('submit',next_original,recorder))
            with self.assertRaisesRegex(RuntimeError,'b2_actor_scope_refused'):
                held.line()
            fresh=self.db.sql(BEGIN+SETTINGS+self.f.call('submit',next_original,recorder)+'COMMIT;\n',role=recorder,check=False)
            self.assertNotEqual(0,fresh.returncode)
            self.assertIn('is not permitted to log in',fresh.stderr)

            raw=self.db.sql(SETTINGS+self.f.call('get_original',query,reader),role=reader).stdout
            self.assertEqual(canonical(accepted)+'\n',raw)
            self.assertEqual(stored,self.f.snapshot())

            def refused(statement,role,marker='b2_package_refused'):
                result=self.db.sql(SETTINGS+statement,role=role,check=False)
                self.assertNotEqual(0,result.returncode)
                self.assertIn(marker,result.stderr)

            refused(self.f.call('get_original',query,control),control)
            foreign=self.other['actors']['reader']
            refused(self.f.call('get_original',query,foreign),foreign,'b2_actor_scope_refused')
            refused(self.f.call('submit',acquire,reader),reader)
            refused(BEGIN+SETTINGS+self.f.call('submit',self.open_stop_command(resume),control)+'COMMIT;\n',control)
            refused(self.f.call('get_original',self.f.query(install),reader),reader)
            refused(self.f.call('get_original',self.f.query(renew),reader),reader)
            wrong_hash=copy.deepcopy(query)
            wrong_hash['expected_original_command_sha256']='f'*64
            refused(self.f.call('get_original',wrong_hash,reader),reader)
            wrong_kind=copy.deepcopy(query)
            wrong_kind['target_kind']='installation'
            refused(self.f.call('get_original',wrong_kind,reader),reader)

            # Each deliberately changed catalog or binding fact exists only
            # inside this fixture transaction. SET LOCAL SESSION AUTHORIZATION
            # exercises the negative path with the exact reader identity.
            # The failed SELECT aborts the transaction and discards the drift.
            scope_wire=literal(canonical(self.s['scope']))
            writer_binding=literal(self.s['bindings']['recorder'])
            for drift in (
                "ALTER ROLE vn_jupiter_b2_0_recorder VALID UNTIL '2000-01-01 00:00:00+00';",
                "ALTER ROLE vn_jupiter_b2_0_installer NOLOGIN;",
                f'GRANT SELECT ON {N}.original_operations TO vn_jupiter_b2_0_reader;',
                f"UPDATE {A}.actor_bindings SET binding_wire='{{}}' WHERE scope_wire={scope_wire} AND binding_id={writer_binding};",
            ):
                with self.subTest(drift=drift):
                    rejected=self.db.sql(BEGIN+SETTINGS+drift+
                        '\nSET LOCAL SESSION AUTHORIZATION vn_jupiter_b2_0_reader;\nSELECT session_user;\n'+
                        self.f.call('get_original',query,reader)+'ROLLBACK;\n',check=False)
                    self.assertNotEqual(0,rejected.returncode)
                    self.assertIn('b2_package_refused',rejected.stderr)
                    self.assertEqual(reader+'\n',rejected.stdout)
                    self.assertEqual(accepted,self.f.get(acquire,reader))
            self.assertEqual(stored,self.f.snapshot())
        finally:
            staged.close()
            held.close()
            self.db.sql('ALTER ROLE vn_jupiter_b2_0_recorder LOGIN;')
        self.assertEqual(accepted,self.f.get(acquire,reader))
        self.assertEqual(stored,self.f.snapshot())

    def test_v19_two_writer_retirement_closes_readback_and_reserved_stop(self):
        self.assertEqual('none',self.db.identity['network'])
        installer=self.s['actors']['installer']
        recorder=self.s['actors']['recorder']
        control=self.s['actors']['control']
        reader=self.s['actors']['reader']
        self.assertEqual((installer,recorder,control,reader),
            ('vn_jupiter_b2_0_installer','vn_jupiter_b2_0_recorder','vn_jupiter_b2_0_control','vn_jupiter_b2_0_reader'))
        install,acquire=self.install_and_acquire_for_resume()
        resume=self.resume_command()
        self.submit(resume)
        stop=self.open_stop_command(resume)
        self.assertEqual(self.s['stop_id'],stop['action_id'])
        self.assertEqual('3',stop['expected_head']['native_sequence'])
        history=[self.f.get(command,reader) for command in (install,acquire)]
        stop_before=self.f.get(stop,reader)
        self.assertEqual('observed_absent_unknown',stop_before['resolution'])
        before=self.f.snapshot()

        # Prove the exact reserved original is admissible before the controlled
        # drift. This owned writer explicitly rolls back the provisional result.
        writer=self.f.writer(control)
        try:
            writer.send(self.f.call('submit',stop,control))
            pending=json.loads(writer.line())
            self.assertTrue(pending['pending_commit'])
            self.assertEqual(sha(canonical(stop)),pending['original_command_sha256'])
            self.assertEqual(stop_before,self.f.get(stop,reader))
            writer.finish('ROLLBACK;')
        finally:
            writer.close()
        self.assertEqual(before,self.f.snapshot())

        def rejected_get(command):
            result=self.db.sql(SETTINGS+self.f.call('get_original',self.f.query(command),reader),role=reader,check=False)
            self.assertNotEqual(0,result.returncode)
            self.assertRegex(result.stderr,r'(?m)^ERROR:\s+P0001: b2_package_refused\s*$')
            self.assertEqual('',result.stdout.strip())

        try:
            self.db.sql('ALTER ROLE vn_jupiter_b2_0_installer NOLOGIN;')
            self.assertEqual(history[0],self.f.get(install,reader))
            rejected_get(acquire)
            one=self.refusal(stop,'b2_package_refused',profile='control')
            self.assertRegex(one.stderr,r'(?m)^ERROR:\s+P0001: b2_package_refused\s*$')

            self.db.sql('ALTER ROLE vn_jupiter_b2_0_recorder NOLOGIN;')
            for role in (installer,recorder):
                self.assertEqual('f',self.db.scalar(
                    "SELECT rolcanlogin FROM pg_catalog.pg_roles WHERE rolname="+literal(role)+";"))
            self.assertEqual(control,self.db.scalar('SELECT session_user;',role=control))
            self.assertEqual(reader,self.db.scalar('SELECT session_user;',role=reader))
            for command in (install,acquire,stop):
                rejected_get(command)
            two=self.refusal(stop,'b2_package_refused',profile='control')
            self.assertRegex(two.stderr,r'(?m)^ERROR:\s+P0001: b2_package_refused\s*$')
            self.assertEqual(before,self.f.snapshot())
        finally:
            # Restore only disposable role bits for fixture reuse. This is
            # not a recovery operation against a retired deployed identity.
            self.db.sql('BEGIN; ALTER ROLE vn_jupiter_b2_0_installer LOGIN; ALTER ROLE vn_jupiter_b2_0_recorder LOGIN; COMMIT;')
        self.assertEqual(history,[self.f.get(command,reader) for command in (install,acquire)])
        self.assertEqual(stop_before,self.f.get(stop,reader))
        self.assertEqual(before,self.f.snapshot())


    def test_explicit_terminal_retirement_recovers_two_writers_and_only_original_stop(self):
        install,acquire=self.install_and_acquire_for_resume()
        resume=self.resume_command()
        self.submit(resume)
        scope=self.s['scope']
        control=self.s['actors']['control']
        reader=self.s['actors']['reader']
        recorder=self.s['actors']['recorder']
        self.assertEqual((control,reader,recorder),
            ('vn_jupiter_b2_0_control','vn_jupiter_b2_0_reader','vn_jupiter_b2_0_recorder'))
        self.assertEqual(self.other['actors']['installer'],'vn_jupiter_b2_1_installer')
        self.assertEqual(self.db.identity['network'],'none')
        stop=self.open_stop_command(resume)
        original_reads=[self.f.get(command,reader) for command in (install,acquire)]
        original_rows=self.f.snapshot()
        marker,owner_sql=self.f.owner_retirement_sql(self.s,stop)
        scope_wire=literal(canonical(scope))

        writer=self.f.writer(control)
        try:
            writer.send(self.f.call('submit',stop,control))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            blocked=self.db.sql(owner_sql,check=False)
            self.assertNotEqual(0,blocked.returncode)
            self.assertIn('55P03',blocked.stderr)
            writer.finish('ROLLBACK;')
        finally:
            writer.close()
        self.assertEqual(original_rows,self.f.snapshot())
        self.assertEqual('t',self.db.scalar("SELECT bool_and(rolcanlogin) FROM pg_catalog.pg_roles WHERE rolname IN ('vn_jupiter_b2_0_installer','vn_jupiter_b2_0_recorder');"))

        direct_update=f'UPDATE {A}.package_inputs SET retirement_wire=NULL WHERE scope_wire={scope_wire};'
        direct_actor=self.db.sql(direct_update,role=control,check=False)
        self.assertNotEqual(0,direct_actor.returncode)
        self.assertIn('42501',direct_actor.stderr)
        direct_sealed=self.db.sql('BEGIN; SET LOCAL ROLE vn_jupiter_b2_sealed_owner; '+direct_update+' ROLLBACK;',check=False)
        self.assertNotEqual(0,direct_sealed.returncode)
        self.assertIn('42501',direct_sealed.stderr)

        try:
            self.db.sql(owner_sql)
            self.assertEqual('t',self.db.scalar("SELECT bool_and(NOT rolcanlogin) FROM pg_catalog.pg_roles WHERE rolname IN ('vn_jupiter_b2_0_installer','vn_jupiter_b2_0_recorder');"))
            self.assertEqual(canonical(marker),self.db.scalar(
                f'SELECT retirement_wire FROM {A}.package_inputs WHERE scope_wire={scope_wire};'))
            boundary=self.f.snapshot()
            self.assertEqual([row for row in original_rows if row[0]==N],[row for row in boundary if row[0]==N])
            self.assertEqual(original_reads,[self.f.get(command,reader) for command in (install,acquire)])

            def rejected(sql,role,marker_text='b2_retirement_refused'):
                refusal=self.db.sql(SETTINGS+sql,role=role,check=False)
                self.assertNotEqual(0,refusal.returncode)
                self.assertIn(marker_text,refusal.stderr)

            fresh=self.db.sql('SELECT session_user;',role=recorder,check=False)
            self.assertNotEqual(0,fresh.returncode)
            self.assertIn('is not permitted to log in',fresh.stderr)
            rejected(self.f.call('get_original',self.f.query(stop),reader),reader)
            rejected(self.f.call('get_original',self.f.query(resume),reader),reader)
            rejected(self.f.call('get_original',self.f.query(acquire),control),control)
            other_reader=self.other['actors']['reader']
            rejected(self.f.call('get_original',self.f.query(acquire),other_reader),other_reader,'b2_actor_scope_refused')
            other_install=self.f.command(self.other)
            rejected(self.f.call('get_original',self.f.query(other_install),other_reader),other_reader,'b2_package_refused')
            rejected(self.f.call('submit',resume,control),control)
            altered=copy.deepcopy(stop)
            altered['expected_head']['native_head_sha256']='f'*64
            rejected(self.f.call('submit',altered,control),control)
            self.assertEqual(boundary,self.f.snapshot())

            # Rolling the login bits back while the marker exists must not
            # fall through to the usual full-K path. The deliberate changes
            # only exist in this rollback-only owned fixture transaction.
            restored=BEGIN+SETTINGS+"""
ALTER ROLE vn_jupiter_b2_0_installer LOGIN;
ALTER ROLE vn_jupiter_b2_0_recorder LOGIN;
SET LOCAL SESSION AUTHORIZATION vn_jupiter_b2_0_control;
"""
            restored_attempt=self.db.sql(restored+self.f.call('submit',stop,control)+'ROLLBACK;\n',check=False)
            self.assertNotEqual(0,restored_attempt.returncode)
            self.assertIn('b2_retirement_refused',restored_attempt.stderr)
            self.assertEqual(boundary,self.f.snapshot())

            # Unexpected unrelated role drift after staging must still be
            # checked at literal COMMIT. Both actions here are synthetic.
            staged=self.f.writer(control)
            try:
                staged.send(self.f.call('submit',stop,control))
                pending=json.loads(staged.line())
                self.assertTrue(pending['pending_commit'])
                self.assertEqual(sha(canonical(stop)),pending['original_command_sha256'])
                rejected(self.f.call('get_original',self.f.query(stop),reader),reader)
                self.db.sql('ALTER ROLE vn_jupiter_b2_1_installer CONNECTION LIMIT 7;')
                code,stderr=staged.finish(check=False)
                self.assertNotEqual(0,code)
                self.assertIn('b2_retirement_refused',stderr)
                self.assertIn('._commit_guard()',stderr)
            finally:
                staged.close()
                self.db.sql('ALTER ROLE vn_jupiter_b2_1_installer CONNECTION LIMIT -1;')
            self.assertEqual(boundary,self.f.snapshot())

            self.submit(stop)
            stopped=self.f.get(stop,reader)
            result,_=self.assert_committed(stop,stopped,4)
            self.assertEqual(dict(previous_mode='open',resulting_mode='stopped',
                previous_control_sha256=sha(canonical(resume)),resulting_fence_revision='2'),result['result_body'])
            immutable=self.f.snapshot()
            for command,old in zip((install,acquire),original_reads):
                recovered=self.f.get(command,reader)
                for field in ('original_command_wire','original_result_wire','original_receipt_wire','dependencies'):
                    self.assertEqual(old[field],recovered[field])
            rejected(self.f.call('submit',stop,control),control)
            self.assertEqual(stopped,self.f.get(stop,reader))
            self.assertEqual(immutable,self.f.snapshot())
        finally:
            self.f.restore_owned_retirement(self.s)


    def test_dedicated_anchor_owner_denies_assumption_and_seals_role_drift(self):
        from tests.postgres.allocation_control_v3_fixture import ANCHOR_OWNER, OWNER
        self.assertEqual((ANCHOR_OWNER,OWNER),('vn_jupiter_b2_anchor_owner','vn_jupiter_b2_sealed_owner'))
        self.assertEqual(self.db.identity['network'],'none')
        before=self.f.snapshot()
        for owner in (ANCHOR_OWNER,OWNER):
            fresh=self.db.sql('SELECT session_user;',role=owner,check=False)
            self.assertNotEqual(0,fresh.returncode)
            self.assertIn('is not permitted to log in',fresh.stderr)
            for scope in (self.s,self.other):
                for actor in scope['actors'].values():
                    denied=self.db.sql(f'SET ROLE {owner};',role=actor,check=False)
                    self.assertNotEqual(0,denied.returncode)
                    self.assertIn('42501',denied.stderr)
        self.assertEqual(before,self.f.snapshot())

        # Admitted installation still traverses the fixed lock broker without
        # changing any protected anchor row.
        original=self.f.command(self.s)
        self.assertTrue(self.submit(original)['pending_commit'])
        reader=self.s['actors']['reader']
        committed=self.f.get(original,reader)
        self.assert_committed(original,committed,1)
        stored=self.f.snapshot()
        self.assertEqual([r for r in before if r[0]==A],[r for r in stored if r[0]==A])

        # These synthetic role changes never commit or publish a login.
        getter=self.f.call('get_original',self.f.query(original),reader)
        for drift in (
            f'ALTER ROLE {ANCHOR_OWNER} LOGIN;',
            'CREATE ROLE vn_jupiter_b2_owner_seal_probe NOLOGIN;'
            f' GRANT vn_jupiter_b2_owner_seal_probe TO {ANCHOR_OWNER}'
            ' WITH ADMIN FALSE,INHERIT FALSE,SET TRUE;',
        ):
            with self.subTest(drift=drift):
                denied=self.db.sql(BEGIN+SETTINGS+drift+
                    f'\nSET LOCAL SESSION AUTHORIZATION {reader};\nSELECT session_user;\n'+
                    getter+'ROLLBACK;\n',check=False)
                self.assertNotEqual(0,denied.returncode)
                self.assertIn('b2_package_refused',denied.stderr)
                self.assertEqual(reader+'\n',denied.stdout)
                self.assertEqual(committed,self.f.get(original,reader))
                self.assertEqual(stored,self.f.snapshot())
        self.assertEqual('0',self.db.scalar("SELECT count(*) FROM pg_catalog.pg_roles WHERE rolname='vn_jupiter_b2_owner_seal_probe';"))

    def test_terminal_retirement_second_role_lock_rolls_back_first_login_removal(self):
        install,_=self.install_and_acquire_for_resume()
        resume=self.resume_command()
        self.submit(resume)
        stop=self.open_stop_command(resume)
        reader=self.s['actors']['reader']
        self.assertEqual(self.s['actors']['recorder'],'vn_jupiter_b2_0_recorder')
        saved=self.f.get(install,reader)
        expected=self.f.snapshot()
        _,owner_sql=self.f.owner_retirement_sql(self.s,stop)
        # StepSession supplies the exact normal BEGIN and SETTINGS. Send
        # the unmodified issuance DO, then let the real DCL error abort it.
        prefix=BEGIN+SETTINGS
        suffix='COMMIT;\n'
        self.assertTrue(owner_sql.startswith(prefix))
        self.assertTrue(owner_sql.endswith(suffix))
        issuance=owner_sql[len(prefix):-len(suffix)]
        role_sql="""SELECT jsonb_agg(jsonb_build_array(oid::text,rolname::text,rolcanlogin,rolconnlimit)
            ORDER BY rolname) FROM pg_catalog.pg_roles
            WHERE rolname IN ('vn_jupiter_b2_0_installer','vn_jupiter_b2_0_recorder');"""
        intact=json.loads(self.db.scalar(role_sql))
        self.assertEqual(2,len(intact))
        self.assertTrue(all(row[2] and row[3]==-1 for row in intact))
        blocker=self.f.anchor_session()
        issuer=self.f.anchor_session()
        try:
            blocker_pid=blocker.backend_pid()
            issuer_pid=issuer.backend_pid()
            # The actual role update holds the recorder catalog tuple. It
            # stays uncommitted, so the independent issuer's held-K check
            # still sees the original catalog.
            blocker.send("ALTER ROLE vn_jupiter_b2_0_recorder CONNECTION LIMIT 7;\nSELECT 'held';\n")
            self.assertEqual('held',blocker.line())
            self.assertEqual(intact,json.loads(self.db.scalar(role_sql)))
            issuer.send(issuance)
            self.f.wait_for_blocker(issuer_pid,blocker_pid)
            with self.assertRaisesRegex(RuntimeError,'55P03') as refused:
                issuer.line()
            # The exact second DCL in the immutable issuance body was
            # reached. The first DCL ran earlier in that same transaction.
            self.assertIn('SQL statement "ALTER ROLE vn_jupiter_b2_0_recorder NOLOGIN"',str(refused.exception))
            self.assertEqual(intact,json.loads(self.db.scalar(role_sql)))
            self.assertEqual(expected,self.f.snapshot())
            blocker.finish('ROLLBACK;')
        finally:
            issuer.close()
            blocker.close()
        self.assertEqual(intact,json.loads(self.db.scalar(role_sql)))
        self.assertEqual(expected,self.f.snapshot())
        self.assertEqual(saved,self.f.get(install,reader))

    def test_terminal_retirement_stale_request_refuses_after_waiting_writer_commits(self):
        _,acquire=self.install_and_acquire_for_resume()
        resume=self.resume_command()
        self.submit(resume)
        stop=self.open_stop_command(resume)
        _,owner_sql=self.f.owner_retirement_sql(self.s,stop)
        recorder=self.s['actors']['recorder']
        reader=self.s['actors']['reader']
        scope_wire=literal(canonical(self.s['scope']))
        acquired=json.loads(self.f.get(acquire,reader)['original_result_wire'])
        fence=acquired['result_body']['original_fence_record']
        renew=self.f.command(self.s,'fence_renew',action_id=str(UUID(int=999601)))
        renew['expected_fence_id']=fence['fence_id']
        renew['expected_fence_revision']=fence['revision']
        renew['body']=dict(fence_id=fence['fence_id'],expected_revision=fence['revision'],
            requested_duration_us='60000000')
        initial=self.f.snapshot()
        writer=self.f.writer(recorder)
        try:
            writer.send(self.f.call('submit',renew,recorder))
            pending=json.loads(writer.line())
            self.assertTrue(pending['pending_commit'])
            self.assertEqual(sha(canonical(renew)),pending['original_command_sha256'])
            self.assertEqual('observed_absent_unknown',self.f.get(renew,reader)['resolution'])
            blocked=self.db.sql(owner_sql,check=False)
            self.assertNotEqual(0,blocked.returncode)
            self.assertIn('55P03',blocked.stderr)
            self.assertEqual(initial,self.f.snapshot())
            writer.finish()
        finally:
            writer.close()
        renewed=self.f.get(renew,reader)
        self.assert_committed(renew,renewed,4)
        self.assertEqual('4',self.f.head(self.s)['native_sequence'])
        committed=self.f.snapshot()
        # Reuse the exact synthetic request after the definitive NOWAIT
        # refusal. Its position-three original Stop cannot be rebased.
        stale=self.db.sql(owner_sql,check=False)
        self.assertNotEqual(0,stale.returncode)
        self.assertRegex(stale.stderr,r'(?m)^ERROR:\s+P0001: b2_owned_retirement_head_refused\s*$')
        self.assertEqual('t',self.db.scalar(f'SELECT retirement_wire IS NULL FROM {A}.package_inputs WHERE scope_wire={scope_wire};'))
        self.assertEqual('t',self.db.scalar("""SELECT count(*)=2 AND bool_and(rolcanlogin)
            FROM pg_catalog.pg_roles WHERE rolname IN ('vn_jupiter_b2_0_installer','vn_jupiter_b2_0_recorder');"""))
        self.assertEqual(committed,self.f.snapshot())
        self.assertEqual(renewed,self.f.get(renew,reader))
        self.assertEqual('observed_absent_unknown',self.f.get(stop,reader)['resolution'])
        self.refusal(stop,'b2_stale_head',profile='control')
        self.assertEqual(committed,self.f.snapshot())



@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationManagedCreatorNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=IsolatedPostgres().start()
        try:cls.fixture=AllocationFixture(cls.db,creator_edges=True)
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def test_actual_limited_creator_accepts_exact_edge_and_refuses_extra_memberships(self):
        f=self.fixture
        f.reset()
        scope=f.scopes[0]
        installer=scope['actors']['installer']
        reader=scope['actors']['reader']
        original=f.command(scope)
        writer=f.writer(installer)
        try:
            writer.send(f.call('submit',original,installer))
            provisional=json.loads(writer.line())
            self.assertTrue(provisional['pending_commit'])
            self.assertEqual(provisional['original_command_sha256'],sha(canonical(original)))
            writer.finish()
        finally:writer.close()
        reply=f.get(original,reader)
        self.assertEqual(reply['original_command_wire'],canonical(original))
        self.assertEqual(f.head(scope)['native_sequence'],'1')
        before=f.snapshot()

        role_pins={row['name']:row for row in f.catalog['value']['roles']}
        self.assertEqual(role_pins['postgres']['oid'],'10')
        self.assertEqual(role_pins[CREATOR]['oid'],self.db.scalar(f"SELECT oid::text FROM pg_roles WHERE rolname={literal(CREATOR)};"))
        self.assertEqual(self.db.scalar(f"""SELECT pg_has_role({literal(CREATOR)},{literal(installer)},'MEMBER')
          AND NOT pg_has_role({literal(CREATOR)},{literal(installer)},'SET')
          AND NOT pg_has_role({literal(CREATOR)},{literal(installer)},'USAGE');"""),'t')
        for owner in (ANCHOR_OWNER,OWNER):
            for statement in (f'SET ROLE {owner};',f'ALTER ROLE {owner} LOGIN;',f'GRANT {owner} TO {CREATOR} WITH SET TRUE;'):
                with self.subTest(owner=owner,statement=statement):
                    denied=self.db.sql(statement,role=CREATOR,check=False)
                    self.assertNotEqual(denied.returncode,0)
                    self.assertIn('42501',denied.stderr)
        self.assertEqual(before,f.snapshot())

        probe='vn_jupiter_b2_creator_extra'
        self.db.sql(f'CREATE ROLE {probe} NOLOGIN NOINHERIT;')
        query=f.query(original)
        try:
            for granted, member, can_set in ((installer,probe,False),(probe,installer,True)):
                with self.subTest(granted=granted,member=member):
                    set_option='TRUE' if can_set else 'FALSE'
                    self.db.sql(f'GRANT {granted} TO {member} WITH ADMIN FALSE, INHERIT FALSE, SET {set_option};')
                    try:
                        self.assertEqual(self.db.scalar(f"""SELECT count(*) FROM pg_auth_members
                          WHERE roleid={literal(granted)}::regrole AND member={literal(member)}::regrole
                          AND grantor='postgres'::regrole AND NOT admin_option AND NOT inherit_option
                          AND set_option IS {set_option};"""),'1')
                        for actor, marker in ((installer,'b2_actor_scope_refused'),(reader,'b2_package_refused')):
                            denied=self.db.sql(SETTINGS+f.call('get_original',query,actor),role=actor,check=False)
                            self.assertNotEqual(denied.returncode,0)
                            self.assertIn(marker,denied.stderr)
                        self.assertEqual(before,f.snapshot())
                    finally:self.db.sql(f'REVOKE {granted} FROM {member};')
                    self.assertEqual(reply,f.get(original,reader))

            # An issuer edge touching no actor or owner must still alter K.
            # Use a single rollback-only transaction so the owned reader
            # check sees the uncommitted membership without publishing it.
            refused=self.db.sql(BEGIN+SETTINGS+f"""
GRANT {probe} TO {CREATOR} WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
SELECT (SELECT count(*) FROM pg_auth_members
 WHERE roleid={literal(probe)}::regrole AND member={literal(CREATOR)}::regrole
 AND grantor='postgres'::regrole AND NOT admin_option AND NOT inherit_option AND set_option)=1
 AND pg_has_role({literal(CREATOR)},{literal(probe)},'SET');
SET LOCAL SESSION AUTHORIZATION {reader};
SELECT session_user;
"""+f.call('get_original',query,reader)+'ROLLBACK;\n',check=False)
            self.assertEqual(refused.stdout.splitlines(),['t',reader])
            self.assertNotEqual(refused.returncode,0)
            self.assertRegex(refused.stderr,r'(?m)^ERROR:\s+P0001: b2_package_refused\s*$')
            self.assertEqual(self.db.scalar(f"""SELECT count(*) FROM pg_auth_members
              WHERE roleid={literal(probe)}::regrole AND member={literal(CREATOR)}::regrole;"""),'0')
            self.assertEqual(reply,f.get(original,reader))
        finally:self.db.sql(f'DROP ROLE {probe};')
        self.assertEqual(before,f.snapshot())


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationDirectScramNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=AllocationScramPostgres().start()
        try:cls.fixture=AllocationFixture(cls.db,creator_edges=True)
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def db_clock_us(self):
        return int(self.db.scalar('SELECT floor(extract(epoch FROM clock_timestamp())*1000000)::bigint;'))

    def wait_for_db_clock(self,target_us):
        remaining_us=target_us-self.db_clock_us()
        self.assertLessEqual(remaining_us,35_000_000)
        if remaining_us>0:
            self.db.sql(f'SELECT pg_sleep({remaining_us}/1000000.0);',timeout=40)
        observed_us=self.db_clock_us()
        self.assertGreaterEqual(observed_us,target_us)
        return observed_us

    def test_direct_scram_actor_credential_expires_before_literal_commit(self):
        f=self.fixture
        s=f.scopes[0]
        installer=s['actors']['installer']
        reader=s['actors']['reader']
        recorder=s['actors']['recorder']
        expiry_us=self.db.actor_deadlines[recorder]
        identity="SELECT session_user,system_user,current_user,inet_client_addr()='127.0.0.1'::inet,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();"
        for role in (installer,reader,recorder):
            self.assertEqual(self.db.scalar(identity,role=role),f'{role}|scram-sha-256:{role}|{role}|t|t')
        for options,expected in (({'host':'wrong.example'},'does not match host name'),
                                 ({'root':'wrong-root.crt'},'certificate verify failed')):
            refused=self.db.begin_direct('SELECT 1;',role=reader,**options).wait(check=False)
            self.assertNotEqual(refused.returncode,0)
            self.assertEqual(refused.stdout,'')
            self.assertIn(expected,refused.stderr)

        install=f.command(s)
        writer=f.writer(installer)
        try:
            writer.send(f.call('submit',install,installer))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            writer.finish()
        finally:writer.close()
        committed=f.get(install,reader)
        self.assertEqual(committed['original_command_wire'],canonical(install))
        self.assertEqual(committed['observed_head']['native_sequence'],'1')
        socket_source=SETTINGS+f.call('get_original',f.query(install),reader)
        socket_result=IsolatedPostgres.begin_sql(self.db,socket_source,role=reader).wait(check=False)
        self.assertNotEqual(socket_result.returncode,0)
        self.assertRegex(socket_result.stderr,r'(?m)^ERROR:\s+42501: b2_direct_scram_required\s*$')

        acquire=f.command(s,'fence_acquire',action_id=str(UUID(int=993021)))
        acquire['body']=dict(fence_id=str(UUID(int=993022)),acquisition_epoch=s['epoch'],
            holder_principal_binding_id=s['bindings']['recorder'],requested_duration_us='60000000')
        before=f.snapshot()
        staged_after_us=self.wait_for_db_clock(expiry_us-6_000_000)
        self.assertLess(staged_after_us,expiry_us-2_000_000)
        writer=f.writer(recorder)
        try:
            writer.send(f.call('submit',acquire,recorder))
            pending=json.loads(writer.line())
            self.assertTrue(pending['pending_commit'])
            self.assertEqual(pending['original_command_sha256'],sha(canonical(acquire)))
            self.assertLess(self.db_clock_us(),expiry_us)
            invisible=f.get(acquire,reader)
            self.assertEqual(invisible['resolution'],'observed_absent_unknown')
            self.assertIsNone(invisible['original_operation_pin'])

            expired_us=self.wait_for_db_clock(expiry_us+150_000)
            writer.send(identity+'\n')
            self.assertEqual(writer.line(),f'{recorder}|scram-sha-256:{recorder}|{recorder}|t|t')
            status,error=writer.finish('COMMIT;',check=False)
            self.assertNotEqual(status,0)
            self.assertRegex(error,r'(?m)^ERROR:\s+42501: b2_credential_expired\s*$')
            self.assertGreater(expired_us,expiry_us)
            self.assertLess(self.db_clock_us(),staged_after_us+60_000_000)
        finally:writer.close()

        refused=self.db.sql('SELECT 1;',role=recorder,check=False)
        self.assertNotEqual(refused.returncode,0)
        self.assertEqual(refused.stdout,'')
        self.assertIn('password authentication failed',refused.stderr)
        self.assertEqual(f.get(acquire,reader),invisible)
        self.assertEqual(f.get(install,reader),committed)
        self.assertEqual(before,f.snapshot())


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationIndependentDeadlineNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=AllocationDeadlineScramPostgres().start()
        try:cls.fixture=AllocationFixture(cls.db,creator_edges=True)
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    db_clock_us=AllocationDirectScramNativeTests.db_clock_us
    wait_for_db_clock=AllocationDirectScramNativeTests.wait_for_db_clock

    def test_independent_write_and_reader_cutoffs_with_live_scram_logins(self):
        f=self.fixture
        s=f.scopes[0]
        installer=s['actors']['installer']
        recorder=s['actors']['recorder']
        reader=s['actors']['reader']
        bindings={b['session_user_name']:b for b in s['manifest']['bindings']}
        write_until=int(bindings[recorder]['write_until_us'])
        recorder_login_until=self.db.actor_deadlines[recorder]
        read_until=int(bindings[reader]['read_until_us'])
        reader_login_until=self.db.actor_deadlines[reader]
        self.assertLess(write_until,recorder_login_until)
        self.assertLess(recorder_login_until,read_until)
        self.assertLess(read_until,reader_login_until)
        for actor in (installer,recorder,reader):
            self.assertEqual(self.db.scalar("SELECT session_user,system_user,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();",
                role=actor),f'{actor}|scram-sha-256:{actor}|t')

        install=f.command(s)
        writer=f.writer(installer)
        try:
            writer.send(f.call('submit',install,installer))
            self.assertTrue(json.loads(writer.line())['pending_commit'])
            writer.finish()
        finally:writer.close()
        committed=f.get(install,reader)
        self.assertEqual(committed['original_command_wire'],canonical(install))
        self.assertEqual(committed['observed_head']['native_sequence'],'1')

        acquire=f.command(s,'fence_acquire',action_id=str(UUID(int=993041)))
        acquire['body']=dict(fence_id=str(UUID(int=993042)),acquisition_epoch=s['epoch'],
            holder_principal_binding_id=s['bindings']['recorder'],requested_duration_us='60000000')
        def getter(command,role):
            return f.call('get_original',f.query(command),role)

        forbidden=self.db.sql(SETTINGS+f.call('submit',acquire,reader),role=reader,check=False)
        self.assertNotEqual(forbidden.returncode,0)
        self.assertRegex(forbidden.stderr,r'(?m)^ERROR:\s+42501: permission denied for function submit\s*$')
        before=f.snapshot()
        staged_after=self.wait_for_db_clock(write_until-6_000_000)
        self.assertLess(staged_after,write_until-2_000_000)
        writer=f.writer(recorder)
        try:
            writer.send(f.call('submit',acquire,recorder))
            pending=json.loads(writer.line())
            self.assertTrue(pending['pending_commit'])
            self.assertEqual(pending['original_command_sha256'],sha(canonical(acquire)))
            self.assertLess(self.db_clock_us(),write_until)
            invisible=f.get(acquire,reader)
            self.assertEqual(invisible['resolution'],'observed_absent_unknown')
            self.assertIsNone(invisible['original_operation_pin'])
            expired=self.wait_for_db_clock(write_until+150_000)
            self.assertLess(expired,recorder_login_until)
            status,error=writer.finish('COMMIT;',check=False)
            self.assertNotEqual(status,0)
            self.assertRegex(error,r'(?m)^ERROR:\s+42501: b2_write_window_closed\s*$')
            self.assertLess(self.db_clock_us(),min(recorder_login_until,staged_after+60_000_000))
        finally:writer.close()

        self.assertEqual(self.db.scalar('SELECT session_user;',role=recorder),recorder)
        for query in (f.call('submit',acquire,recorder),f.call('submit',install,recorder),getter(install,recorder)):
            refused=self.db.sql(BEGIN+SETTINGS+query+'COMMIT;\n',role=recorder,check=False)
            self.assertNotEqual(refused.returncode,0)
            self.assertEqual(refused.stdout,'')
            self.assertRegex(refused.stderr,r'(?m)^ERROR:\s+42501: b2_write_window_closed\s*$')
        self.assertLess(self.db_clock_us(),recorder_login_until)
        self.assertEqual(f.get(install,reader),committed)
        self.assertEqual(f.get(acquire,reader),invisible)
        self.wait_for_db_clock(recorder_login_until+150_000)
        login=self.db.sql('SELECT 1;',role=recorder,check=False)
        self.assertNotEqual(login.returncode,0)
        self.assertEqual(login.stdout,'')
        self.assertIn('password authentication failed',login.stderr)
        self.assertEqual(f.get(install,reader),committed)

        # Only the absent return's scope_state observation takes this relation
        # lock. The actual reader must have passed its authorization first.
        locker=f.anchor_session()
        late_reader=f.writer(reader)
        try:
            locker_pid=locker.backend_pid()
            reader_pid=late_reader.backend_pid()
            locker.send(f"LOCK TABLE {N}.scope_state IN ACCESS EXCLUSIVE MODE; SELECT 'scope_locked';\n")
            self.assertEqual(locker.line(),'scope_locked')
            start=self.wait_for_db_clock(read_until-650_000)
            self.assertLess(start,read_until-350_000)
            late_reader.send(getter(acquire,reader))
            f.wait_for_blocker(reader_pid,locker_pid)
            late_reader._process.stdin.close()
            self.assertLess(self.db_clock_us(),read_until)
            expired=self.wait_for_db_clock(read_until+20_000)
            self.assertLess(expired,reader_login_until)
            locker.finish('ROLLBACK;')
            error=late_reader.failure_stderr()
            self.assertNotEqual(late_reader._process.returncode,0)
            self.assertEqual(late_reader._process.stdout.read(),b'')
            self.assertRegex(error,r'(?m)^ERROR:\s+42501: b2_recovery_window_closed\s*$')
            self.assertRegex(error,r'get_original\(text\) line [1-9][0-9]* at PERFORM')
            self.assertNotIn('_auth(',error)
        finally:
            late_reader.close()
            locker.close()

        self.assertEqual(self.db.scalar('SELECT session_user;',role=reader),reader)
        for original in (install,acquire):
            refused=self.db.sql(SETTINGS+getter(original,reader),role=reader,check=False)
            self.assertNotEqual(refused.returncode,0)
            self.assertEqual(refused.stdout,'')
            self.assertRegex(refused.stderr,r'(?m)^ERROR:\s+42501: b2_recovery_window_closed\s*$')
        self.assertEqual(before,f.snapshot())


class _DeadlineRetirementCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=cls.postgres_fixture().start()
        try:cls.fixture=AllocationFixture(cls.db,creator_edges=True)
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    db_clock_us=AllocationDirectScramNativeTests.db_clock_us
    wait_for_db_clock=AllocationDirectScramNativeTests.wait_for_db_clock

    def submit(self, command, role):
        writer=self.fixture.writer(role)
        try:
            writer.send(self.fixture.call('submit',command,role))
            provisional=json.loads(writer.line())
            self.assertTrue(provisional['pending_commit'])
            self.assertEqual(provisional['original_command_sha256'],sha(canonical(command)))
            writer.finish()
        finally:writer.close()

    def prepare_terminal(self):
        f=self.fixture
        s=f.scopes[0]
        self.assertEqual(len(f.catalog['value']['functions']),len(f.source.functions())+1+3)
        self.assertEqual(self.db.scalar("SELECT session_user,system_user,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();",role=CREATOR),
            f'{CREATOR}|scram-sha-256:{CREATOR}|t')
        installer=s['actors']['installer']
        recorder=s['actors']['recorder']
        control=s['actors']['control']
        install=f.command(s)
        self.submit(install,installer)
        acquire=f.command(s,'fence_acquire',action_id=str(UUID(int=993051)))
        acquire['body']=dict(fence_id=str(UUID(int=993052)),acquisition_epoch=s['epoch'],
            holder_principal_binding_id=s['bindings']['recorder'],requested_duration_us='60000000')
        self.submit(acquire,recorder)
        head=f.head(s)
        resume=f.command(s,'source_resume',action_id=str(UUID(int=993053)))
        resume['expected_fence_id']=head['active_fence_id']
        resume['expected_fence_revision']=head['fence_revision']
        self.submit(resume,control)
        stop=f.command(s,'source_stop')
        stop['body']=dict(expected_control_sha256=sha(canonical(resume)),expected_mode='open')
        expected_marker,_=f.owner_retirement_sql(s,stop)
        permit_id=str(UUID(int=993054))
        permit_expiry=self.db.scalar("SELECT floor(extract(epoch FROM clock_timestamp()+interval '60 seconds')*1000000)::bigint;")
        issuer_oid=self.db.scalar('SELECT oid::text FROM pg_roles WHERE rolname=session_user;',role=CREATOR)
        permit=dict(format='ga-jupiter-b2-terminal-permit-fixture-v1',permit_id=permit_id,scope=s['scope'],
            native_package_sha256=s['package']['native_package_sha256'],catalog_manifest_sha256=s['package']['catalog_manifest_sha256'],
            stop_command_wire=canonical(stop),writer_binding_ids=[s['bindings'][name] for name in ('installer','recorder')],
            expires_at_us=permit_expiry,issuer_oid=issuer_oid)
        sw=literal(canonical(s['scope']))
        self.db.sql(f"BEGIN; SET LOCAL ROLE {ANCHOR_OWNER}; UPDATE {A}.package_inputs SET retirement_permit_wire={literal(canonical(permit))} WHERE scope_wire={sw}; COMMIT;")
        stage=f'SELECT {A}._stage_terminal_retirement({sw},{literal(permit_id)});\n'
        disable=f'ALTER ROLE {installer} NOLOGIN;\nALTER ROLE {recorder} NOLOGIN;\n'
        login_count=f"SELECT count(*) FROM pg_roles WHERE rolcanlogin AND rolname IN({literal(installer)},{literal(recorder)});"
        return s,install,acquire,stop,expected_marker,stage,disable,login_count

    def exercise_short_window(self, profile):
        f=self.fixture
        s,install,acquire,stop,marker,stage,disable,login_count=self.prepare_terminal()
        self.assertEqual(stop['action_id'],s['stop_id'])
        reader=s['actors']['reader']
        originals=[f.get(command,reader) for command in (install,acquire)]
        bindings={row['session_user_name']:row for row in s['manifest']['bindings']}
        actor=s['actors'][profile]
        other_actor=s['actors']['reader' if profile=='control' else 'control']
        cutoff=int(bindings[actor]['write_until_us' if profile=='control' else 'read_until_us'])
        other_cutoff=int(bindings[other_actor]['read_until_us' if profile=='control' else 'write_until_us'])
        before=f.snapshot()
        staged_at=self.wait_for_db_clock(cutoff-8_000_000)
        self.assertLess(staged_at,cutoff-6_000_000)
        issuer=f.writer(CREATOR)
        try:
            issuer.send(stage)
            self.assertEqual(issuer.line(),canonical(marker))
            issuer.send(disable+login_count+'\n')
            self.assertEqual(issuer.line(),'0')
            self.assertLess(self.db_clock_us(),cutoff-5_000_000)
            self.assertEqual(self.db.scalar(login_count),'2')
            self.assertEqual([f.get(command,reader) for command in (install,acquire)],originals)
            near=self.wait_for_db_clock(cutoff-3_000_000)
            self.assertLess(near,cutoff)
            self.assertGreater(cutoff-near,1_000_000)
            self.assertGreater(other_cutoff,near+30_000_000)
            self.assertGreater(self.db.actor_deadlines[actor],near+60_000_000)
            status,error=issuer.finish('COMMIT;',check=False)
            self.assertNotEqual(status,0)
            self.assertRegex(error,rf'(?m)^ERROR:\s+42501: b2_terminal_{profile}_window_refused\s*$')
            self.assertIn('_terminal_retirement_commit_guard()',error)
        finally:issuer.close()

        self.assertLess(self.db_clock_us(),cutoff)
        refused=self.db.sql(BEGIN+SETTINGS+stage+'COMMIT;\n',role=CREATOR,check=False)
        self.assertNotEqual(refused.returncode,0)
        self.assertEqual(refused.stdout,'')
        self.assertRegex(refused.stderr,rf'(?m)^ERROR:\s+42501: b2_terminal_{profile}_window_refused\s*$')
        self.assertIn('_stage_terminal_retirement(text,text)',refused.stderr)
        self.assertLess(self.db_clock_us(),cutoff)
        self.assertEqual(self.db.scalar("SELECT session_user,system_user,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();",role=actor),
            f'{actor}|scram-sha-256:{actor}|t')
        self.assertEqual(self.db.scalar(login_count),'2')
        self.assertEqual(before,f.snapshot())


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationDeadlineRetirementControlTests(_DeadlineRetirementCases):
    postgres_fixture=AllocationControlWindowRetirementPostgres

    def test_control_write_margin_refuses_staging_and_literal_commit(self):
        self.exercise_short_window('control')


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationDeadlineRetirementReaderTests(_DeadlineRetirementCases):
    postgres_fixture=AllocationReaderWindowRetirementPostgres

    def test_reader_recovery_margin_refuses_staging_and_literal_commit(self):
        self.exercise_short_window('reader')


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationDeadlineRetirementSuccessTests(_DeadlineRetirementCases):
    postgres_fixture=AllocationDeadlineRetirementPostgres

    def test_limited_retirement_and_exact_original_stop_with_separate_live_windows(self):
        f=self.fixture
        s,install,acquire,stop,marker,stage,disable,login_count=self.prepare_terminal()
        control=s['actors']['control']
        reader=s['actors']['reader']
        originals=[f.get(command,reader) for command in (install,acquire)]
        sw=literal(canonical(s['scope']))

        def trusted_inputs(package,manifest):
            # Synthetic anchor drift. No clock, role, permit or native-row change.
            self.db.sql(f"BEGIN; SET LOCAL ROLE {ANCHOR_OWNER}; UPDATE {A}.package_inputs "
                f"SET package_wire={literal(canonical(package))},actor_manifest_wire={literal(canonical(manifest))} "
                f"WHERE scope_wire={sw}; COMMIT;")

        legacy_package=dict(s['package'],format='ga-jupiter-b2-fixture-direct-scram-research-v3-v1')
        legacy_manifest=dict(s['manifest'],format='ga-jupiter-b2-capability-manifest-research-v3-v1')
        paired_package=dict(legacy_package,actor_manifest_sha256=sha(canonical(legacy_manifest)))
        for package,manifest,error in (
          (legacy_package,s['manifest'],'b2_terminal_profile_refused'),
          (paired_package,legacy_manifest,'b2_terminal_installation_refused'),
        ):
            trusted_inputs(package,manifest)
            drifted=f.snapshot()
            refused=self.db.sql(BEGIN+SETTINGS+stage+'COMMIT;\n',role=CREATOR,check=False)
            self.assertNotEqual(refused.returncode,0)
            self.assertEqual(refused.stdout,'')
            self.assertRegex(refused.stderr,rf'(?m)^ERROR:\s+P0001: {error}\s*$')
            self.assertEqual(self.db.scalar(login_count),'2')
            self.assertEqual(drifted,f.snapshot())
        trusted_inputs(s['package'],s['manifest'])
        self.assertEqual([f.get(command,reader) for command in (install,acquire)],originals)

        before=[row for row in f.snapshot() if row[0]==N]
        stage_result=self.db.sql(BEGIN+SETTINGS+stage+disable+login_count+'\nCOMMIT;\n',role=CREATOR)
        self.assertEqual(stage_result.stdout.splitlines(),[canonical(marker),'0'])
        self.assertEqual(self.db.scalar(login_count),'0')
        self.assertEqual(self.db.scalar(f'SELECT retirement_wire FROM {A}.package_inputs WHERE scope_wire={sw};'),canonical(marker))
        self.assertEqual(before,[row for row in f.snapshot() if row[0]==N])
        self.assertEqual([f.get(command,reader) for command in (install,acquire)],originals)
        for profile in ('installer','recorder'):
            denied=self.db.sql('SELECT 1;',role=s['actors'][profile],check=False)
            self.assertNotEqual(denied.returncode,0)
            self.assertEqual(denied.stdout,'')
        changed=copy.deepcopy(stop)
        changed['body']['expected_control_sha256']='f'*64
        denied=self.db.sql(BEGIN+SETTINGS+f.call('submit',changed,control)+'COMMIT;\n',role=control,check=False)
        self.assertNotEqual(denied.returncode,0)
        self.assertIn('b2_retirement_refused',denied.stderr)
        self.assertEqual(stop['action_id'],s['stop_id'])
        self.submit(stop,control)
        reply=f.get(stop,reader)
        self.assertEqual(reply['original_command_wire'],canonical(stop))
        self.assertEqual(json.loads(reply['original_receipt_wire'])['original_command_sha256'],sha(canonical(stop)))
        self.assertEqual(reply['observed_head']['native_sequence'],'4')
        self.assertEqual(f.head(s)['source_mode'],'stopped')
        self.assertEqual(f.get(stop,reader),reply)


def submit_handoff_original(f, command, role):
    writer=f.writer(role)
    try:
        writer.send(f.call('submit',command,role))
        provisional=json.loads(writer.line())
        if provisional.get('pending_commit') is not True or provisional.get('original_command_sha256')!=sha(canonical(command)):
            raise AssertionError('b2_handoff_provisional_refused')
        writer.finish()
    finally:writer.close()


def prepare_handoff(f):
    """Prepare one independent local permit; no role is created at this point."""
    if not f.handoff or len(f.scopes)!=1:
        raise AssertionError('b2_handoff_fixture_scope_refused')
    db=f.db
    scope=f.scopes[0]
    installer,recorder,control,reader=(scope['actors'][p] for p in ('installer','recorder','control','reader'))
    install=f.command(scope)
    submit_handoff_original(f,install,installer)
    acquire=f.command(scope,'fence_acquire',action_id=str(UUID(int=993061)))
    acquire['body']=dict(fence_id=str(UUID(int=993062)),acquisition_epoch=scope['epoch'],
        holder_principal_binding_id=scope['bindings']['recorder'],requested_duration_us='60000000')
    submit_handoff_original(f,acquire,recorder)
    head=f.head(scope)
    resume=f.command(scope,'source_resume',action_id=str(UUID(int=993063)))
    resume['expected_fence_id']=head['active_fence_id']
    resume['expected_fence_revision']=head['fence_revision']
    submit_handoff_original(f,resume,control)
    head=f.head(scope)
    renew=f.command(scope,'fence_renew',action_id=str(UUID(int=993064)))
    renew['expected_fence_id']=head['active_fence_id']
    renew['expected_fence_revision']=head['fence_revision']
    renew['body']=dict(fence_id=head['active_fence_id'],expected_revision='1',requested_duration_us='60000000')
    stop=f.command(scope,'source_stop')
    stop['body']=dict(expected_control_sha256=sha(canonical(resume)),expected_mode='open')
    acquire_reply=f.get(acquire,reader)
    old_fence=json.loads(acquire_reply['original_result_wire'])['result_body']['original_fence_record']
    clock=json.loads(db.scalar("""WITH stamp AS MATERIALIZED (SELECT clock_timestamp() AS now)
        SELECT jsonb_build_array(floor(extract(epoch FROM now)*1000000)::bigint::text,
            floor(extract(epoch FROM now+interval '120 seconds')*1000000)::bigint::text,
            floor(extract(epoch FROM now+interval '150 seconds')*1000000)::bigint::text,
            (now+interval '150 seconds')::text) FROM stamp;"""))
    issuer_oid=db.scalar('SELECT oid::text FROM pg_roles WHERE rolname=session_user;',role=CREATOR)
    recorder_entry=next(e for e in scope['manifest']['bindings'] if e['principal_binding_id']==scope['bindings']['recorder'])
    permit=dict(handoff_id=str(UUID(int=993065)),scope=scope['scope'],installation_id=scope['installation_id'],
        package_sha256=scope['package']['native_package_sha256'],catalog_sha256=scope['package']['catalog_manifest_sha256'],
        head_sha256=head['native_head_sha256'],old_binding_id=scope['bindings']['recorder'],old_binding_sha256=sha(canonical(recorder_entry)),
        fence_sha256=sha(canonical(old_fence)),renew_wire=canonical(renew),stop_id=scope['stop_id'],issuer_oid=issuer_oid,
        new_binding_id=str(UUID(int=993066)),issuance_id=str(UUID(int=993067)),
        issued_at_us=clock[0],write_until_us=clock[1],login_until_us=clock[2],expires_us=str(int(clock[0])+45_000_000))
    sw=literal(canonical(scope['scope']))
    handoff=literal(permit['handoff_id'])+'::uuid'
    db.sql(f'BEGIN; SET LOCAL ROLE {ANCHOR_OWNER}; INSERT INTO {A}.credential_handoff'
        f'(scope_wire,handoff_id,permit_wire) VALUES({sw},{handoff},{literal(canonical(permit))}); COMMIT;')
    credentials=db.synthetic_password_clause(SUCCESSOR_RECORDER,clock[3])
    db.actor_deadlines[SUCCESSOR_RECORDER]=int(clock[2])
    stage=f'SELECT {A}._stage_credential_handoff({sw},{handoff});\n'
    finish=f'SELECT {A}._finish_credential_handoff({sw},{handoff});\n'
    ddl=(f"SET LOCAL createrole_self_grant='';\n"
         f'CREATE ROLE {SUCCESSOR_RECORDER} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT '
         f'NOREPLICATION NOBYPASSRLS {credentials};\n'
         f'ALTER ROLE {recorder} NOLOGIN;\nALTER ROLE {SUCCESSOR_RECORDER} LOGIN;\n')
    return dict(scope=scope,install=install,acquire=acquire,resume=resume,stop=stop,renew=renew,permit=permit,
        stage_sql=stage,role_ddl=ddl,finish_sql=finish,successor=SUCCESSOR_RECORDER,login_text=clock[3],
        old_fence=old_fence)


def issue_handoff(f,plan):
    issuer=f.writer(CREATOR)
    try:
        issuer.send(plan['stage_sql'])
        if issuer.line()!='':
            raise RuntimeError('b2_handoff_stage_output_refused')
        issuer.send(plan['role_ddl']+plan['finish_sql'])
        try:
            staged=issuer.line()
        except RuntimeError:
            # Issuance input includes a synthetic verifier. Do not include
            # arbitrary SQL errors from the verifier-bearing statement.
            raise RuntimeError('b2_handoff_role_or_finish_refused') from None
        issuer.finish()
    finally:issuer.close()
    # Discard any client-side commit outcome as authority. Read the exact
    # committed marker independently before allowing successor connection.
    sw=literal(canonical(plan['scope']['scope']))
    stored=f.db.scalar(f"SELECT handoff_wire FROM {A}.credential_handoff WHERE scope_wire={sw} "
        f"AND handoff_id={literal(plan['permit']['handoff_id'])}::uuid;")
    marker=json.loads(stored)
    if staged!=stored or canonical(marker)!=stored or marker['permit_sha256']!=sha(canonical(plan['permit'])):
        raise RuntimeError('b2_handoff_independent_marker_refused')
    return marker


@unittest.skipUnless(os.environ.get(OPT_IN)=='1','Requires isolated PostgreSQL opt-in')
class AllocationCredentialHandoffNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=AllocationHandoffPostgres().start()
        try:cls.fixture=AllocationFixture(cls.db,creator_edges=True)
        except BaseException:
            cls.db.close();raise

    @classmethod
    def tearDownClass(cls):cls.db.close()

    def assert_exact_k2(self,plan,marker):
        f=self.fixture
        current=json.loads(self.db.scalar(SETTINGS+f'SELECT {N}._catalog();',timeout=30))
        expected=copy.deepcopy(f.catalog['value'])
        new_oid=marker['successor_binding']['session_user_oid']
        recorder=plan['scope']['actors']['recorder']
        old_role=next(role for role in expected['roles'] if role['name']==recorder)
        old_oid=old_role['oid']
        old_role['login']=False
        expected['roles'].append(dict(old_role,name=SUCCESSOR_RECORDER,oid=new_oid,login=True,valid_until=plan['login_text']))
        expected['roles'].sort(key=lambda role:int(role['oid']))
        old_edge=next(edge for edge in expected['memberships'] if str(edge['roleid'])==old_oid)
        new_edges=[edge for edge in current['memberships'] if str(edge['roleid'])==new_oid]
        self.assertEqual(len(new_edges),1)
        assigned_edge=new_edges[0]
        expected['memberships'].append(dict(old_edge,oid=assigned_edge['oid'],roleid=type(old_edge['roleid'])(new_oid)))
        expected['memberships'].sort(key=lambda edge:int(edge['oid']))
        allocated=json.loads(self.db.scalar("""SELECT jsonb_build_array(
            'pg_catalog.pg_namespace'::regclass::oid,'pg_catalog.pg_proc'::regclass::oid,
            'pg_catalog.pg_authid'::regclass::oid);"""))
        schema=next(row for row in expected['schemas'] if row['name']==N)
        schema['acl'].append(f'{SUCCESSOR_RECORDER}=U/{OWNER}')
        targets=[(allocated[0],schema['oid'])]
        for name in ('submit','get_original'):
            function=next(row for row in expected['functions'] if row['proname']==name)
            function['proacl'].append(f'{SUCCESSOR_RECORDER}=X/{OWNER}')
            targets.append((allocated[1],function['oid']))
        template=next(row for row in expected['shared_dependencies'] if row['deptype']=='a')
        for cls,obj in targets:
            expected['shared_dependencies'].append(dict(template,
                classid=type(template['classid'])(cls),objid=type(template['objid'])(obj),objsubid=0,
                refclassid=type(template['refclassid'])(allocated[2]),refobjid=type(template['refobjid'])(new_oid),deptype='a'))
        expected['shared_dependencies'].sort(key=lambda d:tuple(int(d[k]) for k in ('dbid','classid','objid','objsubid','refclassid','refobjid'))+(d['deptype'],))
        self.assertEqual(current,expected)
        self.assertEqual(marker['catalog_sha256'],sha(canonical(expected)))

    def test_one_scope_preserves_originals_and_transfers_renewal_to_new_recorder(self):
        f=self.fixture
        plan=prepare_handoff(f)
        scope=plan['scope']
        old=scope['actors']['recorder']
        reader=scope['actors']['reader']
        history=[f.get(plan[k],reader) for k in ('install','acquire','resume')]
        before=f.snapshot()
        before_native=[row for row in before if row[0]==N]
        self.assertEqual(self.db.scalar("SELECT session_user,system_user,ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid();",
            role=CREATOR),f'{CREATOR}|scram-sha-256:{CREATOR}|t')
        self.assertNotEqual(self.db.sql('SELECT 1;',role=SUCCESSOR_RECORDER,check=False).returncode,0)

        competing=copy.deepcopy(plan['renew'])
        competing['action_id']=str(UUID(int=993069))
        blocker=f.writer(old)
        try:
            blocker.send(f.call('submit',competing,old))
            self.assertTrue(json.loads(blocker.line())['pending_commit'])
            blocked=self.db.sql(BEGIN+SETTINGS+plan['stage_sql']+'COMMIT;\n',role=CREATOR,check=False)
            self.assertNotEqual(blocked.returncode,0)
            self.assertRegex(blocked.stderr,r'(?m)^ERROR:\s+55P03:')
            blocker.finish('ROLLBACK;')
        finally:blocker.close()
        incomplete=self.db.sql(BEGIN+SETTINGS+plan['stage_sql']+'COMMIT;\n',role=CREATOR,check=False)
        self.assertNotEqual(incomplete.returncode,0)
        self.assertRegex(incomplete.stderr,r'(?m)^ERROR:\s+P0001: b2_handoff_marker_refused\s*$')
        self.assertEqual(before,f.snapshot())
        issuer=f.writer(CREATOR)
        try:
            issuer.send(plan['stage_sql'])
            self.assertEqual(issuer.line(),'')
            issuer.send(plan['role_ddl']+plan['finish_sql'])
            try:
                self.assertEqual(json.loads(issuer.line())['handoff_id'],plan['permit']['handoff_id'])
            except RuntimeError:
                raise RuntimeError('b2_handoff_role_or_finish_refused') from None
            issuer.send('SET CONSTRAINTS ALL IMMEDIATE;\n')
            issuer._process.stdin.close()
            error=issuer.failure_stderr()
            self.assertNotEqual(issuer._process.returncode,0)
            self.assertRegex(error,r'(?m)^ERROR:\s+P0001: b2_handoff_commit_form_refused\s*$')
        finally:issuer.close()
        self.assertEqual(before,f.snapshot())
        self.assertEqual(self.db.scalar(f"SELECT count(*) FROM pg_roles WHERE rolname={literal(SUCCESSOR_RECORDER)};"),'0')
        self.assertEqual([f.get(plan[k],reader) for k in ('install','acquire','resume')],history)

        held=f.writer(old)
        try:
            held.send('SELECT session_user;\n')
            self.assertEqual(held.line(),old)
            marker=issue_handoff(f,plan)
            held.send(f.call('submit',competing,old))
            held._process.stdin.close()
            error=held.failure_stderr()
            self.assertNotEqual(held._process.returncode,0)
            self.assertEqual(held._process.stdout.read(),b'')
            self.assertRegex(error,r'(?m)^ERROR:\s+P0001: b2_actor_scope_refused\s*$')
        finally:held.close()
        self.assertNotEqual(self.db.sql('SELECT 1;',role=old,check=False).returncode,0)
        self.assertEqual([row for row in f.snapshot() if row[0]==N],before_native)
        self.assertEqual([f.get(plan[k],reader) for k in ('install','acquire','resume')],history)
        self.assert_exact_k2(plan,marker)
        retried=self.db.sql(BEGIN+SETTINGS+plan['stage_sql']+'COMMIT;\n',role=CREATOR,check=False)
        self.assertNotEqual(retried.returncode,0)
        self.assertIn('b2_handoff_permit_refused',retried.stderr)

        changed=self.db.sql(BEGIN+SETTINGS+f.call('submit',competing,SUCCESSOR_RECORDER)+'COMMIT;\n',
            role=SUCCESSOR_RECORDER,check=False)
        self.assertNotEqual(changed.returncode,0)
        self.assertIn('b2_fence_renew_refused',changed.stderr)
        submit_handoff_original(f,plan['renew'],SUCCESSOR_RECORDER)
        renewed=f.get(plan['renew'],reader)
        self.assertEqual(renewed['original_command_wire'],canonical(plan['renew']))
        fence=json.loads(renewed['original_result_wire'])['result_body']['original_fence_record']
        self.assertEqual(fence['fence_id'],plan['old_fence']['fence_id'])
        self.assertEqual(fence['revision'],'2')
        self.assertEqual(fence['holder_principal_binding_id'],plan['permit']['new_binding_id'])
        self.assertEqual(json.loads(renewed['original_receipt_wire'])['catalog_manifest_sha256'],marker['catalog_sha256'])
        for key,original in zip(('install','acquire','resume'),history):
            recovered=f.get(plan[key],reader)
            self.assertEqual({k:v for k,v in recovered.items() if k!='observed_head'},
                {k:v for k,v in original.items() if k!='observed_head'})


if __name__=='__main__':unittest.main()
