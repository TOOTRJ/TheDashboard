"""Failure classification must remain fixed even when error details are hostile."""
import asyncio
import json
import unittest

from tests.security_support import deny_network
with deny_network():
    from vonneumann.core.operation_diagnostics import failure_labels
    from vonneumann.market.feed import MarketFeedError
    from vonneumann.market.provider_contract import ProviderSourceError


class OperationDiagnosticsTests(unittest.TestCase):
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
