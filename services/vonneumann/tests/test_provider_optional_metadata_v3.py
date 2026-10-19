"""Current Price OpenAPI nullable metadata; no provider/runtime acceptance."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import unittest

from tests.security_support import deny_network
with deny_network():
    from vonneumann.market import provider_acquisition_v3 as a,provider_derivation_v3 as d
    from vonneumann.market import prospective_source_v3 as s
    from tests.test_provider_acquisition_v3 import binding, capsule, observe, price_raw

PREVIOUS_ACQUISITION_POLICY = '6aee49826901fcb3730133e8611e4b9879d7717ac0d043565fca9a461dcc9244'
PREVIOUS_SOURCE_POLICY = '70a052bed268a16eb4506724457b142df0739fc598bc8ebb47bf054a87ddd4a5'


class ProviderOptionalMetadataV3Tests(unittest.TestCase):
    def setUp(self):
        self.network = deny_network(); self.network.__enter__()
        self.addCleanup(self.network.__exit__, None, None, None)

    def test_documented_null_change_metadata_preserves_exact_original_bytes(self):
        raw = b' '+price_raw(extra=',"createdAt":"2024-06-05T08:55:25.527Z","liquidity":621679197.67,"priceChange24h":null')+b'\n'
        original = capsule('jupiter-price-v3',raw)
        observation = observe(p=original)
        self.assertEqual(original.raw_body,raw)
        self.assertEqual(original.to_dict()['response_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(observation.to_dict()['price_decimal'],'100.123456789012345678')
        self.assertEqual(observation.to_dict()['block_ref'],'348004023')
        self.assertFalse(observation.provider_authenticated); self.assertFalse(observation.native_admission)
        self.assertNotIn('priceChange24h',observation.to_dict())

    def test_nonessential_null_and_numeric_change_do_not_change_price_or_economics(self):
        baseline=observe().to_dict()
        for token in ('null','0','-3','1.234567890123456789','1e-18'):
            with self.subTest(token=token):
                row=observe(p=capsule('jupiter-price-v3',price_raw(extra=',"priceChange24h":'+token))).to_dict()
                for key in ('price_decimal','block_ref','estimated_source_second','denomination','valuation'):
                    self.assertEqual(row[key],baseline[key])
                self.assertFalse(row['native_admission']); self.assertFalse(row['running_authority'])

    def test_nullable_change_does_not_allow_boolean_string_object_or_array(self):
        for token in ('true','false','"1.2"','{}','[]'):
            with self.subTest(token=token),self.assertRaises(a.AcquisitionError):
                observe(p=capsule('jupiter-price-v3',price_raw(extra=',"priceChange24h":'+token)))

    def test_documented_null_block_is_retained_but_cannot_create_source_observation(self):
        raw=price_raw(block='null',extra=',"priceChange24h":null')
        original=capsule('jupiter-price-v3',raw)
        self.assertEqual(original.raw_body,raw)
        with self.assertRaises(a.AcquisitionError):observe(p=original)

    def test_absent_optional_metadata_remains_explicit_minimal_profile_not_full_schema_claim(self):
        self.assertEqual(observe().to_dict()['price_decimal'],'100.123456789012345678')
        for token in ('null','true','"100"','0','-1'):
            with self.subTest(token=token),self.assertRaises(a.AcquisitionError):
                observe(p=capsule('jupiter-price-v3',price_raw(price=token,extra=',"priceChange24h":null')))

    def test_parser_policy_explicitly_changes_and_old_capsule_binding_is_unsupported(self):
        self.assertIn('nullable-change-v1',a.POLICY_FORMAT)
        self.assertNotEqual(a.POLICY_SHA256,PREVIOUS_ACQUISITION_POLICY)
        raw=price_raw(extra=',"priceChange24h":null')
        original=capsule('jupiter-price-v3',raw)
        old=original.to_dict();old['parser_policy_sha256']=PREVIOUS_ACQUISITION_POLICY
        with self.assertRaises(a.AcquisitionError):a.decode_capsule(a.canonical(old),binding())
        with self.assertRaises(a.AcquisitionError):replace(binding(),parser_policy_sha256=PREVIOUS_ACQUISITION_POLICY)
        self.assertEqual(original.raw_body,raw)

    def test_source_policy_binds_the_actual_acquisition_policy_digest(self):
        self.assertEqual(s._POLICY['acquisition_parser_policy_sha256'],a.POLICY_SHA256)
        self.assertEqual(s.POLICY_SHA256,hashlib.sha256(a.canonical(s._POLICY)).hexdigest())
        altered={**s._POLICY,'acquisition_parser_policy_sha256':PREVIOUS_ACQUISITION_POLICY}
        self.assertNotEqual(s.POLICY_SHA256,hashlib.sha256(a.canonical(altered)).hexdigest())
        self.assertNotEqual(s.POLICY_SHA256,PREVIOUS_SOURCE_POLICY)


if __name__=='__main__':unittest.main()
