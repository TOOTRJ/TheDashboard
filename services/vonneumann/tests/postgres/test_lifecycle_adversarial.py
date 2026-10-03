"""Hostile raw v4 envelopes must roll back independently of the Python validator."""
from copy import deepcopy

from tests.lifecycle_fixtures import lifecycle_trace
from tests.postgres.harness import PostgresContractTestCase
from tests.postgres.test_command_adapter import identity,literal
from tests.postgres.test_decimal_lineage_contract import document
from tests.test_lifecycle_protocol import nodes,evaluation_node
from vonneumann.core import exact_rehearsal as base
from vonneumann.core.optimizer_evidence import encode_optimizer_evidence, validate_optimizer_evidence
from vonneumann.db.lifecycle_protocol import _optimizer_views


class LifecycleAdversarialTests(PostgresContractTestCase):
    def setUp(self):
        self.owner,self.run,self.worker = identity(),identity(),identity()
        self.db.sql(f'INSERT INTO auth.users(id) VALUES ({literal(self.owner)});')
        self.revision = 1

    def payload(self,candidate):
        return {'version':4,'operations':candidate.operations,'transition':candidate.transition}

    def sql(self,payload,revision=None):
        return 'SELECT vn_durability.commit_command('+','.join((literal(self.owner),literal(self.run),
            literal(self.worker),'1',str(self.revision if revision is None else revision),literal(identity()),document(payload)))+');'

    def prefix(self,kind,select,*,strategy='genetic_algorithm'):
        config,candidates = lifecycle_trace(kind,strategy=strategy,owner_id=self.owner,run_id=self.run)
        target_index = next(i for i,c in enumerate(candidates) if select(c))
        statements = ['SELECT vn_durability.create_run('+','.join((literal(self.owner),literal(self.run),
            literal(self.worker),literal(identity()),document(config.run_configuration()),literal(config.initial_cash),'120'))+');']
        for candidate in candidates[:target_index]:
            statements.append(self.sql(self.payload(candidate),candidate.state.revision-1))
        self.db.sql('\n'.join(statements),role='service_role',timeout=60)
        self.revision = candidates[target_index].state.revision-1
        return candidates[target_index],candidates,target_index

    def snapshot(self):
        parts=[]
        for table in ('runs','accounts','positions','commands','distributions','distribution_sources',
                      'account_lineage','lineage_sources','outbox_events','outbox_progress'):
            column='id' if table=='runs' else 'run_id'
            parts.extend((literal(table),"(SELECT coalesce(jsonb_agg(digest ORDER BY digest),'[]'::jsonb) FROM "
                "(SELECT encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') digest "
                f'FROM vn_durability.{table} t WHERE {column}={literal(self.run)}) q)'))
        return self.db.scalar('SELECT jsonb_build_object('+','.join(parts)+');')

    def reject(self,payload,expected=None):
        before=self.snapshot()
        result=self.db.sql(self.sql(payload),role='service_role',check=False)
        self.assertNotEqual(result.returncode,0,'Raw lifecycle mutation was accepted')
        if expected:self.assertIn(expected,result.stderr)
        self.assertEqual(self.snapshot(),before,'Rejected command changed durable rows')

    @staticmethod
    def terminal(candidate):
        return any(a['reason']=='terminal' for a in candidate.transition['evidence']['actions'])

    def test_bootstrap_cannot_claim_another_solvers_lineage(self):
        candidate,_,_=self.prefix('replacement',lambda c:c.transition['before'] is None)
        payload=self.payload(candidate)
        payload['operations'][0]['lineage']['strategy']='differential_evolution'
        self.reject(payload)

    def test_lifecycle_money_requires_decimal_strings_in_raw_requests(self):
        candidate,_,_=self.prefix('replacement',lambda c:c.transition['before'] is None)
        payload=self.payload(candidate)
        payload['transition']['after']['engine']['lifecycle']['risk']['observed_equity']=1000
        self.reject(payload)
        self.run,self.worker=identity(),identity()
        candidate,_,_=self.prefix('terminal',self.terminal)
        payload=self.payload(candidate)
        payload['transition']['after']['engine']['members'][0]['terminal']['cash']=80
        self.reject(payload)

    def test_required_drawdown_death_cannot_be_omitted_with_consistent_live_economics(self):
        candidate,_,_=self.prefix('terminal',self.terminal)
        payload=self.payload(candidate)
        data,strategy,cohort=candidate.state._fork()
        # Rebuild a valid encoded cohort without the terminal snapshots. Keep
        # every protective fill but retain each below-limit account as alive.
        cohort._evaluations.clear()
        total=0
        accounts={a['id']:a for a in data['accounts']}
        for member in data['engine']['members']:
            cash=member['terminal']['cash'];total+=base._amount(cash)
            accounts[member['id']].update(cash=cash,retired=False)
            member['terminal']=None
        data['reserve']=base._text(base._amount(data['reserve'])-total,36)
        data['engine']['cohort']=base._views(cohort.to_dict())
        data['engine']['optimizer']=encode_optimizer_evidence(strategy,cohort)
        pairs=[(op,action) for op,action in zip(payload['operations'],payload['transition']['evidence']['actions'])
               if op['kind']!='retire']
        payload['operations']=[op for op,_ in pairs]
        actions=[action for _,action in pairs]
        for index,action in enumerate(actions):action['operation_index']=index
        payload['transition'].update(after=data,events=[{'kind':a['reason'],'at':55802,
            'account_id':a['account_id'],'position_id':a['position_id'],'operation_index':a['operation_index']} for a in actions])
        payload['transition']['evidence']['actions']=actions
        self.reject(payload,'missing_terminal_member')

    def test_protective_stop_cannot_be_relabeled_as_death_liquidation(self):
        candidate,_,_=self.prefix('terminal',self.terminal)
        payload=self.payload(candidate)
        action=next(a for a in payload['transition']['evidence']['actions'] if a['reason']=='stop_loss')
        action['reason']='death_liquidation'
        event=next(e for e in payload['transition']['events'] if e['operation_index']==action['operation_index'])
        event['kind']='death_liquidation'
        self.reject(payload)

    def test_frozen_score_cannot_be_rewritten_even_when_optimizer_mirror_agrees(self):
        candidate,_,_=self.prefix('terminal',lambda c:c.transition['before'] is not None and
            all(m['terminal'] is not None for m in c.transition['before']['engine']['members']))
        payload=self.payload(candidate);engine=payload['transition']['after']['engine']
        row=engine['cohort']['evaluations'][0];row['fitness']={'float64':1.0.hex()}
        encoded=evaluation_node(engine['optimizer'],row['probe_id']);encoded['fields']['fitness']['hex']=1.0.hex()
        self.reject(payload)

    def test_pause_cannot_modify_retained_position_or_close_it(self):
        candidate,_,_=self.prefix('pause_stop',lambda c:c.transition['evidence']['control'] is not None)
        original=self.payload(candidate)
        changed=deepcopy(original);changed['transition']['after']['positions'][0]['closed']=True
        self.reject(changed)
        changed=deepcopy(original);changed['transition']['after']['positions'][0]['entry']['reference_price']='101'
        self.reject(changed)
        changed=deepcopy(original);changed['operations'].insert(0,{'kind':'retire','id':candidate.state.to_dict()['engine']['members'][0]['id']})
        self.reject(changed)

    def test_recovery_requires_current_trip_identity(self):
        candidate,_,_=self.prefix('recover',lambda c:c.transition['evidence']['control'] is not None)
        payload=self.payload(candidate);payload['transition']['evidence']['control']['trip_id']=identity()
        self.reject(payload)

    def test_cma_distribution_must_retain_the_complete_ordered_evaluation_sources(self):
        candidate,_,_=self.prefix('replacement',lambda c:c.state.to_dict()['engine']['generation']==1,strategy='cma_es')
        original=self.payload(candidate)
        for transform in (lambda ids:ids[:2],lambda ids:list(reversed(ids))):
            payload=deepcopy(original)
            distribution=next(op for op in payload['operations'] if op['kind']=='distribution')
            distribution['source_ids']=transform(distribution['source_ids'])
            self.reject(payload)

    def test_births_cannot_swap_their_bound_offspring_slots(self):
        candidate,_,_=self.prefix('replacement',lambda c:c.state.to_dict()['engine']['generation']==1)
        payload=self.payload(candidate)
        births=[op for op in payload['operations'] if op['kind']=='birth']
        births[0]['lineage']['offspring_index'],births[1]['lineage']['offspring_index']=1,0
        self.reject(payload)

    def test_due_window_cannot_be_committed_as_an_indefinite_noop(self):
        candidate,_,_=self.prefix('replacement',lambda c:c.state.to_dict()['engine']['generation']==1)
        payload=self.payload(candidate);transition=payload['transition']
        after=deepcopy(transition['before']);after['revision']+=1
        after['engine']['decision_timestamp']=transition['evidence']['observation']['timestamp']
        payload['operations']=[]
        transition.update(after=after,events=[])
        transition['evidence']['actions']=[]
        transition['evidence']['observation'].update(candle_end=None,candle_close=None)
        self.reject(payload)

    def test_noop_cannot_reorder_encoded_strategy_maps(self):
        candidate,_,_=self.prefix('replacement',lambda c:c.transition['evidence']['kind']=='protective')
        payload=self.payload(candidate)
        optimizer=payload['transition']['after']['engine']['optimizer']
        expected=_optimizer_views(optimizer)
        mapping=next(n for n in nodes(optimizer['strategy'])
                     if n.get('type')=='map' and [p[0] for p in n['entries'][:2]]==['rsi_period','rsi_oversold'])
        # Swap entries containing simple strings; compound-node reordering
        # would itself violate canonical node allocation before this rule.
        mapping['entries'][0],mapping['entries'][1]=mapping['entries'][1],mapping['entries'][0]
        validate_optimizer_evidence(optimizer)
        self.assertEqual(_optimizer_views(optimizer),expected)
        self.reject(payload)
