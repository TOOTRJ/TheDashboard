"""Inert relay publisher: persist one original event before economic outbox ACK.

The injected acceptance RPC must use the separately reviewed vn_read capability.
No HTTP client, environment, retry, socket, startup wiring or economic write here.
A socket broadcast is an optional downstream wakeup, never acceptance evidence.
"""
from __future__ import annotations
from typing import Protocol
from .command_protocol import canonical_uuid, bounded_integer, canonical_json
from .transition_coordinator import PublicationError


class RelayTransport(Protocol):
    async def accept_event(self, arguments: dict) -> dict: ...


class DurableRelayPublisher:
    def __init__(self, transport: RelayTransport, owner_id: str, run_id: str):
        self._owner = canonical_uuid(owner_id, 'owner_id')
        self._run = canonical_uuid(run_id, 'run_id')
        self._transport = transport

    async def __call__(self, event: dict) -> None:
        try:
            if type(event) is not dict or event.keys() != {
                'owner_id','run_id','command_id','revision','event_index','event_id','event'}:
                raise ValueError()
            if event['owner_id'] != self._owner or event['run_id'] != self._run:
                raise ValueError()
            command = canonical_uuid(event['command_id'], 'command_id')
            index = bounded_integer(event['event_index'], 'event_index', minimum=0, maximum=1024)
            revision = bounded_integer(event['revision'], 'revision')
            identity = f'{self._run}:{command}:{index}'
            if event['event_id'] != identity or type(event['event']) is not dict or len(canonical_json(event)) > 65536:
                raise ValueError()
        except Exception:
            raise PublicationError('invalid relay identity') from None
        # Only identity is sent. SQL reads the event from the committed outbox;
        # callers cannot substitute a payload or manufacture an acceptance.
        receipt = await self._transport.accept_event({
            'owner_id': self._owner, 'run': self._run, 'command_id': command, 'event_index': index})
        try:
            if type(receipt) is not dict or receipt.keys() != {
                'version','owner_id','run_id','command_id','revision','event_index','event_id','sequence','accepted'}:
                raise ValueError()
            if type(receipt['version']) is not int or receipt['version'] != 1 or receipt['accepted'] is not True:
                raise ValueError()
            expected = {'owner_id':self._owner,'run_id':self._run,'command_id':command,
                        'revision':revision,'event_index':index,'event_id':identity}
            if any(type(receipt[k]) is not type(v) or receipt[k] != v for k,v in expected.items()):
                raise ValueError()
            bounded_integer(receipt['sequence'], 'sequence')
        except Exception:
            raise PublicationError('invalid durable relay receipt') from None
