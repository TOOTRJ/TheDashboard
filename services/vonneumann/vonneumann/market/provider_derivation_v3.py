"""Independently reparse original capsules into exact offline observations.

These research DTOs are not accepted native/model state. External issuer and
prior-history bindings are caller trust inputs, not hash-based authentication.
No provider, storage, environment, DB, clock, randomness or worker call occurs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from functools import wraps
import hashlib

from .provider_evidence import decimal_text, ProviderEvidenceError
from ..core.decimal_execution import _units, _text, PRICE_SCALE, DecimalExecutionError
from . import provider_acquisition_v3 as a

OBSERVATION_FORMAT = 'ga-provider-derived-observation-research-v3'
HISTORY_FORMAT = 'ga-provider-derived-history-research-v3'
MAX_DERIVATION_BYTES = 4 * 1024 * 1024


def _safe(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try: return function(*args, **kwargs)
        except a.AcquisitionError: raise
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            raise a.AcquisitionError() from None
    return guarded


def _shape(value, required, optional=()):
    a.require(type(value) is dict and set(required) <= set(value) <= set(required) | set(optional))
    return value


def _number(value, *, positive=False, price=False):
    try:
        text = decimal_text(value, positive=positive)
        if price: a.require(_text(_units(text, PRICE_SCALE, positive=True), PRICE_SCALE) == text)
        return text
    except (ProviderEvidenceError, DecimalExecutionError): raise a.AcquisitionError() from None


def _body(capsule, binding, family):
    a.require(type(capsule) is a.AcquisitionCapsule)
    checked = a.decode_capsule(capsule.wire, binding)
    a.require(checked.raw_body == capsule.raw_body)
    row = checked.to_dict(); a.require(row['provider_family'] == family and row['http_status'] == '200')
    return row, a.request_fields(row['canonical_public_request_wire'].encode(), family), \
        a.read_json(checked.raw_body, a.BODY_LIMITS[family], numeric=True)


def _pin(row, capsule):
    return {'record_id': row['record_id'], 'capsule_sha256': capsule.sha256,
        'raw_response_ref': row['raw_response_ref'], 'response_sha256': row['response_sha256'],
        'request_sha256': row['request_sha256'], 'response_bytes': row['response_bytes'],
        'provider_family': row['provider_family'], 'issuer_binding_id': row['issuer_binding_id'],
        'endpoint_binding_id': row['endpoint_binding_id'], 'parser_policy_sha256': row['parser_policy_sha256'],
        'received_wall_us': row['received_wall_us'], 'received_monotonic_us': row['received_monotonic_us']}


def _scope(row):
    return {key: row[key] for key in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch')}


def _price(capsule, binding):
    row, _, payload = _body(capsule, binding, 'jupiter-price-v3')
    a.fields(payload, {a.MINT})
    info = _shape(payload[a.MINT], {'usdPrice', 'blockId', 'decimals'},
        {'createdAt', 'liquidity', 'priceChange24h'})
    price = _number(info['usdPrice'], positive=True, price=True)
    block = a.integer(info['blockId'], 2**64-1); a.require(type(info['decimals']) is int and info['decimals'] == 9)
    if 'createdAt' in info:
        stamp = info['createdAt']; a.require(type(stamp) is str and 0 < len(stamp) <= 64)
        parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        a.require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0)
    if 'liquidity' in info: _number(info['liquidity'])
    if 'priceChange24h' in info:
        a.require(info['priceChange24h'] is None or type(info['priceChange24h']) in (int, Decimal))
    return row, price, block


def _rpc(capsule, binding, method, *, slot=None):
    row, request, payload = _body(capsule, binding, 'solana-rpc')
    body = a.read_json(request['body_wire'].encode(), a.MAX_REQUEST_BYTES, numeric=True)
    a.require(body['method'] == method and body['params'] == ([] if slot is None else [slot]))
    a.fields(payload, {'jsonrpc', 'id', 'result'})
    a.require(payload['jsonrpc'] == '2.0' and type(payload['id']) is int and payload['id'] == body['id'])
    return row, payload['result']


def _sum_exact(values):
    """Integer-only decimal addition; ambient Decimal context cannot round."""
    fractions = [len(value.split('.')[1]) if '.' in value else 0 for value in values]
    scale = max(fractions, default=0)
    total = 0
    for value in values:
        parts = value.split('.')
        total += int(parts[0])*10**scale + int((parts[1] if len(parts) == 2 else '').ljust(scale, '0') or '0')
    whole, fraction = divmod(total, 10**scale)
    a.require(len(str(whole)) <= 80)
    tail = str(fraction).rjust(scale, '0').rstrip('0') if scale else ''
    return str(whole) + ('.'+tail if tail else '')


def _minutes(payload, start, end):
    a.fields(payload, {'success', 'data'}); a.require(payload['success'] is True)
    body = _shape(payload['data'], {'items', 'is_scaled_ui_token'}, {'multiplier'})
    a.require(body['is_scaled_ui_token'] is False and type(body['items']) is list and len(body['items']) <= 5000)
    multiplier = body.get('multiplier')
    if multiplier is not None: a.require(_number(multiplier, positive=True) == '1')
    result = {}
    for row in body['items']:
        _shape(row, {'unix_time', 'address', 'type', 'currency', 'o', 'h', 'l', 'c', 'v', 'v_usd'}, {'multiplier'})
        stamp = a.integer(row['unix_time'], a.MAX_SECOND, 1)
        a.require(stamp % 60 == 0 and stamp <= end and row['address'] == a.MINT
            and row['type'] == '1m' and row['currency'] == 'usd')
        if row.get('multiplier') is not None: a.require(_number(row['multiplier'], positive=True) == '1')
        prices = [_number(row[key], positive=True, price=True) for key in ('o', 'h', 'l', 'c')]
        opening, high, low, close = [Decimal(value) for value in prices]
        a.require(low <= min(opening, close) <= max(opening, close) <= high)
        minute = {'start': str(stamp), 'end': str(stamp+60), 'open': prices[0], 'high': prices[1],
            'low': prices[2], 'close': prices[3], 'volume': _number(row['v']), 'volume_usd': _number(row['v_usd'])}
        if stamp in result: a.require(result[stamp] == minute)
        result[stamp] = minute
    # Validate old/forming rows and duplicate revisions before excluding them.
    selected = tuple(result[stamp] for stamp in sorted(result) if start <= stamp < end)
    a.require(len(selected) == (end-start)//60 and all(int(row['start']) == start+60*index for index, row in enumerate(selected)))
    return selected


def _bars(minutes):
    a.require(len(minutes) % 15 == 0)
    bars = []
    for index in range(0, len(minutes), 15):
        rows = minutes[index:index+15]
        a.require(int(rows[0]['start']) % 900 == 0)
        bars.append({'start': rows[0]['start'], 'end': rows[-1]['end'], 'open': rows[0]['open'],
            'high': max((row['high'] for row in rows), key=Decimal), 'low': min((row['low'] for row in rows), key=Decimal),
            'close': rows[-1]['close'], 'volume': _sum_exact([row['volume'] for row in rows]),
            'volume_usd': _sum_exact([row['volume_usd'] for row in rows])})
    return tuple(bars)


@dataclass(frozen=True, slots=True, init=False)
class DerivedHistory:
    _wire: bytes = field(repr=False)
    def __init__(self, *args, **kwargs): raise a.AcquisitionError()
    @property
    def wire(self): return self._wire
    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()
    def to_dict(self): return a.read_json(self._wire, MAX_DERIVATION_BYTES, exact=True)
    @property
    def native_admission(self): return False
    @property
    def provider_authenticated(self): return False


@_safe
def derive_history(capsule, binding, clock, *, previous=None, expected_previous_sha256=None):
    """Derive 61-bar warmup or one next bar with the full consumed overlap.

    The expected previous hash is a separate caller/operator trust input. This
    function cannot prove the previous history was accepted by a native server.
    Long backlogs, no overlap, missing minutes or changed consumed values refuse.
    """
    row, request, payload = _body(capsule, binding, 'birdeye-filtered-ohlcv-v3')
    a.require(type(clock) is a.ClockBound and clock.acquisition_epoch == row['acquisition_epoch'])
    age = a.assess_record_age(capsule, binding, clock)
    pin = _pin(row, capsule)
    start, end = [a.counter(request['parameters'][key], a.MAX_SECOND) for key in ('time_from', 'time_to')]
    cutoff = lambda wall: ((wall-5_000_000)//900_000_000)*900
    a.require(start % 900 == 0 and end % 900 == 0 and end > 61*900
        and all(cutoff(value) == end for value in (a.counter(row['request_started_wall_us']),
            a.counter(row['received_wall_us']), clock.wall_lower_us)))
    old = None
    if previous is None:
        a.require(expected_previous_sha256 is None and start == end-61*900)
    else:
        a.require(type(previous) is DerivedHistory and a.digest(expected_previous_sha256) == previous.sha256)
        old = previous.to_dict(); a.require(old['format'] == HISTORY_FORMAT and old['native_admission'] is False)
        for key in ('owner_id', 'run_id', 'market_epoch'): a.require(old['scope'][key] == row[key])
        old_pin = old['record_pin']
        a.require(pin['record_id'] != old_pin['record_id'] or pin['capsule_sha256'] == old_pin['capsule_sha256'])
        a.require(pin['raw_response_ref'] != old_pin['raw_response_ref'] or pin['response_sha256'] == old_pin['response_sha256'])
        previous_end = a.counter(old['range']['end'], a.MAX_SECOND)
        a.require(end == previous_end+900 and start == previous_end-900)
    minutes = _minutes(payload, start, end); bars = _bars(minutes)
    if old is not None:
        a.require(tuple(old['minutes'][-15:]) == minutes[:15])
    value = {'format': HISTORY_FORMAT, 'scope': _scope(row), 'asset': 'SOL/USD', 'mint': a.MINT,
        'denomination': 'USD', 'price_scale': '18', 'volume_unit': 'base_token', 'volume_usd_unit': 'USD',
        'range': {'start': str(start), 'end': str(end), 'completed_minutes': str(len(minutes))},
        'outlier_policy': 'explicit-false-filtered', 'padding': False, 'scaled': False,
        'previous_history_sha256': expected_previous_sha256, 'record_pin': pin,
        'minutes': list(minutes), 'bars': list(bars), 'appended_bars': list(bars if old is None else bars[1:]),
        'receipt_age': age.to_dict(), 'provider_authenticated': False, 'native_admission': False,
        'history_publication_verified': False, 'retention_rights_verified': False, 'running_authority': False}
    raw = a.canonical(value); a.require(len(raw) <= MAX_DERIVATION_BYTES)
    result = object.__new__(DerivedHistory); object.__setattr__(result, '_wire', raw); return result


@dataclass(frozen=True, slots=True, init=False)
class DerivedObservation:
    _wire: bytes = field(repr=False)
    def __init__(self, *args, **kwargs): raise a.AcquisitionError()
    @property
    def wire(self): return self._wire
    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()
    def to_dict(self): return a.read_json(self._wire, MAX_DERIVATION_BYTES, exact=True)
    @property
    def native_admission(self): return False
    @property
    def provider_authenticated(self): return False
    @property
    def running_authority(self): return False


def _clock_wire(clock):
    return {key: str(getattr(clock, key)) for key in ('owner_id', 'run_id', 'market_epoch',
        'acquisition_epoch', 'wall_lower_us', 'wall_upper_us', 'monotonic_us')}


def _carried_source(previous, expected_sha256, price_row, block, source_second, clock, source_age,
                    *, observation_id, current_pins):
    """Keep prior source-age floors while independently comparing clock epochs."""
    if previous is None:
        a.require(expected_sha256 is None); return
    a.require(type(previous) is DerivedObservation and a.digest(expected_sha256) == previous.sha256)
    old = previous.to_dict()
    a.require(old['format'] == OBSERVATION_FORMAT and old['native_admission'] is False)
    a.require(observation_id != old['observation_id'])
    old_records = {pin['record_id']: pin['capsule_sha256'] for pin in old['record_pins']}
    old_blobs = {pin['raw_response_ref']: pin['response_sha256'] for pin in old['record_pins']}
    for pin in current_pins:
        a.require(pin['record_id'] not in old_records or old_records[pin['record_id']] == pin['capsule_sha256'])
        a.require(pin['raw_response_ref'] not in old_blobs or old_blobs[pin['raw_response_ref']] == pin['response_sha256'])
    for key in ('owner_id', 'run_id', 'market_epoch'): a.require(old['scope'][key] == price_row[key])
    old_block = a.counter(old['block_ref'], 2**64-1)
    old_source = a.counter(old['estimated_source_second'], a.MAX_SECOND)
    a.require(block >= old_block and source_second >= old_source
        and (block != old_block or source_second == old_source))
    prior_clock = old['observation_clock']
    a.fields(prior_clock, {'owner_id', 'run_id', 'market_epoch', 'acquisition_epoch',
        'wall_lower_us', 'wall_upper_us', 'monotonic_us'})
    prior = a.ClockBound(**{key: a.counter(item) if key.endswith('_us') else item
        for key, item in prior_clock.items()})
    for key in ('owner_id', 'run_id', 'market_epoch'): a.require(getattr(prior, key) == getattr(clock, key))
    if prior.acquisition_epoch == clock.acquisition_epoch:
        a.require(clock.wall_lower_us >= prior.wall_lower_us and clock.monotonic_us >= prior.monotonic_us)
        elapsed_lower = elapsed_upper = clock.monotonic_us-prior.monotonic_us
    else:
        a.require(clock.wall_lower_us >= prior.wall_upper_us)
        elapsed_lower, elapsed_upper = clock.wall_lower_us-prior.wall_upper_us, clock.wall_upper_us-prior.wall_lower_us
    shift = (source_second-old_source)*1_000_000
    lower = max(a.counter(source_age['source_age_floor_us']),
        a.counter(old['source_age_floor_us'])+elapsed_lower-shift, 0)
    upper = max(a.counter(source_age['source_age_ceiling_us']),
        a.counter(old['source_age_ceiling_us'])+elapsed_upper-shift, lower)
    a.require(upper <= a.MAX_SOURCE_AGE_US)
    source_age['source_age_floor_us'], source_age['source_age_ceiling_us'] = str(lower), str(upper)


@_safe
def derive_observation(price_capsule, genesis_capsule, block_time_capsule, binding, clock,
                       *, observation_id, history_capsule=None, previous_history=None,
                       expected_previous_history_sha256=None, previous_observation=None,
                       expected_previous_observation_sha256=None):
    """Useful exact mark/network/time/history derivation, with all authority false.

    Initial profile requires fresh genesis and block-time records in each packet;
    an old cached RPC anchor has no implicit freshness exemption. Source time is
    an estimate of block production, never provider publication or finality.
    """
    a.uuid(observation_id); a.require(type(clock) is a.ClockBound)
    price_row, price, block = _price(price_capsule, binding)
    genesis_row, genesis = _rpc(genesis_capsule, binding, 'getGenesisHash')
    a.require(type(genesis) is str and genesis == a.GENESIS)
    time_row, source_second = _rpc(block_time_capsule, binding, 'getBlockTime', slot=block)
    a.integer(source_second, a.MAX_SECOND)
    capsules = [(price_capsule, price_row), (genesis_capsule, genesis_row), (block_time_capsule, time_row)]
    history = None
    if history_capsule is not None:
        history = derive_history(history_capsule, binding, clock, previous=previous_history,
            expected_previous_sha256=expected_previous_history_sha256)
        capsules.append((history_capsule, history_capsule.to_dict()))
    else: a.require(previous_history is None and expected_previous_history_sha256 is None)
    ids = [row['record_id'] for _, row in capsules]
    a.require(len(set(ids)) == len(ids) and observation_id not in ids)
    raw_refs = [row['raw_response_ref'] for _, row in capsules]
    a.require(len(set(raw_refs)) == len(raw_refs))
    a.require(all(row['acquisition_epoch'] == clock.acquisition_epoch for _, row in capsules))
    ages = [a.assess_record_age(capsule, binding, clock,
        source_second=source_second if capsule is price_capsule else None).to_dict() for capsule, _ in capsules]
    source_age = ages[0]
    pins = [_pin(row, capsule) for capsule, row in capsules]
    _carried_source(previous_observation, expected_previous_observation_sha256,
        price_row, block, source_second, clock, source_age, observation_id=observation_id, current_pins=pins)
    value = {'format': OBSERVATION_FORMAT, 'scope': _scope(price_row), 'observation_id': observation_id,
        'previous_observation_sha256': expected_previous_observation_sha256,
        'observation_clock': _clock_wire(clock),
        'asset': 'SOL/USD', 'mint': a.MINT, 'denomination': 'USD', 'valuation': 'reference_mark',
        'price_decimal': price, 'decimals': '9', 'block_ref': str(block), 'genesis_hash': genesis,
        'estimated_source_second': str(source_second), 'source_time_basis': 'estimated-block-production-not-provider-publication',
        'source_age_floor_us': source_age['source_age_floor_us'], 'source_age_ceiling_us': source_age['source_age_ceiling_us'],
        'record_pins': pins, 'record_ages': ages,
        'receipt_earliest_us': str(min(a.counter(row['received_wall_us']) for _, row in capsules)),
        'receipt_latest_us': str(max(a.counter(row['received_wall_us']) for _, row in capsules)),
        'history_sha256': None if history is None else history.sha256,
        'history': None if history is None else history.to_dict(),
        'provider_authenticated': False, 'native_admission': False, 'final_visible_instant_freshness': False,
        'history_publication_verified': False, 'archive_verified': False, 'restoration_authority': False,
        'lease_authority': False, 'hosted_authority': False, 'running_authority': False, 'live_trading_authority': False}
    raw = a.canonical(value); a.require(len(raw) <= MAX_DERIVATION_BYTES)
    result = object.__new__(DerivedObservation); object.__setattr__(result, '_wire', raw); return result
