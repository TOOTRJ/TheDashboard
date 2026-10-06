"""Offline source drift/dependency/manifest checks, without a database."""
from __future__ import annotations
import hashlib
import unittest
from unittest.mock import patch

from tests.postgres import canonical_fixture as fixture


class CanonicalV5PackageTests(unittest.TestCase):
    def test_committed_package_reproduces_and_contains_no_old_public_admission(self):
        sql, manifest=fixture.builder.build()
        self.assertEqual(fixture.package(), 'SET dashboard.contract_rehearsal=\'db03a1-isolated\';\n'+sql)
        self.assertEqual(manifest['admitted_command_versions'],[5])
        self.assertFalse(manifest['production_application_available'])
        self.assertFalse(manifest['credential_or_gateway_configuration'])
        self.assertEqual(hashlib.sha256(sql.encode()).hexdigest(),manifest['package_sha256'])
        self.assertNotIn('CREATE POLICY',sql)
        self.assertEqual(len(manifest['tables']),18)
        self.assertEqual(len([m for m in manifest['object_ddl'] if m['kind']=='table']),18)
        self.assertEqual(manifest['removed_core_functions'],[
            'vn_durability.rehearsal_config','vn_durability.rehearsal_evaluation',
            'vn_durability.validate_transition_after','vn_durability.validate_transition_before'])

    def test_dependency_source_drift_fails_closed(self):
        with patch.dict(fixture.builder.SOURCES, {'001_fenced_commands.sql':'0'*64}):
            with self.assertRaisesRegex(ValueError,'Reviewed dependency source changed'):
                fixture.builder.build()

    def test_duplicate_or_unreviewed_function_grammar_is_rejected(self):
        source='CREATE FUNCTION vn_read.x() RETURNS void LANGUAGE sql AS $$ SELECT 1 $$;'
        with self.assertRaisesRegex(ValueError,'grammar or overload'):
            fixture.builder.functions(source+'\n'+source)
        with self.assertRaisesRegex(ValueError,'grammar or overload'):
            fixture.builder.functions(source.replace('$$','$unreviewed$'))

    def test_unknown_callable_dependency_is_rejected(self):
        original=fixture.builder.functions
        def changed(source):
            if source.startswith('-- Canonical v5 admission'):
                source=source.replace('PERFORM vn_durability.provider_config(configuration);',
                    'PERFORM vn_durability.unreviewed_validator(configuration);')
            return original(source)
        with patch.object(fixture.builder,'functions',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Unknown callable dependency'):
                fixture.builder.build()

    def test_reviewed_entrypoint_grants_are_disjoint_and_helpers_are_private(self):
        _,manifest=fixture.builder.build()
        capabilities={role:{m['name'].split('.')[1] for m in manifest['functions'] if m['execute_role']==role}
                      for role in ('vn_economic','vn_relay','authenticated')}
        self.assertEqual(capabilities['vn_economic'],fixture.builder.ECONOMIC)
        self.assertEqual(capabilities['vn_relay'],fixture.builder.RELAY)
        self.assertEqual(capabilities['authenticated'],fixture.builder.READ)
        for a,b in (('vn_economic','vn_relay'),('vn_economic','authenticated'),('vn_relay','authenticated')):
            self.assertFalse(capabilities[a]&capabilities[b])
        names={m['name'] for m in manifest['functions']}
        for fn in manifest['functions']:
            self.assertLessEqual(set(fn['dependencies']),names)
