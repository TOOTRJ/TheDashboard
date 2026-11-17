"""Owned journal replay, unknown acknowledgments and repeated paper evolution."""
from dataclasses import replace
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from tests.test_prospective_ga_v3_model import fill_policy, new_inputs, inputs_for_mark
    from tests.test_prospective_source_v3 import mark, seal, OWNER, RUN, MARKET, PROCESS, PRINCIPAL, PACKAGE, END
    from vonneumann.market import prospective_source_v3 as source
    from vonneumann.research.prospective_ga_v3_policy import V3Config, SourceBinding
    from vonneumann.core.prospective_runtime import ProspectiveRuntime, JournalEntry, RuntimePending, RuntimeRefused, JournalRejected


class MemoryJournal:
    def __init__(self):
        self.rows, self.by_id = [], {}
        self.lose_reply = False

    async def append(self, entry, *, expected_sequence, expected_sha256):
        row = entry.to_dict()
        if row['command_id'] in self.by_id:
            original = self.by_id[row['command_id']]
            if original.wire != entry.wire:
                raise ValueError('identity collision')
            return original
        if expected_sequence != len(self.rows) or expected_sha256 != (self.rows[-1].sha256 if self.rows else None):
            raise ValueError('stale compare and swap')
        self.rows.append(entry); self.by_id[row['command_id']] = entry
        if self.lose_reply:
            self.lose_reply = False
            raise TimeoutError()
        return entry

    async def get(self, command_id):
        return self.by_id.get(command_id)


class ProspectiveRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        with deny_network():
            cls.marks = tuple(mark(index, price='100') for index in range(915))
            cls.initial_history = source.derive_sampled_history(seal(cls.marks))
            cls.initial_series = source.derive_close_series(cls.initial_history,
                expected_history_sha256=cls.initial_history.sha256)

    def setUp(self):
        self.guard = deny_network(); self.guard.__enter__()
        self.addCleanup(self.guard.__exit__, None, None, None)
        self.journal = MemoryJournal()
        self.artifacts = {('history', self.initial_history.sha256): self.initial_history,
            ('series', self.initial_series.sha256): self.initial_series}
        self.runtime = self.fresh()
        self.config = V3Config(OWNER, RUN, MARKET,
            SourceBinding(OWNER, RUN, MARKET, PROCESS, PRINCIPAL, PACKAGE), fill_policy())
        self.serial = 0

    def fresh(self):
        return ProspectiveRuntime(OWNER, RUN, self.journal, lambda kind, digest: self.artifacts[(kind, digest)])

    async def commit(self, candidate):
        self.serial += 1
        return await self.runtime.submit(candidate, command_id=str(UUID(int=900_000+self.serial)))

    async def bootstrap(self):
        return await self.commit(self.runtime.prepare_bootstrap(self.config, self.initial_history,
            self.initial_series, inputs=new_inputs((END+5)*1_000_000, 54_905_000_000)))

    async def observe(self, observation, *, history=None, series=None):
        self.artifacts['mark', observation.sha256] = observation
        if history is not None:
            self.artifacts['history', history.sha256] = history
            self.artifacts['series', series.sha256] = series
        generation = self.runtime.state.to_dict()['engine']['generation']+1
        inputs = inputs_for_mark(observation, serial=10+self.serial, generation=generation)
        await self.commit(self.runtime.prepare_protective(observation, inputs=inputs))
        return await self.commit(self.runtime.prepare_decision(observation, inputs=inputs,
            history=history, series=series))

    async def test_unknown_ack_readback_restores_exact_original_without_double_birth(self):
        self.journal.lose_reply = True
        with self.assertRaises(RuntimePending):
            await self.bootstrap()
        self.assertIsNone(self.runtime.state)
        self.assertTrue(self.runtime.pending)
        with self.assertRaises(RuntimePending):
            self.runtime.prepare_control('stop', new_inputs((END+6)*1_000_000, 54_906_000_000))
        state = await self.runtime.reconcile()
        self.assertEqual(len(state.to_dict()['accounts']), 8)
        self.assertEqual(len(self.journal.rows), 1)
        replayed = self.fresh()
        self.assertEqual(replayed.restore(self.journal.rows).to_dict(), state.to_dict())
        self.assertEqual(replayed.history, self.runtime.history)

    async def test_absent_original_readback_keeps_candidate_pending(self):
        async def reject(*args, **kwargs):
            raise TimeoutError()
        self.journal.append = reject
        with self.assertRaises(RuntimePending):
            await self.bootstrap()
        with self.assertRaises(RuntimePending):
            await self.runtime.reconcile()
        self.assertEqual(self.runtime.sequence, 0)
        self.assertTrue(self.runtime.pending)

    async def test_only_exact_immutable_native_rejection_clears_original_candidate(self):
        rejected = []
        async def reject(entry, **kwargs):
            rejected.append(entry)
            raise JournalRejected(entry.wire)
        self.journal.append = reject
        with self.assertRaises(JournalRejected):
            await self.bootstrap()
        self.assertFalse(self.runtime.pending)
        self.assertIsNone(self.runtime.state)
        self.assertEqual(self.runtime.sequence, 0)
        # An unaffiliated or corrupted rejection cannot clear this candidate.
        async def mismatch(entry, **kwargs):
            raise JournalRejected(rejected[0].wire + b'changed')
        self.journal.append = mismatch
        with self.assertRaises(RuntimePending):
            await self.bootstrap()
        self.assertTrue(self.runtime.pending)
        self.assertIsNone(self.runtime.state)

    async def test_lost_rejection_reply_is_resolved_by_original_native_readback(self):
        retained = []
        async def lose_reply(entry, **kwargs):
            retained.append(entry)
            raise TimeoutError()
        async def original_rejection(command_id):
            self.assertEqual(command_id, retained[0].to_dict()['command_id'])
            raise JournalRejected(retained[0].wire)
        self.journal.append, self.journal.get = lose_reply, original_rejection
        with self.assertRaises(RuntimePending):
            await self.bootstrap()
        with self.assertRaises(JournalRejected):
            await self.runtime.reconcile()
        self.assertFalse(self.runtime.pending)
        self.assertEqual(self.runtime.sequence, 0)
        self.assertIsNone(self.runtime.state)

    async def test_two_complete_generations_restart_preserves_capital_positions_and_lineage(self):
        await self.bootstrap()
        history, all_marks = self.initial_history, list(self.marks)
        trajectory = ('100', '80', '120', '100', '120', '80', '120', '100', '120')
        held_before_restart = False
        for bar, price in enumerate(trajectory):
            series = None
            if bar:
                added = tuple(mark(index, price=trajectory[bar-1])
                    for index in range(915+(bar-1)*15, 915+bar*15))
                all_marks.extend(added)
                end = END+bar*900
                history = source.derive_sampled_history(seal(tuple(all_marks[-30:]), start=end-1800,
                    end=end, seal_id=str(UUID(int=100_000+bar))), previous=history,
                    expected_previous_sha256=history.sha256)
                series = source.derive_close_series(history, expected_history_sha256=history.sha256)
            for later in (False, True):
                observation = mark(915+bar*15+int(later), price=price)
                await self.observe(observation, history=history if bar and not later else None,
                    series=series if bar and not later else None)
            if bar == 3:
                before = self.runtime.state.to_dict()
                held_before_restart = bool(before['positions'])
                restored = self.fresh(); restored.restore(self.journal.rows)
                self.assertEqual(restored.state.to_dict(), before)
                self.assertEqual(restored.history, self.runtime.history)
                self.runtime = restored
        self.assertTrue(held_before_restart)
        state = self.runtime.state.to_dict()
        self.assertEqual(state['engine']['generation'], 2)
        self.assertEqual(len(state['accounts']), 8)
        assessments = [item for row in self.runtime.history for item in row['assessments']
            if item['status'] == 'completed']
        self.assertEqual(len(assessments), 16)
        self.assertTrue(all(item['selection_eligible'] for item in assessments))
        births = [item for row in self.runtime.history for item in row['birth_members']]
        self.assertEqual(len(births), 24)
        replayed = self.fresh(); replayed.restore(self.journal.rows)
        self.assertEqual(replayed.state.to_dict(), state)

    async def test_incomplete_prefix_wrong_scope_and_source_refuse_restore(self):
        await self.bootstrap()
        await self.observe(mark(915, price='100'))
        for entries in (self.journal.rows[1:], list(reversed(self.journal.rows))):
            with self.subTest(entries=len(entries)), self.assertRaises(RuntimeRefused):
                self.fresh().restore(entries)
        wrong = ProspectiveRuntime(str(UUID(int=9)), RUN, self.journal,
            lambda kind, digest: self.artifacts[(kind, digest)])
        with self.assertRaises(RuntimeRefused):
            wrong.restore(self.journal.rows)
        broken = ProspectiveRuntime(OWNER, RUN, self.journal, lambda kind, digest: self.initial_series)
        with self.assertRaises(RuntimeRefused):
            broken.restore(self.journal.rows)

    async def test_stale_writer_cannot_advance_local_state(self):
        stale = self.fresh()
        initial = new_inputs((END+5)*1_000_000, 54_905_000_000)
        candidate = stale.prepare_bootstrap(self.config, self.initial_history, self.initial_series, inputs=initial)
        await self.bootstrap()
        with self.assertRaises(RuntimePending):
            await stale.submit(candidate, command_id=str(UUID(int=8_000_000)))
        self.assertIsNone(stale.state)
        self.assertEqual(len(self.journal.rows), 1)

    async def test_prepared_pair_retains_one_genuine_clock_and_replays_both_exactly(self):
        await self.bootstrap()
        observation = mark(915, price='100')
        self.artifacts['mark', observation.sha256] = observation
        inputs = inputs_for_mark(observation, serial=500, generation=1)
        before = self.runtime.state.to_dict()
        protective, decision = self.runtime.prepare_observation(observation, inputs=inputs)
        self.assertEqual(self.runtime.state.to_dict(), before)
        self.assertEqual(protective._witness['inputs'], decision._witness['inputs'])
        await self.commit(protective)
        await self.commit(decision)
        self.assertEqual(len(self.runtime._ledger._accepted), 1)
        self.assertEqual(len(self.runtime.history), 3)
        self.assertGreaterEqual(len(self.runtime._ledger._identities), 8)
        restored = self.fresh(); restored.restore(self.journal.rows)
        self.assertEqual(restored.state.to_dict(), self.runtime.state.to_dict())
        self.assertEqual(len(restored._ledger._accepted), 1)
        self.assertEqual(restored._ledger._identities, self.runtime._ledger._identities)
        self.assertEqual(restored.history, self.runtime.history)


if __name__ == '__main__':
    unittest.main()
