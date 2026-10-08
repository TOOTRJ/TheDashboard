"""Independent v5 source admission over raw provider bytes, without network I/O."""
from __future__ import annotations

from copy import copy, deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import random
import unittest
from unittest.mock import patch
from uuid import UUID

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_exact_rehearsal import ALGORITHMS, OWNER, RUN, WORKER

with deny_network():
    from vonneumann.market.provider_evidence import ProviderDocument
    from vonneumann.market.exact_records import parse_price_record, parse_candle_records
    from vonneumann.market.jupiter_feed import PriceCapture
    from vonneumann.market.feed import QuoteEvidence
    from vonneumann.market import provider_contract as source
    from vonneumann.core import exact_lifecycle as kernel
    from vonneumann.core import provider_lifecycle as life
    from vonneumann.core.decision_inputs import DecisionInputs
    from vonneumann.db.command_protocol import PreparedCommand, canonical_json
    from vonneumann.db import provider_protocol


MINT = 'So11111111111111111111111111111111111111112'
OTHER_MINT = 'JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN'
EPOCH = str(UUID(int=77001))
END = (1_790_800_000 // 900) * 900
WALL = END + 10
MONO = 1001.0


def raw_capture(*, price='100', block=100, source_second=None, wall=None, mono=None,
                mint=MINT, decimals=9, asset='SOL/USDC', age_floor=None):
    wall = WALL - 1 if wall is None else wall
    mono = MONO - 1 if mono is None else mono
    source_second = WALL - 2 if source_second is None else source_second
    raw = ('{' + json.dumps(mint) + ':{"usdPrice":' + price + ',"blockId":'
           + str(block) + ',"decimals":' + ('null' if decimals is None else str(decimals)) + '}}').encode()
    document = ProviderDocument.capture('jupiter-price-v3', {'ids': mint}, raw, wall, mono)
    record = parse_price_record(document, asset=asset, mint=mint)
    evidence = QuoteEvidence(source_slot=block, received_at=wall, received_monotonic=mono,
                             provider='jupiter-price-v3', quote_currency='USD',
                             source_age_at_receipt=age_floor)
    return PriceCapture(record, source_second, evidence)


def raw_minutes(*, end=END, count=915, close='100', closes=None, wall=None, mono=None,
                scaled=False, multiplier=None, mint=MINT):
    """Every number below originates in a literal provider response, not a float."""
    wall = WALL - 1 if wall is None else wall
    mono = MONO - 1 if mono is None else mono
    start = end - count * 60
    rows = []
    for index in range(count):
        value = close if closes is None else closes[index]
        rows.append('{"unix_time":' + str(start + index * 60) + ',"address":'
            + json.dumps(mint) + ',"type":"1m","currency":"usd","o":' + value
            + ',"h":' + value + ',"l":' + value + ',"c":' + value
            + ',"v":1,"v_usd":' + value + '}')
    body = ('{"success":true,"data":{"is_scaled_ui_token":'
            + ('true' if scaled else 'false')
            + ('' if multiplier is None else ',"multiplier":' + multiplier)
            + ',"items":[' + ','.join(rows) + ']}}').encode()
    parameters = {'address': mint, 'type': '1m', 'mode': 'range', 'time_from': start,
        'time_to': end, 'currency': 'usd', 'chart_type': 'price',
        'ui_amount_mode': 'raw', 'padding': 'false'}
    document = ProviderDocument.capture('birdeye-ohlcv-v3', parameters, body, wall, mono)
    return parse_candle_records(document, asset='SOL/USDC', mint=mint)


def state_source(frame=None, bars=None):
    if bars is None:
        bars = source.derive_bars(seed_bundle())
    return {'version': 1, 'epoch': EPOCH, 'quote_sequence': 0 if frame is None else frame['sequence'],
            'last_quote': deepcopy(frame), 'bars': deepcopy(list(bars))}


def source_inputs(event_second, *, wall=None, mono=MONO, generation=0, serial=0):
    wall = event_second if wall is None else wall
    return DecisionInputs(datetime.fromtimestamp(event_second, timezone.utc),
        datetime.fromtimestamp(wall, timezone.utc), float(mono),
        tuple(str(UUID(int=9_000_000 + serial * 100 + index)) for index in range(9)),
        tuple((generation, f'Provider-{generation}-{serial}-{index}') for index in range(8)))


def seed_bundle(*, close='100', last_close=None):
    closes = [close] * 915
    if last_close is not None:
        closes[-15:] = [last_close] * 15
    return source.build_history(raw_minutes(closes=closes), prior_bars=[], seed=True,
        wall_us=WALL * 1_000_000, monotonic_us=int(MONO * 1_000_000))


class ProviderSourceContractTests(OfflineTestMixin, unittest.TestCase):
    def frame(self, capture=None, prior=None, **clocks):
        return source.make_frame(raw_capture() if capture is None else capture,
            prior_source=state_source() if prior is None else prior, epoch=EPOCH,
            wall_now=clocks.get('wall', WALL), monotonic_now=clocks.get('mono', MONO))

    def test_policy_is_pinned_explicit_usd_and_detached(self):
        policy = source.source_policy(EPOCH)
        self.assertEqual((policy['mint'], policy['asset'], policy['denomination']), (MINT, 'SOL/USD', 'USD'))
        self.assertEqual(policy['evidence_trust'], 'worker-parsed-records-and-manifests-v1')
        self.assertEqual(policy['source_time_policy'], 'jupiter-block-id-as-slot-estimated-time-v1')
        policy['mint'] = OTHER_MINT
        self.assertEqual(source.source_policy(EPOCH)['mint'], MINT)
        for epoch in (None, '', EPOCH.upper().replace('0000', 'FFFF', 1), True):
            with self.subTest(epoch=epoch), self.assertRaises(source.ProviderSourceError):
                source.source_policy(epoch)

    def test_microsecond_conversion_uses_original_float_ratio_and_direction(self):
        for value in (0, 1, 0.1, 1234.0000001, 1234.9999999):
            exact = Fraction(value) * 1_000_000
            self.assertEqual(source.clock_us(value), exact.numerator // exact.denominator)
            self.assertEqual(source.clock_us(value, upper=True), -(-exact.numerator // exact.denominator))
        for value in (True, -1, float('nan'), float('inf'), '1', 10**20):
            with self.subTest(value=value), self.assertRaises(source.ProviderSourceError):
                source.clock_us(value)

    def test_wire_manifest_replaces_float_clocks_and_preserves_request_identity(self):
        capture = raw_capture()
        manifest = source.document_wire(capture.record.document)
        self.assertNotIn('received_at', manifest)
        self.assertNotIn('received_monotonic', manifest)
        self.assertEqual(manifest['received_wall_us'], (WALL - 1) * 1_000_000)
        self.assertEqual(manifest['request_sha256'], hashlib.sha256(canonical_json(manifest['request'])).hexdigest())
        self.assertNotIn('raw_body', manifest)
        manifest['request']['parameters']['ids'] = OTHER_MINT
        self.assertEqual(capture.record.document.parameters['ids'], MINT)

    def test_quote_preserves_eighteen_places_without_legacy_float_view(self):
        capture = raw_capture(price='1.000000000000000001')
        with patch.object(PriceCapture, 'as_tick', side_effect=AssertionError('legacy float path')):
            frame = self.frame(capture)
        self.assertEqual(frame['quote']['price'], '1.000000000000000001')
        self.assertEqual(frame['decision_second'], WALL)
        self.assertEqual(frame['sequence'], 1)
        for capture in (raw_capture(price='1.0000000000000000001'),
                        raw_capture(mint=OTHER_MINT), raw_capture(decimals=8), raw_capture(decimals=None)):
            with self.subTest(record=capture.record), self.assertRaises(source.ProviderSourceError):
                self.frame(capture)

    def test_increasing_block_refs_can_share_the_estimated_source_second(self):
        first = self.frame()
        second = self.frame(raw_capture(block=101, wall=WALL, mono=MONO),
            state_source(first), wall=WALL + 1, mono=MONO + 1)
        self.assertEqual(second['quote']['estimated_source_second'], first['quote']['estimated_source_second'])
        self.assertEqual(second['sequence'], 2)
        self.assertEqual(second['decision_second'], first['decision_second'] + 1)

    def test_ceil_microseconds_cannot_manufacture_a_future_decision_second(self):
        actual = math.nextafter(float(WALL), -math.inf)
        self.assertEqual(source.clock_us(actual, upper=True), WALL * 1_000_000)
        frame = self.frame(raw_capture(wall=WALL - 2, mono=MONO - 1,
                                      source_second=WALL - 3), wall=actual)
        self.assertEqual(frame['decision_second'], WALL - 1)

    def test_fractional_receipt_requires_the_next_actual_second(self):
        capture = raw_capture(wall=WALL - .25, mono=MONO - .25)
        with self.assertRaises(source.ProviderDeferred):
            self.frame(capture, wall=WALL - .1, mono=MONO - .1)
        accepted = self.frame(capture, wall=WALL, mono=MONO)
        self.assertEqual(accepted['decision_second'], WALL)

    def test_same_source_or_same_real_second_defers_without_mutating_watermarks(self):
        first = self.frame()
        prior = state_source(first)
        expected = deepcopy(prior)
        for capture, wall, mono in ((raw_capture(wall=WALL, mono=MONO), WALL + 1, MONO + 1),
                (raw_capture(block=101, wall=WALL - .5, mono=MONO - .5), WALL + .2, MONO + .2)):
            with self.subTest(block=capture.record.block_id), self.assertRaises(source.ProviderDeferred):
                self.frame(capture, prior, wall=wall, mono=mono)
        self.assertEqual(prior, expected)

    def test_lower_or_conflicting_block_and_regressing_estimate_reject(self):
        first = self.frame()
        for capture in (raw_capture(block=99), raw_capture(price='100.000000000000000001'),
                        raw_capture(block=101, source_second=WALL - 3)):
            with self.subTest(record=capture.record), self.assertRaises(source.ProviderSourceError) as caught:
                self.frame(capture, state_source(first), wall=WALL + 1, mono=MONO + 1)
            self.assertNotIsInstance(caught.exception, source.ProviderDeferred)

    def test_duplicate_source_deferral_cannot_hide_staleness_or_clock_regression(self):
        prior = state_source(self.frame())
        cases = ((raw_capture(wall=WALL + 28, mono=MONO + 28), WALL + 29, MONO + 29),
                 (raw_capture(wall=WALL, mono=MONO), WALL + 1, MONO - 2),
                 (raw_capture(wall=WALL, mono=MONO), WALL + 5, MONO + 5))
        for capture, wall, mono in cases:
            with self.subTest(wall=wall), self.assertRaises(source.ProviderSourceError) as caught:
                self.frame(capture, prior, wall=wall, mono=mono)
            self.assertNotIsInstance(caught.exception, source.ProviderDeferred)

    def test_fresh_unchanged_receipt_defers_after_installed_receipt_is_consumed(self):
        prior = state_source(self.frame())
        with self.assertRaises(source.ProviderDeferred):
            self.frame(raw_capture(wall=WALL + 7, mono=MONO + 7), prior,
                       wall=WALL + 7, mono=MONO + 7)

    def test_later_block_carries_conservative_age_floor_across_unequal_clock_elapsed(self):
        first = self.frame(raw_capture(age_floor=20.0))
        prior = state_source(first)
        second = self.frame(raw_capture(block=101, wall=WALL, mono=MONO + 1), prior,
                            wall=WALL + 1, mono=MONO + 2)
        self.assertEqual(second['quote']['source_age_floor_us'], 22_000_000)
        weakened = deepcopy(second);weakened['quote']['source_age_floor_us'] = 0
        with self.assertRaises(source.ProviderSourceError):
            source.validate_frame(weakened, prior_source=prior, epoch=EPOCH)

    def test_builder_rederives_price_and_candle_values_from_the_original_document(self):
        original = raw_capture()
        forged_record = copy(original.record)
        object.__setattr__(forged_record, 'price', '999')
        forged = PriceCapture(forged_record, original.source_timestamp, original.evidence)
        with self.assertRaises(source.ProviderSourceError):source.quote_wire(forged)
        records = list(raw_minutes())
        changed = copy(records[0]);object.__setattr__(changed, 'close', '999')
        records[0] = changed
        with self.assertRaises(source.ProviderSourceError):
            source.build_history(records, prior_bars=[], seed=True,
                wall_us=WALL * 1_000_000, monotonic_us=int(MONO * 1_000_000))

    def test_receipt_expiry_is_exclusive_and_source_age_limit_inclusive(self):
        capture = raw_capture(wall=WALL - 4, mono=MONO - 4, source_second=WALL - 30)
        frame = self.frame(capture)
        source.check_frame(frame, wall_us=WALL * 1_000_000, monotonic_us=int(MONO * 1_000_000))
        for wall_us, mono_us in (((WALL + 1) * 1_000_000, int((MONO + 1) * 1_000_000)),
                                (WALL * 1_000_000 + 1, int(MONO * 1_000_000))):
            with self.subTest(wall=wall_us), self.assertRaises(source.ProviderSourceError):
                source.check_frame(frame, wall_us=wall_us, monotonic_us=mono_us)

    def test_seed_has_exactly_61_bars_and_deduplicated_current_documents(self):
        bundle = seed_bundle(last_close='1.000000000000000001')
        self.assertTrue(bundle['unscaled'])
        self.assertEqual(len(bundle['minutes']), 915)
        self.assertEqual(len(bundle['documents']), 1)
        bars = source.derive_bars(bundle)
        self.assertEqual(len(bars), 61)
        self.assertEqual(bars[-1][:2], [END, '1.000000000000000001'])
        self.assertEqual(bars[-1][2], hashlib.sha256(canonical_json(
            [[row[0], row[1]] for row in bundle['minutes'][-15:]])).hexdigest())
        self.assertGreater(bundle['documents'][0]['received_wall_us'], END * 1_000_000)

    def test_seed_rejects_gap_scaled_other_mint_grid_and_stale_receipt(self):
        good = raw_minutes()
        bad = (good[:-1], good[:17] + good[18:], raw_minutes(scaled=True),
               raw_minutes(multiplier='2'), raw_minutes(mint=OTHER_MINT),
               raw_minutes(close='1.0000000000000000001'),
               raw_minutes(wall=WALL - 6, mono=MONO - 6))
        for records in bad:
            with self.subTest(length=len(records)), self.assertRaises(source.ProviderSourceError):
                source.build_history(records, prior_bars=[], seed=True,
                    wall_us=WALL * 1_000_000, monotonic_us=int(MONO * 1_000_000))

    def test_history_wire_tampering_fails_before_state_admission(self):
        bundle = seed_bundle()
        mutations = [lambda b:b.update(unscaled=False),
            lambda b:b['minutes'][2].__setitem__(0, b['minutes'][1][0]),
            lambda b:b['minutes'][0].__setitem__(2, 99),
            lambda b:b['documents'][0]['request']['parameters'].update(currency='native'),
            lambda b:b['documents'][0].update(request_sha256='0' * 64),
            lambda b:b['documents'].append(deepcopy(b['documents'][0])),
            lambda b:b['documents'][0].update(received_wall_us=(WALL + 1) * 1_000_000)]
        for mutation in mutations:
            bad = deepcopy(bundle);mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises(source.ProviderSourceError):
                source.validate_history(bad, prior_bars=[], seed=True,
                    wall_us=WALL * 1_000_000, monotonic_us=int(MONO * 1_000_000))

    def test_history_fingerprint_ignores_new_document_receipt_but_detects_hidden_revision(self):
        bars = source.derive_bars(seed_bundle())
        later = WALL + 1
        same = raw_minutes(wall=later - 1, mono=MONO)
        self.assertIsNone(source.build_history(same, prior_bars=bars, seed=False,
            wall_us=later * 1_000_000, monotonic_us=int((MONO + 1) * 1_000_000)))
        values = ['100'] * 915;values[4] = '100.000000000000000001'
        revised = raw_minutes(closes=values, wall=later - 1, mono=MONO)
        with self.assertRaises(source.ProviderSourceError):
            source.build_history(revised, prior_bars=bars, seed=False,
                wall_us=later * 1_000_000, monotonic_us=int((MONO + 1) * 1_000_000))

    def test_increment_requires_next_complete_bar_and_rejects_skipped_history(self):
        bars = source.derive_bars(seed_bundle())
        for offset, expected in ((900, True), (1800, False)):
            records = raw_minutes(end=END + offset, count=15, close='120',
                wall=WALL + offset - 1, mono=MONO + offset - 1)
            kwargs = dict(prior_bars=bars, seed=False, wall_us=(WALL + offset) * 1_000_000,
                          monotonic_us=int((MONO + offset) * 1_000_000))
            if expected:
                bundle = source.build_history(records, **kwargs)
                self.assertEqual(source.derive_bars(bundle)[-1][:2], [END + 900, '120'])
            else:
                with self.assertRaises(source.ProviderSourceError):source.build_history(records, **kwargs)


class ProviderLifecycleContractTests(OfflineTestMixin, unittest.TestCase):
    def config(self, algorithm='genetic_algorithm'):
        return life.ProviderLifecycleConfig(kernel.ExactLifecycleConfig(algorithm, OWNER, RUN,
            asset='SOL/USD'), EPOCH)

    def bridge(self, candidate):
        before = candidate.transition['before']
        command = PreparedCommand.batch(OWNER, RUN, WORKER, 1,
            1 if before is None else before['revision'], candidate.operations,
            command_id=str(UUID(int=80_000 + candidate.state.revision)), version=5,
            transition=candidate.transition)
        self.assertEqual(command.expected_request['payload']['version'], 5)
        self.assertEqual(command.expected_request['payload']['transition'], candidate.transition)
        return command

    def test_seed_initializes_only_history_and_preserves_original_provider_envelope(self):
        config = self.config()
        bundle = seed_bundle(last_close='80')
        candidate = life.bootstrap(config, bundle, source_inputs(WALL))
        state = candidate.state.to_dict()
        self.assertEqual(state['engine']['ema']['count'], 61)
        self.assertEqual(state['engine']['ema']['last_end'], END)
        self.assertEqual(state['engine']['cohort']['phase'], 'warming')
        self.assertEqual(state['positions'], [])
        self.assertEqual(state['source']['quote_sequence'], 0)
        self.assertEqual(len(candidate.transition['events']), 9)
        self.assertEqual(candidate.transition['evidence']['source']['phase'], 'bootstrap')
        projected = provider_protocol.model_transition(candidate.transition)
        self.assertNotIn('source', projected['after'])
        self.assertNotIn('source', projected['evidence'])
        self.assertEqual(projected['after']['engine']['ema']['count'], 0)
        self.assertEqual(candidate.state.to_dict()['engine']['ema']['count'], 61)
        self.bridge(candidate)

    def test_provider_config_cannot_be_omitted_downgraded_or_change_denomination(self):
        config = self.config()
        original = config.run_configuration()
        created = PreparedCommand.create(OWNER, RUN, WORKER, original, config.initial_cash,
                                         command_id=str(UUID(int=81000)))
        self.assertEqual(created.expected_request['config'], original)
        for change in ('omit', 'epoch', 'currency', 'version'):
            value = deepcopy(original)
            if change == 'omit':value.pop('source_policy')
            elif change == 'epoch':value['source_policy']['epoch'] = 'unbound'
            elif change == 'currency':value['source_policy']['denomination'] = 'USDC'
            else:value['durability_contract_version'] = 4
            with self.subTest(change=change), self.assertRaises(ValueError):
                PreparedCommand.create(OWNER, RUN, WORKER, value, config.initial_cash,
                                       command_id=str(UUID(int=81001)))

    def test_projection_does_not_let_tampered_seed_ema_or_source_watermarks_pass(self):
        candidate = life.bootstrap(self.config(), seed_bundle(), source_inputs(WALL))
        mutations = [lambda t:t['after']['source']['bars'][-1].__setitem__(1, '999'),
            lambda t:t['after']['engine']['ema']['values'].update({'60': '0x1.0p+0'}),
            lambda t:t['evidence']['source'].update(history=None),
            lambda t:t['evidence']['source'].update(wall_us=(WALL - 5) * 1_000_000)]
        original = candidate.transition
        for mutation in mutations:
            changed = deepcopy(original);mutation(changed)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                PreparedCommand.batch(OWNER, RUN, WORKER, 1, 1, candidate.operations,
                    command_id=str(UUID(int=81002)), version=5, transition=changed)
        self.assertEqual(candidate.transition, original)
        with self.assertRaises(ValueError):
            PreparedCommand.batch(OWNER, RUN, WORKER, 1, 1, candidate.operations,
                command_id=str(UUID(int=81003)), version=4, transition=original)

    def test_all_four_solvers_trade_one_complete_current_time_window(self):
        random_before = random.getstate()
        for algorithm in ALGORITHMS:
            with self.subTest(algorithm=algorithm):
                candidate = life.bootstrap(self.config(algorithm), seed_bundle(last_close='80'),
                                           source_inputs(WALL))
                for serial, offset in enumerate((1, 900, 901, 1800, 1801, 2700, 2701, 3601), 1):
                    wall, mono = WALL + offset, MONO + offset
                    frame = source.make_frame(raw_capture(block=100 + serial,
                        source_second=wall - 2, wall=wall - 1, mono=mono - 1),
                        prior_source=candidate.state.to_dict()['source'], epoch=EPOCH,
                        wall_now=wall, monotonic_now=mono)
                    protected = life.prepare_protective(candidate.state, frame,
                        source_inputs(wall, mono=mono, generation=1, serial=serial * 2))
                    has_bar = offset in (900, 1800, 2700, 3601)
                    history = None if not has_bar else source.build_history(raw_minutes(
                        end=END + (offset // 900) * 900, count=15,
                        close='120' if offset == 900 else '80', wall=wall - 1, mono=mono - 1),
                        prior_bars=protected.state.to_dict()['source']['bars'], seed=False,
                        wall_us=wall * 1_000_000, monotonic_us=int(mono * 1_000_000))
                    candidate = life.prepare_decision(protected.state, frame, history,
                        source_inputs(wall, mono=mono, generation=1, serial=serial * 2 + 1))
                    self.bridge(protected);self.bridge(candidate)
                    self.assertEqual(candidate.state.to_dict()['source']['quote_sequence'], serial)
                    if offset == 900:self.assertEqual(candidate.state.to_dict()['positions'], [])
                    if offset == 901:self.assertEqual(len(candidate.state.to_dict()['positions']), 8)
                self.assertEqual(len(candidate.state.to_dict()['positions']), 8)
                self.assertTrue(all(position['closed'] for position in candidate.state.to_dict()['positions']))
                self.assertEqual(candidate.state.to_dict()['engine']['generation'], 1)
                self.assertEqual(len(candidate.state.to_dict()['accounts']), 16)
        self.assertEqual(random.getstate(), random_before)
