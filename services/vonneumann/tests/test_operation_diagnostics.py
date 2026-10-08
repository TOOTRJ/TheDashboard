"""Failure classification must remain fixed even when error details are hostile."""
import asyncio
import json
import unittest

from tests.security_support import deny_network
with deny_network():
    from vonneumann.core.operation_diagnostics import failure_labels
    from vonneumann.market.feed import MarketFeedError
    from vonneumann.market.provider_contract import ProviderSourceError
    from vonneumann.db.rehearsal_owner import OperationalAdmissionError


class OperationDiagnosticsTests(unittest.TestCase):
    def test_fixed_capture_admission_causes_are_distinguished_without_error_text(self):
        cases = {
            'provider owner admission is closed': 'owner_closed',
            'controller_receipt_boundary_invalid': 'receipt_boundary_invalid',
            'controller_price_acquisition_expired': 'price_acquisition_expired',
            'controller_receipt_clock_did_not_advance': 'receipt_clock_not_advanced',
            'controller_original_receipt_not_admitted': 'original_receipt_not_admitted',
        }
        for message, code in cases.items():
            with self.subTest(code=code):
                labels = failure_labels('capture', OperationalAdmissionError(message)).to_dict()
                self.assertEqual(labels, {'stage': 'capture',
                    'category': 'operational_admission_failed', 'provider_code': None,
                    'admission_code': code})
                self.assertNotIn(message, json.dumps(labels))

    def test_admission_type_does_not_authorize_unknown_private_or_nonstring_details(self):
        for arguments in (('https://private.invalid/?key=do-not-log',),
                          (['private'],), ('controller_price_acquisition_expired', 'private')):
            with self.subTest(arguments=arguments):
                labels = failure_labels('capture', OperationalAdmissionError(*arguments)).to_dict()
                self.assertEqual(labels, {'stage': 'capture',
                    'category': 'operational_admission_failed', 'provider_code': None})
                self.assertNotIn('private', json.dumps(labels))

    def test_unknown_stage_code_and_exception_text_are_not_serialized(self):
        private = 'https://private.invalid/?key=do-not-log'
        for error in (RuntimeError(private), MarketFeedError(private), MarketFeedError([private])):
            with self.subTest(error=type(error).__name__):
                labels = failure_labels(private, error).to_dict()
                self.assertEqual(labels['stage'], 'unknown_stage')
                self.assertNotIn(private, json.dumps(labels))

    def test_source_validation_timeout_and_cancellation_remain_distinct(self):
        for error, category in ((ProviderSourceError(), 'source_validation_failed'),
                                (TimeoutError('private'), 'operation_timeout'),
                                (asyncio.CancelledError('private'), 'operation_cancelled')):
            with self.subTest(category=category):
                self.assertEqual(failure_labels('quote_admission', error).to_dict(), {
                    'stage': 'quote_admission', 'category': category, 'provider_code': None})
