"""Public literal-only forward capsules; no provider or deployment acceptance."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import localcontext, InvalidOperation, Inexact, Rounded
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from vonneumann.market import provider_acquisition_v3 as a, provider_derivation_v3 as d
    from vonneumann.market.provider_evidence import ProviderDocument, ProviderEvidenceError
    from vonneumann.market.exact_records import parse_price_record

OWNER, RUN, MARKET, PROCESS, ISSUER = [str(UUID(int=value)) for value in (11, 12, 13, 14, 15)]
END = 1_800_000_000
WALL = (END+8)*1_000_000
MONO = 100_000_000


def binding(**changes):
    value = a.IssuerBinding(OWNER, RUN, MARKET, PROCESS, ISSUER,
        tuple((family, str(UUID(int=20+index))) for index, family in enumerate(a.BODY_LIMITS)))
    return replace(value, **changes) if changes else value


def clock(*, wall=WALL+1_000_000, mono=MONO+1_000_000, epoch=PROCESS, uncertainty=0):
    return a.ClockBound(OWNER, RUN, MARKET, epoch, wall, wall+uncertainty, mono)


def capsule(family, raw, *, identity=101, expected=None, request=None, wall=WALL,
            mono=MONO, elapsed=100_000, status=200, **changes):
    if expected is None: expected = binding()
    if request is None: request = a.public_request(family)
    values = {'record_id': str(UUID(int=identity)), 'provider_family': family, 'request': request,
        'raw_body': raw, 'http_status': status, 'started_wall_us': wall-elapsed, 'received_wall_us': wall,
        'started_monotonic_us': mono-elapsed, 'received_monotonic_us': mono}
    values.update(changes); return a.capture_capsule(expected, **values)


def price_raw(price='100.123456789012345678', *, block='348004023', decimals='9', extra=''):
    return ('{"'+a.MINT+'":{"usdPrice":'+price+',"blockId":'+block+',"decimals":'+decimals+extra+'}}').encode()


def price(**changes): return capsule('jupiter-price-v3', price_raw(), **changes)


def rpc(method, *, result=None, slot=348004023, identity=102, rpc_id=1, **changes):
    request = a.public_request('solana-rpc', rpc_method=method, rpc_id=rpc_id,
        slot=slot if method == 'getBlockTime' else None)
    if result is None: result = a.GENESIS if method == 'getGenesisHash' else END+6
    raw = a.canonical({'jsonrpc': '2.0', 'id': rpc_id, 'result': result})
    return capsule('solana-rpc', raw, identity=identity, request=request, **changes)


def minute(stamp, **changes):
    row = {'unix_time': stamp, 'address': a.MINT, 'type': '1m', 'currency': 'usd',
        'o': 100, 'h': 102, 'l': 99, 'c': 101, 'v': 3, 'v_usd': 301}
    row.update(changes); return row


def history_raw(start=END-61*900, end=END, *, rows=None, **body_changes):
    body = {'items': [minute(stamp) for stamp in range(start, end, 60)] if rows is None else rows,
        'is_scaled_ui_token': False, 'multiplier': None}
    body.update(body_changes)
    return a.canonical({'success': True, 'data': body})


def history(*, start=END-61*900, end=END, raw=None, identity=104, wall=WALL, **changes):
    return capsule('birdeye-filtered-ohlcv-v3', history_raw(start, end) if raw is None else raw,
        identity=identity, wall=wall, request=a.public_request('birdeye-filtered-ohlcv-v3', start=start, end=end), **changes)


def observe(p=None, g=None, t=None, **changes):
    observation_id = changes.pop('observation_id', str(UUID(int=105)))
    return d.derive_observation(price() if p is None else p,
        rpc('getGenesisHash') if g is None else g,
        rpc('getBlockTime', identity=103, rpc_id=2) if t is None else t,
        binding(), clock(), observation_id=observation_id, **changes)


class ProviderAcquisitionV3Tests(unittest.TestCase):
    def setUp(self):
        self.network = deny_network(); self.network.__enter__(); self.addCleanup(self.network.__exit__, None, None, None)

    def test_original_raw_and_request_survive_canonical_capsule_roundtrip(self):
        raw = b' {"'+a.MINT.encode()+b'":{"usdPrice":100.123456789012345678,"blockId":348004023,"decimals":9}}\n'
        original = capsule('jupiter-price-v3', raw)
        decoded = a.decode_capsule(original.wire, binding())
        self.assertEqual(decoded.raw_body, raw); self.assertEqual(decoded.wire, original.wire)
        row = decoded.to_dict()
        self.assertEqual(row['response_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(row['request_sha256'], hashlib.sha256(a.public_request('jupiter-price-v3')).hexdigest())
        self.assertEqual(row['record_id'], row['raw_response_ref'])
        self.assertFalse(decoded.native_admission); self.assertFalse(decoded.provider_authenticated)
        self.assertFalse(decoded.archive_verified); self.assertFalse(decoded.hosted_activation)
        with self.assertRaises(FrozenInstanceError): decoded._wire = b'changed'
        with self.assertRaises(a.AcquisitionError): a.AcquisitionCapsule()
        changed = decoded.to_dict(); changed['record_id'] = RUN
        self.assertNotEqual(changed, decoded.to_dict())
        self.assertNotIn('100.123', repr(decoded))

    def test_useful_exact_price_network_time_derivation_matches_old_precision(self):
        observed = observe(); row = observed.to_dict()
        self.assertEqual(row['price_decimal'], '100.123456789012345678')
        self.assertEqual(row['estimated_source_second'], str(END+6)); self.assertEqual(row['block_ref'], '348004023')
        self.assertEqual(row['genesis_hash'], a.GENESIS); self.assertEqual(row['source_age_floor_us'], '3000000')
        self.assertEqual(len(row['record_pins']), 3); self.assertEqual(len(row['record_ages']), 3)
        legacy = ProviderDocument.capture('jupiter-price-v3', {'ids': a.MINT}, price_raw(), END+8, 100)
        exact = parse_price_record(legacy, asset='SOL/USD', mint=a.MINT)
        self.assertEqual(row['price_decimal'], exact.price); self.assertEqual(int(row['block_ref']), exact.block_id)
        self.assertTrue(all(row[key] is False for key in ('native_admission', 'provider_authenticated',
            'final_visible_instant_freshness', 'archive_verified', 'restoration_authority', 'lease_authority',
            'hosted_authority', 'running_authority', 'live_trading_authority')))
        self.assertEqual(observe().wire, observed.wire)

    def test_capsule_unknown_duplicate_noncanonical_bad_utf8_and_raw_hash_refusal(self):
        original = price(); row = original.to_dict()
        variants = [original.wire+b' ', b'\xff', b'{"format":"x","format":"y"}']
        for key, value in [('unknown', False), ('record_id', True), ('http_status', 200),
            ('response_sha256', '0'*64), ('response_bytes', '1'), ('request_sha256', '0'*64),
            ('parser_policy_sha256', '0'*64), ('response_base64', row['response_base64']+'='),
            ('safe_response_metadata', {'authorization': 'never-printed'})]:
            altered = dict(row); altered[key] = value; variants.append(a.canonical(altered))
        for raw in variants:
            with self.subTest(raw_size=len(raw)), self.assertRaises(a.AcquisitionError): a.decode_capsule(raw, binding())

    def test_external_scope_issuer_epoch_endpoint_and_policy_are_required(self):
        original = price()
        for key in ('owner_id', 'run_id', 'market_epoch', 'acquisition_epoch', 'issuer_binding_id'):
            with self.subTest(key=key), self.assertRaises(a.AcquisitionError):
                a.decode_capsule(original.wire, replace(binding(), **{key: str(UUID(int=500))}))
        with self.assertRaises(a.AcquisitionError): a.decode_capsule(original.wire, original.to_dict())
        with self.assertRaises(a.AcquisitionError): binding(parser_policy_sha256='a'*64)
        endpoints = tuple((family, str(UUID(int=800+index))) for index, family in enumerate(a.BODY_LIMITS))
        with self.assertRaises(a.AcquisitionError): a.decode_capsule(original.wire, binding(endpoint_bindings=endpoints))

    def test_requests_reject_secret_fields_wrong_chain_padding_and_missing_outlier(self):
        raw = a.public_request('birdeye-filtered-ohlcv-v3', start=END-54900, end=END)
        value = a.read_json(raw, 4096)
        self.assertEqual(value['parameters']['outlier'], 'false')
        self.assertEqual(value['parameters']['padding'], 'false')
        with self.assertRaises(ProviderEvidenceError):
            ProviderDocument.capture('birdeye-ohlcv-v3', {**value['parameters'], 'time_from': END-54900, 'time_to': END}, history_raw(), END+8, 100)
        variants = []
        for field, item in [('headers', {'x-api-key': 'never-read'}), ('endpoint', 'https://private.invalid?key=secret'), ('chain', 'ethereum')]:
            altered = json.loads(raw); altered[field] = item; variants.append(a.canonical(altered))
        for flag, item in [('outlier', 'true'), ('outlier', False), ('padding', 'true'), ('ui_amount_mode', 'scaled')]:
            altered = json.loads(raw); altered['parameters'][flag] = item; variants.append(a.canonical(altered))
        altered = json.loads(raw); altered['parameters'].pop('outlier'); variants.append(a.canonical(altered))
        for request in variants:
            with self.subTest(size=len(request)), self.assertRaises(a.AcquisitionError):
                a.request_fields(request, 'birdeye-filtered-ohlcv-v3')

    def test_http_failures_are_retained_diagnostics_never_observations(self):
        for status, raw in [(429, b'{"error":"rate limit"}'), (403, b''), (503, b'not json')]:
            failed = capsule('jupiter-price-v3', raw, status=status)
            self.assertEqual(failed.raw_body, raw)
            with self.assertRaises(a.AcquisitionError): observe(p=failed)
        with self.assertRaises(a.AcquisitionError): capsule('jupiter-price-v3', b'')
        with self.assertRaises(a.AcquisitionError): capsule('jupiter-price-v3', b'{}', status=True)

    def test_signed_remaining_failure_metadata_and_empty_body_preserve_no_authority(self):
        for remaining in ('-1', '0', str(-(2**63)), str(2**63-1)):
            metadata = {'x_ratelimit_remaining': remaining, 'x_ratelimit_current': str(2**63-1),
                'x_ratelimit_reset': str(a.MAX_SECOND)}
            failed = capsule('jupiter-price-v3', b'', status=429, safe_response_metadata=metadata)
            self.assertEqual(failed.to_dict()['safe_response_metadata'], metadata)
            self.assertEqual(failed.to_dict()['response_bytes'], '0')
            self.assertEqual(a.decode_capsule(failed.wire, binding()).raw_body, b'')
            self.assertTrue(all(getattr(failed, flag) is False for flag in ('native_admission',
                'provider_authenticated', 'archive_verified', 'hosted_activation')))
            with self.assertRaises(a.AcquisitionError): observe(p=failed)

    def test_quota_canonical_signed_unsigned_and_unix_second_bounds(self):
        invalid_remaining = ('-0', '+0', '+1', '00', '-01', ' 0', '-1 ', '-1.0', '1e2',
            str(-(2**63)-1), str(2**63), '', False, -1, -1.0)
        for value in invalid_remaining:
            with self.subTest(kind='remaining', value_type=type(value).__name__), self.assertRaises(a.AcquisitionError):
                capsule('jupiter-price-v3', b'', status=429, safe_response_metadata={'x_ratelimit_remaining': value})
        for key, values in [('x_ratelimit_current', ('-1', '-0', '01', str(2**63), True, 1)),
                            ('x_ratelimit_reset', ('-1', '-0', '01', str(a.MAX_SECOND+1), True, 1))]:
            for value in values:
                with self.subTest(kind=key, value_type=type(value).__name__), self.assertRaises(a.AcquisitionError):
                    capsule('jupiter-price-v3', b'', status=429, safe_response_metadata={key: value})
        for key in ('native_admission', 'quota_verified', 'unknown'):
            with self.assertRaises(a.AcquisitionError):
                capsule('jupiter-price-v3', b'', status=429, safe_response_metadata={key: True})

    def test_zero_and_absent_quota_metadata_never_change_usd_or_runtime_binding(self):
        for metadata in ({}, {'x_ratelimit_remaining': '0', 'x_ratelimit_current': '0', 'x_ratelimit_reset': '0'}):
            original = price(safe_response_metadata=metadata)
            self.assertEqual(original.to_dict()['safe_response_metadata'], metadata)
            row = observe(p=original).to_dict()
            self.assertEqual(row['denomination'], 'USD'); self.assertFalse(row['native_admission'])
            self.assertFalse(row['provider_authenticated']); self.assertFalse(row['running_authority'])
            with self.assertRaises(a.AcquisitionError):
                observe(p=capsule('jupiter-price-v3', price_raw('0'), safe_response_metadata=metadata))
        from vonneumann.research.runtime_profile_v3_contract import proposal
        profile = proposal(OWNER, RUN, MARKET, PROCESS).to_dict()
        self.assertTrue(all(value is None for value in profile['implementation_bindings'].values()))
        self.assertTrue(all(value is False for value in profile['authority'].values()))

    def test_changed_quota_policy_digest_does_not_reinterpret_historical_capsules(self):
        original = price(); value = original.to_dict()
        value['parser_policy_sha256'] = '396df7236cb58fed359714b77110075791709eb894a0833e5fb7eb05aef863b9'
        with self.assertRaises(a.AcquisitionError): a.decode_capsule(a.canonical(value), binding())
        self.assertEqual(a.POLICY_FORMAT, 'ga-provider-acquisition-parser-policy-research-v3-quota-v2-nullable-change-v1')

    def test_raw_price_duplicate_nonfinite_boolean_string_precision_and_metadata_refusal(self):
        invalid = [b'{}', b'{"'+a.MINT.encode()+b'":null}', b'{"'+a.MINT.encode()+b'":{"usdPrice":100,"usdPrice":101,"blockId":1,"decimals":9}}',
            price_raw('NaN'), price_raw('Infinity'), price_raw('-0'), price_raw('-0.0'), price_raw('false'),
            price_raw('"100"'), price_raw('0'), price_raw('-1'), price_raw('1e81'), price_raw('1e37'),
            price_raw('0.0000000000000000001'), price_raw(block='1.0'), price_raw(block='true'),
            price_raw(decimals='8'), price_raw(decimals='true'), price_raw(extra=',"unknown":1'),
            price_raw(extra=',"createdAt":false'), price_raw(extra=',"liquidity":-1'),
            price_raw(extra=',"priceChange24h":"1"')]
        for raw in invalid:
            with self.subTest(raw_size=len(raw)), self.assertRaises(a.AcquisitionError):
                observe(p=capsule('jupiter-price-v3', raw))
        good = capsule('jupiter-price-v3', price_raw(extra=',"createdAt":"2024-06-05T08:55:25.527Z","liquidity":3,"priceChange24h":-1.2'))
        self.assertEqual(observe(p=good).to_dict()['estimated_source_second'], str(END+6))

    def test_large_integer_slot_and_exact_decimal_lexemes_survive(self):
        p = capsule('jupiter-price-v3', price_raw('1.000000000000000001', block='9007199254740993'))
        t = rpc('getBlockTime', slot=9007199254740993, identity=103, rpc_id=2)
        row = observe(p=p, t=t).to_dict()
        self.assertEqual(row['block_ref'], '9007199254740993'); self.assertEqual(row['price_decimal'], '1.000000000000000001')
        self.assertEqual(observe(p=capsule('jupiter-price-v3', price_raw('1e2'))).to_dict()['price_decimal'], '100')

    def test_rpc_wrong_network_null_time_error_id_slot_method_and_type_refusal(self):
        with self.assertRaises(a.AcquisitionError): observe(g=rpc('getGenesisHash', result='wrong-network'))
        with self.assertRaises(a.AcquisitionError): observe(t=rpc('getBlockTime', slot=348004024, identity=103))
        for result in [None, True, -1, 10_000_000_001, '1800000006']:
            raw = a.canonical({'jsonrpc': '2.0', 'id': 2, 'result': result})
            request = a.public_request('solana-rpc', rpc_method='getBlockTime', rpc_id=2, slot=348004023)
            with self.subTest(result_type=type(result).__name__), self.assertRaises(a.AcquisitionError):
                observe(t=capsule('solana-rpc', raw, request=request, identity=103))
        for raw in [b'{"jsonrpc":"2.0","id":2,"result":1800000006,"error":null}',
                    b'{"jsonrpc":"2.0","id":true,"result":1800000006}',
                    b'{"jsonrpc":"2.0","id":2,"id":2,"result":1800000006}',
                    b'{"jsonrpc":"2.0","id":2,"result":1800000006.0}']:
            request = a.public_request('solana-rpc', rpc_method='getBlockTime', rpc_id=2, slot=348004023)
            with self.assertRaises(a.AcquisitionError): observe(t=capsule('solana-rpc', raw, request=request, identity=103))

    def test_packet_receipt_bounds_include_price_every_rpc_and_history(self):
        h = history(wall=WALL-500_000, mono=MONO-500_000)
        row = observe(history_capsule=h).to_dict()
        self.assertEqual(len(row['record_pins']), 4)
        self.assertEqual(row['receipt_earliest_us'], str(WALL-500_000))
        self.assertEqual(row['receipt_latest_us'], str(WALL))
        for family in ('genesis', 'time', 'history'):
            with self.subTest(family=family), self.assertRaises(a.AcquisitionError):
                if family == 'genesis': observe(g=rpc('getGenesisHash', wall=WALL-4_000_000, mono=MONO-4_000_000))
                elif family == 'time': observe(t=rpc('getBlockTime', identity=103, wall=WALL-4_000_000, mono=MONO-4_000_000))
                else: observe(history_capsule=history(wall=WALL-4_000_000, mono=MONO-4_000_000))
        with self.assertRaises(a.AcquisitionError): observe(g=rpc('getGenesisHash', wall=WALL+4_000_000, mono=MONO+4_000_000))
        with self.assertRaises(a.AcquisitionError): observe(t=rpc('getBlockTime', result=END+12, identity=103))
        with self.assertRaises(a.AcquisitionError): observe(t=rpc('getBlockTime', result=END-30, identity=103))

    def test_original_record_and_raw_reference_collisions_are_refused(self):
        with self.assertRaises(a.AcquisitionError): observe(g=rpc('getGenesisHash', identity=101))
        with self.assertRaises(a.AcquisitionError): observe(g=rpc('getGenesisHash', raw_response_ref=str(UUID(int=101))))
        with self.assertRaises(a.AcquisitionError):
            d.derive_observation(price(), rpc('getGenesisHash'), rpc('getBlockTime', identity=103), binding(), clock(), observation_id=str(UUID(int=101)))

    def test_history_complete_915_minutes_and_exact_61_bar_aggregation(self):
        derived = d.derive_history(history(), binding(), clock()); row = derived.to_dict()
        self.assertEqual(len(row['minutes']), 915); self.assertEqual(len(row['bars']), 61)
        self.assertEqual(len(row['appended_bars']), 61)
        self.assertEqual(row['bars'][0]['volume'], '45'); self.assertEqual(row['bars'][0]['volume_usd'], '4515')
        self.assertEqual(row['outlier_policy'], 'explicit-false-filtered')
        self.assertFalse(row['history_publication_verified']); self.assertFalse(row['retention_rights_verified'])
        self.assertFalse(derived.native_admission); self.assertFalse(derived.provider_authenticated)

    def test_history_increment_requires_original_consumed_overlap_and_independent_prior_hash(self):
        previous = d.derive_history(history(), binding(), clock())
        end = END+900; new_wall = (end+8)*1_000_000; new_mono = MONO+900_000_000
        incremental = history(start=END-900, end=end, wall=new_wall, mono=new_mono, identity=204)
        current_clock = clock(wall=new_wall+1_000_000, mono=new_mono+1_000_000)
        result = d.derive_history(incremental, binding(), current_clock, previous=previous, expected_previous_sha256=previous.sha256)
        self.assertEqual(len(result.to_dict()['appended_bars']), 1)
        self.assertEqual(result.to_dict()['appended_bars'][0]['start'], str(END))
        for digest in (None, '0'*64):
            with self.assertRaises(a.AcquisitionError):
                d.derive_history(incremental, binding(), current_clock, previous=previous, expected_previous_sha256=digest)
        rows = [minute(stamp) for stamp in range(END-900, end, 60)]; rows[0]['c'] = 100
        altered = history(start=END-900, end=end, raw=history_raw(rows=rows), wall=new_wall, mono=new_mono, identity=204)
        with self.assertRaises(a.AcquisitionError):
            d.derive_history(altered, binding(), current_clock, previous=previous, expected_previous_sha256=previous.sha256)

    def test_no_overlap_or_multi_bar_backlog_cannot_reseed_previous_ema(self):
        previous = d.derive_history(history(), binding(), clock())
        for count in (2, 62):
            end = END+count*900; new_wall = (end+8)*1_000_000; new_mono = MONO+count*900_000_000
            fresh = history(start=end-61*900, end=end, wall=new_wall, mono=new_mono)
            with self.subTest(count=count), self.assertRaises(a.AcquisitionError):
                d.derive_history(fresh, binding(), clock(wall=new_wall+1_000_000, mono=new_mono+1_000_000),
                    previous=previous, expected_previous_sha256=previous.sha256)

    def test_history_increment_original_record_and_raw_ids_bind_previous_exact_bytes(self):
        previous = d.derive_history(history(), binding(), clock())
        end = END+900; new_wall = (end+8)*1_000_000; new_mono = MONO+900_000_000
        current_clock = clock(wall=new_wall+1_000_000, mono=new_mono+1_000_000)
        for identity, raw_ref in [(104, 204), (204, 104), (104, 104)]:
            changed = history(start=END-900, end=end, wall=new_wall, mono=new_mono,
                identity=identity, raw_response_ref=str(UUID(int=raw_ref)))
            with self.subTest(record_id=identity, raw_ref=raw_ref), self.assertRaises(a.AcquisitionError):
                d.derive_history(changed, binding(), current_clock, previous=previous, expected_previous_sha256=previous.sha256)
            # Supplying only previous_history must retain its own original IDs,
            # independently of the optional previous_observation source seam.
            with self.subTest(packet=True, record_id=identity, raw_ref=raw_ref), self.assertRaises(a.AcquisitionError):
                d.derive_observation(price(identity=201, wall=new_wall, mono=new_mono),
                    rpc('getGenesisHash', identity=202, wall=new_wall, mono=new_mono),
                    rpc('getBlockTime', identity=203, rpc_id=2, result=end+6, wall=new_wall, mono=new_mono),
                    binding(), current_clock, observation_id=str(UUID(int=205)), history_capsule=changed,
                    previous_history=previous, expected_previous_history_sha256=previous.sha256)

    def test_unchanged_original_history_bytes_cannot_be_reused_as_next_bar(self):
        original = history(); previous = d.derive_history(original, binding(), clock())
        with self.assertRaises(a.AcquisitionError):
            d.derive_history(original, binding(), clock(), previous=previous, expected_previous_sha256=previous.sha256)

    def test_history_gaps_conflicting_duplicates_scaled_padding_currency_and_unknown_refusal(self):
        base = [minute(stamp) for stamp in range(END-61*900, END, 60)]
        variants = [history_raw(rows=base[1:]), history_raw(rows=base+[minute(base[0]['unix_time'], c=100)]),
            history_raw(rows=base, is_scaled_ui_token=True), history_raw(rows=base, multiplier=2),
            history_raw(rows=base, is_scaled_ui_token=0), history_raw(rows=base, multiplier='1'),
            history_raw(rows=[minute(base[0]['unix_time'], currency='native')]+base[1:]),
            history_raw(rows=[minute(base[0]['unix_time'], o=True)]+base[1:]),
            history_raw(rows=[minute(base[0]['unix_time'], h=98)]+base[1:]),
            history_raw(rows=[minute(base[0]['unix_time'], v=-1)]+base[1:]),
            history_raw(rows=[minute(base[0]['unix_time'], unknown=1)]+base[1:]),
            b'{"success":false,"data":null}', b'{"success":true,"data":{"items":[],"is_scaled_ui_token":false,"padding":true}}']
        for raw in variants:
            with self.subTest(size=len(raw)), self.assertRaises(a.AcquisitionError): d.derive_history(history(raw=raw), binding(), clock())
        good = history(raw=history_raw(rows=list(reversed(base))+[base[0]], multiplier=1))
        self.assertEqual(len(d.derive_history(good, binding(), clock()).to_dict()['minutes']), 915)

    def test_excluded_older_forming_rows_are_validated_before_exclusion(self):
        base = [minute(stamp) for stamp in range(END-61*900, END, 60)]
        good = history(raw=history_raw(rows=[minute(END-61*900-60)]+base+[minute(END)]))
        self.assertEqual(len(d.derive_history(good, binding(), clock()).to_dict()['minutes']), 915)
        for excluded in [minute(END, c=0), minute(END-61*900-60, v=-1), minute(END+60)]:
            with self.assertRaises(a.AcquisitionError):
                d.derive_history(history(raw=history_raw(rows=base+[excluded])), binding(), clock())

    def test_history_exact_volume_sum_ignores_decimal_context(self):
        raw = history_raw().replace(b'"v":3', b'"v":0.000000000000000001').replace(b'"v_usd":301', b'"v_usd":9007199254740993.000000000000000001')
        with localcontext() as context:
            context.prec = 2
            for flag in (InvalidOperation, Inexact, Rounded): context.traps[flag] = True
            result = d.derive_history(history(raw=raw), binding(), clock()).to_dict()
        self.assertEqual(result['bars'][0]['volume'], '0.000000000000000015')
        self.assertEqual(result['bars'][0]['volume_usd'], '135107988821114895.000000000000000015')

    def test_clock_future_receipt_acquisition_timeout_regression_and_boolean_refusal(self):
        original = price()
        for sample in [clock(wall=WALL-3_000_000), clock(mono=MONO-1), clock(wall=WALL+5_000_000, mono=MONO+5_000_000)]:
            with self.assertRaises(a.AcquisitionError): a.assess_record_age(original, binding(), sample)
        with self.assertRaises(a.AcquisitionError): a.assess_record_age(price(elapsed=6_000_000), binding(), clock())
        with self.assertRaises(a.AcquisitionError): a.assess_record_age(price(elapsed=5_000_000), binding(), clock())
        with self.assertRaises(a.AcquisitionError): price(started_wall_us=WALL+1)
        with self.assertRaises(a.AcquisitionError): price(started_monotonic_us=True)
        with self.assertRaises(a.AcquisitionError): replace(clock(), monotonic_us=True)
        with self.assertRaises(a.AcquisitionError): replace(clock(), wall_upper_us=WALL+4_000_000)

    def test_cross_process_monotonic_origin_is_unrelated_and_receipt_never_rebased(self):
        original = price(); first = a.assess_record_age(original, binding(), clock(), source_second=END+6)
        other = str(UUID(int=900)); second_clock = clock(wall=WALL+3_000_000, mono=1, epoch=other)
        second = a.assess_record_age(original, binding(), second_clock, source_second=END+6, previous=first)
        row = second.to_dict()
        self.assertEqual(row['receipt_age_floor_us'], '3000000'); self.assertEqual(row['source_age_floor_us'], '5000000')
        self.assertEqual(row['record_id'], original.to_dict()['record_id']); self.assertEqual(original.to_dict()['received_wall_us'], str(WALL))
        with self.assertRaises(a.AcquisitionError):
            a.assess_record_age(original, binding(), clock(wall=WALL-1, mono=1, epoch=other))
        uncertain = a.assess_record_age(original, binding(), clock(uncertainty=1_000_000))
        with self.assertRaises(a.AcquisitionError):
            a.assess_record_age(original, binding(), clock(wall=WALL+1_500_000, mono=1, epoch=other), previous=uncertain)
        with self.assertRaises(a.AcquisitionError):
            a.assess_record_age(original, binding(), clock(wall=WALL+5_000_000, mono=1, epoch=other), previous=second)
        with self.assertRaises(a.AcquisitionError):
            d.derive_observation(original, rpc('getGenesisHash'), rpc('getBlockTime', identity=103), binding(), second_clock, observation_id=str(UUID(int=105)))

    def test_fresh_packets_carry_repeated_source_age_across_unrelated_process_origins(self):
        previous = observe()
        other = str(UUID(int=900)); current_binding = binding(acquisition_epoch=other)
        wall = WALL+3_000_000; mono = 500_000
        current_clock = clock(wall=wall+1_000_000, mono=mono+1_000_000, epoch=other)
        p = price(expected=current_binding, identity=201, wall=wall, mono=mono)
        g = rpc('getGenesisHash', expected=current_binding, identity=202, wall=wall, mono=mono)
        t = rpc('getBlockTime', expected=current_binding, identity=203, rpc_id=2, wall=wall, mono=mono)
        result = d.derive_observation(p, g, t, current_binding, current_clock,
            observation_id=str(UUID(int=205)), previous_observation=previous,
            expected_previous_observation_sha256=previous.sha256).to_dict()
        self.assertEqual(result['source_age_floor_us'], '6000000')
        self.assertEqual(result['source_age_ceiling_us'], '6000000')
        self.assertEqual(result['record_ages'][0]['receipt_age_floor_us'], '1000000')
        self.assertEqual(result['previous_observation_sha256'], previous.sha256)
        self.assertEqual(previous.to_dict()['source_age_floor_us'], '3000000')
        for claimed_hash in (None, '0'*64):
            with self.assertRaises(a.AcquisitionError):
                d.derive_observation(p, g, t, current_binding, current_clock,
                    observation_id=str(UUID(int=205)), previous_observation=previous,
                    expected_previous_observation_sha256=claimed_hash)

    def test_repeated_block_changed_time_or_regressed_block_source_cannot_reset_age(self):
        previous = observe()
        for block, source in [(348004022, END+6), (348004023, END+7), (348004024, END+5)]:
            p = capsule('jupiter-price-v3', price_raw(block=str(block)), identity=201)
            t = rpc('getBlockTime', slot=block, result=source, identity=203, rpc_id=2)
            with self.subTest(block=block, source=source), self.assertRaises(a.AcquisitionError):
                observe(p=p, t=t, observation_id=str(UUID(int=205)), previous_observation=previous, expected_previous_observation_sha256=previous.sha256)
        p = capsule('jupiter-price-v3', price_raw(block='348004024'), identity=201)
        t = rpc('getBlockTime', slot=348004024, result=END+7, identity=203, rpc_id=2)
        row = observe(p=p, t=t, observation_id=str(UUID(int=205)), previous_observation=previous, expected_previous_observation_sha256=previous.sha256).to_dict()
        self.assertEqual(row['source_age_floor_us'], '2000000')

    def test_previous_original_observation_record_and_blob_identity_cannot_change_bytes(self):
        previous = observe()
        with self.assertRaises(a.AcquisitionError):
            observe(previous_observation=previous, expected_previous_observation_sha256=previous.sha256)
        changed_original = capsule('jupiter-price-v3', price_raw('101'), identity=101)
        with self.assertRaises(a.AcquisitionError):
            observe(p=changed_original, observation_id=str(UUID(int=205)),
                previous_observation=previous, expected_previous_observation_sha256=previous.sha256)
        changed_blob = capsule('jupiter-price-v3', price_raw('101'), identity=201,
            raw_response_ref=str(UUID(int=101)))
        with self.assertRaises(a.AcquisitionError):
            observe(p=changed_blob, observation_id=str(UUID(int=205)),
                previous_observation=previous, expected_previous_observation_sha256=previous.sha256)
        # Exact retained records may be reused while still fresh; no new receipt
        # or record ID is manufactured for them by this pure operation.
        next_row = observe(observation_id=str(UUID(int=205)),
            previous_observation=previous, expected_previous_observation_sha256=previous.sha256).to_dict()
        self.assertEqual(next_row['record_pins'], previous.to_dict()['record_pins'])

    def test_uncertain_cross_epoch_order_and_stale_carried_source_refuse(self):
        old_clock = clock(wall=WALL+1_000_000, mono=MONO+1_000_000, uncertainty=1_000_000)
        previous = d.derive_observation(price(), rpc('getGenesisHash'), rpc('getBlockTime', identity=103), binding(), old_clock,
            observation_id=str(UUID(int=105)))
        other = str(UUID(int=900)); expected = binding(acquisition_epoch=other)
        wall = WALL+1_000_000; mono = 200_000
        p = price(expected=expected, wall=wall, mono=mono, identity=201)
        g = rpc('getGenesisHash', expected=expected, wall=wall, mono=mono, identity=202)
        t = rpc('getBlockTime', expected=expected, wall=wall, mono=mono, identity=203)
        with self.assertRaises(a.AcquisitionError):
            d.derive_observation(p, g, t, expected, clock(wall=WALL+1_500_000, mono=700_000, epoch=other),
                observation_id=str(UUID(int=205)), previous_observation=previous, expected_previous_observation_sha256=previous.sha256)
        # A new HTTP receipt for the same old block is still stale source data.
        wall = WALL+30_000_000; mono = 500_000
        p = price(expected=expected, wall=wall, mono=mono, identity=201)
        g = rpc('getGenesisHash', expected=expected, wall=wall, mono=mono, identity=202)
        t = rpc('getBlockTime', expected=expected, wall=wall, mono=mono, identity=203)
        with self.assertRaises(a.AcquisitionError):
            d.derive_observation(p, g, t, expected, clock(wall=wall+1_000_000, mono=mono+1_000_000, epoch=other),
                observation_id=str(UUID(int=205)), previous_observation=previous, expected_previous_observation_sha256=previous.sha256)

    def test_capsule_json_body_and_history_row_limits_are_enforced(self):
        with self.assertRaises(a.AcquisitionError): a.decode_capsule(b' '*(a.MAX_CAPSULE_BYTES+1), binding())
        for family in a.BODY_LIMITS:
            with self.subTest(family=family), self.assertRaises(a.AcquisitionError):
                capsule(family, b'x'*(a.BODY_LIMITS[family]+1), request=a.public_request('jupiter-price-v3'))
        with self.assertRaises(a.AcquisitionError): a.read_json(b'['*33+b'0'+b']'*33, 4096, numeric=True)
        with self.assertRaises(a.AcquisitionError): a.read_json(b'"\\ud800"', 4096, numeric=True)
        with self.assertRaises(a.AcquisitionError): a.read_json(b'{"x":"\\u0000"}', 4096, numeric=True)
        with self.assertRaises(a.AcquisitionError): a.read_json(b'['+b','.join([b'0']*5001)+b']', 65536, numeric=True)
        with self.assertRaises(a.AcquisitionError):
            d.derive_history(history(raw=history_raw(rows=[minute(END-60)]*5001)), binding(), clock())

    def test_only_pure_imports_and_original_ids_no_clock_env_network_database_or_rng(self):
        modules = [Path(a.__file__), Path(d.__file__)]
        forbidden = {'os', 'socket', 'aiohttp', 'requests', 'httpx', 'random', 'time', 'pickle',
            'subprocess', 'supabase', 'psycopg', 'dotenv', 'config', 'repository', 'jupiter_feed', 'birdeye_candles', 'solana_time'}
        for path in modules:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [alias.name for alias in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                    self.assertTrue(all(not set(name.split('.')) & forbidden for name in names))
        code = '''import builtins, socket, time, random, os
from unittest.mock import patch
original=builtins.__import__
def guarded(name,*args,**kwargs):
 if name in ('dotenv','vonneumann.config') or name.startswith(('vonneumann.db','aiohttp','requests','psycopg','supabase')): raise AssertionError('private/resource import')
 return original(name,*args,**kwargs)
with patch.object(builtins,'__import__',guarded), patch.object(socket.socket,'connect',side_effect=AssertionError('network')), patch.object(time,'time',side_effect=AssertionError('clock')), patch.object(time,'monotonic',side_effect=AssertionError('clock')), patch.object(random,'Random',side_effect=AssertionError('rng')):
 from vonneumann.market import provider_acquisition_v3, provider_derivation_v3
 assert provider_acquisition_v3.POLICY_SHA256
'''
        env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
            'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
