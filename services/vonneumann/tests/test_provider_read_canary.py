"""Offline operation ownership, quota stop and secret-safe reporting checks."""
import asyncio
from contextlib import redirect_stdout
import io
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.security_support import OfflineTestMixin, deny_network
with deny_network():
    from tools import provider_read_canary as module
    from vonneumann.market.feed import MarketFeedError


class ClosedProviderCanaryTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def test_admission_and_operator_credentials_are_refused(self):
        valid = {'VN_SERVICE_MODE': 'closed', 'PYTHON_DOTENV_DISABLED': '1',
            'VN_ENVIRONMENT': 'production',
            'SUPABASE_URL': 'https://fxpxsciltakyypunglzr.supabase.co',
            'VN_ALLOWED_ORIGINS': 'https://the-dashboard-chi.vercel.app',
            'JUPITER_API_KEY': 'fake-secret', 'BIRDEYE_API_KEY': 'fake-secret',
            'VN_SOLANA_RPC_URL': 'https://rpc.invalid/?api-key=fake-secret'}
        self.assertEqual(len(module.configuration(valid)), 3)
        for key, value in [('VN_SERVICE_MODE', 'paper-v5'),
                ('SUPABASE_URL', 'https://other.supabase.co'),
                ('VN_ECONOMIC_PASSWORD', 'fake-secret'), ('RAILWAY_TOKEN', 'fake-secret'),
                ('SUPABASE_SERVICE_ROLE_KEY', 'fake-secret')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.configuration({**valid, key: value})

    def test_quota_allowlist_does_not_export_headers(self):
        self.assertEqual(module.quota_headers({'Authorization': 'secret',
            'x-ratelimit-limit': '60', 'x-ratelimit-remaining': '-1',
            'x-ratelimit-reset': 'bad'}), {'limit': 60, 'remaining': -1})

    async def test_actual_assessment_closes_resources_after_failure_without_retry(self):
        instances = []
        class FakeFeed:
            api_call_count = 0
            def __init__(self, **keys):
                self._candles = SimpleNamespace(api_call_count=1)
                self._source_time = SimpleNamespace(api_call_count=0)
                instances.append(self)
            async def get_provider_history(self):
                raise MarketFeedError('candles_rate_limited')
            async def close(self):
                await self._session.close()
        output = io.StringIO()
        with redirect_stdout(output):
            report = await module.assess(('fake-secret',)*3, feed_factory=FakeFeed)
        self.assertEqual(report['phase'], 'refused')
        self.assertEqual(report['code'], 'candles_rate_limited')
        self.assertEqual(len(instances), 1)
        self.assertTrue(instances[0]._session.closed)
        self.assertIsNone(report['price_seconds'])
        self.assertFalse(report['economic_writes'])
        self.assertNotIn('fake-secret', output.getvalue())

    async def test_cancellation_closes_original_feed_and_does_not_report_success(self):
        entered = asyncio.Event()
        instances = []
        class FakeFeed:
            api_call_count = 0
            def __init__(self, **keys):
                self._candles = SimpleNamespace(api_call_count=1)
                self._source_time = SimpleNamespace(api_call_count=0)
                instances.append(self)
            async def get_provider_history(self):
                entered.set()
                await asyncio.Future()
            async def close(self):
                await self._session.close()
        output = io.StringIO()
        with redirect_stdout(output):
            task = asyncio.create_task(module.assess(('fake-secret',)*3, feed_factory=FakeFeed))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(instances[0]._session.closed)
        self.assertIn('"phase": "interrupted"', output.getvalue())
        self.assertNotIn('"phase": "passed"', output.getvalue())

    async def test_shared_quota_margin_stops_before_another_price_call(self):
        instances = []
        class FakeFeed:
            api_call_count = 0
            def __init__(self, **keys):
                self._candles = SimpleNamespace(api_call_count=1)
                self._source_time = SimpleNamespace(api_call_count=1)
                instances.append(self)
            async def get_provider_history(self):
                doc = SimpleNamespace(raw_body=b'{}', response_sha256='0'*64)
                return (SimpleNamespace(document=doc, multiplier=None),)*915
            async def get_price_captures(self, assets):
                self.api_call_count += 1
                params = SimpleNamespace(url=SimpleNamespace(host='api.jup.ag', path='/price/v3'),
                    response=SimpleNamespace(headers={'x-ratelimit-remaining': '11'}))
                await self._session._trace_configs[0].on_request_end.send(self._session, None, params)
                return {'SOL/USDC': SimpleNamespace(evidence=SimpleNamespace(
                    source_age_at_receipt=1, received_monotonic=time.monotonic()))}
            async def close(self):
                await self._session.close()
        with redirect_stdout(io.StringIO()), patch.object(module, 'INTERVAL', 0):
            report = await module.assess(('fake-secret',)*3, feed_factory=FakeFeed)
        self.assertEqual(report['code'], 'shared_quota_margin_unavailable')
        self.assertEqual(report['phase'], 'refused')
        self.assertEqual(report['price_seconds']['count'], 1)
        self.assertEqual(instances[0].api_call_count, 1)
        self.assertTrue(instances[0]._session.closed)


if __name__ == '__main__':
    unittest.main()
