"""Pure B1 fixture policy cases; no native start, Docker or network calls."""
import copy
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest.mock import patch

from tests.security_support import deny_network
with deny_network():
    from tests.postgres import actor_catalog_v3_fixture as f
    from tests.postgres.harness import OPT_IN

PROJECT = Path(__file__).resolve().parents[3]


class ActorCatalogV3FixturePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = runpy.run_path(str(PROJECT / 'scripts/check-ci-images.py'))
        self.pin = next(pin for pin in self.policy['PINS'] if pin['tag'] == f.IMAGE_TAG)
        self.native_start = patch.object(f.IsolatedPostgres, 'start', side_effect=AssertionError('No native fixture'))
        self.native_start.start(); self.addCleanup(self.native_start.stop)
        self.no_process = patch.object(subprocess, 'run', side_effect=AssertionError('No subprocess'))
        self.process = self.no_process.start(); self.addCleanup(self.no_process.stop)

    def tearDown(self):
        self.process.assert_not_called()

    def identity(self, image):
        return {'image': f.IMAGE_TAG, 'image_id': image['Id'], 'postgres_version': '17.6'}

    def image(self, *, repository=None, identity=None):
        return {'Architecture': 'amd64', 'Os': 'linux', 'Id': identity or self.pin['config'],
                'RepoDigests': [(repository or self.pin['repository']) + '@' + self.pin['manifest']]}

    def check(self, metadata):
        original = copy.deepcopy(metadata)
        with deny_network():
            f.verify_owned_postgres_image(metadata, self.identity(metadata))
        self.assertEqual(metadata, original)

    def refuse(self, metadata, *, identity=None):
        original = copy.deepcopy(metadata)
        with deny_network(), self.assertRaisesRegex(RuntimeError, '^b1_owned_image_pin_mismatch$'):
            f.verify_owned_postgres_image(metadata, identity or self.identity(metadata))
        self.assertEqual(metadata, original)

    def test_current_original_amd64_config_and_manifest_ids(self):
        for identity in (self.pin['config'], self.pin['manifest']):
            with self.subTest(identity=identity):
                self.check(self.image(identity=identity))

    def test_current_proven_mirror_amd64_without_invented_ecr_digest(self):
        mirror = self.policy['MIRRORS'][self.pin['repository']]
        for repository in mirror['digest_repositories']:
            for identity in (self.pin['config'], self.pin['manifest']):
                with self.subTest(repository=repository, identity=identity):
                    image = self.image(repository=repository, identity=identity)
                    self.assertNotIn(self.pin['repository'] + '@' + self.pin['manifest'], image['RepoDigests'])
                    self.check(image)

    def test_wrong_amd64_digest_id_repository_and_os_refuse(self):
        for delta in ({'RepoDigests': []}, {'RepoDigests': None}, {'RepoDigests': [True]},
                      {'RepoDigests': self.pin['repository'] + '@' + self.pin['manifest']},
                      {'RepoDigests': ['foreign.invalid/postgres@' + self.pin['manifest']]},
                      {'RepoDigests': ['docker.io/supabase/postgrest@' + self.pin['manifest']]},
                      {'Id': 'sha256:' + '0' * 64}, {'Os': 'windows'}, {'Architecture': 'unknown'}):
            with self.subTest(delta=delta):
                self.refuse({**self.image(), **delta})

    def test_only_original_observed_arm_index_store_identity_is_retained(self):
        image = {'Architecture': 'arm64', 'Os': 'linux', 'Id': f.REPO_DIGEST.rsplit('@', 1)[1],
                 'RepoDigests': [f.REPO_DIGEST]}
        self.check(image)
        # Cross-platform aliasing cannot reuse the original ARM index as AMD.
        self.refuse({**image, 'Architecture': 'amd64'})
        self.refuse({**self.image(), 'Architecture': 'arm64'})

    def test_unmeasured_arm_leaf_config_mirror_and_foreign_store_refuse(self):
        index = f.REPO_DIGEST.rsplit('@', 1)[1]
        image = {'Architecture': 'arm64', 'Os': 'linux', 'Id': index, 'RepoDigests': [f.REPO_DIGEST]}
        for delta in ({'Id': 'sha256:35ebf7c6d3b77a430146b0a91974ed1fc14432b5741db4a3e41cd5f899b17f1a'},
                      {'Id': 'sha256:eb4503f2adfcd1e268644063ef506322beb669099d811b26c1b437de1bcfe3bf'},
                      {'RepoDigests': ['supabase/postgres@' + index]},
                      {'RepoDigests': []}, {'Os': 'windows'}):
            with self.subTest(delta=delta):
                self.refuse({**image, **delta})

    def test_wrong_harness_image_version_or_image_id_refuses(self):
        image = self.image()
        for delta in ({'image': 'foreign.invalid/postgres:17.6.1.095'}, {'postgres_version': '17.7'},
                      {'image_id': 'sha256:' + '0' * 64}):
            with self.subTest(delta=delta):
                self.refuse(image, identity={**self.identity(image), **delta})

    def test_actual_native_class_uses_canonical_opt_in_skip_reason(self):
        path = Path(f.__file__).with_name('test_actor_catalog_v3.py')
        spec = importlib.util.spec_from_file_location('b1_native_skip_policy_fixture', path)
        native = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {OPT_IN: '0'}), deny_network():
            spec.loader.exec_module(native)
        case = native.ActorCatalogV3NativeTests
        self.assertIs(case.__unittest_skip__, True)
        self.assertEqual(case.__unittest_skip_why__, 'Requires isolated PostgreSQL opt-in')
