"""Real controller status passes the API allowlist into saved runtime JSON."""

from copy import deepcopy
import importlib
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.security_support import A1, USER_A, OfflineTestMixin, deny_network
from tests.test_repository_security import RecordingDB

with deny_network():
    from vonneumann.core.genesis import GenesisController, LIFECYCLE_POLICY
    from vonneumann.core.strategies import get_strategy
    from vonneumann.core.types import EventType
    from vonneumann.db.repository import PersistenceError
    from vonneumann.market.sim_feed import SimulationFeed
    from vonneumann.server.auth import VerifiedUser
    from vonneumann.server.models import StartRequest
    app_module = importlib.import_module('vonneumann.server.app')


class LifecyclePolicyPersistenceTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.db = RecordingDB()
        self.offline_stack.enter_context(patch('vonneumann.db.repository.get_supabase', return_value=self.db))
        self.broadcast = self.offline_stack.enter_context(patch.object(
            app_module.ws_manager, 'broadcast_to_user', new=AsyncMock()))
        self.offline_stack.enter_context(patch.object(app_module, 'uuid', SimpleNamespace(uuid4=lambda: A1)))

    async def start_controller(self):
        async def create(**kwargs):
            # Keep the API's real repository, persistence callback, event
            # persister and broadcast handler; omit only its background task.
            self.controller = GenesisController(
                SimulationFeed(seed=4), get_strategy(kwargs['strategy_name']),
                kwargs['colony_id'], kwargs['user_id'], mode=kwargs['mode'],
                gen0_count=kwargs['gen0_count'], max_probes=kwargs['max_probes'],
                seed_capital=kwargs['seed_capital'], max_capital=kwargs['max_capital'],
                colony_config=kwargs['colony_config'], search_seed=kwargs['search_seed'],
                on_event=kwargs['on_event'], persist_risk_status=kwargs['persist_status'])
            await self.controller.prepare()
            self.controller.set_lifecycle('running')
        with patch.object(app_module.colony_manager, 'create_colony', new=AsyncMock(side_effect=create)):
            await app_module._start_colony(StartRequest(gen0_count=2, max_probes=2),
                                          VerifiedUser(USER_A, int(time.time()) + 3600))
        return self.controller

    def saved_runtime(self):
        rows = [call for call in self.db.calls
                if call['table'] == 'vn_colonies' and call['operation'] == 'update']
        self.assertTrue(rows, 'The real status callback must save a colony row')
        return rows[-1], rows[-1]['fields']['config']['runtime']

    async def test_controller_simulation_status_saves_the_same_lifecycle_policy_it_broadcasts(self):
        controller = await self.start_controller()
        self.broadcast.reset_mock()
        await controller._publish_evaluation()
        row, runtime = self.saved_runtime()
        self.assertEqual(runtime['lifecycle_policy'], LIFECYCLE_POLICY)
        self.assertEqual(runtime['lifecycle_policy']['terminal_event'], 'probe_dead')
        self.assertEqual(runtime['lifecycle_policy']['generation_completion'],
                         'sealed_births_all_terminal_acknowledged')
        self.assertEqual(set(row['filters']), {('id', A1), ('user_id', USER_A)})
        self.assertTrue(runtime['state_persisted'])
        self.broadcast.assert_awaited_once()
        owner, message = self.broadcast.await_args.args
        self.assertEqual(owner, USER_A)
        self.assertEqual(message['colony_id'], A1)
        self.assertEqual(message['type'], EventType.SIMULATION_STATUS.value)
        self.assertEqual(message['data']['lifecycle_policy'], runtime['lifecycle_policy'])
        self.assertEqual(row['fields']['config']['search_seed'], '0')

    async def test_policy_snapshot_is_detached_and_unknown_status_fields_stay_out_of_saved_config(self):
        controller = await self.start_controller()
        status = controller.status()
        expected = deepcopy(status['lifecycle_policy'])
        status['private_extra'] = 'unapproved runtime data'
        await controller._save_risk_status(status)
        status['lifecycle_policy']['dead_probe_retention'] = -1
        row, runtime = self.saved_runtime()
        self.assertEqual(runtime['lifecycle_policy'], expected)
        self.assertNotIn('private_extra', runtime)
        self.assertNotIn('private_extra', row['fields']['config'])
        self.assertEqual(controller.status()['lifecycle_policy'], expected)

    async def test_failed_policy_write_is_not_broadcast_as_an_acknowledged_status(self):
        controller = await self.start_controller()
        self.broadcast.reset_mock()
        with patch.object(self.db, 'table', side_effect=RuntimeError('offline database failure')):
            with self.assertRaises(PersistenceError):
                await controller._publish_evaluation()
        self.broadcast.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
