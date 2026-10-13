"""Inert proposal validation, not source/native/model conformance acceptance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from vonneumann.research import runtime_profile_v3_contract as contract

OWNER = '00000000-0000-0000-0000-000000000001'
RUN = '00000000-0000-0000-0000-000000000002'
MARKET = '00000000-0000-0000-0000-000000000003'
PROCESS = '00000000-0000-0000-0000-000000000004'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


class RuntimeProfileV3ProposalTests(unittest.TestCase):
    def setUp(self): self.profile = contract.proposal(OWNER, RUN, MARKET, PROCESS)

    def test_closed_proposal_roundtrip_is_stable_and_grants_no_authority(self):
        self.assertEqual(contract.decode_profile(self.profile.wire), self.profile)
        self.assertEqual(self.profile.sha256, hashlib.sha256(self.profile.wire).hexdigest())
        value = self.profile.to_dict()
        self.assertEqual(value['format'], 'paper-provider-runtime-profile-proposal-v3')
        self.assertEqual(value['status'], 'review_only_not_implemented')
        self.assertEqual(value['market']['account_currency'], 'USD')
        self.assertEqual(value['search']['genes'], ['ema_fast', 'ema_slow'])
        self.assertEqual(value['history']['parameters']['outlier'], 'false')
        self.assertEqual(value['history']['warmup_minutes'], '915')
        self.assertTrue(all(flag is False for flag in value['authority'].values()))
        self.assertTrue(all(digest is None for digest in value['implementation_bindings'].values()))
        self.assertFalse(self.profile.native_admission); self.assertFalse(self.profile.hosted_activation)
        self.assertFalse(self.profile.lease_acquisition)

    def test_valid_proposal_cannot_be_used_as_runtime_configuration(self):
        with self.assertRaises(contract.ProfileProposalError): contract.refuse_runtime_use(self.profile)
        with self.assertRaises(contract.ProfileProposalError): contract.ProfileProposal(self.profile.wire)

    def test_unknown_nested_fields_and_unsupported_versions_cannot_relabel_original_v2(self):
        for section in ['versions', 'price', 'history', 'epochs', 'implementation_bindings', 'authority']:
            value = self.profile.to_dict(); value[section]['unknown'] = 'x'
            with self.subTest(section=section), self.assertRaises(contract.ProfileProposalError): contract.decode_profile(canonical(value))
        for key, version in [('model', 'ga-portable-provider-model-research-v2'),
                ('checkpoint', 'ga-portable-provider-checkpoint-research-v2'), ('command', 5),
                ('source', 'ga-provider-source-research-v1'), ('receipt', 'ga-portable-native-receipt-lab-v1')]:
            value = self.profile.to_dict(); value['versions'][key] = version
            with self.subTest(version=version), self.assertRaises(contract.ProfileProposalError): contract.decode_profile(canonical(value))
        value = self.profile.to_dict(); value['market']['source'] = 'synthetic-exact-fixture-v1'
        with self.assertRaises(contract.ProfileProposalError): contract.decode_profile(canonical(value))

    def test_current_real_data_adapter_choices_and_open_retention_gates_are_pinned(self):
        for section, key, value in [('price', 'endpoint', 'https://lite-api.jup.ag/price/v2'),
                ('history', 'endpoint', 'https://api.jup.ag/history'), ('history', 'provider', 'jupiter-history'),
                ('retention', 'birdeye_rights', 'approved'), ('retention', 'birdeye_coverage', 'complete'),
                ('retention', 'jupiter', 'ask_user_again'), ('admission', 'cadence', '1'),
                ('implementation_bindings', 'native_catalog_sha256', 'a' * 64)]:
            altered = self.profile.to_dict(); altered[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(contract.ProfileProposalError): contract.decode_profile(canonical(altered))
        for key, value in [('outlier', 'true'), ('padding', 'true'), ('currency', 'native'), ('ui_amount_mode', 'scaled')]:
            altered = self.profile.to_dict(); altered['history']['parameters'][key] = value
            with self.subTest(key=key), self.assertRaises(contract.ProfileProposalError): contract.decode_profile(canonical(altered))

    def test_boolean_integer_aliases_floats_and_authority_claims_are_refused(self):
        for key in self.profile.to_dict()['authority']:
            value = self.profile.to_dict(); value['authority'][key] = True
            with self.subTest(key=key), self.assertRaises(contract.ProfileProposalError): contract.decode_profile(canonical(value))
        for section, key, value in [('search', 'population', 8), ('search', 'seed', True),
                ('freshness', 'max_receipt_age_us', 5000000.0), ('rpc', 'archive_request_response', 1)]:
            altered = self.profile.to_dict(); altered[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(contract.ProfileProposalError): contract.decode_profile(canonical(altered))

    def test_seed_bps_and_process_epoch_identity_bounds_are_explicit(self):
        maximum = contract.proposal(OWNER, RUN, MARKET, PROCESS, search_seed=str(2**64 - 1), account_loss_bps='10000')
        self.assertEqual(maximum.to_dict()['search']['seed'], str(2**64 - 1))
        for seed in ['01', '-1', '1.0', str(2**64), True, 0]:
            with self.subTest(seed=seed), self.assertRaises(contract.ProfileProposalError): contract.proposal(OWNER, RUN, MARKET, PROCESS, search_seed=seed)
        for bps in ['0', '10001', '03000', False]:
            with self.subTest(bps=bps), self.assertRaises(contract.ProfileProposalError): contract.proposal(OWNER, RUN, MARKET, PROCESS, account_loss_bps=bps)
        with self.assertRaises(contract.ProfileProposalError): contract.proposal(OWNER, RUN, MARKET, MARKET)
        with self.assertRaises(contract.ProfileProposalError): contract.proposal(OWNER.upper().replace('000000000001', 'AAAAAAAAAAAA'), RUN, MARKET, PROCESS)

    def test_wire_is_bounded_canonical_and_duplicate_free(self):
        for raw in [self.profile.wire + b' ', b'{"format":"x","format":"y"}', b'\xff',
                b'[' * 2000 + b']' * 2000, b'x' * (contract.MAX_PROFILE_BYTES + 1)]:
            with self.subTest(size=len(raw)), self.assertRaises(contract.ProfileProposalError): contract.decode_profile(raw)
        original = self.profile.to_dict(); copy = self.profile.to_dict(); copy['scope']['owner_id'] = RUN
        self.assertEqual(self.profile.to_dict(), original)
        with self.assertRaises(TypeError): contract.PROPOSED_VERSIONS['model'] = 'fake-v3'

    def test_new_proposal_never_allocates_identifiers_seeds_or_contacts_a_resource(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for target in ['uuid.uuid4', 'random.Random.seed', 'socket.getaddrinfo', 'socket.create_connection', 'socket.socket.connect']:
                stack.enter_context(patch(target, side_effect=AssertionError('Inert profile must not allocate or contact resources')))
            self.assertEqual(contract.proposal(OWNER, RUN, MARKET, PROCESS), self.profile)

    def test_import_boundary_excludes_old_models_provider_database_and_private_environment(self):
        project = Path(__file__).resolve().parents[1]
        code = '''
import importlib.abc, sys
class Boundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked=('dotenv','aiohttp','supabase','numpy','vonneumann.config','vonneumann.market','vonneumann.db','vonneumann.core',
                 'vonneumann.research.provider_portable_ga_model','vonneumann.research.provider_source')
        if any(fullname==item or fullname.startswith(item+'.') for item in blocked):
            raise AssertionError('Forbidden inert profile dependency: '+fullname)
sys.meta_path.insert(0,Boundary())
from vonneumann.research import runtime_profile_v3_contract
print('inert-profile-import-pass')
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=project,
            env={'PATH': '/usr/bin:/bin', 'PYTHONPATH': str(project), 'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(result.stdout.strip(), 'inert-profile-import-pass')


if __name__ == '__main__': unittest.main()
