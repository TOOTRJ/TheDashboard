"""Identity-only relay acceptance, no network/database/application startup."""
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock
from tests.test_exact_rehearsal import OWNER, RUN
from tests.postgres.test_command_adapter import identity
from vonneumann.db.relay_acceptance import DurableRelayPublisher
from vonneumann.db.transition_coordinator import PublicationError


class RelayAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.command = identity()
        self.event = {'owner_id':OWNER,'run_id':RUN,'command_id':self.command,'revision':2,'event_index':0,
                      'event_id':f'{RUN}:{self.command}:0','event':{'kind':'birth'}}
        self.receipt = {k:v for k,v in self.event.items() if k != 'event'}
        self.receipt.update(version=1,sequence=1,accepted=True)
        self.transport = AsyncMock()
        self.transport.accept_event.return_value = self.receipt
        self.publisher = DurableRelayPublisher(self.transport, OWNER, RUN)

    async def test_identity_only_request_and_repeated_original_receipt(self):
        await self.publisher(self.event)
        await self.publisher(self.event)
        self.assertEqual(self.transport.accept_event.call_count, 2)
        self.transport.accept_event.assert_awaited_with({'owner_id':OWNER,'run':RUN,
                                                       'command_id':self.command,'event_index':0})

    async def test_foreign_or_malformed_identity_never_reaches_transport(self):
        for changes in ({'owner_id':identity()},{'run_id':identity()},{'event_id':'new'},
                        {'event_index':True},{'revision':False},{'event':[]},{'extra':1}):
            with self.subTest(changes=changes), self.assertRaises(PublicationError):
                await self.publisher({**self.event,**changes})
        self.transport.accept_event.assert_not_awaited()

    async def test_unverified_receipt_never_allows_ack(self):
        for changes in ({'accepted':False},{'version':True},{'revision':3},{'event_index':False},
                        {'owner_id':identity()},{'sequence':0},{'extra':1}):
            self.transport.accept_event.return_value = {**self.receipt,**changes}
            with self.subTest(changes=changes), self.assertRaises(PublicationError):
                await self.publisher(self.event)

    async def test_lost_reply_propagates_without_new_identity_or_retry(self):
        before = deepcopy(self.event)
        self.transport.accept_event.side_effect = TimeoutError('fixture lost reply')
        with self.assertRaises(TimeoutError): await self.publisher(self.event)
        self.transport.accept_event.assert_awaited_once()
        self.assertEqual(self.event, before)
