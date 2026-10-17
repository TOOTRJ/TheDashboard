"""Pure, bounded original acquisition capsules for a forward research profile.

No acquisition, authentication, archive, native admission or running authority.
An independently trusted operator must supply IssuerBinding; its Python value
does not authenticate that operator or the provider. Literal bytes stay intact.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import re
from types import MappingProxyType
from uuid import UUID

FORMAT = 'ga-provider-acquisition-capsule-research-v3'
REQUEST_FORMAT = 'ga-provider-public-request-research-v3'
AGE_FORMAT = 'ga-provider-record-age-research-v3'
MINT = 'So11111111111111111111111111111111111111112'
GENESIS = '5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d'
MAX_CAPSULE_BYTES = 6 * 1024 * 1024
MAX_REQUEST_BYTES = 4096
MAX_CLOCK = 2**63 - 1
MAX_SECOND = 10_000_000_000
MAX_RECEIPT_AGE_US = 5_000_000
MAX_SOURCE_AGE_US = 30_000_000
FUTURE_US = 2_000_000
BODY_LIMITS = MappingProxyType({'jupiter-price-v3': 131072, 'solana-rpc': 65536,
                              'birdeye-filtered-ohlcv-v3': 4194304})
POLICY_FORMAT = 'ga-provider-acquisition-parser-policy-research-v3-quota-v2-nullable-change-v1'
_POLICY = {'format': POLICY_FORMAT,
    'json': 'duplicate-free-exact-decimal-utf8-v1', 'depth': '32', 'nodes': '200000',
    'row_cap': '5000', 'mint': MINT, 'chain': 'solana', 'price_grid': '18',
    'history': 'complete-1m-usd-raw-padding-false-outlier-false-v1',
    'rpc': 'literal-mainnet-genesis-and-integer-block-time-v1',
    'price_metadata': 'optional-creation-liquidity-change-nullable-change-v1',
    'clock': 'integer-us-bounded-utc-cross-epoch-no-rebase-v1',
    'metadata': 'signed-int64-remaining-unsigned-current-unix-seconds-reset-v1',
    'known_predecessor_identity': 'original-record-capsule-and-raw-response-sha-v1'}


class AcquisitionError(ValueError):
    """A fixed private-safe error; never echo a body, URL, ID or secret."""
    def __init__(self): super().__init__('Forward acquisition evidence is invalid or unsupported')


def require(condition):
    if not condition: raise AcquisitionError()


def uuid(value):
    require(type(value) is str and len(value) == 36)
    try: require(str(UUID(value)) == value)
    except ValueError: raise AcquisitionError() from None
    return value


def digest(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value, re.ASCII) is not None)
    return value


def integer(value, maximum=MAX_CLOCK, minimum=0):
    require(type(value) is int and minimum <= value <= maximum)
    return value


def counter(value, maximum=MAX_CLOCK, minimum=0):
    require(type(value) is str and re.fullmatch('0|[1-9][0-9]{0,19}', value, re.ASCII) is not None)
    return integer(int(value), maximum, minimum)


def signed_counter(value):
    require(type(value) is str and re.fullmatch('0|-?[1-9][0-9]{0,18}', value, re.ASCII) is not None)
    result = int(value); require(-(2**63) <= result <= MAX_CLOCK)
    return result


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected))
    return value


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError): raise AcquisitionError() from None


POLICY_SHA256 = hashlib.sha256(canonical(_POLICY)).hexdigest()


def read_json(raw, maximum, *, numeric=False, exact=False):
    """Pre-bound nesting, exact numeric lexemes and duplicate/object/node limits."""
    require(type(raw) is bytes and 0 < len(raw) <= maximum)
    def number(token, integral=False):
        require(numeric and len(token) <= 128)
        parts = re.split('[eE]', token, maxsplit=1)
        require(sum(char.isdigit() for char in parts[0]) <= 80)
        if len(parts) == 2: require(-80 <= int(parts[1]) <= 80)
        require(token != '-0')
        result = int(token) if integral else Decimal(token)
        require(type(result) is int or result.is_finite())
        return result
    def pairs(items):
        require(len(items) <= 1024); result = {}
        for key, value in items:
            require(key not in result); result[key] = value
        return result
    def constant(_): raise AcquisitionError()
    try:
        text = raw.decode('utf-8', errors='strict'); require(not text.startswith('\ufeff'))
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped: escaped = False
                elif char == '\\': escaped = True
                elif char == '"': quoted = False
            elif char == '"': quoted = True
            elif char in '[{':
                depth += 1; require(depth <= 32)
            elif char in ']}':
                depth -= 1; require(depth >= 0)
        result = json.loads(text, object_pairs_hook=pairs,
            parse_int=lambda token: number(token, True), parse_float=number, parse_constant=constant)
        stack, visits = [result], 0
        while stack:
            item = stack.pop(); visits += 1; require(visits <= 200000)
            if type(item) is dict: stack.extend(item.keys()); stack.extend(item.values())
            elif type(item) is list: require(len(item) <= 5000); stack.extend(item)
            elif type(item) is str:
                require('\x00' not in item and not any(0xd800 <= ord(char) <= 0xdfff for char in item))
            else: require(item is None or type(item) in (bool, int, Decimal))
        if exact: require(canonical(result) == raw)
        return result
    except AcquisitionError: raise
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError): raise AcquisitionError() from None


def public_request(family, *, start=None, end=None, rpc_method=None, rpc_id=None, slot=None):
    """Canonical safe request identity. RPC endpoint URL/auth are never inputs."""
    require(type(family) is str and family in BODY_LIMITS)
    body = None
    if family == 'jupiter-price-v3':
        require(all(value is None for value in (start, end, rpc_method, rpc_id, slot)))
        method, endpoint, parameters = 'GET', 'https://api.jup.ag/price/v3', {'ids': MINT}
    elif family == 'birdeye-filtered-ohlcv-v3':
        require(rpc_method is None and rpc_id is None and slot is None)
        integer(start, MAX_SECOND, 1); integer(end, MAX_SECOND, 1)
        require(start < end and start % 60 == 0 and end % 60 == 0 and (end-start)//60 <= 5000)
        method, endpoint = 'GET', 'https://public-api.birdeye.so/defi/v3/ohlcv'
        parameters = {'address': MINT, 'type': '1m', 'mode': 'range', 'currency': 'usd',
            'chart_type': 'price', 'ui_amount_mode': 'raw', 'padding': 'false', 'outlier': 'false',
            'time_from': str(start), 'time_to': str(end)}
    else:
        require(start is None and end is None and type(rpc_method) is str
            and rpc_method in {'getGenesisHash', 'getBlockTime'})
        integer(rpc_id, 2**31-1, 1)
        if rpc_method == 'getGenesisHash': require(slot is None); params = []
        else: params = [integer(slot, 2**64-1)]
        body = canonical({'jsonrpc': '2.0', 'id': rpc_id, 'method': rpc_method, 'params': params}).decode()
        method, endpoint, parameters = 'POST', 'operator-bound-solana-rpc', {}
    return canonical({'format': REQUEST_FORMAT, 'method': method, 'endpoint': endpoint,
        'chain': 'solana', 'parameters': parameters, 'body_wire': body})


def request_fields(raw, family):
    require(type(raw) is bytes and len(raw) <= MAX_REQUEST_BYTES)
    value = fields(read_json(raw, MAX_REQUEST_BYTES, exact=True),
        {'format', 'method', 'endpoint', 'chain', 'parameters', 'body_wire'})
    require(value['format'] == REQUEST_FORMAT and value['chain'] == 'solana')
    if family == 'jupiter-price-v3': expected = public_request(family)
    elif family == 'birdeye-filtered-ohlcv-v3':
        parameters = value['parameters']; require(type(parameters) is dict)
        expected = public_request(family, start=counter(parameters.get('time_from'), MAX_SECOND),
            end=counter(parameters.get('time_to'), MAX_SECOND))
    else:
        require(family == 'solana-rpc' and type(value['body_wire']) is str)
        body = fields(read_json(value['body_wire'].encode(), MAX_REQUEST_BYTES, numeric=True),
            {'jsonrpc', 'id', 'method', 'params'})
        require(body['jsonrpc'] == '2.0' and type(body['params']) is list)
        method = body['method']; require(type(method) is str and method in {'getGenesisHash', 'getBlockTime'})
        require(len(body['params']) == (0 if method == 'getGenesisHash' else 1))
        expected = public_request(family, rpc_method=method, rpc_id=body['id'],
            slot=None if not body['params'] else body['params'][0])
    require(expected == raw)
    return value


@dataclass(frozen=True, slots=True)
class IssuerBinding:
    """External operator trust input, not an authentication proof or credential."""
    owner_id: str
    run_id: str
    market_epoch: str
    acquisition_epoch: str
    issuer_binding_id: str
    endpoint_bindings: tuple[tuple[str, str], ...]
    parser_policy_sha256: str = POLICY_SHA256

    def __post_init__(self):
        for value in (self.owner_id, self.run_id, self.market_epoch, self.acquisition_epoch, self.issuer_binding_id): uuid(value)
        require(self.market_epoch != self.acquisition_epoch and self.parser_policy_sha256 == POLICY_SHA256)
        require(type(self.endpoint_bindings) is tuple and 1 <= len(self.endpoint_bindings) <= 3)
        seen = set()
        for entry in self.endpoint_bindings:
            require(type(entry) is tuple and len(entry) == 2 and type(entry[0]) is str
                and entry[0] in BODY_LIMITS and entry[0] not in seen)
            uuid(entry[1]); seen.add(entry[0])

    def endpoint(self, family):
        self.__post_init__()
        found = [identifier for actual, identifier in self.endpoint_bindings if actual == family]
        require(len(found) == 1); return found[0]


_CAPSULE_KEYS = {'format', 'owner_id', 'run_id', 'market_epoch', 'acquisition_epoch', 'record_id',
    'issuer_binding_id', 'provider_family', 'endpoint_binding_id', 'method', 'canonical_public_request_wire',
    'request_sha256', 'http_status', 'response_bytes', 'response_sha256', 'raw_response_ref', 'response_base64',
    'request_started_wall_us', 'received_wall_us', 'request_started_monotonic_us', 'received_monotonic_us',
    'safe_response_metadata', 'parser_policy_sha256'}


def _metadata(value):
    require(type(value) is dict and set(value) <= {'content_type', 'x_ratelimit_current',
        'x_ratelimit_remaining', 'x_ratelimit_reset'})
    for key, item in value.items():
        if key == 'content_type': require(item == 'application/json' and type(item) is str)
        elif key == 'x_ratelimit_remaining': signed_counter(item)
        elif key == 'x_ratelimit_reset': counter(item, MAX_SECOND)
        else: counter(item)


@dataclass(frozen=True, slots=True, init=False)
class AcquisitionCapsule:
    _wire: bytes = field(repr=False)
    _raw_body: bytes = field(repr=False)

    def __init__(self, *args, **kwargs): raise AcquisitionError()
    @property
    def wire(self): return self._wire
    @property
    def raw_body(self): return self._raw_body
    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()
    def to_dict(self): return json.loads(self._wire)
    @property
    def native_admission(self): return False
    @property
    def provider_authenticated(self): return False
    @property
    def archive_verified(self): return False
    @property
    def hosted_activation(self): return False


def decode_capsule(raw, expected):
    require(type(expected) is IssuerBinding); expected.__post_init__()
    value = fields(read_json(raw, MAX_CAPSULE_BYTES, exact=True), _CAPSULE_KEYS)
    require(value['format'] == FORMAT)
    for key in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch', 'issuer_binding_id', 'parser_policy_sha256'):
        require(value[key] == getattr(expected, key))
    uuid(value['record_id']); uuid(value['raw_response_ref'])
    family = value['provider_family']; require(type(family) is str and family in BODY_LIMITS)
    require(value['endpoint_binding_id'] == expected.endpoint(family))
    require(type(value['canonical_public_request_wire']) is str)
    request = value['canonical_public_request_wire'].encode('utf-8')
    info = request_fields(request, family); require(value['method'] == info['method'])
    require(digest(value['request_sha256']) == hashlib.sha256(request).hexdigest())
    status = counter(value['http_status'], 599, 100); size = counter(value['response_bytes'], BODY_LIMITS[family])
    require(type(value['response_base64']) is str and len(value['response_base64']) <= ((BODY_LIMITS[family]+2)//3)*4)
    try: body = base64.b64decode(value['response_base64'], validate=True)
    except (ValueError, TypeError): raise AcquisitionError() from None
    require(base64.b64encode(body).decode('ascii') == value['response_base64'] and len(body) == size
        and (size > 0 or status != 200) and digest(value['response_sha256']) == hashlib.sha256(body).hexdigest())
    start_wall, wall, start_mono, mono = [counter(value[key]) for key in ('request_started_wall_us',
        'received_wall_us', 'request_started_monotonic_us', 'received_monotonic_us')]
    require(start_wall <= wall and start_mono <= mono)
    _metadata(value['safe_response_metadata'])
    result = object.__new__(AcquisitionCapsule)
    object.__setattr__(result, '_wire', raw); object.__setattr__(result, '_raw_body', body)
    return result


def capture_capsule(expected, *, record_id, provider_family, request, raw_body, http_status,
                    started_wall_us, received_wall_us, started_monotonic_us, received_monotonic_us,
                    raw_response_ref=None, safe_response_metadata=None):
    require(type(expected) is IssuerBinding); expected.__post_init__()
    uuid(record_id); require(type(raw_body) is bytes and type(provider_family) is str and provider_family in BODY_LIMITS
        and len(raw_body) <= BODY_LIMITS[provider_family])
    require(type(request) is bytes); info = request_fields(request, provider_family)
    integer(http_status, 599, 100)
    for value in (started_wall_us, received_wall_us, started_monotonic_us, received_monotonic_us): integer(value)
    value = {key: getattr(expected, key) for key in ('owner_id', 'run_id', 'market_epoch',
        'acquisition_epoch', 'issuer_binding_id', 'parser_policy_sha256')}
    value.update(format=FORMAT, record_id=record_id, provider_family=provider_family,
        endpoint_binding_id=expected.endpoint(provider_family), method=info['method'],
        canonical_public_request_wire=request.decode('utf-8'), request_sha256=hashlib.sha256(request).hexdigest(),
        http_status=str(http_status), response_bytes=str(len(raw_body)), response_sha256=hashlib.sha256(raw_body).hexdigest(),
        raw_response_ref=record_id if raw_response_ref is None else raw_response_ref,
        response_base64=base64.b64encode(raw_body).decode('ascii'), request_started_wall_us=str(started_wall_us),
        received_wall_us=str(received_wall_us), request_started_monotonic_us=str(started_monotonic_us),
        received_monotonic_us=str(received_monotonic_us), safe_response_metadata={} if safe_response_metadata is None else safe_response_metadata)
    return decode_capsule(canonical(value), expected)


@dataclass(frozen=True, slots=True)
class ClockBound:
    """Explicit independently bounded UTC interval; no clock is read here."""
    owner_id: str
    run_id: str
    market_epoch: str
    acquisition_epoch: str
    wall_lower_us: int
    wall_upper_us: int
    monotonic_us: int

    def __post_init__(self):
        for value in (self.owner_id, self.run_id, self.market_epoch, self.acquisition_epoch): uuid(value)
        for value in (self.wall_lower_us, self.wall_upper_us, self.monotonic_us): integer(value)
        require(self.market_epoch != self.acquisition_epoch and self.wall_lower_us <= self.wall_upper_us
            and self.wall_upper_us-self.wall_lower_us <= FUTURE_US)


@dataclass(frozen=True, slots=True, init=False)
class RecordAge:
    _wire: bytes = field(repr=False)
    def __init__(self, *args, **kwargs): raise AcquisitionError()
    def to_dict(self): return json.loads(self._wire)
    @property
    def native_admission(self): return False


def _age_value(raw):
    value = fields(read_json(raw, 4096, exact=True), {'format', 'record_id', 'capsule_sha256',
        'source_second', 'receipt_age_floor_us', 'receipt_age_ceiling_us', 'source_age_floor_us',
        'source_age_ceiling_us', 'clock', 'native_admission'})
    require(value['format'] == AGE_FORMAT and value['native_admission'] is False)
    uuid(value['record_id']); digest(value['capsule_sha256'])
    require(counter(value['receipt_age_floor_us']) <= counter(value['receipt_age_ceiling_us']) < MAX_RECEIPT_AGE_US)
    keys = {'owner_id', 'run_id', 'market_epoch', 'acquisition_epoch', 'wall_lower_us', 'wall_upper_us', 'monotonic_us'}
    clock = fields(value['clock'], keys)
    ClockBound(**{key: counter(item) if key.endswith('_us') else item for key, item in clock.items()})
    if value['source_second'] is None:
        require(value['source_age_floor_us'] is None and value['source_age_ceiling_us'] is None)
    else:
        counter(value['source_second'], MAX_SECOND)
        require(counter(value['source_age_floor_us']) <= counter(value['source_age_ceiling_us']) <= MAX_SOURCE_AGE_US)
    return value


def assess_record_age(capsule, binding, clock, *, source_second=None, previous=None):
    """Conservative age without cross-process monotonic subtraction or rebase.

    Cross-epoch UTC ordering must be independently bounded. A prior age snapshot
    can only grow; a cache hit cannot refresh its original receipt/source clock.
    This is a pure proposed-policy check, not a native server observation.
    """
    require(type(capsule) is AcquisitionCapsule and type(clock) is ClockBound)
    checked = decode_capsule(capsule.wire, binding); require(checked.raw_body == capsule.raw_body)
    clock.__post_init__(); row = checked.to_dict()
    for key in ('owner_id', 'run_id', 'market_epoch'): require(row[key] == getattr(clock, key))
    wall, mono = counter(row['received_wall_us']), counter(row['received_monotonic_us'])
    start_wall, start_mono = counter(row['request_started_wall_us']), counter(row['request_started_monotonic_us'])
    require(mono-start_mono < MAX_RECEIPT_AGE_US and wall-start_wall < MAX_RECEIPT_AGE_US
        and abs((wall-start_wall)-(mono-start_mono)) <= FUTURE_US)
    lower, upper = max(0, clock.wall_lower_us-wall), max(0, clock.wall_upper_us-wall)
    if clock.acquisition_epoch == row['acquisition_epoch']:
        require(clock.monotonic_us >= mono and wall <= clock.wall_lower_us+FUTURE_US)
        elapsed = clock.monotonic_us-mono; lower, upper = max(lower, elapsed), max(upper, elapsed)
    else:
        # No meaningful subtraction of another process's arbitrary clock origin.
        require(clock.wall_lower_us >= wall)
    source_lower = source_upper = None
    if source_second is not None:
        integer(source_second, MAX_SECOND); source_us = source_second*1_000_000
        require(source_us <= clock.wall_lower_us+FUTURE_US)
        original_floor = max(0, wall-source_us)
        source_lower = max(0, clock.wall_lower_us-source_us, original_floor+lower)
        source_upper = max(0, clock.wall_upper_us-source_us, original_floor+upper)
    if previous is not None:
        require(type(previous) is RecordAge)
        old = _age_value(previous._wire)
        require(old['record_id'] == row['record_id'] and old['capsule_sha256'] == checked.sha256
            and old['source_second'] == (None if source_second is None else str(source_second)))
        old_clock = old['clock']
        for key in ('owner_id', 'run_id', 'market_epoch'): require(old_clock[key] == getattr(clock, key))
        if old_clock['acquisition_epoch'] == clock.acquisition_epoch:
            elapsed = clock.monotonic_us-counter(old_clock['monotonic_us']); require(elapsed >= 0)
            require(clock.wall_lower_us >= counter(old_clock['wall_lower_us']))
            upper_elapsed = elapsed
        else:
            require(clock.wall_lower_us >= counter(old_clock['wall_upper_us']))
            elapsed = clock.wall_lower_us-counter(old_clock['wall_upper_us'])
            upper_elapsed = clock.wall_upper_us-counter(old_clock['wall_lower_us'])
        lower = max(lower, counter(old['receipt_age_floor_us'])+elapsed)
        upper = max(upper, counter(old['receipt_age_ceiling_us'])+upper_elapsed)
        if source_second is not None:
            source_lower = max(source_lower, counter(old['source_age_floor_us'])+elapsed)
            source_upper = max(source_upper, counter(old['source_age_ceiling_us'])+upper_elapsed)
    require(upper < MAX_RECEIPT_AGE_US and (source_upper is None or source_upper <= MAX_SOURCE_AGE_US))
    value = {'format': AGE_FORMAT, 'record_id': row['record_id'], 'capsule_sha256': checked.sha256,
        'source_second': None if source_second is None else str(source_second),
        'receipt_age_floor_us': str(lower), 'receipt_age_ceiling_us': str(upper),
        'source_age_floor_us': None if source_lower is None else str(source_lower),
        'source_age_ceiling_us': None if source_upper is None else str(source_upper),
        'clock': {key: str(getattr(clock, key)) for key in ('owner_id', 'run_id', 'market_epoch',
            'acquisition_epoch', 'wall_lower_us', 'wall_upper_us', 'monotonic_us')}, 'native_admission': False}
    result = object.__new__(RecordAge); object.__setattr__(result, '_wire', canonical(value)); return result
