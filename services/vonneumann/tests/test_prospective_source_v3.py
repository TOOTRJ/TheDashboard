"""Literal original records and independent trust inputs; no native acceptance."""
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import localcontext, Inexact, Rounded
import hashlib
from pathlib import Path
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from vonneumann.market import provider_acquisition_v3 as a, provider_derivation_v3 as d
    from vonneumann.market import prospective_source_v3 as s

OWNER, RUN, MARKET, PROCESS, ISSUER, PRINCIPAL = [str(UUID(int=value)) for value in (11, 12, 13, 14, 15, 16)]
START = 1_800_000_000
END = START+915*60
PACKAGE = 'a'*64
RECEIPT = 'b'*64


def mark(index, *, accepted=None, available=None, price='100.123456789012345678',
         block=None, source_second=None, epoch=PROCESS, sequence=None, identity=None,
         receipt_age=300_000, reference_changes=None, observation_monotonic_us=None):
    accepted = (START+index*60+50)*1_000_000 if accepted is None else accepted
    available = accepted+100_000 if available is None else available
    wall, mono = accepted-receipt_age, (index+1)*60_000_000+1_000_000
    source_second = wall//1_000_000-2 if source_second is None else source_second
    block = 348004023+index if block is None else block
    base = 1000+index*10 if identity is None else identity
    binding = a.IssuerBinding(OWNER, RUN, MARKET, epoch, ISSUER,
        (('jupiter-price-v3', str(UUID(int=21))), ('solana-rpc', str(UUID(int=22)))))
    def capture(family, raw, request, offset):
        return a.capture_capsule(binding, record_id=str(UUID(int=base+offset)),
            provider_family=family, request=request, raw_body=raw, http_status=200,
            started_wall_us=wall-100_000, received_wall_us=wall,
            started_monotonic_us=mono-100_000, received_monotonic_us=mono)
    p = capture('jupiter-price-v3', ('{"'+a.MINT+'":{"usdPrice":'+price+
        ',"blockId":'+str(block)+',"decimals":9}}').encode(), a.public_request('jupiter-price-v3'), 1)
    g = capture('solana-rpc', a.canonical({'jsonrpc': '2.0', 'id': 1, 'result': a.GENESIS}),
        a.public_request('solana-rpc', rpc_method='getGenesisHash', rpc_id=1), 2)
    t = capture('solana-rpc', a.canonical({'jsonrpc': '2.0', 'id': 2, 'result': source_second}),
        a.public_request('solana-rpc', rpc_method='getBlockTime', rpc_id=2, slot=block), 3)
    clock = a.ClockBound(OWNER, RUN, MARKET, epoch, accepted-100_000,
        accepted-100_000, mono+receipt_age-100_000 if observation_monotonic_us is None
            else observation_monotonic_us)
    observed = d.derive_observation(p, g, t, binding, clock, observation_id=str(UUID(int=base+4)))
    ref = s.RecordReference(OWNER, RUN, MARKET, epoch, str(UUID(int=base+4)), observed.sha256,
        str(UUID(int=base+5)), index+1 if sequence is None else sequence,
        accepted, available, PRINCIPAL, PACKAGE, RECEIPT)
    if reference_changes: ref = replace(ref, **reference_changes)
    return s.capture_mark(observed, ref)


def seal(marks, *, start=START, end=END, **changes):
    ref = s.SealReference(OWNER, RUN, MARKET, str(UUID(int=100_000)), s.record_set_digest(marks),
        max(int(item.to_dict()['reference']['ingest_sequence']) for item in marks),
        start, end, end*1_000_000+s.COMPLETION_MARGIN_US, PACKAGE)
    if changes: ref = replace(ref, **changes)
    return s.freeze_records(marks, ref)


def replaced_mark(original, **changes):
    value = original.to_dict(); value.update(changes)
    result = object.__new__(s.SourceMark); object.__setattr__(result, '_wire', a.canonical(value)); return result


class ProspectiveSourceV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with deny_network():
            cls.marks = tuple(mark(index) for index in range(915))
            cls.advanced_marks = tuple(mark(index, block=348004024+index) for index in range(1, 915))
            cls.frozen = seal(cls.marks)
            cls.history = s.derive_sampled_history(cls.frozen)

    def setUp(self):
        self.network = deny_network(); self.network.__enter__()
        self.addCleanup(self.network.__exit__, None, None, None)

    def test_915_actual_original_minute_anchors_make_61_close_only_bars(self):
        row = self.history.to_dict()
        self.assertEqual(row['range'], {'start': str(START), 'end': str(END),
            'observed_minutes': '915', 'complete_bars': '61'})
        self.assertEqual(len(row['minutes']), 915); self.assertEqual(len(row['bars']), 61)
        for index, bar in enumerate(row['bars']):
            self.assertEqual(bar['close'], '100.123456789012345678')
            self.assertEqual(bar['close_offset_us'], '9900000')
            self.assertEqual(len(bar['minute_anchor_pins']), 15)
            group = row['minutes'][index*15:index*15+15]
            self.assertEqual(bar['minute_anchors_sha256'], hashlib.sha256(a.canonical(group)).hexdigest())
            self.assertFalse({'open', 'high', 'low', 'volume', 'volume_usd'} & set(bar))
            self.assertEqual(bar['close_source_age_at_acceptance_ceiling_us'], '3000000')
        self.assertFalse(self.history.native_admission); self.assertFalse(self.history.running_authority)
        for key in ('provider_attested', 'native_admission', 'historical_ohlcv', 'volume_available',
                    'executable_quote', 'current_freshness', 'complete_native_ledger_verified', 'running_authority'):
            self.assertIs(row[key], False)

    def test_latest_eligible_native_acceptance_wins_independent_of_input_order(self):
        extra = mark(0, accepted=(START+55)*1_000_000, price='101', block=348004024,
            sequence=2, identity=100_001)
        shifted = (self.marks[0], extra)+tuple(replaced_mark(item,
            reference={**item.to_dict()['reference'], 'ingest_sequence': str(index+3)})
            for index, item in enumerate(self.advanced_marks))
        one = s.derive_sampled_history(seal(shifted))
        two = s.derive_sampled_history(seal(tuple(reversed(shifted))))
        self.assertEqual(one.wire, two.wire)
        self.assertEqual(one.to_dict()['minutes'][0]['price_decimal'], '101')

    def test_same_native_acceptance_microsecond_uses_unique_ingest_sequence(self):
        original = self.marks[0]; ref = original.to_dict()['reference']
        extra = mark(0, accepted=int(ref['accepted_at_us']), price='100.123456789012345678',
            sequence=2, identity=100_002)
        marks = (original, extra)+tuple(replaced_mark(item,
            reference={**item.to_dict()['reference'], 'ingest_sequence': str(index+3)})
            for index, item in enumerate(self.marks[1:]))
        history = s.derive_sampled_history(seal(marks))
        self.assertEqual(history.to_dict()['minutes'][0]['observation_id'], extra.to_dict()['reference']['observation_id'])

    def test_missing_minute_refuses_no_zero_padding_or_interpolation(self):
        with self.assertRaises(a.AcquisitionError):
            s.derive_sampled_history(seal(self.marks[:100]+self.marks[101:]))

    def test_native_accepted_before_end_but_readback_late_cannot_fill_minute(self):
        late = mark(0, accepted=(START+59)*1_000_000,
            available=(START+60)*1_000_000+1)
        with self.assertRaises(a.AcquisitionError):
            s.derive_sampled_history(seal((late,)+self.marks[1:]))

    def test_late_readback_does_not_replace_an_earlier_causally_available_anchor(self):
        late = mark(0, accepted=(START+59)*1_000_000,
            available=(START+60)*1_000_000+1, block=348004024, sequence=2, identity=100_003)
        marks = (self.marks[0], late)+tuple(replaced_mark(item,
            reference={**item.to_dict()['reference'], 'ingest_sequence': str(index+3)})
            for index, item in enumerate(self.advanced_marks))
        row = s.derive_sampled_history(seal(marks)).to_dict()
        self.assertEqual(row['minutes'][0]['observation_id'], self.marks[0].to_dict()['reference']['observation_id'])

    def test_end_boundary_readback_is_eligible_with_zero_sample_offset(self):
        edge = mark(14, accepted=(START+899)*1_000_000, available=(START+900)*1_000_000)
        marks = self.marks[:14]+(edge,)+self.marks[15:]
        row = s.derive_sampled_history(seal(marks)).to_dict()
        self.assertEqual(row['bars'][0]['close_offset_us'], '0')

    def test_first_instant_boundary_is_not_labeled_a_subminute_close(self):
        edge = mark(14, accepted=(START+840)*1_000_000, available=(START+840)*1_000_000)
        with self.assertRaises(a.AcquisitionError):
            s.derive_sampled_history(seal(self.marks[:14]+(edge,)+self.marks[15:]))

    def test_actual_native_acceptance_assigns_minute_not_earlier_price_receipt(self):
        changed = mark(0, accepted=(START+60)*1_000_000, receipt_age=1_000_000)
        with self.assertRaises(a.AcquisitionError):
            s.derive_sampled_history(seal((changed,)+self.marks[1:]))

    def test_completion_margin_boundary_and_future_inventory_refuse(self):
        with self.assertRaises(a.AcquisitionError): seal(self.marks, sealed_at_us=END*1_000_000+4_999_999)
        self.assertEqual(self.frozen._reference.sealed_at_us, END*1_000_000+5_000_000)
        with self.assertRaises(a.AcquisitionError): seal(self.marks, through_ingest_sequence=914)

    def test_separately_bound_recorder_package_and_source_policy_cannot_drift(self):
        with self.assertRaises(a.AcquisitionError): seal(self.marks, recorder_package_sha256='c'*64)
        changed = replaced_mark(self.marks[-1], reference={**self.marks[-1].to_dict()['reference'],
            'recorder_package_sha256': 'c'*64})
        with self.assertRaises(a.AcquisitionError): seal(self.marks[:-1]+(changed,))

    def test_separate_frozen_inventory_digest_cannot_accept_added_or_changed_records(self):
        with self.assertRaises(a.AcquisitionError): s.freeze_records(self.marks[:-1], self.frozen._reference)
        changed = replaced_mark(self.marks[0], price_decimal='101')
        with self.assertRaises(a.AcquisitionError): s.freeze_records((changed,)+self.marks[1:], self.frozen._reference)

    def test_duplicate_native_sequence_observation_and_admission_id_refuse(self):
        base = self.marks[0].to_dict()['reference']
        for key in ('ingest_sequence', 'observation_id', 'record_admission_id'):
            with self.subTest(key=key), self.assertRaises(a.AcquisitionError):
                changed = replaced_mark(self.marks[1],
                    reference={**self.marks[1].to_dict()['reference'], key: base[key]})
                seal((self.marks[0], changed)+self.marks[2:])

    def test_original_raw_uuid_and_record_uuid_cannot_change_hash(self):
        first = self.marks[0].to_dict()['record_pins'][0]
        for key in ('record_id', 'raw_response_ref'):
            with self.subTest(key=key), self.assertRaises(a.AcquisitionError):
                pins = self.marks[1].to_dict()['record_pins']; pins[0][key] = first[key]
                seal((self.marks[0], replaced_mark(self.marks[1], record_pins=pins))+self.marks[2:])

    def test_regressed_native_clock_block_source_and_same_block_changed_price_refuse(self):
        prior = self.marks[0].to_dict()
        changes = [{'reference': {**self.marks[1].to_dict()['reference'],
            'accepted_at_us': str(int(prior['reference']['accepted_at_us'])-1)}},
            {'block_ref': str(int(prior['block_ref'])-1)},
            {'estimated_source_second': str(int(prior['estimated_source_second'])-1)},
            {'block_ref': prior['block_ref'], 'estimated_source_second': prior['estimated_source_second'], 'price_decimal': '102'}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(a.AcquisitionError):
                seal((self.marks[0], replaced_mark(self.marks[1], **change))+self.marks[2:])

    def test_receipt_and_source_freshness_at_original_acceptance_not_15_hours_later(self):
        accepted = (START+50)*1_000_000
        good = mark(0, accepted=accepted, available=accepted+4_699_999)
        self.assertEqual(good.to_dict()['reference']['available_at_upper_us'], str(accepted+4_699_999))
        with self.assertRaises(a.AcquisitionError): mark(0, accepted=accepted, available=accepted+4_700_000)
        with self.assertRaises(a.AcquisitionError): mark(0, accepted=accepted,
            reference_changes={'accepted_at_us': accepted+28_000_001, 'available_at_upper_us': accepted+28_000_001})
        self.assertFalse(self.history.to_dict()['current_freshness'])

    def test_wrong_owner_run_epoch_digest_and_future_reference_refuse(self):
        for changes in ({'owner_id': str(UUID(int=999))}, {'run_id': str(UUID(int=999))},
                {'acquisition_epoch': str(UUID(int=999))}, {'observation_sha256': 'c'*64},
                {'accepted_at_us': (START+45)*1_000_000}):
            with self.subTest(changes=changes), self.assertRaises(a.AcquisitionError): mark(0, reference_changes=changes)

    def test_public_mark_validation_requires_independent_original_digest(self):
        original = self.marks[0]
        self.assertIs(s.validate_mark(original, expected_mark_sha256=original.sha256), original)
        with self.assertRaises(a.AcquisitionError): s.validate_mark(original, expected_mark_sha256='c'*64)
        with self.assertRaises(a.AcquisitionError): s.validate_mark(original.to_dict(), expected_mark_sha256=original.sha256)

    def test_current_action_rechecks_original_receipts_monotonic_age_and_epoch_without_rebase(self):
        original = self.marks[0]; value = original.to_dict()
        old = value['original_observation_clock']; received = int(value['record_pins'][0]['received_wall_us'])
        target = ((received+999_999)//1_000_000+1)*1_000_000
        delta = target-int(old['wall_lower_us'])
        clock = a.ClockBound(OWNER, RUN, MARKET, PROCESS, target, target,
            int(old['monotonic_us'])+delta)
        self.assertIs(s.validate_current_mark(original, clock, expected_mark_sha256=original.sha256), original)
        with self.assertRaises(a.AcquisitionError): s.validate_current_mark(original,
            replace(clock, monotonic_us=clock.monotonic_us+5_000_000), expected_mark_sha256=original.sha256)
        with self.assertRaises(a.AcquisitionError): s.validate_current_mark(original,
            replace(clock, wall_lower_us=target+5_000_000, wall_upper_us=target+5_000_000),
            expected_mark_sha256=original.sha256)
        with self.assertRaises(a.AcquisitionError): s.validate_current_mark(original,
            replace(clock, acquisition_epoch=str(UUID(int=777))), expected_mark_sha256=original.sha256)
        self.assertEqual(original.to_dict(), value)

    def test_current_action_preserves_exact_fractional_causality_without_integral_wait(self):
        accepted = (START+50)*1_000_000+800_000
        original = mark(0, accepted=accepted, available=accepted+100_000)
        old = original.to_dict()['original_observation_clock']
        before = a.ClockBound(OWNER, RUN, MARKET, PROCESS, accepted+100_000,
            accepted+100_000, int(old['monotonic_us'])+200_000)
        self.assertIs(s.validate_current_mark(original, before,
            expected_mark_sha256=original.sha256), original)
        self.assertEqual(before.wall_lower_us//1_000_000,
            int(original.to_dict()['record_pins'][0]['received_wall_us'])//1_000_000)
        after = a.ClockBound(OWNER, RUN, MARKET, PROCESS, (START+51)*1_000_000,
            (START+51)*1_000_000, int(old['monotonic_us'])+300_000)
        self.assertIs(s.validate_current_mark(original, after, expected_mark_sha256=original.sha256), original)
        self.assertEqual(original.to_dict()['record_pins'][0]['received_wall_us'], str(accepted-300_000))

    def test_current_action_clock_interval_must_be_known_after_original_committed_readback(self):
        original = self.marks[0]; value = original.to_dict()
        available = int(value['reference']['available_at_upper_us'])
        old = value['original_observation_clock']
        overlap = a.ClockBound(OWNER, RUN, MARKET, PROCESS, available-100_000,
            available+900_000, int(old['monotonic_us'])+1_100_000)
        with self.assertRaises(a.AcquisitionError): s.validate_current_mark(original, overlap,
            expected_mark_sha256=original.sha256)
        exact = a.ClockBound(OWNER, RUN, MARKET, PROCESS, available, available,
            int(old['monotonic_us'])+available-int(old['wall_lower_us']))
        self.assertIs(s.validate_current_mark(original, exact, expected_mark_sha256=original.sha256), original)

    def test_current_exact_us_one_before_each_causal_bound_refuses_without_rounding(self):
        original = self.marks[0]; value = original.to_dict()
        available = int(value['reference']['available_at_upper_us']); old = value['original_observation_clock']
        before = a.ClockBound(OWNER, RUN, MARKET, PROCESS, available-1, available-1,
            int(old['monotonic_us'])+available-1-int(old['wall_lower_us']))
        with self.assertRaises(a.AcquisitionError): s.validate_current_mark(original, before,
            expected_mark_sha256=original.sha256)
        # Separately adversarial but permitted original UTC skew: the raw
        # receipt is future by100ms within2s tolerance; native/readback upper is
        # earlier. This isolates latest-receipt causality from readback causality.
        accepted = (START+50)*1_000_000+800_000
        future_receipt = mark(0, accepted=accepted, available=accepted+50_000,
            receipt_age=-100_000, observation_monotonic_us=61_100_000)
        row = future_receipt.to_dict(); observed = row['original_observation_clock']
        receipt = int(row['record_pins'][0]['received_wall_us'])
        self.assertGreater(receipt, int(row['reference']['available_at_upper_us']))
        for offset, valid in ((-1, False), (0, True)):
            now = receipt+offset
            clock = a.ClockBound(OWNER, RUN, MARKET, PROCESS, now, now,
                int(observed['monotonic_us'])+now-int(observed['wall_lower_us']))
            if valid:
                self.assertIs(s.validate_current_mark(future_receipt, clock,
                    expected_mark_sha256=future_receipt.sha256), future_receipt)
            else:
                with self.assertRaises(a.AcquisitionError): s.validate_current_mark(future_receipt,
                    clock, expected_mark_sha256=future_receipt.sha256)

    def test_clock_type_and_counter_aliases_and_private_input_fields_refuse(self):
        ref = self.frozen._reference
        for changes in ({'sealed_at_us': True}, {'start_second': -1},
                {'through_ingest_sequence': 2**63}, {'source_policy_sha256': 'c'*64}):
            with self.subTest(changes=changes), self.assertRaises(a.AcquisitionError): replace(ref, **changes)
        for changes in ({'source_policy_sha256': 'c'*64}, {'price_decimal': 100},
                {'block_ref': True}, {'native_admission': True}, {'api_key': 'not-a-real-key'},
                {'price_decimal': '100.0'}):
            with self.subTest(changes=changes), self.assertRaises(a.AcquisitionError):
                s.record_set_digest((replaced_mark(self.marks[0], **changes),))

    def test_one_next_bar_preserves_all_consumed_overlap_and_61_bar_window(self):
        records = self.marks[-15:]+tuple(mark(index) for index in range(915, 930))
        next_frozen = seal(records, start=END-900, end=END+900,
            seal_id=str(UUID(int=100_001)))
        next_history = s.derive_sampled_history(next_frozen, previous=self.history,
            expected_previous_sha256=self.history.sha256)
        row = next_history.to_dict(); old = self.history.to_dict()
        self.assertEqual(len(row['minutes']), 915); self.assertEqual(len(row['bars']), 61)
        self.assertEqual(row['minutes'][:900], old['minutes'][15:])
        self.assertEqual(row['bars'][:60], old['bars'][1:]); self.assertEqual(len(row['appended_bars']), 1)

    def test_missing_prior_digest_no_overlap_backlog_and_changed_consumed_overlap_refuse(self):
        records = self.marks[-15:]+tuple(mark(index) for index in range(915, 930))
        next_frozen = seal(records, start=END-900, end=END+900, seal_id=str(UUID(int=100_001)))
        with self.assertRaises(a.AcquisitionError): s.derive_sampled_history(next_frozen, previous=self.history)
        changed = replaced_mark(records[0], price_decimal='101')
        with self.assertRaises(a.AcquisitionError):
            s.derive_sampled_history(seal((changed,)+records[1:], start=END-900, end=END+900,
                seal_id=str(UUID(int=100_001))), previous=self.history, expected_previous_sha256=self.history.sha256)
        with self.assertRaises(a.AcquisitionError): seal(records, start=END, end=END+900)
        with self.assertRaises(a.AcquisitionError): seal(records, start=END-900, end=END+1800)

    def test_original_uuid_reuse_outside_overlap_cannot_replace_earlier_identity(self):
        records = self.marks[-15:]+tuple(mark(index) for index in range(915, 930))
        old = self.marks[0].to_dict()
        for key in ('observation_id', 'record_admission_id'):
            ref = records[-1].to_dict()['reference']; ref[key] = old['reference'][key]
            changed = records[:-1]+(replaced_mark(records[-1], reference=ref),)
            with self.subTest(key=key), self.assertRaises(a.AcquisitionError):
                s.derive_sampled_history(seal(changed, start=END-900, end=END+900,
                    seal_id=str(UUID(int=100_001))), previous=self.history, expected_previous_sha256=self.history.sha256)

    def test_increment_revalidates_prior_full_schema_and_refuses_package_relabeling(self):
        records = self.marks[-15:]+tuple(mark(index) for index in range(915, 930))
        frozen = seal(records, start=END-900, end=END+900, seal_id=str(UUID(int=100_001)))
        for change in ('package', 'unknown', 'authority', 'historical_bar'):
            value = self.history.to_dict()
            if change == 'package': value['recorder_package_sha256'] = 'c'*64
            elif change == 'unknown': value['unexpected'] = 'x'
            elif change == 'authority': value['historical_ohlcv'] = True
            else: value['bars'][0]['close'] = '101'
            bad = object.__new__(s.SampledHistory); object.__setattr__(bad, '_wire', a.canonical(value))
            with self.subTest(change=change), self.assertRaises(a.AcquisitionError):
                s.derive_sampled_history(frozen, previous=bad, expected_previous_sha256=bad.sha256)

    def test_process_epochs_retained_without_cross_process_monotonic_subtraction(self):
        changed = mark(914, epoch=str(UUID(int=777)))
        row = s.derive_sampled_history(seal(self.marks[:914]+(changed,))).to_dict()
        self.assertEqual(row['minutes'][-1]['acquisition_epoch'], str(UUID(int=777)))
        self.assertEqual(row['minutes'][0]['acquisition_epoch'], PROCESS)
        self.assertFalse(row['complete_native_ledger_verified'])

    def test_immutable_decimal_exact_records_ignore_decimal_context(self):
        with localcontext() as context:
            context.prec = 1; context.traps[Inexact] = True; context.traps[Rounded] = True
            result = s.derive_sampled_history(self.frozen)
        self.assertEqual(result.wire, self.history.wire)
        with self.assertRaises(FrozenInstanceError): self.history._wire = b'changed'
        with self.assertRaises(a.AcquisitionError): s.SampledHistory()
        row = self.history.to_dict(); row['bars'][0]['close'] = '1'
        self.assertEqual(self.history.to_dict()['bars'][0]['close'], '100.123456789012345678')
        self.assertNotIn('100.123', repr(self.history))

    def test_raw_record_count_and_exact_type_limits_refuse_before_derivation(self):
        for values in ([], list(self.marks), (), (self.marks[0],)*(s.MAX_RECORDS+1)):
            with self.subTest(size=len(values)), self.assertRaises(a.AcquisitionError): s.record_set_digest(values)
        with self.assertRaises(a.AcquisitionError): s.derive_sampled_history(self.frozen.to_dict())

    def test_typed_model_close_series_keeps_exact_prices_and_original_readback_raw_pins(self):
        series = s.derive_close_series(self.history, expected_history_sha256=self.history.sha256)
        row = series.to_dict(); original = self.history.to_dict()
        self.assertEqual(row['history_sha256'], self.history.sha256); self.assertEqual(len(row['closes']), 61)
        for index, close in enumerate(row['closes']):
            anchor = original['minutes'][index*15+14]
            self.assertEqual(close['close'], original['bars'][index]['close'])
            self.assertEqual(close['close_mark_sha256'], anchor['mark_sha256'])
            self.assertEqual(close['close_observation_sha256'], anchor['observation_sha256'])
            self.assertEqual(close['close_native_record_receipt_sha256'], anchor['native_record_receipt_sha256'])
            self.assertEqual(close['close_original_record_pins'], anchor['original_record_pins'])
        self.assertFalse(series.native_admission); self.assertFalse(series.running_authority)
        self.assertEqual(series.wire, s.derive_close_series(self.history,
            expected_history_sha256=self.history.sha256).wire)

    def test_model_series_refuses_unknown_format_revised_bar_authority_and_unbound_history(self):
        with self.assertRaises(a.AcquisitionError): s.derive_close_series(self.history, expected_history_sha256='c'*64)
        for change in ('profile', 'bars', 'native_admission', 'foreign_extra'):
            value = self.history.to_dict()
            if change == 'profile': value['profile'] = 'birdeye-ohlcv-v3'
            elif change == 'bars': value['bars'][0]['close'] = '101'
            elif change == 'native_admission': value['native_admission'] = True
            else: value['api_key'] = 'not-a-real-key'
            bad = object.__new__(s.SampledHistory); object.__setattr__(bad, '_wire', a.canonical(value))
            with self.subTest(change=change), self.assertRaises(a.AcquisitionError):
                s.derive_close_series(bad, expected_history_sha256=bad.sha256)

    def test_model_series_minute_availability_and_exact_price_cannot_change_even_with_new_hash(self):
        for key, replacement in (('available_at_upper_us', str((START+61)*1_000_000)),
                ('price_decimal', '100.0'), ('accepted_at_us', True)):
            value = self.history.to_dict(); value['minutes'][0][key] = replacement
            bad = object.__new__(s.SampledHistory); object.__setattr__(bad, '_wire', a.canonical(value))
            with self.subTest(key=key), self.assertRaises(a.AcquisitionError):
                s.derive_close_series(bad, expected_history_sha256=bad.sha256)

    def test_model_series_raw_pin_schema_and_append_claim_are_rechecked(self):
        for change in ('pin', 'appended'):
            value = self.history.to_dict()
            if change == 'pin': value['minutes'][0]['original_record_pins'][0]['response_bytes'] = True
            else: value['appended_bars'] = []
            bad = object.__new__(s.SampledHistory); object.__setattr__(bad, '_wire', a.canonical(value))
            with self.subTest(change=change), self.assertRaises(a.AcquisitionError):
                s.derive_close_series(bad, expected_history_sha256=bad.sha256)

    def test_rehashed_model_dto_cannot_hide_causal_age_future_order_or_identity_defects(self):
        for change in ('old_receipt', 'future_receipt', 'old_source', 'future_source',
                       'duplicate_sequence', 'regressed_sequence', 'duplicate_observation', 'regressed_block', 'market_process_alias'):
            value = self.history.to_dict(); minute = value['minutes'][1]
            accepted = int(minute['accepted_at_us'])
            if change == 'old_receipt': minute['original_record_pins'][0]['received_wall_us'] = '0'
            elif change == 'future_receipt': minute['original_record_pins'][0]['received_wall_us'] = str(accepted+2_000_001)
            elif change == 'old_source': minute['estimated_source_second'] = '0'; minute['source_age_at_acceptance_ceiling_us'] = '0'
            elif change == 'future_source': minute['estimated_source_second'] = str(accepted//1_000_000+3)
            elif change == 'duplicate_sequence': minute['ingest_sequence'] = value['minutes'][0]['ingest_sequence']
            elif change == 'regressed_sequence': minute['ingest_sequence'] = '1'; value['minutes'][0]['ingest_sequence'] = '2'
            elif change == 'duplicate_observation': minute['observation_id'] = value['minutes'][0]['observation_id']
            elif change == 'market_process_alias': minute['acquisition_epoch'] = MARKET
            else: minute['block_ref'] = str(int(value['minutes'][0]['block_ref'])-1)
            value['bars'] = list(s._bars(tuple(value['minutes'])))
            value['appended_bars'] = value['bars']
            bad = object.__new__(s.SampledHistory); object.__setattr__(bad, '_wire', a.canonical(value))
            with self.subTest(change=change), self.assertRaises(a.AcquisitionError):
                s.derive_close_series(bad, expected_history_sha256=bad.sha256)

    def test_import_and_calls_have_no_transport_clock_rng_environment_or_native_side_effects(self):
        source = Path(s.__file__).read_text(); tree = ast.parse(source)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.extend(item.name for item in node.names)
            elif isinstance(node, ast.ImportFrom): imports.append(node.module or '')
        self.assertEqual(set(imports), {'__future__', 'dataclasses', 'hashlib', '', 'core.decimal_execution'})
        forbidden = {'time', 'time_ns', 'monotonic', 'monotonic_ns', 'uuid4', 'open',
            'getenv', 'seed', 'connect', 'request', 'post', 'get', 'commit', 'execute'}
        # dict.get is data access; no transport import or other forbidden call is allowed.
        forbidden.remove('get')
        calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        calls |= {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse(calls & forbidden)
        self.assertFalse(self.frozen.native_admission)


if __name__ == '__main__': unittest.main()
