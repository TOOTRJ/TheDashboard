"""Genuine v4 lifecycle commands and adversarial edits of their wire evidence."""
from copy import deepcopy
from functools import lru_cache
import unittest

from tests.security_support import OfflineTestMixin
from tests.test_exact_lifecycle import ALGORITHMS, OWNER, RUN, initial, opened, advance, life, inputs
from tests.test_exact_rehearsal import WORKER
from vonneumann.core.decimal_execution import DecimalExecutionConfig
from vonneumann.db.command_protocol import CommandValidationError, PreparedCommand


def command(candidate, *, transition=None, operations=None, version=4):
    return PreparedCommand.batch(OWNER, RUN, WORKER, 1, candidate.state.revision - 1,
        candidate.operations if operations is None else operations, version=version,
        transition=candidate.transition if transition is None else transition)


@lru_cache(maxsize=12)
def risk_trace(algorithm='genetic_algorithm'):
    config, original = opened(algorithm, loss='50')
    halted = life.prepare_protective(original.state, life.ExactObservation(55802, '97.5'), inputs(55802))
    rebound = life.prepare_protective(halted.state, life.ExactObservation(55803, '100'), inputs(55803))
    trip = rebound.state.to_dict()['engine']['lifecycle']['risk']['trip_id']
    recovered = life.prepare_control(rebound.state, 'recover', inputs(55803),
        life.ExactObservation(55803, '100', 55800, '120'), trip_id=trip)
    protected, restart = advance(recovered.state, 55804, end=55800, close='120')
    return config, original, halted, rebound, recovered, protected, restart


@lru_cache(maxsize=8)
def death_trace(algorithm='genetic_algorithm'):
    config, original = opened(algorithm)
    terminal = life.prepare_protective(original.state, life.ExactObservation(55802, '20'), inputs(55802))
    candidate = terminal
    frames = []
    for bar in (63, 64, 65):
        protected, candidate = advance(candidate.state, bar * 900, end=bar * 900, close='120')
        frames.extend((protected, candidate))
    return config, original, terminal, frames


def nodes(value):
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from nodes(child)
    elif type(value) is list:
        for child in value:
            yield from nodes(child)


def evaluation_node(optimizer, identity):
    return next(node for node in nodes(optimizer) if node.get('class') == 'EvaluatedCandidate'
                and node['fields']['probe_id'] == identity)


class LifecycleProtocolTests(OfflineTestMixin, unittest.TestCase):
    def reject(self, candidate, mutation):
        body, operations = candidate.transition, candidate.operations
        mutation(body, operations)
        with self.assertRaises(CommandValidationError):
            command(candidate, transition=body, operations=operations)

    def test_all_four_actual_control_recovery_restart_commands_and_v3_separation(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                config, *candidates = risk_trace(algorithm)
                PreparedCommand.create(OWNER, RUN, WORKER, config.run_configuration(), config.initial_cash)
                start = life.bootstrap(config, inputs(0))
                original = candidates[0]
                pause = life.prepare_control(original.state, 'pause', inputs(55802))
                resume = life.prepare_control(pause.state, 'resume', inputs(55803))
                stop = life.prepare_control(original.state, 'stop', inputs(55802))
                for candidate in (start, *candidates, pause, resume, stop):
                    with self.subTest(phase=candidate.transition['evidence']['kind'],
                                      status=candidate.state.to_dict()['status']):
                        prepared = command(candidate)
                        self.assertEqual(prepared.rpc_args['payload']['version'], 4)
                        self.assertEqual(prepared.rpc_args['payload']['transition'], candidate.transition)
                with self.assertRaises(CommandValidationError):
                    command(candidates[-1], version=3)
        from tests.test_exact_rehearsal import initial as v3_initial
        _, legacy = v3_initial()
        command(legacy, version=3)
        with self.assertRaises(CommandValidationError):
            command(legacy, version=4)

    def test_all_four_early_terminal_and_complete_deadline_commands_validate(self):
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                _, original, terminal, frames = death_trace(algorithm)
                for candidate in (original, terminal, *frames):
                    command(candidate)
                final = frames[-1]
                self.assertEqual(final.state.to_dict()['engine']['generation'], 1)
                self.assertEqual(sum(op['kind'] == 'birth' for op in final.operations), 8)

    def test_recovery_can_refresh_one_contiguous_candle_without_rewriting_member_cursor(self):
        _, _, halted, *_ = risk_trace()
        rebound = life.prepare_protective(halted.state, life.ExactObservation(56700, '100'), inputs(56700))
        trip = rebound.state.to_dict()['engine']['lifecycle']['risk']['trip_id']
        recovered = life.prepare_control(rebound.state, 'recover', inputs(56700),
            life.ExactObservation(56700, '100', 56700, '120'), trip_id=trip)
        self.assertEqual(recovered.state.to_dict()['engine']['ema']['last_end'], 56700)
        self.assertTrue(all(m['cursor'] == 55800 for m in recovered.state.to_dict()['engine']['members']))
        command(recovered)
        protected, restarted = advance(recovered.state, 56701, end=56700, close='120')
        command(protected); command(restarted)

    def test_controls_reject_invented_counters_latches_and_signal_boundaries(self):
        _, original, halted, _, recovered, protected, _ = risk_trace()
        pause = life.prepare_control(original.state, 'pause', inputs(55802))
        changes = (
            (pause, lambda t, o: t['after']['engine']['lifecycle'].__setitem__('search_epoch', 1)),
            (pause, lambda t, o: t['after']['engine']['lifecycle'].__setitem__('signals_after', 55802)),
            (pause, lambda t, o: t['after']['engine']['lifecycle']['risk'].__setitem__('recovery_count', 1)),
            (halted, lambda t, o: t['after']['engine']['lifecycle']['risk'].__setitem__('trip_equity', '994')),
            (halted, lambda t, o: t['after']['engine']['lifecycle']['risk'].__setitem__('observed_equity', '994')),
            (halted, lambda t, o: t['after']['engine']['lifecycle']['risk'].__setitem__('tripped_at', 55801)),
            (recovered, lambda t, o: t['after']['engine']['lifecycle']['risk'].__setitem__('recovery_count', 2)),
            (recovered, lambda t, o: t['evidence']['control'].__setitem__('trip_id', RUN)),
            (protected, lambda t, o: t['after']['engine']['lifecycle'].__setitem__('signals_after', None)),
        )
        for index, (candidate, change) in enumerate(changes):
            with self.subTest(change=index):
                self.reject(candidate, change)

    def test_initial_risk_crossing_cannot_be_replaced_with_final_post_fee_equity(self):
        _, original = opened(loss='50', execution=DecimalExecutionConfig('35'))
        halted = life.prepare_protective(original.state, life.ExactObservation(55802, '97'), inputs(55802))
        command(halted)
        risk = halted.state.to_dict()['engine']['lifecycle']['risk']
        self.assertNotEqual(risk['trip_equity'], risk['observed_equity'])
        self.reject(halted, lambda t, o: t['after']['engine']['lifecycle']['risk'].__setitem__(
            'trip_equity', risk['observed_equity']))

    def test_cohort_mirror_cannot_disagree_with_optimizer_or_original_slot(self):
        _, _, terminal, _ = death_trace()
        changes = (
            lambda t, o: t['after']['engine']['cohort']['member_ids'].reverse(),
            lambda t, o: t['after']['engine']['cohort'].__setitem__('completed_count', 7),
            lambda t, o: t['after']['engine']['cohort']['evaluations'][0].__setitem__('fitness', {'float64': 0.0.hex()}),
            lambda t, o: t['after']['engine']['cohort']['evaluations'][0].__setitem__('cohort_complete', True),
            lambda t, o: t['after']['engine']['optimizer']['cohort']['fields'].__setitem__('phase', 'completed'),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                self.reject(terminal, change)

    def test_aborted_optimizer_cannot_keep_live_selection_state_or_advance_rng(self):
        for algorithm in ALGORITHMS:
            _, _, halted, *_ = risk_trace(algorithm)
            command(halted)
            with self.subTest(algorithm=algorithm, mutation='live_optimizer'):
                self.reject(halted, lambda t, o: t['after']['engine']['optimizer'].__setitem__(
                    'strategy', deepcopy(t['before']['engine']['optimizer']['strategy'])))
            def mutate_rng(t, _):
                rng = t['after']['engine']['optimizer']['strategy']['fields']['_rng']
                # The first RNG-state word is still a valid uint32, but it is
                # not the state produced by the interruption.
                rng['words'][0] ^= 1
            with self.subTest(algorithm=algorithm, mutation='rng'):
                self.reject(halted, mutate_rng)

    def test_restart_lineage_cannot_downgrade_to_founder_or_forge_selected_ancestry(self):
        _, _, _, _, _, _, restarted = risk_trace()
        def downgrade(_t, operations):
            lineage = next(op['lineage'] for op in operations if op['kind'] == 'birth')
            lineage.update(version=1, operation='founder', source_iteration_id=None,
                           offspring_index=None, sources=[], distribution_id=None)
        def wrong_parent(t, operations):
            lineage = next(op['lineage'] for op in operations if op['kind'] == 'birth')
            identity = t['before']['engine']['members'][1]['id']
            for source in lineage['sources']:
                source['source_id'] = identity
        for change in (downgrade, wrong_parent):
            with self.subTest(change=change.__name__):
                self.reject(restarted, change)

    def test_pause_control_cannot_silently_close_reclaim_or_reprice_retained_positions(self):
        _, original, *_ = risk_trace()
        paused = life.prepare_control(original.state, 'pause', inputs(55802))
        changes = (
            lambda t, o: t['after']['positions'].clear(),
            lambda t, o: t['after']['positions'][0].__setitem__('closed', True),
            lambda t, o: t['after']['accounts'][0].__setitem__('cash', '100'),
            lambda t, o: t['after'].__setitem__('reserve', '225'),
            lambda t, o: t['after']['engine']['last_quote'].__setitem__('price', '99'),
            lambda t, o: t['after']['engine']['members'][0].__setitem__('peak_equity', '101'),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                self.reject(paused, change)

    def test_protection_cannot_fabricate_entry_or_remove_eligible_exit_intents(self):
        _, original, *_ = risk_trace()
        _, signaled = advance(original.state, 56700, end=56700, close='80')
        self.assertTrue(any(m['pending'] is not None for m in signaled.state.to_dict()['engine']['members']))
        protected = life.prepare_protective(signaled.state, life.ExactObservation(56701, '100'), inputs(56701))
        command(protected)
        self.reject(protected, lambda t, o: t['after']['engine']['members'][0].__setitem__('pending', None))
        _, start = initial()
        _, first = advance(start.state, 900, end=900, close='100')
        clean = life.prepare_protective(first.state, life.ExactObservation(901, '100'), inputs(901))
        def invented(t, _):
            member = t['after']['engine']['members'][0]
            member.update(cursor=900, pending={'action':'entry','signal_at':900,'position_id':None})
        self.reject(clean, invented)

    def test_frozen_terminal_cash_and_scores_cannot_be_rewritten_in_both_mirrors(self):
        _, _, terminal, frames = death_trace()
        def corrupt_new_score(t, _):
            engine = t['after']['engine']
            row = engine['cohort']['evaluations'][0]
            row['fitness'] = {'float64': 0.0.hex()}
            saved = evaluation_node(engine['optimizer'], row['probe_id'])
            saved['fields']['fitness']['hex'] = 0.0.hex()
        self.reject(terminal, corrupt_new_score)
        later = frames[0]
        self.reject(later, corrupt_new_score)
        self.reject(terminal, lambda t, o: t['after']['engine']['members'][0]['terminal'].__setitem__('cash', '81'))

    def test_market_observation_cannot_invent_an_unrequested_evaluation_abort(self):
        _, original, *_ = risk_trace()
        paused = life.prepare_control(original.state, 'pause', inputs(55802))
        def unrequested(t, operations):
            operations.clear()
            t['evidence'].update(kind='protective', control=None, actions=[],
                observation={'timestamp':55802,'price':'100','candle_end':None,'candle_close':None})
            t['events'] = [event for event in t['events'] if event['kind'] == 'evaluation_aborted']
            t['after']['status'] = 'running'
            t['after']['engine']['last_quote'] = {'timestamp':55802,'price':'100'}
            t['after']['engine']['lifecycle']['last_control_at'] = None
            t['after']['engine']['lifecycle']['risk']['observed_at'] = 55802
        self.reject(paused, unrequested)

    def test_cohort_cannot_start_before_its_complete_history_is_ready(self):
        _, start = initial()
        _, first = advance(start.state, 900, end=900, close='100')
        protected = life.prepare_protective(first.state, life.ExactObservation(901, '100'), inputs(901))
        def start_early(t, _):
            engine = t['after']['engine']
            engine['cohort'].update(phase='evaluating', started_at={'float64':901.0.hex()},
                                     ends_at={'float64':4501.0.hex()})
            fields = engine['optimizer']['cohort']['fields']
            fields.update(phase='evaluating', started_at={'type':'float','hex':901.0.hex()},
                          ends_at={'type':'float','hex':4501.0.hex()})
        self.reject(protected, start_early)

    def test_reference_expansion_has_an_independent_bounded_audit_budget(self):
        from vonneumann.db.lifecycle_protocol import _optimizer_views
        # Acyclic, backward-only references create linear encoded size but an
        # exponentially expanding audit view unless each traversal is charged.
        graph = {'type':'list','node':1,'items':['bounded leaf']}
        for identity in range(2, 24):
            graph = {'type':'list','node':identity,'items':[graph,{'ref':identity-1}]}
        with self.assertRaisesRegex(CommandValidationError, 'expansion exceeds'):
            _optimizer_views({'strategy':graph,'cohort':None})

    def test_nonaborted_strategy_rejects_map_order_change_hidden_by_primitive_views(self):
        from vonneumann.core.optimizer_evidence import validate_optimizer_evidence
        from vonneumann.db.lifecycle_protocol import _optimizer_views
        _, original, *_ = risk_trace()
        protected = life.prepare_protective(original.state, life.ExactObservation(55802, '100'), inputs(55802))
        command(protected)
        body = protected.transition
        optimizer = body['after']['engine']['optimizer']
        expected = _optimizer_views(optimizer)
        signature = next(node for node in nodes(optimizer['strategy'])
            if node.get('type') == 'map' and [pair[0] for pair in node['entries'][:2]] ==
            ['rsi_period', 'rsi_oversold'])
        signature['entries'][0], signature['entries'][1] = signature['entries'][1], signature['entries'][0]
        validate_optimizer_evidence(optimizer)
        self.assertEqual(_optimizer_views(optimizer), expected)
        with self.assertRaisesRegex(CommandValidationError, 'encoded strategy continuation'):
            command(protected, transition=body)

    def test_new_deadline_result_cannot_claim_historical_drawdown_termination(self):
        from tests.lifecycle_fixtures import lifecycle_trace
        _, candidates = lifecycle_trace('replacement')
        completed = candidates[-1]
        command(completed)
        self.assertEqual(completed.transition['before']['engine']['cohort']['evaluations'], [])
        for backdate in (False, True):
            with self.subTest(backdate=backdate):
                body = completed.transition
                result = body['after']['engine']['last_evaluation']['cohort']['evaluations'][0]
                self.assertEqual(result['reason'], 'window_complete')
                result['reason'] = 'drawdown'
                if backdate:
                    result['terminated_at'] = {'float64': 55802.0.hex()}
                with self.assertRaisesRegex(CommandValidationError, 'actual completion reason or source time'):
                    command(completed, transition=body)

    def test_paired_abort_mirrors_must_name_the_actual_control_cause(self):
        _, original, *_ = risk_trace()
        pause = life.prepare_control(original.state, 'pause', inputs(55802))
        body = pause.transition
        engine = body['after']['engine']
        for cohort in (engine['cohort'], engine['last_evaluation']['cohort']):
            cohort['abort_reason'] = 'stopped'
            for row in cohort['evaluations']:
                row['reason'] = 'stopped'
        engine['optimizer']['cohort']['fields']['abort_reason'] = 'stopped'
        for node in nodes(engine['optimizer']['cohort']):
            if node.get('class') == 'EvaluatedCandidate':
                node['fields']['reason'] = 'stopped'
        with self.assertRaisesRegex(CommandValidationError, 'actual lifecycle cause'):
            command(pause, transition=body)

    def test_due_evaluation_cannot_be_skipped_by_an_empty_decision(self):
        from tests.lifecycle_fixtures import lifecycle_trace
        _, candidates = lifecycle_trace('replacement')
        due = candidates[-1]
        body = due.transition
        body['after'] = deepcopy(body['before'])
        body['after']['revision'] += 1
        at = body['evidence']['observation']['timestamp']
        body['after']['engine']['decision_timestamp'] = at
        body['evidence']['observation'].update(candle_end=None, candle_close=None)
        body['evidence']['actions'] = []
        body['events'] = []
        self.assertEqual(body['before']['engine']['cohort']['phase'], 'evaluating')
        self.assertGreaterEqual(at, float.fromhex(body['before']['engine']['cohort']['ends_at']['float64']))
        with self.assertRaisesRegex(CommandValidationError, 'Due evaluation must complete'):
            command(due, transition=body, operations=[])

    def test_cma_distribution_requires_full_ordered_sources_and_actual_chain(self):
        _, _, _, frames = death_trace('cma_es')
        first = frames[-1]
        command(first)
        changes = (
            lambda op: op.__setitem__('source_ids', op['source_ids'][:2]),
            lambda op: op['source_ids'].reverse(),
            lambda op: op.__setitem__('source_iteration_id', 'invented-window'),
            lambda op: op.update(stage='update', previous_distribution_id=RUN),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                operations = first.operations
                distribution = next(op for op in operations if op['kind'] == 'distribution')
                change(distribution)
                with self.assertRaisesRegex(CommandValidationError, 'complete ordered cohort or preceding distribution'):
                    command(first, operations=operations)
        following = first
        for bar in (66, 67, 68, 69):
            _, following = advance(following.state, bar * 900, end=bar * 900, close='120')
        command(following)
        current = next(op for op in following.operations if op['kind'] == 'distribution')
        self.assertEqual(current['stage'], 'update')
        self.assertEqual(current['previous_distribution_id'], first.state.to_dict()['engine']['distribution_id'])
        def reset_chain(_body, operations):
            next(op for op in operations if op['kind'] == 'distribution').update(
                stage='bootstrap', previous_distribution_id=None)
        self.reject(following, reset_chain)

    def test_selection_slots_roles_and_flat_parent_ids_bind_current_evaluated_cohort(self):
        _, _, _, frames = death_trace()
        first = frames[-1]
        command(first)
        def wrong_slot(_body, operations):
            next(op for op in operations if op['kind'] == 'birth')['lineage']['offspring_index'] = 99
        self.reject(first, wrong_slot)
        operations = first.operations
        lineage = next(op['lineage'] for op in operations if op['kind'] == 'birth')
        current = first.transition['before']['engine']['cohort']['member_ids']
        existing = {source['source_id'] for source in lineage['sources']}
        lineage['sources'][0]['source_id'] = next(identity for identity in current if identity not in existing)
        with self.assertRaisesRegex(CommandValidationError, 'Flat parent identities contradict'):
            command(first, operations=operations)
        following = first
        for bar in (66, 67, 68, 69):
            _, following = advance(following.state, bar * 900, end=bar * 900, close='120')
        command(following)
        operations = following.operations
        lineage = next(op['lineage'] for op in operations if op['kind'] == 'birth')
        lineage['sources'][0]['source_id'] = current[0]
        with self.assertRaisesRegex(CommandValidationError, 'offspring slot or current cohort'):
            command(following, operations=operations)


if __name__ == '__main__':
    unittest.main()
