"""Portable-model stable candle/indicator partition; offline evidence only.

Fork of partitioned_checkpoint.py at PR96 with factory-owned immutable resolution
memoization. Original partitions, wire/policy meanings and full validators stay
unchanged; this optimization changes the Python implementation bytes.

The original eleven-slot provider format is unchanged. This thirteen-slot
format delegates complete model checks to its validator after a bounded,
lossless expansion. It creates no runtime state, receipt or database authority.
"""
from dataclasses import dataclass
import hashlib
import json
import re
from weakref import WeakKeyDictionary

from . import provider_portable_checkpoint as legacy
from . import provider_portable_ga_model as kernel
from . import numeric_wire as numbers
from ..db.command_protocol import (
    CommandValidationError, MAX_BIGINT, _keys, bounded_integer, canonical_json,
    canonical_uuid,
)
from .checkpoint_reference import jsonb_text_bytes

FORMAT = 'ga-portable-provider-checkpoint-research-v2'
COMPONENT_FORMAT = 'ga-portable-provider-component-research-v2'
TRANSPORT_FORMAT = 'ga-portable-provider-compact-command-research-v2'
HASH_POLICY = legacy.HASH_POLICY
MAX_MANIFEST_BYTES = legacy.MAX_MANIFEST_BYTES
MAX_COMPONENT_BYTES = legacy.MAX_COMPONENT_BYTES
MAX_RESOLVED_BYTES = legacy.MAX_RESOLVED_BYTES
MAX_COMPONENTS = 13
STOP_RESERVE_BYTES = legacy.STOP_RESERVE_BYTES
ORDINARY_COMMAND_BYTES = legacy.ORDINARY_COMMAND_BYTES
_STABLE = {'source_bars', 'ema'}
_ENGINE_FIELDS = legacy._ENGINE_MUTABLE - {'ema'}
_require, _bounded, _safe = legacy._require, legacy._bounded, legacy._safe


def _slot(kind, entity, generation):
    if type(kind) is str and kind in _STABLE:
        _require(entity == kind and type(generation) is int and generation == 0,
                 'Stable evidence requires its fixed slot and generation zero')
    else:
        legacy._slot(kind, entity, generation)


@dataclass(frozen=True, slots=True)
class TypedComponent:
    _wire: bytes

    def __post_init__(self):
        self._checked_value()

    def _checked_value(self):
        _require(type(self._wire) is bytes and len(self._wire) <= MAX_COMPONENT_BYTES,
                 'Component wire exceeds capacity')
        value = numbers.decode(self._wire, maximum=MAX_COMPONENT_BYTES)
        _bounded(value)
        _keys(value, {'format', 'hash_policy', 'owner_id', 'run_id', 'kind',
                      'entity_id', 'generation', 'body'})
        _require(value['format'] == COMPONENT_FORMAT and value['hash_policy'] == HASH_POLICY,
                 'Unknown partitioned component format/hash policy')
        legacy._scope(value['owner_id'], value['run_id'])
        _slot(value['kind'], value['entity_id'], value['generation'])
        _require(type(value['body']) is dict, 'Component body must be an object')
        _require(numbers.encode(value, maximum=MAX_COMPONENT_BYTES) == self._wire
                 and jsonb_text_bytes(value) <= MAX_COMPONENT_BYTES,
                 'Component encoding is noncanonical or exceeds capacity')
        return value

    @classmethod
    def make(cls, owner, run, kind, entity, generation, body):
        legacy._scope(owner, run); _slot(kind, entity, generation)
        value = {'format': COMPONENT_FORMAT, 'hash_policy': HASH_POLICY,
                 'owner_id': owner, 'run_id': run, 'kind': kind,
                 'entity_id': entity, 'generation': generation, 'body': body}
        return cls(numbers.encode(_bounded(value), maximum=MAX_COMPONENT_BYTES))

    @property
    def identity(self):
        return hashlib.sha256(self._wire).hexdigest()

    def to_dict(self):
        return self._checked_value()

    def reference(self):
        value = self.to_dict()
        return {key: value[key] for key in ('kind', 'entity_id', 'generation')} | {
            'sha256': self.identity}


@_safe
def resolve_manifest(manifest, components, *, owner_id, run_id, revision):
    """Audit all thirteen blocks before bounded expansion and legacy validation."""
    legacy._scope(owner_id, run_id)
    bounded_integer(revision, minimum=2, maximum=MAX_BIGINT)
    _bounded(manifest)
    _keys(manifest, {'format', 'source_model_version', 'owner_id', 'run_id',
                     'revision', 'status', 'reserve', 'accounts', 'positions',
                     'engine', 'source', 'components'})
    _require(manifest['format'] == FORMAT and manifest['source_model_version'] == kernel.MODEL_FORMAT
             and manifest['owner_id'] == owner_id and manifest['run_id'] == run_id
             and type(manifest['revision']) is int and manifest['revision'] == revision,
             'Partitioned manifest binding differs')
    aggregate = len(numbers.encode(manifest, maximum=MAX_MANIFEST_BYTES))
    _require(jsonb_text_bytes(manifest) <= MAX_MANIFEST_BYTES, 'Manifest exceeds capacity')
    refs = manifest['components']
    _require(type(refs) is list and len(refs) == MAX_COMPONENTS and
             type(components) is tuple and len(components) == MAX_COMPONENTS,
             'Complete thirteen-slot component set required')
    blocks = {}
    for block in components:
        _require(type(block) is TypedComponent, 'Partitioned immutable components required')
        value = block._checked_value()
        aggregate += len(block._wire)
        _require(aggregate <= MAX_RESOLVED_BYTES, 'Complete dependency aggregate exceeds capacity')
        _require(value['owner_id'] == owner_id and value['run_id'] == run_id,
                 'Component owner/run differs')
        _require(block.identity not in blocks, 'Repeated component identity')
        blocks[block.identity] = value
    slots, seen = {}, set()
    for ref in refs:
        _keys(ref, {'kind', 'entity_id', 'generation', 'sha256'})
        _slot(ref['kind'], ref['entity_id'], ref['generation'])
        digest = ref['sha256']
        _require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) is not None
                 and digest in blocks and digest not in seen, 'Missing/duplicate component reference')
        seen.add(digest)
        block = blocks[digest]
        _require(all(type(block[k]) is type(ref[k]) and block[k] == ref[k]
                     for k in ('kind', 'entity_id', 'generation')), 'Typed reference differs')
        slot = (ref['kind'], ref['entity_id'])
        _require(slot not in slots, 'Repeated component slot')
        slots[slot] = block
    _require(all((kind, kind) in slots for kind in _STABLE), 'Stable slots are missing')
    _keys(manifest['engine'], _ENGINE_FIELDS | {'members'})
    _require(type(manifest['source']) is dict and 'bars' not in manifest['source'],
             'Source bars must use the explicit stable slot')
    bars = slots['source_bars', 'source_bars']['body']
    _keys(bars, {'bars'})
    expanded = json.loads(canonical_json(manifest))
    expanded['format'] = legacy.FORMAT
    expanded['source']['bars'] = bars['bars']
    expanded['engine']['ema'] = slots['ema', 'ema']['body']
    original_blocks = tuple(legacy.TypedComponent.make(owner_id, run_id, ref['kind'],
        ref['entity_id'], ref['generation'], blocks[ref['sha256']]['body'])
        for ref in refs if ref['kind'] not in _STABLE)
    expanded['components'] = [block.reference() for block in original_blocks]
    # The original validator additionally charges the fully expanded manifest,
    # dependencies and resolved model and checks source/EMA equality and mirrors.
    resolved = legacy.resolve_manifest(expanded, original_blocks,
        owner_id=owner_id, run_id=run_id, revision=revision)
    resolved['format'] = FORMAT
    return resolved


@dataclass(frozen=True, slots=True)
class _OwnedResolution:
    """Factory validation evidence; no capture back-reference or mutable view."""
    manifest_wire: bytes
    expected_wire: bytes
    components: tuple
    component_wires: tuple

    def unchanged(self, capture):
        return (type(capture) is ActiveCheckpoint
            and capture._ActiveCheckpoint__wire is self.manifest_wire
            and capture._ActiveCheckpoint__expected is self.expected_wire
            and capture._ActiveCheckpoint__components is self.components
            and type(self.components) is tuple and type(self.component_wires) is tuple
            and len(self.components) == len(self.component_wires) == MAX_COMPONENTS
            and all(type(block) is TypedComponent and block._wire is wire
                for block, wire in zip(self.components, self.component_wires)))


# This is private factory ownership, never source/server/receipt authority.
# Unregistered or changed captures continue through the full validator below.
_OWNED_RESOLUTIONS = WeakKeyDictionary()


class ActiveCheckpoint:
    __slots__ = ('__wire', '__components', '__expected', '__weakref__')

    def __init__(self, *args, **kwargs):
        raise CommandValidationError('Capture an owned candidate first')

    def __setattr__(self, name, value):
        raise AttributeError('ActiveCheckpoint is immutable')

    def to_dict(self):
        return numbers.decode(self.__wire, maximum=MAX_MANIFEST_BYTES)

    @property
    def components(self):
        return self.__components

    @property
    def manifest_bytes(self):
        return len(self.__wire)

    @property
    def resolved_bytes(self):
        return jsonb_text_bytes(json.loads(self.__expected))

    def resolve(self):
        proof = _OWNED_RESOLUTIONS.get(self) if type(self) is ActiveCheckpoint else None
        if type(proof) is _OwnedResolution and proof.unchanged(self):
            return json.loads(proof.expected_wire)
        value = self.to_dict()
        result = resolve_manifest(value, self.components, owner_id=value['owner_id'],
            run_id=value['run_id'], revision=value['revision'])
        _require(canonical_json(result) == self.__expected, 'Capture differs from its owned evidence')
        return result


def capture_owned_candidate(candidate, *, legacy_capture=None):
    """Partition complete owned evidence without removing any continuation data."""
    _require(type(candidate) is kernel.GACandidate, 'Owned provider candidate required')
    candidate.__post_init__()
    old = legacy.capture_owned_candidate(candidate) if legacy_capture is None else legacy_capture
    _require(type(old) is legacy.ActiveCheckpoint, 'Owned original capture required')
    expected = candidate.state.to_dict()
    expected.pop('version')
    expected.update(format=legacy.FORMAT, source_model_version=kernel.MODEL_FORMAT)
    _require(old.resolve() == expected, 'Original capture differs from the candidate')
    expected['format'] = FORMAT
    manifest = old.to_dict()
    owner, run = manifest['owner_id'], manifest['run_id']
    components = [TypedComponent.make(owner, run, b['kind'], b['entity_id'], b['generation'], b['body'])
                  for b in (block.to_dict() for block in old.components)]
    components.extend((TypedComponent.make(owner, run, 'source_bars', 'source_bars', 0,
                       {'bars': manifest['source'].pop('bars')}),
                       TypedComponent.make(owner, run, 'ema', 'ema', 0, manifest['engine'].pop('ema'))))
    manifest.update(format=FORMAT, components=[block.reference() for block in components])
    _require(resolve_manifest(manifest, tuple(components), owner_id=owner, run_id=run,
             revision=manifest['revision']) == expected, 'Partition loses original evidence')
    result = object.__new__(ActiveCheckpoint)
    object.__setattr__(result, '_ActiveCheckpoint__wire', numbers.encode(manifest, maximum=MAX_MANIFEST_BYTES))
    object.__setattr__(result, '_ActiveCheckpoint__components', tuple(components))
    object.__setattr__(result, '_ActiveCheckpoint__expected', canonical_json(expected))
    _OWNED_RESOLUTIONS[result] = _OwnedResolution(result._ActiveCheckpoint__wire,
        result._ActiveCheckpoint__expected, result.components, tuple(block._wire for block in result.components))
    return result


def component_updates(previous, following):
    _require(type(previous) is ActiveCheckpoint and type(following) is ActiveCheckpoint,
             'Owned partitioned captures required')
    old, new = previous.resolve(), following.resolve()
    _require(old['owner_id'] == new['owner_id'] and old['run_id'] == new['run_id']
             and old['revision'] < new['revision'], 'Component comparison scope/revision differs')
    retained = {block.identity for block in previous.components}
    return tuple(block for block in following.components if block.identity not in retained)


def prepare_transport(candidate, following, *, command_id, previous=None):
    """Original compact request including all immutable history; no ACK semantics."""
    canonical_uuid(command_id)
    _require(type(candidate) is kernel.GACandidate and type(following) is ActiveCheckpoint,
             'Owned partitioned candidate/capture required')
    candidate.__post_init__()
    resolved = following.resolve()
    resolved.pop('format'); resolved.pop('source_model_version'); resolved['version'] = kernel.MODEL_FORMAT
    _require(resolved == candidate.state.to_dict(), 'Capture differs from candidate')
    before = candidate.transition['before']
    if previous is None:
        _require(before is None, 'Missing prior owned checkpoint')
        changes, prior = following.components, None
    else:
        _require(type(previous) is ActiveCheckpoint, 'Prior partitioned checkpoint required')
        old = previous.resolve()
        old.pop('format'); old.pop('source_model_version'); old['version'] = kernel.MODEL_FORMAT
        _require(old == before, 'Prior checkpoint evidence differs')
        retained = {block.identity for block in previous.components}
        changes = tuple(block for block in following.components if block.identity not in retained)
        prior = {'revision': before['revision'], 'sha256': hashlib.sha256(numbers.encode(previous.to_dict())).hexdigest()}
    body = {'format': TRANSPORT_FORMAT, 'command_id': command_id,
        'owner_id': resolved['owner_id'], 'run_id': resolved['run_id'], 'prior': prior,
        'checkpoint': following.to_dict(), 'components': [block.to_dict() for block in changes],
        'operations': candidate.operations, 'history': candidate.history,
        'evidence': candidate.transition['evidence'], 'events': candidate.transition['events']}
    control = body['evidence']['control']
    maximum = MAX_RESOLVED_BYTES if control is not None and control['action'] == 'stop' else ORDINARY_COMMAND_BYTES
    wire = numbers.encode(body, maximum=maximum)
    expanded = len(json.dumps(numbers.decode(wire), sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(', ', ': ')).encode('utf-8'))
    _require(jsonb_text_bytes(json.loads(wire)) <= maximum and expanded <= maximum,
             'Complete expanded command exceeds capacity')
    return wire
