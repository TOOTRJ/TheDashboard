"""Pure prospective Jupiter sampled-close source, with no runtime authority.

Native receipt/readback references are independent caller trust inputs. These
Python values, research hashes and fixtures do not authenticate an issuer,
provider, transport, database, clock or committed original record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

from . import provider_acquisition_v3 as a
from . import provider_derivation_v3 as d
from ..core.decimal_execution import _units, _text, PRICE_SCALE

PROFILE = 'jupiter-price-v3-prospective-minute-sampled-close-v1'
MARK_FORMAT = 'ga-jupiter-prospective-mark-research-v3'
SET_FORMAT = 'ga-jupiter-prospective-frozen-record-set-research-v3'
HISTORY_FORMAT = 'ga-jupiter-prospective-history-research-v3'
CLOSE_SERIES_FORMAT = 'ga-jupiter-prospective-close-series-research-v3'
MAX_RECORDS = 4000
MAX_MARK_BYTES = 16384
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_HISTORY_BYTES = 4 * 1024 * 1024
WARMUP_MINUTES = 915
BAR_SECONDS = 900
COMPLETION_MARGIN_US = 5_000_000
_POLICY = {'format': 'ga-jupiter-prospective-source-policy-research-v3',
    'profile': PROFILE, 'asset': 'SOL/USD', 'mint': a.MINT, 'mainnet_genesis': a.GENESIS, 'price_scale': '18',
    'acquisition_parser_policy_sha256': a.POLICY_SHA256,
    'minute': 'original-committed-readback-upper-before-end-v1',
    'selection': 'max-native-accepted-us-then-unique-ingest-sequence-v1',
    'bar': 'close-only-final-minute-plus-15-original-anchor-pins-v1',
    'history': '915-complete-observed-minutes-no-padding-backfill-v1',
    'overlap': 'exact-original-last-15-anchor-and-bar-bytes-v1',
    'clock': 'integer-us-original-process-epochs-no-rebase-v1',
    'action_clock': 'integer-us-causal-after-original-readback-and-latest-receipt-v1',
    'freshness': 'all-trio-receipts-under-5s-source-at-most-30s-at-original-acceptance-v1',
    'completion_margin_us': str(COMPLETION_MARGIN_US),
    'trust': 'independent-authenticated-scoped-native-original-readback-required-v1'}
POLICY_SHA256 = hashlib.sha256(a.canonical(_POLICY)).hexdigest()
_PIN_FIELDS = {'record_id', 'capsule_sha256', 'raw_response_ref', 'response_sha256',
    'request_sha256', 'response_bytes', 'provider_family', 'issuer_binding_id',
    'endpoint_binding_id', 'parser_policy_sha256', 'received_wall_us', 'received_monotonic_us'}


def _safe(function):
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except a.AcquisitionError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
            raise a.AcquisitionError() from None
    return guarded


@dataclass(frozen=True, slots=True)
class RecordReference:
    """Independent original native/readback evidence; lexical checks only."""
    owner_id: str
    run_id: str
    market_epoch: str
    acquisition_epoch: str
    observation_id: str
    observation_sha256: str
    record_admission_id: str
    ingest_sequence: int
    accepted_at_us: int
    available_at_upper_us: int
    issuer_principal_binding_id: str
    recorder_package_sha256: str
    native_record_receipt_sha256: str

    def __post_init__(self):
        for key in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch',
                    'observation_id', 'record_admission_id', 'issuer_principal_binding_id'):
            a.uuid(getattr(self, key))
        for key in ('observation_sha256', 'recorder_package_sha256', 'native_record_receipt_sha256'):
            a.digest(getattr(self, key))
        a.integer(self.ingest_sequence, 2**63-1, 1)
        a.integer(self.accepted_at_us); a.integer(self.available_at_upper_us)
        a.require(self.market_epoch != self.acquisition_epoch
            and self.observation_id != self.record_admission_id
            and self.accepted_at_us <= self.available_at_upper_us)


@dataclass(frozen=True, slots=True)
class SealReference:
    """Independent authenticated frozen inventory reference, not a seal proof."""
    owner_id: str
    run_id: str
    market_epoch: str
    seal_id: str
    records_sha256: str
    through_ingest_sequence: int
    start_second: int
    end_second: int
    sealed_at_us: int
    recorder_package_sha256: str
    source_policy_sha256: str = POLICY_SHA256

    def __post_init__(self):
        for key in ('owner_id', 'run_id', 'market_epoch', 'seal_id'):
            a.uuid(getattr(self, key))
        a.digest(self.records_sha256); a.digest(self.source_policy_sha256); a.digest(self.recorder_package_sha256)
        a.integer(self.through_ingest_sequence, 2**63-1, 1)
        a.integer(self.start_second, a.MAX_SECOND)
        a.integer(self.end_second, a.MAX_SECOND)
        a.integer(self.sealed_at_us)
        a.require(self.source_policy_sha256 == POLICY_SHA256
            and self.start_second % BAR_SECONDS == self.end_second % BAR_SECONDS == 0
            and self.start_second < self.end_second
            and self.end_second-self.start_second in (WARMUP_MINUTES*60, 2*BAR_SECONDS)
            and self.sealed_at_us >= self.end_second*1_000_000+COMPLETION_MARGIN_US)


@dataclass(frozen=True, slots=True, init=False)
class SourceMark:
    _wire: bytes = field(repr=False)
    def __init__(self, *args, **kwargs): raise a.AcquisitionError()
    @property
    def wire(self): return self._wire
    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()
    def to_dict(self): return a.read_json(self._wire, MAX_MARK_BYTES, exact=True)
    @property
    def native_admission(self): return False
    @property
    def running_authority(self): return False


def _scope(reference):
    return {key: getattr(reference, key) for key in ('owner_id', 'run_id', 'market_epoch')}


def _reference_wire(reference):
    return {key: str(getattr(reference, key)) for key in RecordReference.__dataclass_fields__}


def _record_pins(pins):
    a.require(type(pins) is list and len(pins) == 3)
    for pin in pins:
        a.fields(pin, _PIN_FIELDS)
        for key in ('record_id', 'raw_response_ref', 'issuer_binding_id', 'endpoint_binding_id'): a.uuid(pin[key])
        for key in ('capsule_sha256', 'response_sha256', 'request_sha256', 'parser_policy_sha256'): a.digest(pin[key])
        a.require(pin['parser_policy_sha256'] == a.POLICY_SHA256)
        a.counter(pin['received_wall_us']); a.counter(pin['received_monotonic_us'])
        a.counter(pin['response_bytes'], a.BODY_LIMITS.get(pin['provider_family'], 0), 1)
    a.require(sorted(pin['provider_family'] for pin in pins) == ['jupiter-price-v3', 'solana-rpc', 'solana-rpc'])
    for key in ('record_id', 'raw_response_ref'):
        a.require(len(set(pin[key] for pin in pins)) == 3)


def _mark_value(mark):
    a.require(type(mark) is SourceMark)
    value = a.fields(mark.to_dict(), {'format', 'profile', 'source_policy_sha256',
        'scope', 'acquisition_epoch', 'reference', 'price_decimal', 'block_ref',
        'estimated_source_second', 'source_age_at_acceptance_ceiling_us', 'source_age_at_observation_ceiling_us',
        'original_observation_clock', 'record_pins', 'provider_attested',
        'native_admission', 'current_freshness', 'running_authority'})
    a.require(value['format'] == MARK_FORMAT and value['profile'] == PROFILE
        and value['source_policy_sha256'] == POLICY_SHA256
        and all(value[key] is False for key in ('provider_attested', 'native_admission',
            'current_freshness', 'running_authority')))
    ref = a.fields(value['reference'], set(RecordReference.__dataclass_fields__))
    numeric = {'ingest_sequence', 'accepted_at_us', 'available_at_upper_us'}
    reference = RecordReference(**{key: a.counter(item) if key in numeric else item for key, item in ref.items()})
    a.require(value['scope'] == _scope(reference) and value['acquisition_epoch'] == reference.acquisition_epoch)
    a.require(type(value['price_decimal']) is str
        and _text(_units(value['price_decimal'], PRICE_SCALE, positive=True), PRICE_SCALE) == value['price_decimal'])
    a.counter(value['block_ref'], 2**64-1); a.counter(value['estimated_source_second'], a.MAX_SECOND)
    a.counter(value['source_age_at_acceptance_ceiling_us'], a.MAX_SOURCE_AGE_US)
    original_age = a.counter(value['source_age_at_observation_ceiling_us'], a.MAX_SOURCE_AGE_US)
    clock = a.fields(value['original_observation_clock'], {'owner_id', 'run_id', 'market_epoch',
        'acquisition_epoch', 'wall_lower_us', 'wall_upper_us', 'monotonic_us'})
    checked_clock = a.ClockBound(**{key: a.counter(item) if key.endswith('_us') else item for key, item in clock.items()})
    a.require(all(getattr(checked_clock, key) == getattr(reference, key)
        for key in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch'))
        and reference.accepted_at_us >= checked_clock.wall_lower_us
        and reference.available_at_upper_us >= checked_clock.wall_upper_us)
    source_us = a.counter(value['estimated_source_second'], a.MAX_SECOND)*1_000_000
    a.require(source_us <= reference.accepted_at_us+a.FUTURE_US
        and a.counter(value['source_age_at_acceptance_ceiling_us']) >= max(
            0, reference.accepted_at_us-source_us,
            original_age+max(0, reference.accepted_at_us-checked_clock.wall_lower_us)))
    _record_pins(value['record_pins'])
    for pin in value['record_pins']:
        received = a.counter(pin['received_wall_us']); monotonic = a.counter(pin['received_monotonic_us'])
        a.require(received <= reference.accepted_at_us+a.FUTURE_US
            and reference.available_at_upper_us-received < a.MAX_RECEIPT_AGE_US
            and monotonic <= checked_clock.monotonic_us)
    for key in ('record_id', 'raw_response_ref'):
        ids = [pin[key] for pin in value['record_pins']]
        a.require(len(set(ids)) == 3 and reference.observation_id not in ids
            and reference.record_admission_id not in ids)
    return value, reference


@_safe
def capture_mark(observation, reference):
    """Bind a derived trio to explicit independent original readback inputs.

No referenced server/transport is contacted. The output remains research-only.
Old source receipts cannot become fresh by changing a native reference clock.
"""
    a.require(type(observation) is d.DerivedObservation and type(reference) is RecordReference)
    reference.__post_init__()
    value = a.fields(observation.to_dict(), {'format', 'scope', 'observation_id',
        'previous_observation_sha256', 'observation_clock', 'asset', 'mint',
        'denomination', 'valuation', 'price_decimal', 'decimals', 'block_ref',
        'genesis_hash', 'estimated_source_second', 'source_time_basis',
        'source_age_floor_us', 'source_age_ceiling_us', 'record_pins', 'record_ages',
        'receipt_earliest_us', 'receipt_latest_us', 'history_sha256', 'history',
        'provider_authenticated', 'native_admission', 'final_visible_instant_freshness',
        'history_publication_verified', 'archive_verified', 'restoration_authority',
        'lease_authority', 'hosted_authority', 'running_authority', 'live_trading_authority'})
    a.require(value['format'] == d.OBSERVATION_FORMAT and observation.sha256 == reference.observation_sha256
        and value['observation_id'] == reference.observation_id
        and value['scope'] == {**_scope(reference), 'acquisition_epoch': reference.acquisition_epoch}
        and value['history'] is None and value['history_sha256'] is None
        and value['asset'] == 'SOL/USD' and value['mint'] == a.MINT
        and value['genesis_hash'] == a.GENESIS and value['denomination'] == 'USD'
        and value['valuation'] == 'reference_mark'
        and value['source_time_basis'] == 'estimated-block-production-not-provider-publication')
    flags = ('provider_authenticated', 'native_admission', 'final_visible_instant_freshness',
        'history_publication_verified', 'archive_verified', 'restoration_authority',
        'lease_authority', 'hosted_authority', 'running_authority', 'live_trading_authority')
    a.require(all(value[key] is False for key in flags))
    clock = value['observation_clock']
    lower, upper = a.counter(clock['wall_lower_us']), a.counter(clock['wall_upper_us'])
    a.require(reference.accepted_at_us >= lower and reference.available_at_upper_us >= upper)
    age = a.counter(value['source_age_ceiling_us'], a.MAX_SOURCE_AGE_US)
    age += max(0, reference.accepted_at_us-lower)
    a.require(age <= a.MAX_SOURCE_AGE_US)
    pins = value['record_pins']; a.require(len(pins) == len(value['record_ages']) == 3)
    for pin, recorded_age in zip(pins, value['record_ages']):
        receipt = a.counter(pin['received_wall_us'])
        a.require(receipt <= reference.accepted_at_us+a.FUTURE_US
            and reference.available_at_upper_us-receipt < a.MAX_RECEIPT_AGE_US
            and a.counter(recorded_age['receipt_age_ceiling_us'])+
                max(0, reference.available_at_upper_us-lower) < a.MAX_RECEIPT_AGE_US)
    a.require(a.counter(value['estimated_source_second'], a.MAX_SECOND)*1_000_000
        <= reference.accepted_at_us+a.FUTURE_US)
    row = {'format': MARK_FORMAT, 'profile': PROFILE, 'source_policy_sha256': POLICY_SHA256,
        'scope': _scope(reference), 'acquisition_epoch': reference.acquisition_epoch,
        'reference': _reference_wire(reference), 'price_decimal': value['price_decimal'],
        'block_ref': value['block_ref'], 'estimated_source_second': value['estimated_source_second'],
        'source_age_at_acceptance_ceiling_us': str(age),
        'source_age_at_observation_ceiling_us': value['source_age_ceiling_us'],
        'original_observation_clock': value['observation_clock'], 'record_pins': pins,
        'provider_attested': False, 'native_admission': False, 'current_freshness': False,
        'running_authority': False}
    raw = a.canonical(row); a.require(len(raw) <= MAX_MARK_BYTES)
    mark = object.__new__(SourceMark); object.__setattr__(mark, '_wire', raw)
    _mark_value(mark); return mark


@_safe
def validate_mark(mark, *, expected_mark_sha256):
    """Strict immutable mark validation against an independent expected digest."""
    a.require(type(mark) is SourceMark and a.digest(expected_mark_sha256) == mark.sha256)
    _mark_value(mark); return mark


@_safe
def validate_current_mark(mark, clock, *, expected_mark_sha256):
    """Actual supplied current clock checks, never action/native permission.

The caller must bind a genuine clock and the independent original mark digest.
The native boundary must reobserve clocks after processing and locks. No cached
or historical mark receives a new receipt, sequence, process epoch or authority.
"""
    validate_mark(mark, expected_mark_sha256=expected_mark_sha256)
    a.require(type(clock) is a.ClockBound); clock.__post_init__()
    value, reference = _mark_value(mark)
    for key in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch'):
        a.require(getattr(clock, key) == getattr(reference, key))
    original = value['original_observation_clock']
    original_wall = a.counter(original['wall_lower_us'])
    original_mono = a.counter(original['monotonic_us'])
    a.require(clock.wall_lower_us >= original_wall and clock.monotonic_us >= original_mono
        and clock.wall_lower_us >= reference.available_at_upper_us)
    latest = 0
    for pin in value['record_pins']:
        receipt, receipt_mono = a.counter(pin['received_wall_us']), a.counter(pin['received_monotonic_us'])
        a.require(clock.monotonic_us >= receipt_mono and receipt <= clock.wall_lower_us+a.FUTURE_US
            and max(0, clock.wall_upper_us-receipt, clock.monotonic_us-receipt_mono) < a.MAX_RECEIPT_AGE_US)
        latest = max(latest, receipt)
    source_us = a.counter(value['estimated_source_second'], a.MAX_SECOND)*1_000_000
    age = max(0, clock.wall_upper_us-source_us,
        a.counter(value['source_age_at_acceptance_ceiling_us'])+max(0, clock.wall_upper_us-reference.accepted_at_us),
        a.counter(value['source_age_at_observation_ceiling_us'])+clock.monotonic_us-original_mono)
    a.require(source_us <= clock.wall_lower_us+a.FUTURE_US and age <= a.MAX_SOURCE_AGE_US
        and clock.wall_lower_us >= latest)
    return mark


@_safe
def record_set_digest(marks):
    """Hash supplied immutable marks; this never establishes a complete ledger."""
    a.require(type(marks) is tuple and 0 < len(marks) <= MAX_RECORDS)
    checked = [(_mark_value(mark)[1], mark) for mark in marks]
    ordered = sorted(checked, key=lambda item: (item[0].ingest_sequence, item[0].observation_id))
    inventory = [{'observation_id': reference.observation_id,
        'record_admission_id': reference.record_admission_id,
        'ingest_sequence': str(reference.ingest_sequence), 'mark_sha256': mark.sha256}
        for reference, mark in ordered]
    return hashlib.sha256(a.canonical(inventory)).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class FrozenRecords:
    _wire: bytes = field(repr=False)
    _marks: tuple = field(repr=False)
    _reference: SealReference = field(repr=False)
    def __init__(self, *args, **kwargs): raise a.AcquisitionError()
    @property
    def wire(self): return self._wire
    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()
    def to_dict(self): return a.read_json(self._wire, MAX_MANIFEST_BYTES, exact=True)
    @property
    def native_admission(self): return False


@_safe
def freeze_records(marks, reference):
    """Compare the complete supplied inventory with a separate seal reference.

The real native head must supply that reference and prevent reopening a seal.
This pure function does not authenticate, query or create such a native head.
"""
    a.require(type(reference) is SealReference); reference.__post_init__()
    a.require(record_set_digest(marks) == reference.records_sha256)
    seen = {key: {} for key in ('sequence', 'observation', 'admission', 'record', 'raw')}
    source_prior = None
    checked = sorted([(_mark_value(mark)[0], _mark_value(mark)[1], mark) for mark in marks],
        key=lambda item: item[1].ingest_sequence)
    for value, original, mark in checked:
        a.require(value['scope'] == _scope(reference)
            and original.recorder_package_sha256 == reference.recorder_package_sha256
            and original.ingest_sequence <= reference.through_ingest_sequence
            and original.available_at_upper_us <= reference.sealed_at_us)
        for kind, identity in (('sequence', original.ingest_sequence),
                ('observation', original.observation_id), ('admission', original.record_admission_id)):
            a.require(identity not in seen[kind]); seen[kind][identity] = mark.sha256
        for pin in value['record_pins']:
            for kind, identity, digest in (('record', pin['record_id'], pin['capsule_sha256']),
                    ('raw', pin['raw_response_ref'], pin['response_sha256'])):
                a.require(identity not in seen[kind] or seen[kind][identity] == digest)
                seen[kind][identity] = digest
        point = (a.counter(value['block_ref'], 2**64-1),
                 a.counter(value['estimated_source_second'], a.MAX_SECOND))
        if source_prior is not None:
            a.require(original.accepted_at_us >= source_prior[0]
                and point[0] >= source_prior[1][0] and point[1] >= source_prior[1][1]
                and (point[0] != source_prior[1][0] or
                     (point[1] == source_prior[1][1] and value['price_decimal'] == source_prior[2])))
        source_prior = (original.accepted_at_us, point, value['price_decimal'])
    row = {'format': SET_FORMAT, 'profile': PROFILE, 'source_policy_sha256': POLICY_SHA256,
        'scope': _scope(reference), 'seal_id': reference.seal_id,
        'records_sha256': reference.records_sha256,
        'through_ingest_sequence': str(reference.through_ingest_sequence),
        'start_second': str(reference.start_second), 'end_second': str(reference.end_second),
        'sealed_at_us': str(reference.sealed_at_us),
        'recorder_package_sha256': reference.recorder_package_sha256,
        'records': [{'ingest_sequence': str(original.ingest_sequence),
            'observation_id': original.observation_id, 'mark_sha256': mark.sha256}
            for _, original, mark in checked],
        'complete_native_ledger_verified': False, 'native_admission': False, 'running_authority': False}
    wire = a.canonical(row); a.require(len(wire) <= MAX_MANIFEST_BYTES)
    result = object.__new__(FrozenRecords)
    object.__setattr__(result, '_wire', wire); object.__setattr__(result, '_marks', tuple(item[2] for item in checked))
    object.__setattr__(result, '_reference', reference); return result


def _minute_anchors(frozen):
    reference = frozen._reference; selected = {}
    for mark in frozen._marks:
        value, original = _mark_value(mark)
        minute = original.accepted_at_us//60_000_000*60
        if not reference.start_second <= minute < reference.end_second:
            continue
        # A committed original readback observed after end is diagnostic evidence,
        # not a historical minute anchor even when Price receipt preceded end.
        if not minute*1_000_000 < original.available_at_upper_us <= (minute+60)*1_000_000:
            continue
        candidate = (original.accepted_at_us, original.ingest_sequence)
        if minute in selected and candidate <= selected[minute][0]:
            continue
        selected[minute] = (candidate, {'start': str(minute), 'end': str(minute+60),
            'observation_id': original.observation_id, 'mark_sha256': mark.sha256,
            'observation_sha256': original.observation_sha256,
            'record_admission_id': original.record_admission_id,
            'native_record_receipt_sha256': original.native_record_receipt_sha256,
            'issuer_principal_binding_id': original.issuer_principal_binding_id,
            'ingest_sequence': str(original.ingest_sequence),
            'accepted_at_us': str(original.accepted_at_us),
            'available_at_upper_us': str(original.available_at_upper_us),
            'acquisition_epoch': original.acquisition_epoch,
            'price_decimal': value['price_decimal'], 'block_ref': value['block_ref'],
            'estimated_source_second': value['estimated_source_second'],
            'source_age_at_acceptance_ceiling_us': value['source_age_at_acceptance_ceiling_us'],
            'original_record_pins': value['record_pins']})
    anchors = tuple(selected[minute][1] for minute in range(reference.start_second, reference.end_second, 60)
        if minute in selected)
    a.require(len(anchors) == (reference.end_second-reference.start_second)//60)
    return anchors


def _bars(anchors):
    a.require(len(anchors) % 15 == 0); bars = []
    for index in range(0, len(anchors), 15):
        group = anchors[index:index+15]; end = a.counter(group[-1]['end'], a.MAX_SECOND)
        a.require(a.counter(group[0]['start'], a.MAX_SECOND) % BAR_SECONDS == 0)
        offset = end*1_000_000-a.counter(group[-1]['available_at_upper_us'])
        a.require(0 <= offset < 60_000_000)
        bars.append({'start': group[0]['start'], 'end': group[-1]['end'],
            'close': group[-1]['price_decimal'], 'close_offset_us': str(offset),
            'close_observation_id': group[-1]['observation_id'],
            'close_source_age_at_acceptance_ceiling_us': group[-1]['source_age_at_acceptance_ceiling_us'],
            'minute_anchors_sha256': hashlib.sha256(a.canonical(list(group))).hexdigest(),
            'minute_anchor_pins': [{'start': row['start'], 'observation_id': row['observation_id'],
                'mark_sha256': row['mark_sha256']} for row in group]})
    return tuple(bars)


def _retained_anchors(anchors, start, market_epoch):
    """Self-contained causal/identity checks; no raw/authentication substitute."""
    minute_fields = {'start', 'end', 'observation_id', 'mark_sha256', 'observation_sha256',
        'record_admission_id', 'native_record_receipt_sha256', 'issuer_principal_binding_id',
        'ingest_sequence', 'accepted_at_us', 'available_at_upper_us', 'acquisition_epoch',
        'price_decimal', 'block_ref', 'estimated_source_second',
        'source_age_at_acceptance_ceiling_us', 'original_record_pins'}
    seen = {key: {} for key in ('observation', 'admission', 'sequence', 'record', 'raw')}
    prior = None
    for index, minute in enumerate(anchors):
        a.fields(minute, minute_fields)
        a.require(minute['start'] == str(start+index*60) and minute['end'] == str(start+(index+1)*60))
        for key in ('observation_id', 'record_admission_id', 'issuer_principal_binding_id', 'acquisition_epoch'):
            a.uuid(minute[key])
        a.require(minute['acquisition_epoch'] != market_epoch)
        for key in ('mark_sha256', 'observation_sha256', 'native_record_receipt_sha256'): a.digest(minute[key])
        sequence = a.counter(minute['ingest_sequence'], 2**63-1, 1)
        accepted, available = a.counter(minute['accepted_at_us']), a.counter(minute['available_at_upper_us'])
        lower, upper = (start+index*60)*1_000_000, (start+(index+1)*60)*1_000_000
        a.require(lower <= accepted < upper and lower < available <= upper and accepted <= available)
        block = a.counter(minute['block_ref'], 2**64-1)
        source = a.counter(minute['estimated_source_second'], a.MAX_SECOND)
        age = a.counter(minute['source_age_at_acceptance_ceiling_us'], a.MAX_SOURCE_AGE_US)
        a.require(source*1_000_000 <= accepted+a.FUTURE_US and age >= max(0, accepted-source*1_000_000)
            and _text(_units(minute['price_decimal'], PRICE_SCALE, positive=True), PRICE_SCALE) == minute['price_decimal'])
        _record_pins(minute['original_record_pins'])
        a.require(minute['observation_id'] != minute['record_admission_id'])
        for kind, identity in (('observation', minute['observation_id']),
                ('admission', minute['record_admission_id']), ('sequence', sequence)):
            a.require(identity not in seen[kind]); seen[kind][identity] = minute['mark_sha256']
        for pin in minute['original_record_pins']:
            receipt = a.counter(pin['received_wall_us'])
            a.require(receipt <= accepted+a.FUTURE_US and available-receipt < a.MAX_RECEIPT_AGE_US
                and pin['record_id'] not in (minute['observation_id'], minute['record_admission_id'])
                and pin['raw_response_ref'] not in (minute['observation_id'], minute['record_admission_id']))
            for kind, identity, digest in (('record', pin['record_id'], pin['capsule_sha256']),
                    ('raw', pin['raw_response_ref'], pin['response_sha256'])):
                a.require(identity not in seen[kind] or seen[kind][identity] == digest)
                seen[kind][identity] = digest
        if prior is not None:
            a.require(sequence > prior[0] and accepted >= prior[1] and block >= prior[2]
                and source >= prior[3] and (block != prior[2] or
                    (source == prior[3] and minute['price_decimal'] == prior[4])))
        prior = (sequence, accepted, block, source, minute['price_decimal'])


@dataclass(frozen=True, slots=True, init=False)
class SampledHistory:
    _wire: bytes = field(repr=False)
    def __init__(self, *args, **kwargs): raise a.AcquisitionError()
    @property
    def wire(self): return self._wire
    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()
    def to_dict(self): return a.read_json(self._wire, MAX_HISTORY_BYTES, exact=True)
    @property
    def native_admission(self): return False
    @property
    def running_authority(self): return False


@_safe
def derive_sampled_history(frozen, *, previous=None, expected_previous_sha256=None):
    """915 prospective minute anchors, or one next bar with unchanged overlap."""
    a.require(type(frozen) is FrozenRecords)
    # Reconstruct through the same bounded inventory path; forged/replaced fields
    # cannot acquire authority by possessing this Python type.
    checked = freeze_records(frozen._marks, frozen._reference)
    a.require(checked.wire == frozen.wire)
    anchors = _minute_anchors(checked); bars = _bars(anchors); reference = checked._reference
    old = None
    if previous is None:
        a.require(expected_previous_sha256 is None and len(anchors) == WARMUP_MINUTES)
        all_anchors, all_bars, appended = anchors, bars, bars
    else:
        a.require(type(previous) is SampledHistory and a.digest(expected_previous_sha256) == previous.sha256)
        derive_close_series(previous, expected_history_sha256=expected_previous_sha256)
        old = previous.to_dict()
        a.require(old['format'] == HISTORY_FORMAT and old['profile'] == PROFILE
            and old['source_policy_sha256'] == POLICY_SHA256 and old['scope'] == _scope(reference)
            and old['recorder_package_sha256'] == reference.recorder_package_sha256
            and old['native_admission'] is False and old['running_authority'] is False
            and len(old['minutes']) == WARMUP_MINUTES and len(old['bars']) == 61
            and len(anchors) == 30 and len(bars) == 2)
        end = a.counter(old['range']['end'], a.MAX_SECOND)
        a.require(reference.start_second == end-BAR_SECONDS and reference.end_second == end+BAR_SECONDS
            and tuple(old['minutes'][-15:]) == anchors[:15] and old['bars'][-1] == bars[0])
        a.require(old['seal_id'] != reference.seal_id)
        # Check every identity available in the retained predecessor, not only
        # the overlap. The complete historical native ledger remains necessary.
        identities = {key: {} for key in ('observation', 'admission', 'sequence', 'record', 'raw')}
        for anchor in old['minutes']:
            for kind, identity in (('observation', anchor['observation_id']),
                    ('admission', anchor['record_admission_id']), ('sequence', anchor['ingest_sequence'])):
                identities[kind][identity] = anchor['mark_sha256']
            for pin in anchor['original_record_pins']:
                identities['record'][pin['record_id']] = pin['capsule_sha256']
                identities['raw'][pin['raw_response_ref']] = pin['response_sha256']
        for mark in checked._marks:
            value, original = _mark_value(mark)
            for kind, identity in (('observation', original.observation_id),
                    ('admission', original.record_admission_id), ('sequence', str(original.ingest_sequence))):
                a.require(identity not in identities[kind] or identities[kind][identity] == mark.sha256)
            for pin in value['record_pins']:
                for kind, identity, digest in (('record', pin['record_id'], pin['capsule_sha256']),
                        ('raw', pin['raw_response_ref'], pin['response_sha256'])):
                    a.require(identity not in identities[kind] or identities[kind][identity] == digest)
        all_anchors = tuple(old['minutes'][15:])+anchors[15:]
        all_bars = tuple(old['bars'][1:])+bars[1:]; appended = bars[1:]
    row = {'format': HISTORY_FORMAT, 'profile': PROFILE, 'source_policy_sha256': POLICY_SHA256,
        'scope': _scope(reference), 'asset': 'SOL/USD', 'mint': a.MINT, 'denomination': 'USD',
        'valuation': 'reference_mark', 'bar_kind': 'prospective-sampled-close-only',
        'range': {'start': all_anchors[0]['start'], 'end': all_anchors[-1]['end'],
            'observed_minutes': str(len(all_anchors)), 'complete_bars': str(len(all_bars))},
        'seal_id': reference.seal_id, 'frozen_records_sha256': checked.sha256,
        'recorder_package_sha256': reference.recorder_package_sha256,
        'previous_history_sha256': expected_previous_sha256,
        'minutes': list(all_anchors), 'bars': list(all_bars), 'appended_bars': list(appended),
        'provider_attested': False, 'native_admission': False, 'historical_ohlcv': False,
        'volume_available': False, 'executable_quote': False, 'current_freshness': False,
        'complete_native_ledger_verified': False, 'running_authority': False}
    wire = a.canonical(row); a.require(len(wire) <= MAX_HISTORY_BYTES)
    result = object.__new__(SampledHistory); object.__setattr__(result, '_wire', wire); return result


@dataclass(frozen=True, slots=True, init=False)
class SampledCloseSeries:
    """Typed close-only model input; history/raw/native references remain required."""
    _wire: bytes = field(repr=False)
    def __init__(self, *args, **kwargs): raise a.AcquisitionError()
    @property
    def wire(self): return self._wire
    @property
    def sha256(self): return hashlib.sha256(self._wire).hexdigest()
    def to_dict(self): return a.read_json(self._wire, MAX_MANIFEST_BYTES, exact=True)
    @property
    def native_admission(self): return False
    @property
    def running_authority(self): return False


@_safe
def derive_close_series(history, *, expected_history_sha256):
    """Model seam with exact 61 closes and immutable history/readback/raw pins.

The expected digest must come from an independent accepted history reader in a
future runtime. This research comparison neither obtains nor proves that reader.
"""
    a.require(type(history) is SampledHistory and a.digest(expected_history_sha256) == history.sha256)
    value = a.fields(history.to_dict(), {'format', 'profile', 'source_policy_sha256',
        'scope', 'asset', 'mint', 'denomination', 'valuation', 'bar_kind', 'range',
        'seal_id', 'frozen_records_sha256', 'recorder_package_sha256',
        'previous_history_sha256', 'minutes', 'bars', 'appended_bars',
        'provider_attested', 'native_admission', 'historical_ohlcv', 'volume_available',
        'executable_quote', 'current_freshness', 'complete_native_ledger_verified', 'running_authority'})
    a.require(value['format'] == HISTORY_FORMAT and value['profile'] == PROFILE
        and value['source_policy_sha256'] == POLICY_SHA256
        and value['asset'] == 'SOL/USD' and value['mint'] == a.MINT
        and value['denomination'] == 'USD' and value['valuation'] == 'reference_mark'
        and value['bar_kind'] == 'prospective-sampled-close-only'
        and all(value[key] is False for key in ('provider_attested', 'native_admission',
            'historical_ohlcv', 'volume_available', 'executable_quote', 'current_freshness',
            'complete_native_ledger_verified', 'running_authority'))
        and type(value['minutes']) is list and len(value['minutes']) == WARMUP_MINUTES
        and type(value['bars']) is list and len(value['bars']) == 61)
    a.fields(value['scope'], {'owner_id', 'run_id', 'market_epoch'})
    for identity in value['scope'].values(): a.uuid(identity)
    a.digest(value['recorder_package_sha256']); a.digest(value['frozen_records_sha256']); a.uuid(value['seal_id'])
    a.fields(value['range'], {'start', 'end', 'observed_minutes', 'complete_bars'})
    start, end = a.counter(value['range']['start'], a.MAX_SECOND), a.counter(value['range']['end'], a.MAX_SECOND)
    a.require(start % BAR_SECONDS == end % BAR_SECONDS == 0 and end-start == WARMUP_MINUTES*60
        and value['range']['observed_minutes'] == '915' and value['range']['complete_bars'] == '61')
    _retained_anchors(value['minutes'], start, value['scope']['market_epoch'])
    a.require(list(_bars(tuple(value['minutes']))) == value['bars'])
    if value['previous_history_sha256'] is None:
        a.require(value['appended_bars'] == value['bars'])
    else:
        a.digest(value['previous_history_sha256']); a.require(value['appended_bars'] == value['bars'][-1:])
    closes = []
    for index, bar in enumerate(value['bars']):
        minute = value['minutes'][index*15+14]
        closes.append({**bar, 'close_mark_sha256': minute['mark_sha256'],
            'close_observation_sha256': minute['observation_sha256'],
            'close_record_admission_id': minute['record_admission_id'],
            'close_native_record_receipt_sha256': minute['native_record_receipt_sha256'],
            'close_original_record_pins': minute['original_record_pins']})
    row = {'format': CLOSE_SERIES_FORMAT, 'profile': PROFILE, 'source_policy_sha256': POLICY_SHA256,
        'scope': value['scope'], 'history_sha256': history.sha256,
        'recorder_package_sha256': value['recorder_package_sha256'],
        'range': value['range'], 'asset': 'SOL/USD', 'denomination': 'USD',
        'bar_seconds': str(BAR_SECONDS), 'price_scale': '18', 'closes': closes,
        'historical_ohlcv': False, 'executable_quote': False, 'current_freshness': False,
        'native_admission': False, 'running_authority': False}
    wire = a.canonical(row); a.require(len(wire) <= MAX_MANIFEST_BYTES)
    result = object.__new__(SampledCloseSeries); object.__setattr__(result, '_wire', wire); return result
