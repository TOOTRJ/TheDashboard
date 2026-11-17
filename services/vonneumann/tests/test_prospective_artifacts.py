"""Original capsule recipes reconstruct through public parsers after restart."""
from dataclasses import replace
import hashlib
import unittest
from uuid import UUID

from tests.security_support import deny_network
with deny_network():
    from tests.test_prospective_source_v3 import OWNER, RUN, MARKET, PROCESS, ISSUER, PRINCIPAL, PACKAGE, RECEIPT, START, END
    from vonneumann.market import provider_acquisition_v3 as a, provider_derivation_v3 as d
    from vonneumann.market import prospective_source_v3 as s
    from vonneumann.core.prospective_artifacts import mark_recipe, history_recipe, series_recipe, SourceRecipeReader, SourceRecipeStore
    from vonneumann.core.prospective_runtime import RuntimeRefused


def literal_recipe(serial=0):
    wall = (START+50+serial*60)*1_000_000
    mono = (serial+1)*60_000_000
    binding = a.IssuerBinding(OWNER, RUN, MARKET, PROCESS, ISSUER,
        (('jupiter-price-v3', str(UUID(int=21))), ('solana-rpc', str(UUID(int=22)))))
    slot = 348004023+serial
    requests = (a.public_request('jupiter-price-v3'),
        a.public_request('solana-rpc', rpc_method='getGenesisHash', rpc_id=1),
        a.public_request('solana-rpc', rpc_method='getBlockTime', rpc_id=2, slot=slot))
    bodies = (('{"'+a.MINT+'":{"usdPrice":100.123456789,"blockId":'+str(slot)+',"decimals":9}}').encode(),
        a.canonical({'jsonrpc': '2.0', 'id': 1, 'result': a.GENESIS}),
        a.canonical({'jsonrpc': '2.0', 'id': 2, 'result': wall//1_000_000-2}))
    base = 1_000_000+serial*10
    capsules = tuple(a.capture_capsule(binding, record_id=str(UUID(int=base+index)),
        provider_family='jupiter-price-v3' if index == 0 else 'solana-rpc',
        request=request, raw_body=body, http_status=200,
        started_wall_us=wall-100_000, received_wall_us=wall,
        started_monotonic_us=mono-100_000, received_monotonic_us=mono)
        for index, (request, body) in enumerate(zip(requests, bodies)))
    clock = a.ClockBound(OWNER, RUN, MARKET, PROCESS, wall+100_000, wall+100_000, mono+100_000)
    observed = d.derive_observation(*capsules, binding, clock, observation_id=str(UUID(int=base+4)))
    reference = s.RecordReference(OWNER, RUN, MARKET, PROCESS, str(UUID(int=base+4)),
        observed.sha256, str(UUID(int=base+5)), serial+1, wall+200_000, wall+300_000,
        PRINCIPAL, PACKAGE, RECEIPT)
    return mark_recipe(*capsules, binding, clock, reference)


class RecipeJournal:
    def __init__(self):
        self.rows = []
    async def put_artifact(self, kind, digest, wire):
        for row in self.rows:
            if (row['kind'], row['sha256']) == (kind, digest):
                if row['wire'] != wire:
                    raise ValueError()
                return row['wire']
        self.rows.append({'sequence': len(self.rows)+1, 'kind': kind, 'sha256': digest, 'wire': wire})
        return wire
    async def get_artifact(self, kind, digest):
        return next((row['wire'] for row in self.rows if (row['kind'], row['sha256']) == (kind, digest)), None)
    async def artifact_inventory(self, after_sequence=0, limit=100):
        return self.rows[after_sequence:after_sequence+1]


class ProspectiveArtifactsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        guard = deny_network(); guard.__enter__()
        self.addCleanup(guard.__exit__, None, None, None)

    async def test_fresh_store_replays_actual_original_capsules_and_partial_inventory_pages(self):
        journal = RecipeJournal()
        writer = SourceRecipeStore(journal, OWNER, RUN)
        originals = []
        for index in range(3):
            mark, recipe = literal_recipe(index)
            originals.append(mark)
            await writer.put('mark', mark.sha256, recipe.wire)
        reader = SourceRecipeStore(journal, OWNER, RUN)
        rows = await reader.scan('mark')
        self.assertEqual(len(rows), 3)
        for original in originals:
            replay = reader.reader('mark', original.sha256)
            self.assertEqual(replay.wire, original.wire)
            self.assertEqual(replay.to_dict()['reference'], original.to_dict()['reference'])

    async def test_changed_original_raw_body_and_wrong_owner_are_rejected(self):
        original, recipe = literal_recipe()
        value = recipe.to_dict()
        capsule = a.read_json(value['inputs']['capsules'][0].encode(), a.MAX_CAPSULE_BYTES, exact=True)
        capsule['response_base64'] = 'e30='
        value['inputs']['capsules'][0] = a.canonical(capsule).decode()
        reader = SourceRecipeReader(OWNER, RUN, lambda *args: a.canonical(value))
        with self.assertRaises((RuntimeRefused, a.AcquisitionError)):
            reader('mark', original.sha256)
        other = SourceRecipeReader(str(UUID(int=999)), RUN, lambda *args: recipe.wire)
        with self.assertRaises(RuntimeRefused):
            other('mark', original.sha256)

    async def test_released_derived_cache_keeps_exact_previous_history_chain_reconstructible(self):
        recipes, marks = {}, []
        for index in range(930):
            mark, recipe = literal_recipe(index)
            marks.append(mark); recipes['mark', mark.sha256] = recipe.wire
        def freeze(window, start, end, previous=None, serial=0):
            window = tuple(window)
            reference = s.SealReference(OWNER, RUN, MARKET, str(UUID(int=10_000+serial)),
                s.record_set_digest(window), max(int(mark.to_dict()['reference']['ingest_sequence']) for mark in window),
                start, end, end*1_000_000+s.COMPLETION_MARGIN_US, PACKAGE)
            history, recipe = history_recipe(window, reference, previous=previous)
            series, series_original = series_recipe(history)
            recipes['history', history.sha256] = recipe.wire
            recipes['series', series.sha256] = series_original.wire
            return history, series
        first, first_series = freeze(marks[:915], START, END)
        following, following_series = freeze(marks[900:930], END-900, END+900, first, 1)
        reader = SourceRecipeReader(OWNER, RUN, lambda kind, digest: recipes[kind, digest])
        self.assertEqual(reader('history', first.sha256).wire, first.wire)
        self.assertGreater(reader.cached_count, 900)
        reader.retain({('history', first.sha256)})
        self.assertEqual(reader.cached_count, 1)
        self.assertEqual(reader('history', following.sha256).wire, following.wire)
        self.assertEqual(reader('series', following_series.sha256).wire, following_series.wire)
        reader.retain({('history', following.sha256), ('series', following_series.sha256)})
        self.assertEqual(reader.cached_count, 2)


if __name__ == '__main__':
    unittest.main()
