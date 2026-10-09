"""Offline checkpoint-reference transport experiment, never a runtime command.

The server hash is an opaque PostgreSQL-17 JSONB fingerprint, not this client's
JSON encoding. Only the locked SQL fixture can verify it. Expansion deliberately
keeps the existing v5/model byte limits: a smaller wire is not permission to
validate an unbounded graph, restore a solver, or discard ledger history.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re

from ..core import exact_rehearsal as base
from ..db.command_protocol import (
    CommandValidationError, MAX_BIGINT, canonical_json, canonical_uuid, _keys,
)
from ..db.provider_protocol import validate_transition

TRANSPORT = 'checkpoint-reference-research-v1'
HASH_POLICY = 'postgres17-jsonb-sha256-v1'
MAX_WIRE_BYTES = 262144
MAX_EXPANDED_BYTES = 262144


def jsonb_text_bytes(value):
    """Measure the supported exact JSON subset with the existing spacing rule.

    This is a byte-admission estimate, never the server hash representation.
    Actual PostgreSQL octet_length is independently tested in the SQL fixture.
    """
    copied = json.loads(canonical_json(value))
    return len(json.dumps(copied, ensure_ascii=False, sort_keys=True,
        separators=(', ', ': '), allow_nan=False).encode('utf-8'))


def _require(condition, message):
    if not condition:
        raise CommandValidationError(message)


@dataclass(frozen=True, slots=True)
class CheckpointReference:
    owner_id: str
    run_id: str
    revision: int
    sha256: str

    def __post_init__(self):
        canonical_uuid(self.owner_id); canonical_uuid(self.run_id)
        _require(type(self.revision) is int and 1 <= self.revision < MAX_BIGINT,
                 'Invalid checkpoint revision')
        _require(type(self.sha256) is str and re.fullmatch('[0-9a-f]{64}', self.sha256) is not None,
                 'Invalid opaque server checkpoint hash')

    def to_dict(self):
        self.__post_init__()
        return {'version': 1, 'owner_id': self.owner_id, 'run_id': self.run_id,
                'revision': self.revision, 'hash_policy': HASH_POLICY, 'sha256': self.sha256}

    @classmethod
    def from_dict(cls, value):
        _keys(value, {'version', 'owner_id', 'run_id', 'revision', 'hash_policy', 'sha256'})
        _require(type(value['version']) is int and value['version'] == 1
                 and value['hash_policy'] == HASH_POLICY, 'Unsupported checkpoint reference')
        return cls(value['owner_id'], value['run_id'], value['revision'], value['sha256'])


def expand_for_validation(payload, reference, checkpoint):
    """Pure local structural/model verification; does NOT verify the server hash.

    The SQL fixture resolves the current checkpoint under the run lock and
    independently compares the full reference before using this shape. This
    local helper has no decoder, installer, transport or retry authority.
    """
    _require(type(reference) is CheckpointReference, 'Checkpoint reference required')
    descriptor = reference.to_dict()
    _require(jsonb_text_bytes(payload) <= MAX_WIRE_BYTES, 'Reference wire exceeds capacity')
    payload = json.loads(canonical_json(payload))
    _keys(payload, {'transport', 'model_version', 'before_reference', 'operations', 'transition'})
    _require(payload['transport'] == TRANSPORT and type(payload['model_version']) is int
             and payload['model_version'] == 5, 'Unsupported research transport')
    _require(canonical_json(payload['before_reference']) == canonical_json(descriptor),
             'Checkpoint reference binding differs')
    transition = payload['transition']
    _keys(transition, {'version', 'after', 'evidence', 'events'})
    if checkpoint is None:
        _require(reference.revision == 1, 'Only fresh creation has no checkpoint')
    else:
        _require(type(checkpoint) is dict and checkpoint.get('owner_id') == reference.owner_id
                 and checkpoint.get('run_id') == reference.run_id
                 and type(checkpoint.get('revision')) is int
                 and checkpoint['revision'] == reference.revision,
                 'Checkpoint owner/run/revision differs')
    transition['before'] = json.loads(canonical_json(checkpoint))
    expanded = {'version': 5, 'operations': payload['operations'], 'transition': transition}
    _require(jsonb_text_bytes(expanded) <= MAX_EXPANDED_BYTES, 'Expanded model exceeds capacity')
    validate_transition(transition, expanded['operations'], reference.owner_id,
                        reference.run_id, reference.revision)
    return expanded


class ReferencedTransition:
    """Detached immutable research wire. It cannot enter PreparedCommand v5."""
    __slots__ = ('__wire', '__expanded_bytes')

    def __init__(self, *args, **kwargs):
        raise CommandValidationError('Use encode_owned_candidate for research capture')

    def __setattr__(self, name, value):
        raise AttributeError('ReferencedTransition is immutable')

    @property
    def wire(self):
        return self.__wire

    @property
    def payload_bytes(self):
        return jsonb_text_bytes(self.to_dict())

    @property
    def expanded_bytes(self):
        return self.__expanded_bytes

    def to_dict(self):
        return json.loads(self.__wire)


def encode_owned_candidate(candidate, reference):
    _require(type(candidate) is base.ExactCandidate, 'Owned exact candidate required')
    # Revalidate the pair, including the unchanged inner candidate byte limit.
    base.ExactCandidate(candidate.state, candidate._wire, candidate.payload_bytes)
    original = json.loads(candidate._wire)
    _keys(original, {'version', 'operations', 'transition'})
    _keys(original['transition'], {'version', 'before', 'after', 'evidence', 'events'})
    _require(type(original['version']) is int and original['version'] == 5,
             'Only existing provider v5 evidence is measured')
    before = original['transition'].pop('before')
    _require(type(reference) is CheckpointReference, 'Checkpoint reference required')
    payload = {'transport': TRANSPORT, 'model_version': 5,
               'before_reference': reference.to_dict(), 'operations': original['operations'],
               'transition': original['transition']}
    expanded = expand_for_validation(payload, reference, before)
    _require(canonical_json(expanded) == candidate._wire,
             'Reference expansion changed original evidence')
    value = object.__new__(ReferencedTransition)
    object.__setattr__(value, '_ReferencedTransition__wire', canonical_json(payload))
    object.__setattr__(value, '_ReferencedTransition__expanded_bytes', jsonb_text_bytes(expanded))
    return value
