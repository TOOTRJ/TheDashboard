"""Offline adversarial integration of source bytes and real provider feed caches."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from types import SimpleNamespace
import traceback
import unittest
from unittest.mock import AsyncMock, patch

from tests.security_support import OfflineTestMixin, deny_network
from tests.test_feed_reliability import Response as PriceResponse, Session as PriceSession
from tests.test_birdeye_candles import Response as CandleResponse, Session as CandleSession, CUTOFF, MINTS, row, body

with deny_network():
    from vonneumann.market import jupiter_feed as jupiter
    from vonneumann.market import birdeye_candles as birdeye
    from vonneumann.market.feed import MarketFeedError, QuoteEvidence
    from vonneumann.market.provider_evidence import MAX_DOCUMENT_BYTES, ProviderEvidenceError
    from vonneumann.market.quote_freshness import quote_source_age

SOL, JUP = 'SOL/USDC', 'JUP/USDC'
SECRET = 'fake-exact-provider-secret-must-not-leak'
SLOT = 345678901


class Number(str):
    """Literal numeric test token without a binary64 intermediary."""


def wire(value):
    if isinstance(value, Number):
        return str(value)
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(k)+':'+wire(v) for k,v in value.items()) + '}'
    if isinstance(value, list):
        return '[' + ','.join(wire(v) for v in value) + ']'
    return json.dumps(value, ensure_ascii=False)


def price_body(values, *, slot=SLOT):
    return wire({MINTS[asset]: {'usdPrice': Number(value), 'blockId': slot, 'decimals': 9}
                 for asset,value in values.items()}).encode()


def candle_body(cutoff=CUTOFF, *, asset=SOL, count=2, changes=None, scaled=False, multiplier=None):
    rows = [row(stamp, asset=asset) for stamp in range(cutoff-count*60, cutoff, 60)]
    for index, fields in (changes or {}).items():
        rows[index].update(fields)
    payload = body(*rows)
    payload['data']['is_scaled_ui_token'] = scaled
    if multiplier is not None:
        payload['data']['multiplier'] = Number(multiplier)
    return wire(payload).encode()


class StreamResponse(PriceResponse):
    def __init__(self, chunks, *, wait_after=None, content_length=None):
        super().__init__()
        self.chunks, self.wait_after, self.content_length = chunks, wait_after, content_length
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.read_count = 0

    async def iter_chunked(self, size):
        for index, chunk in enumerate(self.chunks):
            self.read_count += 1
            yield chunk
            if index == self.wait_after:
                self.entered.set()
                await self.release.wait()


class ExactProviderFeedTests(OfflineTestMixin, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        super().setUp()
        self.wall, self.mono, self.source = CUTOFF + 10.0, 1000.0, CUTOFF
        clock = SimpleNamespace(time=lambda: self.wall, monotonic=lambda: self.mono)
        self.enterContext(patch.object(jupiter, 'time', clock))
        self.enterContext(patch.object(birdeye, 'time', clock))
        self.enterContext(patch.object(birdeye, 'REQUEST_SPACING_SECONDS', 0))

    def feed(self, *responses):
        feed = jupiter.JupiterFeed(api_key=SECRET, rpc_url='https://rpc.example.test/?key='+SECRET)
        feed._session = PriceSession(*responses)
        async def resolve(_session, slots, *, deadline):
            return {slot:self.source for slot in slots}, {}
        feed._source_time.resolve = AsyncMock(side_effect=resolve)
        return feed

    def candles(self, *responses):
        adapter = birdeye.BirdeyeCandles(SECRET, MINTS)
        adapter._session = CandleSession(*responses)
        return adapter

    async def failure(self, awaitable, code=None):
        with self.assertRaises(MarketFeedError) as caught:
            await awaitable
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        self.assertNotIn(SECRET, ''.join(traceback.format_exception(caught.exception)))
        return caught.exception

    def assert_document(self, document, raw, provider, endpoint, parameters):
        self.assertEqual(document.raw_body, raw)
        self.assertEqual(document.response_sha256, hashlib.sha256(raw).hexdigest())
        origin = {'jupiter-price-v3':'https://api.jup.ag','birdeye-ohlcv-v3':'https://public-api.birdeye.so'}[provider]
        request = {'method':'GET','endpoint':origin+endpoint,'chain':'solana','parameters':parameters}
        expected = json.dumps(request, sort_keys=True, separators=(',',':'), ensure_ascii=True).encode('ascii')
        self.assertEqual(document.request, expected)
        self.assertEqual(document.request_sha256, hashlib.sha256(expected).hexdigest())
        manifest = document.manifest()
        self.assertEqual(manifest['response_bytes'], len(raw))
        self.assertEqual(manifest['provider'], provider)
        self.assertEqual((manifest['received_at'],manifest['received_monotonic']),(self.wall,self.mono))
        self.assertNotIn(SECRET, json.dumps(manifest))
        self.assertNotIn('headers', manifest['request'])
        self.assertNotIn('rpc.example.test', json.dumps(manifest))

    async def test_price_collision_retains_original_precision_bytes_and_request_hash(self):
        raw = b' \n'+price_body({SOL:'1.000000000000000001',JUP:'1.000000000000000002'})+b'\n'
        feed = self.feed(PriceResponse(raw))
        captures = await feed.get_price_captures([SOL,JUP])
        self.assertNotEqual(captures[SOL].record.price,captures[JUP].record.price)
        self.assertEqual(captures[SOL].as_tick().price,captures[JUP].as_tick().price)
        self.assertIs(captures[SOL].record.document,captures[JUP].record.document)
        self.assert_document(captures[SOL].record.document,raw,'jupiter-price-v3','/price/v3',
                             {'ids':MINTS[SOL]+','+MINTS[JUP]})
        self.assertEqual(captures[SOL].source_timestamp,self.source)
        captures[SOL].validate(wall_now=self.wall,monotonic_now=self.mono)
        self.assertNotIn(SECRET,repr(captures[SOL]))

    async def test_price_exact_and_legacy_share_fetch_and_original_receipt(self):
        for exact_first in (False,True):
            with self.subTest(exact_first=exact_first):
                feed = self.feed(PriceResponse(price_body({SOL:'123.000000000000000001'})))
                first = await (feed.get_price_captures([SOL]) if exact_first else feed.get_ticks([SOL]))
                capture = feed._captures[SOL]
                self.wall += .2; self.mono += .2
                tick = await feed.get_tick(SOL)
                self.assertIs((await feed.get_price_captures([SOL]))[SOL],capture)
                self.assertIs(tick.evidence,capture.evidence)
                self.assertEqual(capture.record.document.received_at,self.wall-.2)
                self.assertEqual(feed.api_call_count,1)
                self.assertEqual(feed._source_time.resolve.await_count,1)
                if not exact_first:
                    self.assertIs(first[SOL],tick)

    async def test_legacy_tick_mutation_cannot_rewrite_capture_or_renew_age_anchor(self):
        feed = self.feed(PriceResponse(price_body({SOL:'100.000000000000000001'})),
                         PriceResponse(price_body({SOL:'100.000000000000000002'})))
        old = (await feed.get_price_captures([SOL]))[SOL]
        tick = await feed.get_tick(SOL)
        tick.price=999;tick.timestamp=self.wall+5000;tick.asset=JUP
        tick.evidence=QuoteEvidence(SLOT+999,self.wall+5000,self.mono)
        self.wall-=5;self.mono+=.2
        repaired=await feed.get_tick(SOL)
        self.assertEqual((repaired.asset,repaired.price,repaired.timestamp),(SOL,100.0,self.source))
        self.assertIs(repaired.evidence,old.evidence)
        self.assertIs((await feed.get_price_captures([SOL]))[SOL],old)
        self.mono+=5.8
        refreshed=(await feed.get_price_captures([SOL]))[SOL]
        self.assertEqual(refreshed.record.price,'100.000000000000000002')
        self.assertEqual(refreshed.evidence.source_age_at_receipt,16)
        self.assertEqual(quote_source_age(refreshed.as_tick(),wall_now=self.wall,monotonic_now=self.mono),16)
        self.assertEqual(old.record.document.received_monotonic,1000)

    async def test_price_capture_is_immutable_and_metadata_detached(self):
        capture=(await self.feed(PriceResponse(price_body({SOL:'100.000000000000000001'}))).get_price_captures([SOL]))[SOL]
        for obj,key,value in ((capture,'source_timestamp',0),(capture.record,'price','1'),
                              (capture.evidence,'received_at',0),(capture.record.document,'raw_body',b'{}')):
            with self.subTest(key=key),self.assertRaises(FrozenInstanceError):setattr(obj,key,value)
        exposed=capture.to_dict();exposed['record']['price']='999'
        exposed['record']['document']['request']['parameters']['ids']='forged'
        decoded=capture.record.document.decode();decoded[MINTS[SOL]]['usdPrice']=1
        self.assertEqual(capture.record.price,'100.000000000000000001')
        self.assertEqual(capture.record.document.parameters,{'ids':MINTS[SOL]})

    async def test_partial_price_failure_keeps_both_caches_and_slot_watermarks(self):
        feed=self.feed(PriceResponse(price_body({SOL:'100',JUP:'1'})),
                       PriceResponse(price_body({SOL:'101.000000000000000001',JUP:'null'},slot=SLOT+1)))
        original=await feed.get_price_captures([SOL,JUP])
        cache,slots=dict(feed._cache),dict(feed._source_slots)
        self.wall+=1;self.mono+=1
        error=await self.failure(feed.get_price_captures([SOL,JUP]),'price_invalid')
        self.assertEqual(set(error.valid_ticks),{SOL})
        self.assertEqual(error.valid_ticks[SOL].price,101.0)
        self.assertEqual(feed._cache,cache);self.assertEqual(feed._source_slots,slots)
        self.assertTrue(all(feed._captures[a] is c for a,c in original.items()))

    async def test_price_stream_cancellation_preserves_cache_and_retry(self):
        blocked=StreamResponse([b'{',b'}'],wait_after=0)
        feed=self.feed(PriceResponse(price_body({SOL:'100'})),blocked,PriceResponse(price_body({SOL:'101'})))
        original=(await feed.get_price_captures([SOL]))[SOL]
        cache=dict(feed._cache);self.wall+=1;self.mono+=1
        task=asyncio.create_task(feed.get_price_captures([SOL]))
        await asyncio.wait_for(blocked.entered.wait(),1);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(feed._cache,cache);self.assertIs(feed._captures[SOL],original)
        self.assertEqual((await feed.get_price_captures([SOL]))[SOL].record.price,'101')

    async def test_price_oversize_duplicate_keys_and_read_errors_fail_safely(self):
        duplicate=b'{'+json.dumps(MINTS[SOL]).encode()+b':{"usdPrice":100,"usdPrice":101,"blockId":345678901}}'
        oversized=StreamResponse([b'x'*16384]*10,content_length=1)
        for response in (PriceResponse(duplicate),oversized,PriceResponse(error=RuntimeError(SECRET))):
            with self.subTest(response=type(response).__name__):
                feed=self.feed(response)
                await self.failure(feed.get_price_captures([SOL]),'price_invalid')
                self.assertEqual(feed._captures,{})
                self.assertEqual(feed._cache,{})
                feed._source_time.resolve.assert_not_awaited()
        self.assertLess(oversized.read_count,10)

    async def test_exact_candle_delegation_does_not_use_jupiter_session(self):
        feed=self.feed();sentinel=[object()]
        feed._candles.get_exact_candles=AsyncMock(return_value=sentinel)
        self.assertIs(await feed.get_exact_candles([SOL],warmup=True),sentinel)
        feed._candles.get_exact_candles.assert_awaited_once_with([SOL],warmup=True)
        self.assertEqual(feed.api_call_count,0);self.assertEqual(feed._session.calls,[])

    async def test_candle_precision_and_document_survive_legacy_projection(self):
        raw=candle_body(changes={0:{'c':Number('101.000000000000000001'),
            'v':Number('3.000000000000000001'),'v_usd':Number('301.000000000000000001')}})
        adapter=self.candles(CandleResponse(raw))
        exact=await adapter.get_exact_candles([SOL],warmup=True)
        legacy=await adapter.get_candles([SOL])
        self.assertEqual((exact[0].close,exact[0].volume,exact[0].volume_usd),
            ('101.000000000000000001','3.000000000000000001','301.000000000000000001'))
        self.assertEqual((legacy[0].close,legacy[0].volume),(101.0,3.0))
        self.assert_document(exact[0].document,raw,'birdeye-ohlcv-v3','/defi/v3/ohlcv',adapter._session.calls[0][1]['params'])
        self.assertEqual(adapter.api_call_count,1)
        self.assertIs((await adapter.get_exact_candles([SOL]))[0],exact[0])

    async def test_candle_cutoff_cache_does_not_refresh_receipt(self):
        adapter=self.candles(CandleResponse(candle_body()))
        await adapter.get_candles([SOL])
        first=(await adapter.get_exact_candles([SOL]))[0]
        receipt=(first.document.received_at,first.document.received_monotonic)
        self.wall+=20;self.mono+=20
        second=(await adapter.get_exact_candles([SOL],warmup=True))[0]
        self.assertIs(first,second)
        self.assertEqual((second.document.received_at,second.document.received_monotonic),receipt)
        self.assertEqual(adapter.api_call_count,1)
        self.assertEqual(adapter._cutoffs,{SOL:CUTOFF})

    async def test_duplicate_candle_revision_below_float_precision_is_rejected(self):
        for field,one,two in (('c','101.000000000000000001','101.000000000000000002'),
                              ('v_usd','301.000000000000000001','301.000000000000000002')):
            with self.subTest(field=field):
                self.assertEqual(float(one),float(two))
                raw=wire(body(row(CUTOFF-60,**{field:Number(one)}),row(CUTOFF-60,**{field:Number(two)}))).encode()
                adapter=self.candles(CandleResponse(raw))
                await self.failure(adapter.get_exact_candles([SOL]),'candles_revision')
                self.assertEqual(adapter._exact_cache,{})
                self.assertEqual(adapter._cache,{})
                self.assertEqual(adapter._cutoffs,{})

    async def test_overlapping_candle_revision_keeps_accepted_exact_and_legacy_cache(self):
        for field,one,two in (('c','101.000000000000000001','101.000000000000000002'),
                              ('v_usd','301.000000000000000001','301.000000000000000002')):
            with self.subTest(field=field):
                self.wall=CUTOFF+10;self.mono=1000
                adapter=self.candles(CandleResponse(candle_body(changes={1:{field:Number(one)}})),
                    CandleResponse(candle_body(CUTOFF+60,count=3,changes={1:{field:Number(two)}})))
                first=await adapter.get_exact_candles([SOL]);old=dict(adapter._cache)
                self.wall+=60;self.mono+=60
                await self.failure(adapter.get_candles([SOL]),'candles_revision')
                self.assertEqual(adapter._cache,old)
                self.assertIs(adapter._exact_cache[SOL][1],first[1])
                self.assertEqual(adapter._cutoffs,{SOL:CUTOFF})

    async def test_identical_overlap_with_new_document_is_not_a_false_revision(self):
        adapter=self.candles(CandleResponse(candle_body()),CandleResponse(b' '+candle_body(CUTOFF+60,count=3)+b'\n'))
        first=await adapter.get_exact_candles([SOL]);self.wall+=60;self.mono+=60
        second=await adapter.get_exact_candles([SOL])
        self.assertEqual(first[1].close,second[1].close)
        self.assertNotEqual(first[1].document.response_sha256,second[1].document.response_sha256)
        self.assertEqual(second[-1].end,CUTOFF+60)

    async def test_scaled_flags_are_retained_immutable_and_require_explicit_policy(self):
        for scaled,multiplier in ((False,None),(True,'1.234567890123456789')):
            with self.subTest(scaled=scaled):
                adapter=self.candles(CandleResponse(candle_body(scaled=scaled,multiplier=multiplier)))
                record=(await adapter.get_exact_candles([SOL]))[0]
                self.assertEqual(record.is_scaled_ui_token,scaled)
                self.assertEqual(record.multiplier,multiplier)
                self.assertEqual(record.close,'101')
                if scaled:
                    with self.assertRaises(ProviderEvidenceError):record.require_unscaled()
                else:self.assertIs(record.require_unscaled(),record)
                with self.assertRaises(FrozenInstanceError):record.close='1'
                metadata=record.to_dict();metadata['close']='1';metadata['document']['request']['parameters']['address']='changed'
                self.assertEqual(record.close,'101')
                self.assertEqual(record.document.parameters['address'],MINTS[SOL])

    async def test_multicandle_partial_failure_preserves_both_caches_and_watermarks(self):
        adapter=self.candles(CandleResponse(candle_body()),CandleResponse(candle_body(asset=JUP)),
            CandleResponse(candle_body(CUTOFF+60,count=3)),CandleResponse(status=503))
        await adapter.get_exact_candles([SOL,JUP])
        legacy,exact,cutoffs,starts=map(dict,(adapter._cache,adapter._exact_cache,adapter._cutoffs,adapter._first_starts))
        self.wall+=60;self.mono+=60
        await self.failure(adapter.get_exact_candles([SOL,JUP]),'candles_unavailable')
        self.assertEqual(adapter._cache,legacy);self.assertEqual(adapter._exact_cache,exact)
        self.assertEqual(adapter._cutoffs,cutoffs);self.assertEqual(adapter._first_starts,starts)
        self.assertIs(adapter._exact_cache[SOL][0],exact[SOL][0])

    async def test_cancelled_second_candle_read_cannot_commit_first_asset(self):
        blocked=StreamResponse([b'{',b'}'],wait_after=0)
        adapter=self.candles(CandleResponse(candle_body()),CandleResponse(candle_body(asset=JUP)),
            CandleResponse(candle_body(CUTOFF+60,count=3)),blocked)
        await adapter.get_exact_candles([SOL,JUP])
        exact,legacy,cutoffs=map(dict,(adapter._exact_cache,adapter._cache,adapter._cutoffs))
        self.wall+=60;self.mono+=60
        task=asyncio.create_task(adapter.get_exact_candles([SOL,JUP]))
        await asyncio.wait_for(blocked.entered.wait(),1);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(adapter._exact_cache,exact);self.assertEqual(adapter._cache,legacy)
        self.assertEqual(adapter._cutoffs,cutoffs)

    async def test_candle_oversize_duplicate_keys_and_read_errors_fail_safely(self):
        duplicate=b'{"success":true,"success":false,"data":{"items":[]}}'
        oversized=StreamResponse([b'x'*16384]*(MAX_DOCUMENT_BYTES['birdeye-ohlcv-v3']//16384+2),content_length=1)
        for response in (CandleResponse(duplicate),oversized,CandleResponse(error=RuntimeError(SECRET))):
            with self.subTest(response=type(response).__name__):
                adapter=self.candles(response)
                await self.failure(adapter.get_exact_candles([SOL]),'candles_invalid')
                self.assertEqual(adapter._exact_cache,{})
                self.assertEqual(adapter._cutoffs,{})
        self.assertLess(oversized.read_count,len(oversized.chunks))


    async def test_capture_rejects_evidence_from_another_slot_or_receipt(self):
        capture=(await self.feed(PriceResponse(price_body({SOL:'100'}))).get_price_captures([SOL]))[SOL]
        for changes in ({'source_slot':SLOT+1},{'received_at':self.wall+1},
                        {'received_monotonic':self.mono+1},{'provider':'other-provider'},
                        {'quote_currency':'EUR'}):
            with self.subTest(changes=changes),self.assertRaises(ProviderEvidenceError):
                jupiter.PriceCapture(capture.record,capture.source_timestamp,replace(capture.evidence,**changes))
        with self.assertRaises(ProviderEvidenceError):
            jupiter.PriceCapture(capture.record,True,capture.evidence)

    async def test_warmup_detects_older_retained_revision_after_incremental_cache_roll(self):
        adapter=self.candles(CandleResponse(candle_body(count=5)),
            CandleResponse(candle_body(CUTOFF+60,count=3)),
            CandleResponse(candle_body(CUTOFF+60,count=6,changes={0:{'c':Number('101.000000000000000001')}})))
        initial=await adapter.get_exact_candles([SOL],warmup=True)
        self.wall+=60;self.mono+=60
        incremental=await adapter.get_exact_candles([SOL])
        self.assertNotIn(initial[0].start,{r.start for r in incremental})
        before=deepcopy((adapter._accepted_fingerprints,adapter._cutoffs,adapter._first_starts))
        exact,legacy=dict(adapter._exact_cache),dict(adapter._cache)
        await self.failure(adapter.get_exact_candles([SOL],warmup=True),'candles_revision')
        self.assertEqual((adapter._accepted_fingerprints,adapter._cutoffs,adapter._first_starts),before)
        self.assertEqual(adapter._exact_cache,exact);self.assertEqual(adapter._cache,legacy)
        self.assertIs(adapter._exact_cache[SOL][0],incremental[0])

    async def test_same_cutoff_warmup_widens_incremental_cache_once(self):
        adapter=self.candles(CandleResponse(candle_body(count=3)),
            CandleResponse(candle_body(CUTOFF+60,count=3)),
            CandleResponse(candle_body(CUTOFF+60,count=4)))
        initial=await adapter.get_exact_candles([SOL],warmup=True)
        self.wall+=60;self.mono+=60
        narrow=await adapter.get_exact_candles([SOL])
        self.assertGreater(narrow[0].start,initial[0].start)
        wide=await adapter.get_exact_candles([SOL],warmup=True)
        self.assertEqual(len(wide),4);self.assertEqual(wide[0].start,initial[0].start)
        self.assertEqual(adapter.api_call_count,3)
        self.assertEqual(adapter._session.calls[-1][1]['params']['time_from'],CUTOFF+60-birdeye.WARMUP_MINUTES*60)
        self.assertIs((await adapter.get_exact_candles([SOL],warmup=True))[0],wide[0])
        self.assertEqual(adapter.api_call_count,3)

    async def test_candle_read_wall_rollback_rejects_future_cutoff_without_committing(self):
        async def rollback_during_read():
            self.wall = CUTOFF
        adapter = self.candles(CandleResponse(candle_body()), CandleResponse(
            candle_body(CUTOFF+60,count=3), before_json=rollback_during_read))
        accepted = await adapter.get_exact_candles([SOL])
        before = deepcopy((adapter._accepted_fingerprints, adapter._cutoffs, adapter._first_starts))
        exact, legacy = dict(adapter._exact_cache), dict(adapter._cache)
        self.wall += 60; self.mono += 60
        await self.failure(adapter.get_exact_candles([SOL]), 'candles_clock_invalid')
        self.assertEqual((adapter._accepted_fingerprints, adapter._cutoffs, adapter._first_starts), before)
        self.assertEqual(adapter._exact_cache, exact)
        self.assertEqual(adapter._cache, legacy)
        self.assertIs(adapter._exact_cache[SOL][0], accepted[0])

    async def test_exact_revision_fingerprints_retain_only_newest_bounded_minutes(self):
        adapter = self.candles(CandleResponse(candle_body(count=3660)),
            CandleResponse(candle_body(CUTOFF+500*60,count=502)))
        initial = await adapter.get_exact_candles([SOL],warmup=True)
        self.assertEqual(len(adapter._accepted_fingerprints[SOL]),3660)
        old_document = initial[0].document
        self.wall += 500*60; self.mono += 500*60
        latest = await adapter.get_exact_candles([SOL])
        retained = adapter._accepted_fingerprints[SOL]
        self.assertEqual(len(retained),4096)
        self.assertEqual(min(retained),CUTOFF+500*60-4096*60)
        self.assertEqual(max(retained),CUTOFF+499*60)
        self.assertNotIn(initial[0].start,retained)
        self.assertTrue(all(type(digest) is str and len(digest)==64 for digest in retained.values()))
        self.assertEqual(len(latest),502)
        self.assertEqual(len(adapter._exact_cache[SOL]),502)
        self.assertIsNot(latest[0].document,old_document)
        self.assertTrue(all(record.document is latest[0].document for record in adapter._exact_cache[SOL]))
        self.assertEqual(adapter.api_call_count,2)
