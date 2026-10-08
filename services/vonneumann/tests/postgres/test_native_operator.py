"""Actual bound inputs, limited invoker authority, logs and original-pair revoke."""
import json
import os
import unittest
from uuid import uuid4
from tests.postgres import forward_fixture as fixture, harness, native_issuer_fixture

operator = fixture.builder.module('bound_native_operator_test', native_issuer_fixture.DIRECTORY / 'operator.py')


@unittest.skipUnless(os.environ.get(harness.OPT_IN) == '1', 'Requires isolated PostgreSQL opt-in')
class NativeOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = fixture.start(cls)
        fixture.install(cls.db)
        cls.db.sql("ALTER DATABASE postgres SET log_statement='ddl'; ALTER DATABASE postgres SET log_parameter_max_length_on_error=0; "
                   "ALTER DATABASE postgres SET pgaudit.log='none';", role=fixture.ADMIN)
        cls.db.sql(operator.install())

    def setUp(self):
        self.owner, self.run = str(uuid4()), str(uuid4())
        self.db.sql(f"INSERT INTO auth.users(id) VALUES('{self.owner}');", role=fixture.ADMIN)
        self.pair = native_issuer_fixture.Pair.new(self.owner, self.run)
        self.verifiers = [native_issuer_fixture.scram_verifier(p) for p in self.pair.passwords]
        self.input = {'owner': self.owner, 'run': self.run, 'names': self.pair.names,
                      'issuances': self.pair.issuances, 'verifiers': self.verifiers,
                      'write_seconds': 300, 'recovery_seconds': 600, 'delay_seconds': 0}

    def call(self, name, value, role='postgres', set_role=None):
        # psql 17 extended-protocol bind; no secrets in the SQL statement text.
        encoded = json.dumps(value).replace("'", "''")
        prefix = '' if set_role is None else 'SET ROLE ' + set_role + ';\n'
        return self.db.sql(prefix + f"SELECT {operator.SCHEMA}.{name}($1::jsonb)\n\\bind '{encoded}'\n\\g\n", role=role, check=False)

    def logs(self):
        value = self.db._command(['logs', self.db._container_id]).stderr
        for secret in (*self.pair.passwords, *self.verifiers):
            self.assertNotIn(secret, value)
        return value

    def test_bound_pair_can_authenticate_and_revoke_without_logging_material(self):
        result = self.call('issue', self.input)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual([r['capability'] for r in rows], ['economic', 'relay'])
        for name, password, capability in zip(self.pair.names, self.pair.passwords, ('economic', 'relay')):
            self.db.write_private(name + '.pgpass', f'*:5432:postgres:{name}:{password}\n')
            self.assertEqual(self.db.native(name, capability, 'SELECT current_user;').stdout.strip(), 'vn_' + capability)
        revoke = {k: self.input[k] for k in ('owner', 'run', 'names', 'issuances')}
        revoke['oids'] = [r['oid'] for r in rows]
        result = self.call('revoke', revoke)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(r['revoked'] and not r['login'] for r in json.loads(result.stdout)))
        self.logs()

    def test_original_pair_collision_is_atomic_and_error_context_has_no_verifier(self):
        self.db.sql(f'CREATE ROLE {self.pair.names[1]} NOLOGIN;')
        result = self.call('issue', self.input)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('native_operator_failed', result.stderr)
        for secret in (*self.pair.passwords, *self.verifiers):
            self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(self.db.scalar(f"SELECT count(*) FROM pg_roles WHERE rolname='{self.pair.names[0]}';"), '0')
        self.logs()

    def test_api_and_capability_roles_cannot_invoke_installer(self):
        for role in ('anon', 'authenticated', 'service_role', 'vn_economic', 'vn_relay'):
            result = self.call('issue', self.input, fixture.ADMIN, set_role=role)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('42501', result.stderr)
        self.assertEqual(self.db.scalar(f"SELECT count(*) FROM pg_roles WHERE rolname=ANY(ARRAY['{self.pair.names[0]}','{self.pair.names[1]}']);"), '0')

    def test_installer_is_invoker_not_an_elevated_function_and_can_be_removed(self):
        source = self.db.scalar(f"SELECT jsonb_build_object('owner',proowner='postgres'::regrole,'definer',prosecdef,'settings',proconfig) FROM pg_proc WHERE oid='{operator.SCHEMA}.issue(jsonb)'::regprocedure;")
        self.assertEqual(json.loads(source), {'owner': True, 'definer': False, 'settings': None})
        # The tracked release catalog is unchanged even while this unexposed
        # operator schema exists; removing it needs no durable-schema rewrite.
        self.db.sql((fixture.HERE / 'verify.sql').read_text())
        self.db.sql(operator.remove())
        self.assertEqual(self.db.scalar(f"SELECT to_regnamespace('{operator.SCHEMA}') IS NULL;"), 't')
        self.db.sql(operator.install())
