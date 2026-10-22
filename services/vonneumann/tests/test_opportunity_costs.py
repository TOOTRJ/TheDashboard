"""Hand-calculated population accounting; no prices, API calls or orders."""
import copy
from contextlib import ExitStack, contextmanager
import unittest
from unittest.mock import patch


@contextmanager
def deny_network():
    with ExitStack() as stack:
        for target in ('socket.getaddrinfo', 'socket.create_connection',
                       'socket.socket.connect', 'socket.socket.connect_ex'):
            stack.enter_context(patch(target, side_effect=AssertionError('Offline fee scenarios forbid network access')))
        yield


with deny_network():
    from vonneumann.research.fee_provenance import FeeCharge, FeeLedger
    from vonneumann.research.opportunity_costs import (
        MAX_OPPORTUNITIES, OpportunityCostError, ScenarioAttempt, ScenarioOpportunity,
        summarize_opportunities,
    )

H = 'a' * 64


def charge(identity, amount, *, currency='SOL_lamports', kind='network_signature',
           payer='account', disposition='additional_debit', refundable=False, refund='0',
           charged_on=('success', 'failed_processed'), source=None):
    return FeeCharge(identity, source or identity, kind, currency, payer, amount,
                     disposition, 'declared_scenario', charged_on, refundable, refund)


def attempt(identity, outcome, *charges):
    return ScenarioAttempt(identity, H, FeeLedger(outcome, tuple(charges)))


def opportunity(identity, *attempts):
    return ScenarioOpportunity(identity, 'attempted', H, tuple(attempts))


def unattempted(identity, status='missing_quote', *, known_zero=True):
    ledger = FeeLedger('rejected_before_submission', ()) if known_zero else None
    return ScenarioOpportunity(identity, status, H, (), ledger)


def report(*opportunities):
    return summarize_opportunities('scenario', tuple(opportunities), scenario_evidence_sha256=H)


class OpportunityCostTests(unittest.TestCase):
    def setUp(self):
        self.network_guard = deny_network()
        self.network_guard.__enter__()
        self.addCleanup(self.network_guard.__exit__, None, None, None)

    def test_failed_attempts_and_unsuccessful_opportunities_stay_in_cost_numerator(self):
        result = report(opportunity('a', attempt('a1', 'failed_processed', charge('fee-a1', '5')),
            attempt('a2', 'success', charge('fee-a2', '7'))), unattempted('b'),
            opportunity('c', attempt('c1', 'failed_processed', charge('fee-c1', '3'))))
        self.assertEqual(3, result['opportunities'])
        self.assertEqual(3, result['attempts'])
        self.assertEqual(1, result['completed_opportunities'])
        self.assertEqual({'SOL_lamports': '15'}, result['complete_population_totals']['additional_account_debits'])
        self.assertEqual({'SOL_lamports': dict(numerator_amount='15', denominator=3)}, result['cost_per_opportunity'])
        self.assertEqual({'SOL_lamports': dict(numerator_amount='15', denominator=1)}, result['cost_per_completed_flow'])
        self.assertEqual(2, result['attempt_outcome_counts']['failed_processed'])
        self.assertEqual(3, len(result['opportunity_reviews']))

    def test_zero_successes_report_costs_without_division_by_zero(self):
        result = report(opportunity('a', attempt('a1', 'failed_processed', charge('fee-a1', '9'))))
        self.assertEqual({'SOL_lamports': '9'}, result['complete_population_totals']['additional_account_debits'])
        self.assertIsNone(result['cost_per_completed_flow'])
        self.assertTrue(result['no_completed_flow'])

    def test_uncertain_outcome_blocks_population_totals_but_retains_known_subtotal(self):
        result = report(opportunity('a', attempt('a1', 'success', charge('fee-a1', '7'))),
            opportunity('b', attempt('b1', 'uncertain', charge('fee-b1', '5'))))
        self.assertIsNone(result['complete_population_totals'])
        self.assertIsNone(result['cost_per_opportunity'])
        self.assertEqual({'SOL_lamports': '7'}, result['known_subtotals_from_fully_resolved_ledgers']['additional_account_debits'])
        self.assertEqual(1, result['unresolved_opportunities'])
        self.assertEqual(1, result['attempt_outcome_counts']['uncertain'])

    def test_unknown_fee_amount_and_missing_quote_accounting_are_never_zero(self):
        result = report(opportunity('a', attempt('a1', 'success', charge('fee-a1', None))),
                        unattempted('b', known_zero=False))
        self.assertEqual(2, result['unresolved_opportunities'])
        self.assertIsNone(result['complete_population_totals'])
        self.assertEqual('unattempted_fee_evidence_missing', result['opportunity_reviews'][1]['missing_evidence'])
        self.assertEqual(1, result['completed_opportunities'])

    def test_explicit_unprocessed_expiry_excludes_network_fee_conditionally(self):
        result = report(opportunity('a', attempt('a1', 'expired_unprocessed', charge('fee-a1', '5000'))))
        self.assertEqual({}, result['complete_population_totals']['additional_account_debits'])
        self.assertEqual(['fee-a1'], result['opportunity_reviews'][0]['fee_reviews'][0]['fee_review']['excluded_by_explicit_outcome'])
        self.assertEqual(1, result['attempt_outcome_counts']['expired_unprocessed'])

    def test_included_fees_sponsors_and_refunds_are_separate(self):
        result = report(opportunity('a', attempt('a1', 'success',
            charge('included', '0.25', currency='USD_reference', kind='platform', disposition='included_in_quote'),
            charge('sponsored', '5000', payer='sponsor'),
            charge('rent', '2039280', kind='rent', refundable=True, refund='2039280'))))
        total = result['complete_population_totals']
        self.assertEqual({'SOL_lamports': '0'}, total['additional_account_debits'])
        self.assertEqual({'USD_reference': '0.25'}, total['included_in_quote_disclosure'])
        self.assertEqual({'SOL_lamports': '5000'}, total['sponsor_additional_debits'])

    def test_separate_denominations_and_exact_decimal_addition(self):
        result = report(opportunity('a', attempt('a1', 'success',
            charge('usd-a', '0.1', currency='USD_reference', kind='explicit_other'),
            charge('sol-a', '2'), charge('usdc-a', '3', currency='USDC_atomic', kind='transfer'))),
            opportunity('b', attempt('b1', 'success', charge('usd-b', '0.2', currency='USD_reference', kind='explicit_other'))))
        self.assertEqual({'SOL_lamports': '2', 'USDC_atomic': '3', 'USD_reference': '0.3'},
                         result['complete_population_totals']['additional_account_debits'])
        self.assertEqual('none', result['currency_conversion'])

    def test_duplicate_attempt_or_charge_source_cannot_double_count(self):
        one = opportunity('a', attempt('same', 'success', charge('fee-a', '1')))
        two = opportunity('b', attempt('same', 'success', charge('fee-b', '1')))
        with self.assertRaises(OpportunityCostError): report(one, two)
        two = opportunity('b', attempt('other', 'success', charge('fee-b', '1', source='fee-a')))
        with self.assertRaises(OpportunityCostError): report(one, two)

    def test_aggregate_priority_and_separate_tip_alias_is_refused_across_attempts(self):
        one = opportunity('a', attempt('a1', 'failed_processed', charge('aggregate', '2', kind='network_priority_and_tip', source='same-source')),
            attempt('a2', 'success', charge('tip', '1', kind='tip', source='same-source')))
        with self.assertRaises(OpportunityCostError): report(one)

    def test_explicitly_excluded_quote_charge_may_be_disclosed_on_later_success(self):
        quote = charge('platform', '0.1', currency='USD_reference', kind='platform',
                       disposition='included_in_quote', charged_on=('success',), source='quote')
        result = report(opportunity('a', attempt('a1', 'failed_processed', quote), attempt('a2', 'success', quote)))
        self.assertEqual({'USD_reference': '0.1'}, result['complete_population_totals']['included_in_quote_disclosure'])
        self.assertEqual({}, result['complete_population_totals']['additional_account_debits'])

    def test_new_attempt_after_success_or_uncertainty_requires_new_protocol(self):
        for outcome in ('success', 'uncertain'):
            with self.subTest(outcome=outcome), self.assertRaises(OpportunityCostError):
                opportunity('a', attempt('a1', outcome), attempt('a2', 'failed_processed'))

    def test_input_status_and_population_capacity_are_closed(self):
        with self.assertRaises(OpportunityCostError):
            ScenarioOpportunity('a', 'missing_quote', H, (attempt('a1', 'success'),))
        with self.assertRaises(OpportunityCostError): ScenarioOpportunity('a', 'attempted', H)
        with self.assertRaises(OpportunityCostError):
            ScenarioOpportunity('a', 'not_submitted', H, (), FeeLedger('failed_processed', ()))
        with self.assertRaises(OpportunityCostError):
            report(*(unattempted('o'+str(i)) for i in range(MAX_OPPORTUNITIES+1)))

    def test_population_amount_overflow_is_refused_without_float_rounding(self):
        maximum = str(2**64 - 1)
        with self.assertRaises(OpportunityCostError):
            report(opportunity('a', attempt('a1', 'success', charge('fee-a', maximum))),
                   opportunity('b', attempt('b1', 'success', charge('fee-b', '1'))))

    def test_review_is_repeatable_and_report_mutation_cannot_change_input(self):
        inputs = (opportunity('a', attempt('a1', 'success', charge('fee-a', '7'))), unattempted('b', 'assembly_refused'))
        before = copy.deepcopy([v.to_dict() for v in inputs])
        first = report(*inputs)
        expected = copy.deepcopy(first)
        first['complete_population_totals']['additional_account_debits']['SOL_lamports'] = '999'
        first['opportunity_reviews'].clear()
        self.assertEqual(expected, report(*inputs))
        self.assertEqual(before, [v.to_dict() for v in inputs])
        self.assertTrue(all(expected[key] is False for key in ('calibration', 'population_completeness_verified', 'provider_authentication',
            'quote_completeness_verified', 'settlement_authority', 'historical_replay_authority',
            'paper_integration', 'live_trading_authority')))


if __name__ == '__main__':
    unittest.main()
