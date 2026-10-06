"""Offline composition checks; opt-in authentication tests live separately."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from tests.postgres import session_auth_fixture as fixture


class SessionAuthPackageTests(unittest.TestCase):
    def test_artifacts_reproduce_without_credentials_or_activation(self):
        sql,manifest=fixture.builder.build()
        self.assertEqual(fixture.package(),"SET dashboard.contract_rehearsal='db03a1-isolated';\n"+sql)
        self.assertFalse(manifest['production_application_available'])
        self.assertFalse(manifest['provisioned_credentials'])
        self.assertEqual(manifest['supported_connection_profiles'],['direct_tls_scram'])
        self.assertEqual(fixture.builder.base.sha(sql),manifest['package_sha256'])
        self.assertEqual(sql.count('BEGIN;'),1)
        self.assertEqual(sql.count('COMMIT;'),1)
        self.assertNotIn('CREATE ROLE vn_native_',sql)

    def test_pinned_base_drift_fails_closed(self):
        with patch.object(fixture.builder,'BASE_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'Reviewed v5 dependency changed'):
                fixture.builder.build()

    def test_all_successful_returns_and_admission_paths_are_guarded(self):
        sql,manifest=fixture.builder.build()
        operations={g['name'].split('.')[1] for g in manifest['guarded_functions']}
        self.assertEqual(operations,fixture.builder.base.ECONOMIC|fixture.builder.base.RELAY)
        for guard in manifest['guarded_functions']:
            name=guard['name'];operation=name.split('.')[1]
            ddl=sql[sql.index('CREATE OR REPLACE FUNCTION '+name+'('):]
            ddl=ddl[:ddl.index('END $$;')]
            call=f"PERFORM vn_access.require_actor(owner_id,run,'{guard['capability']}','{operation}');"
            self.assertEqual(ddl.count(call),guard['successful_returns']+1)

    def test_role_authentication_has_no_caller_claim_or_current_user_dependency(self):
        access=(fixture.DIRECTORY/'access.sql').read_text()
        self.assertIn('system_user IS DISTINCT FROM',access)
        self.assertIn('rolname=session_user',access)
        self.assertNotIn('current_setting',access)
        self.assertNotIn('auth.uid()',access)
        self.assertNotIn('current_user',access)

    def test_unreviewed_inline_return_grammar_fails_closed(self):
        build=fixture.builder.base.build
        def changed():
            sql,manifest=build()
            sql=sql.replace('    RETURN existing.response;', '    IF true THEN RETURN existing.response; END IF;')
            return sql,manifest
        # Digest admission rejects modified pinned grammar before rewriting it.
        with patch.object(fixture.builder.base,'build',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Reviewed v5 dependency changed'):
                fixture.builder.build()
