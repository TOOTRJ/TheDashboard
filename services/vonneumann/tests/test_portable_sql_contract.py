"""Source/package boundaries of the original-v2 SQL laboratory, no Docker/network."""
import hashlib
import json
from pathlib import Path
import re
import unittest

from tests.security_support import OfflineTestMixin
from vonneumann.research import numeric_wire as numbers,provider_portable_ga_model as model

ROOT=Path(__file__).resolve().parents[1]
SQL=ROOT/'db-contract/research'


class PortableSqlContractTests(OfflineTestMixin,unittest.TestCase):
    def test_trusted_configuration_literal_matches_every_original_v2_tag_and_policy(self):
        source=(SQL/'portable_configuration.sql').read_text()
        literal=re.search(r" SELECT '([^']+)'::jsonb\n\$function\$;",source).group(1)
        expected=model.GAConfig('genetic_algorithm','00000000-0000-0000-0000-000000000000',
            '00000000-0000-0000-0000-000000000000',asset='SOL/USD').to_dict()
        self.assertEqual(literal.encode(),numbers.encode(expected))
        self.assertEqual(json.loads(literal)['lifecycle_policy']['max_lifespan_seconds'],{'$integer':'0'})

    def test_original_sql_and_model_policies_are_preserved_by_the_v2_fork(self):
        manifest=json.loads((ROOT/'research/portable-sql-source-contract.json').read_text())
        for relative,digest in manifest['original_v1_sources_sha256'].items():
            with self.subTest(path=relative):self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),digest)
        self.assertEqual(manifest['original_model_format'],model.MODEL_FORMAT)
        self.assertEqual(manifest['authority'],{'native_admission':False,'restoration':False,'hosted':False})

    def test_original_v2_guarded_artifacts_bind_exact_source_inventory(self):
        manifest=json.loads((ROOT/'research/portable-sql-source-contract.json').read_text())
        for relative,digest in manifest['portable_sql_sources_sha256'].items():
            with self.subTest(path=relative):self.assertEqual(hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),digest)
        self.assertEqual(len(manifest['portable_sql_sources_sha256']),12)
        self.assertEqual(manifest['reviewed_type_repair'],'PAPER-COMPACT-TYPE1')
        self.assertEqual(manifest['complete_entry_point'],'vn_portable_semantic_research.validate_request(uuid,uuid,text)')

    def test_frozen_unicode15_nonprintable_intervals_match_all_original_python_scalars(self):
        source=(SQL/'portable_transition.sql').read_text()
        literal=re.search(r"invalid int4multirange:='([^']+)'::int4multirange",source).group(1)
        allowed=bytearray(b'\x01')*0x110000
        previous=0
        for lo,hi in re.findall(r'\[([0-9]+),([0-9]+)\)',literal):
            lo,hi=int(lo),int(hi)
            self.assertGreaterEqual(lo,previous);self.assertGreater(hi,lo);self.assertLessEqual(hi,0x110000)
            allowed[lo:hi]=bytes(hi-lo);previous=hi
        for point,printable in enumerate(allowed):
            if bool(printable)!=chr(point).isprintable():self.fail(f'Unicode15 printable policy differs at U+{point:04X}')
