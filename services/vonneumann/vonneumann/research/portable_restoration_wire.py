"""Bounded original-v2 readback decoding; no authentication, I/O or authority.

Expected bindings come from the caller's independently authenticated scoped
reader/operator package check. A digest or boolean in JSON cannot establish it.
Outer PostgreSQL JSON ordering/spacing is immaterial; inner wires remain exact.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from uuid import UUID

MAX_ENVELOPE_BYTES = 589824
MAX_MANIFEST_BYTES = 65536
MAX_COMPONENT_BYTES = 196608
MAX_AGGREGATE_BYTES = 262144
MAX_DEPTH = 64
MAX_NODES = 20000
FORMAT = 'ga-portable-native-checkpoint-readback-lab-v1'
RECEIPT_FORMAT = 'ga-portable-native-receipt-lab-v1'
MODEL_FORMAT = 'ga-portable-provider-model-research-v2'
ASSESSMENT_FORMAT = 'ga-portable-provider-assessment-research-v2'
CHECKPOINT_FORMAT = 'ga-portable-provider-checkpoint-research-v2'
COMPONENT_FORMAT = 'ga-portable-provider-component-research-v2'
HASH_POLICY = 'tagged-numeric-json-utf8-sha256-research-v1'
STATUSES = frozenset({'created', 'running', 'paused', 'risk_halted', 'stopped', 'failed'})
_HASH = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_DECIMAL = re.compile(r'0|[1-9][0-9]{0,18}\Z', re.ASCII)


class RestorationError(ValueError):
    """Readback or continuation differs from the reviewed restoration contract."""


def require(value, message='Portable restoration binding differs'):
    if not value:
        raise RestorationError(message)


def fields(value, expected):
    require(type(value) is dict and value.keys() == set(expected), 'Unexpected restoration fields')


def uuid(value):
    require(type(value) is str and len(value) == 36, 'Canonical restoration UUID required')
    try:
        require(str(UUID(value)) == value, 'Canonical restoration UUID required')
    except ValueError:
        raise RestorationError('Canonical restoration UUID required') from None
    return value


def digest(value):
    require(type(value) is str and _HASH.fullmatch(value) is not None, 'Canonical restoration digest required')
    return value


def revision(value):
    require(type(value) is str and _DECIMAL.fullmatch(value) is not None, 'Decimal revision string required')
    result = int(value)
    require(1 <= result <= 2**63 - 1, 'Restoration revision exceeds counter policy')
    return result


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _preflight(text):
    # Bound container/key allocation before json.loads builds attacker structure.
    depth = nodes = 0
    quoted = escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                quoted = False
            continue
        if character == '"':
            quoted = True
            nodes += 1
        elif character in '{[':
            depth += 1
            nodes += 1
        elif character in '}]':
            depth -= 1
        elif character in ',:':
            nodes += 1
        require(0 <= depth <= MAX_DEPTH and nodes <= MAX_NODES * 3,
                'Restoration JSON exceeds structural capacity')
    require(not quoted and depth == 0, 'Truncated restoration JSON')


def parse_json(wire, *, maximum=MAX_ENVELOPE_BYTES, exact=False):
    require(type(wire) is bytes and 0 < len(wire) <= maximum, 'Restoration wire exceeds byte capacity')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate restoration key')
            result[key] = value
        return result
    def number(_):
        raise RestorationError('Untagged restoration JSON number')
    try:
        text = wire.decode('utf-8', errors='strict')
        _preflight(text)
        value = json.loads(text, object_pairs_hook=pairs, parse_int=number,
                           parse_float=number, parse_constant=number)
        if exact:
            require(canonical(value) == wire, 'Noncanonical original restoration wire')
        return value
    except (UnicodeError, RecursionError, OverflowError, TypeError, ValueError):
        raise RestorationError('Invalid bounded restoration JSON') from None


def decode_numeric(wire, *, maximum):
    """Independent tagged primitive decoder; no classes or serialization hooks."""
    value = parse_json(wire, maximum=maximum, exact=True)
    visits = 0
    def visit(item, depth=0):
        nonlocal visits
        visits += 1
        require(visits <= MAX_NODES and depth <= MAX_DEPTH, 'Numeric restoration traversal exceeds capacity')
        kind = type(item)
        if item is None or kind is bool:
            return item
        if kind is str:
            require('\x00' not in item and len(item.encode('utf-8')) <= 16384,
                    'Numeric restoration string exceeds capacity')
            return item
        require(kind in (dict, list) and len(item) <= 4096, 'Unknown numeric restoration value')
        if kind is list:
            return [visit(child, depth + 1) for child in item]
        tags = {'$integer', '$float64'}.intersection(item)
        if tags:
            require(len(item) == 1, 'Reserved numeric restoration tag collision')
            key, text = next(iter(item.items()))
            require(type(text) is str and len(text) <= 100, 'Invalid numeric restoration tag')
            if key == '$integer':
                require(re.fullmatch(r'0|-?[1-9][0-9]*', text, re.ASCII) is not None, 'Noncanonical restoration integer')
                result = int(text)
                require(result.bit_length() <= 256, 'Restoration integer exceeds capacity')
                return result
            try:
                result = float.fromhex(text)
            except (ValueError, OverflowError):
                raise RestorationError('Invalid restoration binary64') from None
            require(math.isfinite(result) and result.hex() == text, 'Noncanonical restoration binary64')
            return result
        return {visit(key, depth + 1): visit(child, depth + 1) for key, child in item.items()}
    return visit(value)


@dataclass(frozen=True, slots=True)
class ExpectedHead:
    """Operator/independent-reader inputs, never recovered from response claims.

    This value carries no credential or proof of native authentication itself.
    Pure fixture construction does not establish a server-accepted semantic head.
    """
    owner_id: str
    run_id: str
    revision: int
    manifest_sha256: str
    command_id: str
    command_sha256: str
    semantic_validator_sha256: str
    native_package_sha256: str
    allow_historical: bool = False

    def __post_init__(self):
        uuid(self.owner_id); uuid(self.run_id); uuid(self.command_id)
        require(type(self.revision) is int and 2 <= self.revision <= 2**63 - 1)
        for value in (self.manifest_sha256, self.command_sha256,
                      self.semantic_validator_sha256, self.native_package_sha256):
            digest(value)
        require(type(self.allow_historical) is bool)


@dataclass(frozen=True, slots=True, init=False)
class DecodedCheckpoint:
    expected: ExpectedHead
    manifest_wire: bytes
    component_wires: tuple[bytes, ...]
    current_revision: int
    current_status: str
    guard_observed_at: str

    def __init__(self, *args, **kwargs):
        raise RestorationError('Use the bounded independently bound readback decoder')

    @property
    def is_current(self):
        return self.current_revision == self.expected.revision

    @property
    def restoration_authority(self):
        return False

    @property
    def pending_command_authority(self):
        return False

    @property
    def hosted_authority(self):
        return False


_RECEIPT_FIELDS = {'format', 'owner_id', 'run_id', 'command_id', 'command_sha256', 'revision',
    'manifest_sha256', 'model_format', 'assessment_format', 'semantic_validator_sha256',
    'native_package_sha256', 'record_observed', 'pending_until_commit', 'guard_observed_at',
    'final_visible_instant_freshness', 'restoration_authority', 'hosted_authority'}


def validate_receipt(receipt, expected):
    fields(receipt, _RECEIPT_FIELDS)
    require(receipt['format'] == RECEIPT_FORMAT and receipt['model_format'] == MODEL_FORMAT
            and receipt['assessment_format'] == ASSESSMENT_FORMAT, 'Unsupported restoration receipt/model')
    for key in ('owner_id', 'run_id', 'command_id', 'manifest_sha256', 'command_sha256',
                'semantic_validator_sha256', 'native_package_sha256'):
        require(type(receipt[key]) is str and receipt[key] == getattr(expected, key))
    require(revision(receipt['revision']) == expected.revision)
    require(receipt['record_observed'] is True and receipt['pending_until_commit'] is False,
            'A pending/claimed receipt is not an observed committed record')
    for key in ('final_visible_instant_freshness', 'restoration_authority', 'hosted_authority'):
        require(receipt[key] is False, 'Receipt cannot claim loading/activation authority')
    timestamp = receipt['guard_observed_at']
    require(type(timestamp) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00', timestamp, re.ASCII) is not None,
            'Observed receipt requires normalized UTC guard time')
    try:
        parsed = datetime.fromisoformat(timestamp)
        require(parsed.tzinfo == timezone.utc and parsed.isoformat(timespec='microseconds') == timestamp)
    except ValueError:
        raise RestorationError('Invalid observed guard time') from None
    return timestamp


def decode_readback(wire, expected):
    require(type(expected) is ExpectedHead, 'Independent expected restoration head required')
    expected.__post_init__()
    envelope = parse_json(wire)
    fields(envelope, {'format', 'manifest_wire', 'component_wires', 'receipt', 'current_revision',
        'current_status', 'pending_command_authority', 'restoration_authority', 'hosted_authority'})
    require(envelope['format'] == FORMAT, 'Unsupported readback envelope')
    for key in ('pending_command_authority', 'restoration_authority', 'hosted_authority'):
        require(envelope[key] is False, 'Readback cannot grant authority')
    require(type(envelope['manifest_wire']) is str and type(envelope['component_wires']) is list
            and len(envelope['component_wires']) == 13, 'Complete original readback wires required')
    try:
        manifest_wire = envelope['manifest_wire'].encode('utf-8')
        component_wires = tuple(value.encode('utf-8') for value in envelope['component_wires'] if type(value) is str)
    except UnicodeError:
        raise RestorationError('Invalid readback wire Unicode') from None
    require(len(component_wires) == 13 and len(manifest_wire) <= MAX_MANIFEST_BYTES
            and all(len(value) <= MAX_COMPONENT_BYTES for value in component_wires)
            and len(manifest_wire) + sum(map(len, component_wires)) <= MAX_AGGREGATE_BYTES,
            'Original readback dependency aggregate exceeds capacity')
    require(hashlib.sha256(manifest_wire).hexdigest() == expected.manifest_sha256,
            'Original manifest digest differs from independent head')
    manifest = decode_numeric(manifest_wire, maximum=MAX_MANIFEST_BYTES)
    require(type(manifest) is dict and manifest.get('format') == CHECKPOINT_FORMAT
            and manifest.get('source_model_version') == MODEL_FORMAT
            and manifest.get('owner_id') == expected.owner_id and manifest.get('run_id') == expected.run_id
            and type(manifest.get('revision')) is int and manifest['revision'] == expected.revision)
    refs = manifest.get('components')
    require(type(refs) is list and len(refs) == 13, 'Complete original component references required')
    seen = set()
    for reference, component_wire in zip(refs, component_wires):
        fields(reference, {'kind', 'entity_id', 'generation', 'sha256'})
        identity = digest(reference['sha256'])
        require(identity not in seen and hashlib.sha256(component_wire).hexdigest() == identity,
                'Ordered original component reference differs')
        seen.add(identity)
        component = decode_numeric(component_wire, maximum=MAX_COMPONENT_BYTES)
        fields(component, {'format', 'hash_policy', 'owner_id', 'run_id', 'kind', 'entity_id', 'generation', 'body'})
        require(component['format'] == COMPONENT_FORMAT and component['hash_policy'] == HASH_POLICY
                and component['owner_id'] == expected.owner_id and component['run_id'] == expected.run_id)
        for key in ('kind', 'entity_id', 'generation'):
            require(type(component[key]) is type(reference[key]) and component[key] == reference[key])
    guard = validate_receipt(envelope['receipt'], expected)
    current_revision = revision(envelope['current_revision'])
    status = envelope['current_status']
    require(type(status) is str and status in STATUSES and current_revision >= expected.revision)
    require(expected.allow_historical or current_revision == expected.revision,
            'Historical readback is not the expected current head')
    require(current_revision != expected.revision or status == manifest.get('status'),
            'Current native status differs from its checkpoint')
    result = object.__new__(DecodedCheckpoint)
    for key, value in [('expected', expected), ('manifest_wire', manifest_wire),
            ('component_wires', component_wires), ('current_revision', current_revision),
            ('current_status', status), ('guard_observed_at', guard)]:
        object.__setattr__(result, key, value)
    return result
