"""Independent exact fee annotation, refusal, payer and outcome cases."""
from dataclasses import FrozenInstanceError, replace
from decimal import localcontext, ROUND_DOWN
import unittest

from tests.security_support import OfflineTestMixin, deny_network
with deny_network():
    from vonneumann.research.fee_provenance import FeeCharge, FeeLedger, FeeProvenanceError


def charge(**changes):
    value = dict(component_id='fee', source_ref='quote1', kind='platform',
                 currency='USD_reference', payer='account', amount='0.25',
                 disposition='included_in_quote', provenance='declared_scenario',
                 charged_on=('success',), refundable=False, refund_amount='0')
    return FeeCharge(**(value | changes))


class FeeProvenanceTests(OfflineTestMixin, unittest.TestCase):
    def test_included_cost_is_disclosed_not_debited_twice_and_currencies_remain_separate(self):
        ledger = FeeLedger('success', (charge(),
            charge(component_id='network', kind='network_signature', currency='SOL_lamports', amount='5000', disposition='additional_debit'),
            charge(component_id='transfer', kind='transfer', currency='USDC_atomic', amount='20000', disposition='additional_debit'),
            charge(component_id='sponsored', source_ref='sponsor1', kind='network_priority_and_tip',
                   currency='SOL_lamports', amount='10000', payer='sponsor', disposition='additional_debit')))
        result = ledger.require_resolved()
        self.assertEqual(result['additional_account_debits'], {'SOL_lamports': '5000', 'USDC_atomic': '20000'})
        self.assertEqual(result['included_in_quote_disclosure'], {'USD_reference': '0.25'})
        self.assertEqual(result['sponsor_additional_debits'], {'SOL_lamports': '10000'})
        self.assertFalse(result['settlement_authority']); self.assertFalse(result['quote_completeness_verified'])
        self.assertEqual(result['currency_conversion'], 'none')

    def test_combined_priority_fee_and_tip_double_count_and_duplicate_fee_are_refused(self):
        for charges in ((charge(), charge(component_id='extra', disposition='additional_debit')),
                        (charge(), charge(source_ref='different')),
                        (charge(kind='network_priority_and_tip'), charge(component_id='tip', kind='tip'))):
            with self.assertRaises(FeeProvenanceError) as caught:
                FeeLedger('success', charges)
            self.assertEqual(caught.exception.code, 'fee_double_count')
        # Independently identified transactions can have separate charged components.
        self.assertTrue(FeeLedger('success', (charge(kind='network_priority_and_tip'),
            charge(component_id='tip', source_ref='transaction2', kind='tip'))).require_resolved()['resolved'])

    def test_unknown_amount_payer_refund_and_transaction_outcome_never_become_zero(self):
        for item in (charge(amount=None), charge(payer='unknown'), charge(refundable=True, refund_amount=None)):
            ledger = FeeLedger('success', (item,))
            result = ledger.review()
            self.assertFalse(result['resolved']); self.assertIsNone(result['additional_account_debits'])
            self.assertIsNone(result['included_in_quote_disclosure'])
            with self.assertRaises(FeeProvenanceError) as caught: ledger.require_resolved()
            self.assertEqual(caught.exception.code, 'fee_unresolved')
        result = FeeLedger('uncertain', (charge(),)).review()
        self.assertFalse(result['resolved']); self.assertIn('transaction_outcome', result['unresolved'])
        self.assertIsNone(result['additional_account_debits'])

    def test_outcome_exclusion_is_explicit_and_failed_processed_cost_rule_is_declared(self):
        network = charge(component_id='network', kind='network_signature', currency='SOL_lamports', amount='5000',
                         disposition='additional_debit', charged_on=('success', 'failed_processed'))
        self.assertEqual(FeeLedger('failed_processed', (network,)).require_resolved()['additional_account_debits'], {'SOL_lamports': '5000'})
        for outcome in ('expired_unprocessed', 'rejected_before_submission'):
            result = FeeLedger(outcome, (network, charge(amount=None))).require_resolved()
            self.assertEqual(result['additional_account_debits'], {})
            self.assertEqual(result['excluded_by_explicit_outcome'], ['network', 'fee'])
        with self.assertRaises(FeeProvenanceError): charge(kind='network_signature', charged_on=('expired_unprocessed',))

    def test_rent_refund_and_decimal_arithmetic_do_not_depend_on_ambient_precision(self):
        rent = charge(kind='rent', currency='SOL_lamports', amount='2039280', refundable=True,
                      refund_amount='2039280', disposition='additional_debit', provenance='observed_wallet')
        a = charge(component_id='a', source_ref='a', amount='0.000000000000000000000000000000000001', disposition='additional_debit')
        b = charge(component_id='b', source_ref='b', amount='0.999999999999999999999999999999999999', disposition='additional_debit')
        with localcontext() as context:
            context.prec = 2; context.rounding = ROUND_DOWN
            result = FeeLedger('success', (rent, a, b)).require_resolved()
        self.assertEqual(result['additional_account_debits'], {'SOL_lamports': '0', 'USD_reference': '1'})
        with self.assertRaises(FeeProvenanceError): replace(rent, refund_amount='2039281')
        with self.assertRaises(FeeProvenanceError): charge(refund_amount='0.1')

    def test_exact_types_capacity_canonical_strings_and_safe_errors(self):
        for field, value in (('amount', False), ('amount', '0.0'), ('amount', '01'),
                             ('amount', '-1'), ('amount', '1e3'), ('amount', '0.' + '0'*36 + '1'),
                             ('refundable', 1), ('charged_on', ('uncertain',)), ('charged_on', ['success']),
                             ('source_ref', '/private/secret'), ('currency', 'USD'), ('payer', None)):
            with self.assertRaises(FeeProvenanceError) as caught: charge(**{field: value})
            if value == '/private/secret': self.assertNotIn(value, str(caught.exception))
        with self.assertRaises(FeeProvenanceError): charge(currency='SOL_lamports', amount=str(2**64))
        with self.assertRaises(FeeProvenanceError): FeeLedger('success', tuple(charge(component_id=str(i), source_ref=str(i)) for i in range(33)))
        with self.assertRaises(FeeProvenanceError):
            FeeLedger('success', (charge(currency='SOL_lamports', amount=str(2**64-1), disposition='additional_debit'),
                charge(component_id='two', source_ref='two', currency='SOL_lamports', amount='1', disposition='additional_debit'))).require_resolved()

    def test_roundtrip_nested_immutability_and_strict_extra_fields(self):
        ledger = FeeLedger('success', (charge(),))
        copied = ledger.to_dict(); copied['charges'][0]['amount'] = '999'
        self.assertEqual(ledger.charges[0].amount, '0.25')
        self.assertEqual(FeeLedger.from_dict(ledger.to_dict()), ledger)
        with self.assertRaises(FrozenInstanceError): ledger.outcome = 'uncertain'
        with self.assertRaises(FrozenInstanceError): ledger.charges[0].amount = '1'
        value = ledger.to_dict(); value['charges'][0]['extra'] = True
        with self.assertRaises(FeeProvenanceError): FeeLedger.from_dict(value)
