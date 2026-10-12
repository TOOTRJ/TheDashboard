"""Unscored post-abort terminals remain capturable; scored evidence stays frozen."""
from copy import deepcopy
import unittest

from tests.security_support import OfflineTestMixin
from tests.postgres.test_economic_transition import extra_sequence
from tests.test_provider_contract import OWNER,RUN
from vonneumann.db.command_protocol import CommandValidationError
from vonneumann.research import partitioned_checkpoint as cp


class ProviderTerminalCaptureTests(OfflineTestMixin,unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.risk=extra_sequence(death=True,risk_bps='1000')
        cls.terminal=extra_sequence(death=True)

    def test_risk_abort_precedes_terminal_without_inventing_a_scored_snapshot(self):
        candidate,capture,_=self.risk[-2]
        state=candidate.state.to_dict()
        self.assertTrue(state['engine']['lifecycle']['risk']['active'])
        self.assertEqual(state['engine']['cohort']['phase'],'aborted')
        self.assertTrue(all(m['terminal'] and m['assessment'] is None for m in state['engine']['members']))
        self.assertTrue(all(a['fitness_float64'] is None for a in candidate.history['assessments']))
        self.assertEqual(capture.resolve()['engine']['members'],state['engine']['members'])
        self.assertEqual(self.risk[-1][1].resolve()['status'],'stopped')

    def test_pre_abort_scored_terminal_snapshot_cannot_be_deleted(self):
        candidate,capture,_=self.terminal[-2]
        self.assertTrue(all(m['assessment'] for m in candidate.state.to_dict()['engine']['members']))
        manifest=capture.to_dict()
        manifest['engine']['members'][0]['assessment']=None
        with self.assertRaises(CommandValidationError):
            cp.resolve_manifest(manifest,capture.components,owner_id=OWNER,run_id=RUN,revision=manifest['revision'])

    def test_post_abort_terminal_cannot_invent_a_scored_snapshot(self):
        capture=self.risk[-2][1]; manifest=capture.to_dict()
        manifest['engine']['members'][0]['assessment']=deepcopy(
            self.terminal[-2][1].to_dict()['engine']['members'][0]['assessment'])
        with self.assertRaises(CommandValidationError):
            cp.resolve_manifest(manifest,capture.components,owner_id=OWNER,run_id=RUN,revision=manifest['revision'])

    def test_later_stop_preserves_the_original_pre_abort_frozen_snapshot(self):
        earlier=self.terminal[-2][1].resolve()['engine']['members']
        stopped=self.terminal[-1][1].resolve()['engine']['members']
        self.assertEqual([m['assessment'] for m in earlier],[m['assessment'] for m in stopped])
        self.assertTrue(all(a['early_terminal_frozen'] and a['fitness_float64'] is None
            for a in self.terminal[-1][0].history['assessments']))
