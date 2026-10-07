"""Offline source/injection/secret boundary checks, no connection or credentials."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from tests.postgres import native_issuer_fixture as fixture


class NativeIssuerPackageTests(unittest.TestCase):
    def setUp(self):
        self.pair = fixture.Pair.new(str(uuid4()),str(uuid4()))

    def test_reviewed_sources_pin_dependency_and_have_no_production_entrypoint(self):
        sources = fixture.sources()
        declaration,_ = self.pair.declarations()
        sql = fixture.compose('issue.sql',declaration)
        self.assertEqual(set(sources),{'boundary.sql','issue.sql','revoke.sql'})
        self.assertEqual(sql.count('BEGIN;'),1)
        self.assertEqual(sql.count('COMMIT;'),1)
        self.assertIn('limited_native_issuer_required',sql)
        self.assertNotIn('CREATE FUNCTION',sql)
        self.assertNotIn('SECURITY DEFINER',sql)

    def test_native_auth_dependency_drift_refuses_composition(self):
        with patch.object(fixture,'BASE_SHA','0'*64):
            with self.assertRaisesRegex(ValueError,'dependency changed'):
                fixture.sources()

    def test_passwords_are_absent_from_repr_and_sql(self):
        declaration,verifiers = self.pair.declarations()
        for password in self.pair.passwords:
            self.assertNotIn(password,repr(self.pair))
            self.assertNotIn(password,declaration)
        self.assertEqual(len(set(verifiers)),2)
        self.assertTrue(all(value.startswith('SCRAM-SHA-256$4096:') for value in verifiers))

    def test_invalid_identity_and_password_inputs_cannot_reach_sql(self):
        for pair in (replace(self.pair,owner="'; DROP ROLE postgres; --"),
                     replace(self.pair,run=str(uuid4()).upper()),
                     replace(self.pair,names=("vn_native_x';",self.pair.names[1])),
                     replace(self.pair,names=(self.pair.names[0],self.pair.names[0])),
                     replace(self.pair,issuances=(self.pair.issuances[0],self.pair.issuances[0])),
                     replace(self.pair,passwords=("'; SELECT 1; --",self.pair.passwords[1])),
                     replace(self.pair,passwords=(self.pair.passwords[0],self.pair.passwords[0]))):
            with self.subTest(identity=pair.names):
                with self.assertRaises(ValueError): pair.declarations()

    def test_finite_lifetime_and_precision_bounds(self):
        for changes in ({'write_seconds':0},{'write_seconds':7201},{'recovery_seconds':86401},
                        {'recovery_seconds':1},{'write_seconds':True},{'write_seconds':float('nan')},
                        {'recovery_seconds':Decimal('Infinity')},{'delay_seconds':300},
                        {'delay_seconds':-1},{'write_seconds':Decimal('.0000001')}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): replace(self.pair,**changes).declarations()
        replace(self.pair,write_seconds=Decimal('.5'),recovery_seconds=1).declarations()

    def test_exact_revocation_oids_are_mandatory(self):
        # No container is instantiated; the source-only method reads no state.
        builder = object.__new__(fixture.LimitedIssuerPostgres)
        for oids in ((1,1),(True,2),(0,2),(1,2**32),[1,2]):
            with self.assertRaises(ValueError): builder.revoke_source(self.pair,oids)
        scope = fixture.Scope(self.pair.owner,self.pair.run,self.pair.names,self.pair.issuances)
        source = builder.revoke_source(scope,(123,456))
        self.assertIn('principal_oids oid[]:=ARRAY[123,456]',source)
        self.assertNotIn('DROP ROLE',source)
        self.assertNotIn('SCRAM',source)
        self.assertFalse(hasattr(scope,'passwords'))

    def test_source_hash_drift_is_rejected_before_sql_is_composed(self):
        with tempfile.TemporaryDirectory(prefix='dashboard-native-issuer-') as directory:
            target = Path(directory)
            for name in ('manifest.json','boundary.sql','issue.sql','revoke.sql'):
                (target/name).write_bytes((fixture.DIRECTORY/name).read_bytes())
            with (target/'issue.sql').open('a') as source:
                source.write('\n-- unreviewed source drift\n')
            with patch.object(fixture,'DIRECTORY',target):
                with self.assertRaisesRegex(ValueError,'source changed'):
                    fixture.compose('issue.sql',self.pair.declarations()[0])
