"""DRAFT actual owned B1 acceptance cases; no fixture run authorized yet.

No provider/real project is accessed. Existing explicit PostgreSQL opt-in and
concrete parent review are required. Outcomes may describe actor/catalog facts
only; all source/native/runtime limits remain literal false.
"""
from contextlib import contextmanager
import hashlib
import json
import os
import unittest
from uuid import UUID

from tests.postgres.harness import IsolatedPostgres, OPT_IN
from tests.postgres import actor_catalog_v3_fixture as f


LIMITS = {key: False for key in (
    "provider_attested", "calibrated_clock", "original_identity_registry", "epoch_registry",
    "source_freshness", "capture_retention", "native_source_admission", "committed_packet_readback",
    "terminal_resolution", "availability_authority", "complete_inventory", "history_seal",
    "model_native_join", "lease_authority", "hosted_authority", "running_authority", "live_trading_authority",
)}


@unittest.skipUnless(os.environ.get(OPT_IN) == "1", "Requires isolated PostgreSQL opt-in")
class ActorCatalogV3NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Held source validation precedes even the owned harness startup.
        cls.source = f.SRC["extract_source"](f.SQL.read_bytes(), expected_package_sha256=f.SOURCE_SHA256,
            expected_policy_sha256=f.POLICY_SHA256)
        cls.db = IsolatedPostgres()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()
        cls.receipt = f.prepare_actor_catalog(cls.db)

    def query(self, serial=0, *, function="verify_scoped_actor", arguments=None):
        scope = f.FAKE_SCOPES[serial // 4]
        if arguments is None:
            arguments = (*scope, "verify_actor" if function == "verify_scoped_actor" else str(UUID(int=101 + serial)))
        values = ",".join("NULL::text" if v is None else f.literal(v) + "::text" for v in arguments)
        return f"SELECT {f.N}.{function}({values});"

    def evidence(self, serial=0):
        return json.loads(self.db.scalar(self.query(serial), role=f.ACTORS[serial], timeout=30))

    def refuse(self, command, *, role=None, state="55000", message="b1_actor_catalog_refused"):
        result = self.db.sql(command, role=f.ACTORS[0] if role is None else role, check=False, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(state, result.stderr)
        self.assertIn(message, result.stderr)
        return result

    @contextmanager
    def mutate(self, command, undo):
        self.db.sql(command, timeout=30)
        try:
            yield
        finally:
            self.db.sql(undo, timeout=30)
            self.evidence()

    def test_all_eight_actual_sessions_share_K_with_distinct_verified_identity(self):
        values = []
        for serial, actor in enumerate(f.ACTORS):
            self.assertEqual(self.db.scalar("SELECT session_user;", role=actor), actor)
            value = self.evidence(serial)
            self.assertEqual(set(value), {"format", "actor_catalog_policy_sha256", "scope",
                "principal_binding_id", "session_user_oid", "session_user_name", "profile", "capability_checked",
                "actor_catalog_package_sha256", "installation_manifest_sha256", "accepted_catalog_sha256",
                "observed_catalog_sha256", "role_closure_sha256", "limits"})
            self.assertEqual(value["format"], "ga-jupiter-actor-catalog-evidence-research-v3-b1-v3")
            self.assertEqual(value["actor_catalog_policy_sha256"], f.POLICY_SHA256)
            self.assertEqual(value["actor_catalog_package_sha256"], f.SOURCE_SHA256)
            self.assertEqual(value["session_user_name"], actor)
            self.assertEqual(value["session_user_oid"], self.db.scalar("SELECT oid::text FROM pg_catalog.pg_roles WHERE rolname=" + f.literal(actor) + ";"))
            self.assertEqual(value["scope"], dict(zip(("owner_id", "run_id", "market_epoch"), f.FAKE_SCOPES[serial // 4])))
            self.assertEqual(value["principal_binding_id"], str(UUID(int=101 + serial)))
            self.assertEqual(value["capability_checked"], "verify_actor")
            self.assertEqual(value["limits"], LIMITS)
            self.assertTrue(all(v is False for v in value["limits"].values()))
            self.assertEqual(value["observed_catalog_sha256"], self.receipt["pins"]["K"])
            self.assertEqual(value["accepted_catalog_sha256"], self.receipt["pins"]["K"])
            self.assertLessEqual(len(f.canonical(value)), 8192)
            values.append(value)
        self.assertEqual(len({x["session_user_oid"] for x in values}), 8)
        self.assertEqual(len({x["observed_catalog_sha256"] for x in values}), 1)

    def test_found_foreign_and_unknown_lookup_no_identity_or_scope_oracle(self):
        own = json.loads(self.db.scalar(self.query(function="get_scoped_binding"), role=f.ACTORS[0], timeout=30))
        self.assertEqual(own["resolution"], "found")
        self.assertEqual(own["evidence"]["principal_binding_id"], str(UUID(int=101)))
        absent = []
        for identifier in (str(UUID(int=105)), str(UUID(int=909))):
            result = json.loads(self.db.scalar(self.query(function="get_scoped_binding", arguments=(*f.FAKE_SCOPES[0], identifier)), role=f.ACTORS[0], timeout=30))
            self.assertEqual(result["resolution"], "absent")
            self.assertIsNone(result["evidence"])
            self.assertEqual(result["limits"], LIMITS)
            self.assertTrue(all(v is False for v in result["limits"].values()))
            result.pop("requested_binding_id")
            absent.append(result)
        self.assertEqual(*absent)
        self.refuse(self.query(arguments=(*f.FAKE_SCOPES[1], "verify_actor")))

    def test_each_NULL_position_reaches_fixed_body_refusal_both_entries(self):
        for function in ("verify_scoped_actor", "get_scoped_binding"):
            original = [*f.FAKE_SCOPES[0], "verify_actor" if function == "verify_scoped_actor" else str(UUID(int=101))]
            for index in range(4):
                values = original.copy()
                values[index] = None
                with self.subTest(function=function, index=index):
                    self.refuse(self.query(function=function, arguments=values), state="22023", message="b1_invalid_input")
        rows = json.loads(self.db.scalar(f"SELECT json_agg(json_build_object('strict',proisstrict,'args',proargtypes::text,'defaults',pronargdefaults,'variadic',provariadic::text)) FROM pg_catalog.pg_proc WHERE oid IN('{f.N}.verify_scoped_actor(text,text,text,text)'::regprocedure,'{f.N}.get_scoped_binding(text,text,text,text)'::regprocedure);"))
        self.assertTrue(all(x["strict"] is False and x["defaults"] == 0 and x["variadic"] == "0" for x in rows))

    def test_canonical_finalTEXT_and_explicit_equivalent_CAST_boundary(self):
        a, b, c = f.FAKE_SCOPES[0]
        self.assertEqual(json.loads(self.db.scalar(f"SELECT {f.N}.verify_scoped_actor({f.literal(a)}::uuid::text,{f.literal(b)}::text,{f.literal(c)}::text,'verify_actor'::text);", role=f.ACTORS[0], timeout=30))["session_user_name"], f.ACTORS[0])
        for values in ((" " + a, b, c, "verify_actor"), ("AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA", b, c, "verify_actor"),
                       (a, b, c, "VERIFY_ACTOR"), (a, b, c, "source_admit"), (a, b, c, "x" * 4097)):
            self.refuse(self.query(arguments=values), state="22023", message="b1_invalid_input")

    def test_actor_and_installer_private_reads_writes_helpers_replacement_deny(self):
        for role in (f.ACTORS[0], "vn_jupiter_b1_installer"):
            for command in (f"SELECT * FROM {f.A}.installer_reference;", f"UPDATE {f.A}.installer_reference SET fixture_id=fixture_id;",
                            f"SELECT * FROM {f.N}.actor_bindings;", f"UPDATE {f.N}.accepted_pins SET singleton=singleton;",
                            f"SELECT {f.N}._catalog_preimage();", f"CREATE TABLE {f.N}.unreviewed(x int);",
                            f"ALTER FUNCTION {f.N}.verify_scoped_actor(text,text,text,text) STRICT;", f"SET ROLE {f.OWNER};"):
                self.refuse(command, role=role, state="42501", message="")
        self.evidence()
        self.assertEqual(self.db.scalar(f"SELECT count(*) FROM pg_catalog.pg_auth_members WHERE member=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='vn_jupiter_b1_installer') OR roleid=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname={f.literal(f.OWNER)});"), "0")

    def test_pg17_MAINTAIN_and_actual_ANALYZE_denial_then_catalog_drift(self):
        table = f.N + ".actor_bindings"
        before_acl = f.actor_bindings_acl(self.db)
        before_k, _ = f.original_bootstrap_preimage(self.db, "_catalog_preimage")
        self.assertEqual(before_k, self.receipt["pins"]["K"])
        for role in f.ACTORS:
            with self.subTest(role=role):
                # Fresh actual role connection: no SET ROLE, superuser or
                # database-owner exemption can make the denial meaningless.
                identity = json.loads(self.db.scalar(
                    "SELECT json_build_object('session',session_user::text,"
                    "'superuser',r.rolsuper,'database_owner',d.datdba=r.oid) "
                    "FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_database d "
                    "WHERE r.rolname=session_user AND d.datname=current_database();",
                    role=role))
                self.assertEqual(identity, {"session": role, "superuser": False, "database_owner": False})
                self.assertEqual(self.db.scalar(
                    f"SELECT has_table_privilege({f.literal(role)},{f.literal(table)},'MAINTAIN');"), "f")
                result = self.db.sql(f"ANALYZE {table};", role=role, check=False, timeout=30)
                # PostgreSQL17 deliberately warns/skips and may exit zero.
                self.assertEqual(result.returncode, 0)
                self.assertIn('permission denied to analyze "actor_bindings", skipping it', result.stderr)
        role = f.ACTORS[0]
        self.db.sql(f"GRANT MAINTAIN ON TABLE {table} TO {role};", timeout=30)
        try:
            self.assertEqual(self.db.scalar(
                f"SELECT has_table_privilege({f.literal(role)},{f.literal(table)},'MAINTAIN');"), "t")
            allowed = self.db.sql(f"ANALYZE {table};", role=role, check=False, timeout=30)
            self.assertEqual(allowed.returncode, 0)
            self.assertNotIn("permission denied", allowed.stderr.lower())
            self.assertNotIn("skipping", allowed.stderr.lower())
            self.assertGreater(int(self.db.scalar(
                f"SELECT count(*) FROM pg_catalog.pg_statistic WHERE starelid={f.literal(table)}::regclass;")), 0)
            # The controlled grant is still forbidden package/catalog drift.
            self.refuse(self.query())
        finally:
            self.db.sql(f"REVOKE MAINTAIN ON TABLE {table} FROM {role};", timeout=30)
            after_acl = f.actor_bindings_acl(self.db)
            self.assertEqual(after_acl, before_acl)
            restored_k, _ = f.original_bootstrap_preimage(self.db, "_catalog_preimage")
            self.assertEqual(restored_k, before_k)
            self.evidence()
        # Ordinary authorized maintenance changes statistics, not the full
        # catalog identity. It must not require accepting any replacement K.
        ordinary = self.db.sql(f"ANALYZE {table};", role="postgres", check=False, timeout=30)
        self.assertEqual(ordinary.returncode, 0)
        self.assertNotIn("permission denied", ordinary.stderr.lower())
        self.assertNotIn("skipping", ordinary.stderr.lower())
        after_analyze_k, _ = f.original_bootstrap_preimage(self.db, "_catalog_preimage")
        self.assertEqual(after_analyze_k, before_k)
        self.assertEqual(f.actor_bindings_acl(self.db), before_acl)
        self.evidence()

    def test_temp_shadow_preserves_shared_TEMP_and_qualified_guard(self):
        command = "CREATE TEMP TABLE actor_bindings(x int); CREATE TEMP TABLE installer_reference(x int);" + self.query()
        value = json.loads(self.db.scalar(command, role=f.ACTORS[0], timeout=30))
        self.assertEqual(value["observed_catalog_sha256"], self.receipt["pins"]["K"])
        self.assertEqual(value["session_user_name"], f.ACTORS[0])

    def test_independent_source_body_and_native_guard_drift_refusal(self):
        declaration = self.source.installer_sql.split(f"CREATE FUNCTION {f.N}._binding_core()", 1)[1].split("$b1$;", 1)[0]
        original = f"CREATE OR REPLACE FUNCTION {f.N}._binding_core()" + declaration + "$b1$;"
        modified = original.replace("\nBEGIN\n", "\n-- altered original source\nBEGIN\n", 1)
        self.assertNotEqual(modified, original)
        with self.mutate(modified, original):
            with self.assertRaisesRegex(RuntimeError, "b1_source_function_definition_mismatch"):
                f._source_function_rows(self.db, self.source, sealed=True)
            self.refuse(self.query())

    def test_strict_header_and_helper_execute_ACL_drift_refuse(self):
        sig = f"{f.N}.verify_scoped_actor(text,text,text,text)"
        with self.mutate(f"ALTER FUNCTION {sig} STRICT;", f"ALTER FUNCTION {sig} CALLED ON NULL INPUT;"):
            with self.assertRaisesRegex(RuntimeError, "b1_source_function_definition_mismatch"):
                f._source_function_rows(self.db, self.source, sealed=True)
            self.refuse(self.query())
        with self.mutate(f"GRANT EXECUTE ON FUNCTION {f.N}._binding_core() TO {f.ACTORS[0]};", f"REVOKE EXECUTE ON FUNCTION {f.N}._binding_core() FROM {f.ACTORS[0]};"):
            self.refuse(self.query())

    def test_role_rename_dangerous_attribute_and_SET_membership_refuse(self):
        role = f.ACTORS[0]
        with self.mutate(f"ALTER ROLE {role} RENAME TO vn_jupiter_b1_renamed;", f"ALTER ROLE vn_jupiter_b1_renamed RENAME TO {role};"):
            self.refuse(self.query(), role="vn_jupiter_b1_renamed")
        with self.mutate(f"ALTER ROLE {role} CREATEROLE;", f"ALTER ROLE {role} NOCREATEROLE;"):
            self.refuse(self.query())
        with self.mutate(f"GRANT vn_jupiter_b1_installer TO {role} WITH INHERIT FALSE, SET TRUE, ADMIN FALSE;", f"REVOKE vn_jupiter_b1_installer FROM {role};"):
            self.refuse(self.query())

    def test_PUBLIC_parameter_privilege_not_omitted_from_all_actor_union(self):
        with self.mutate("GRANT SET ON PARAMETER session_replication_role TO PUBLIC;", "REVOKE SET ON PARAMETER session_replication_role FROM PUBLIC;"):
            self.assertNotEqual(self.db.scalar("SELECT count(*) FROM pg_catalog.pg_parameter_acl p CROSS JOIN LATERAL pg_catalog.aclexplode(p.paracl) a WHERE a.grantee=0;"), "0")
            self.refuse(self.query())

    def test_complete_node_bound64_and_overflow65_no_truncation(self):
        roles = ["vn_jupiter_b1_bound_" + str(i) for i in range(57)]
        self.db.sql("".join(f"CREATE ROLE {r} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;" for r in roles), timeout=30)
        try:
            self.db.sql("".join(f"GRANT {r} TO {f.ACTORS[0]} WITH ADMIN FALSE, INHERIT FALSE, SET FALSE;" for r in roles[:56]), timeout=30)
            value = json.loads(self.db.scalar(f.SETTINGS_SQL + f"SELECT {f.N}._role_closure();", timeout=30))
            self.assertEqual(len(value["nodes"]), 64)
            self.assertEqual(len(value["edges"]), 56)
            self.db.sql(f"GRANT {roles[-1]} TO {f.ACTORS[0]} WITH ADMIN FALSE, INHERIT FALSE, SET FALSE;")
            self.refuse(f.SETTINGS_SQL + f"SELECT {f.N}._role_closure();", role="postgres")
            self.refuse(self.query())
        finally:
            self.db.sql("".join(f"REVOKE {r} FROM {f.ACTORS[0]}; DROP ROLE {r};" for r in roles), timeout=30)
            self.evidence()

    def test_excluded_pins_and_current_drift_digest_do_not_become_gold(self):
        for table, column, old in ((f.N + ".accepted_pins", "catalog_manifest_sha256", self.receipt["pins"]["K"]),
                                   (f.N + ".actor_bindings", "installation_manifest_sha256", self.receipt["pins"]["M"])):
            with self.mutate(f"UPDATE {table} SET {column}={f.literal('a'*64)};", f"UPDATE {table} SET {column}={f.literal(old)};"):
                self.refuse(self.query())
        with self.mutate(f"ALTER TABLE {f.N}.actor_bindings ALTER COLUMN profile SET STORAGE MAIN;", f"ALTER TABLE {f.N}.actor_bindings ALTER COLUMN profile SET STORAGE EXTENDED; UPDATE {f.N}.accepted_pins SET catalog_manifest_sha256={f.literal(self.receipt['pins']['K'])};"):
            with self.assertRaisesRegex(RuntimeError, "b1_source_table_mismatch"):
                f.compare_source_constructors(self.db, self.source)
            value = json.loads(self.db.scalar(f.SETTINGS_SQL + f"SELECT {f.N}._catalog_preimage();", timeout=30))
            current = hashlib.sha256(f.canonical(value)).hexdigest()
            self.assertNotEqual(current, self.receipt["pins"]["K"])
            self.db.sql(f"UPDATE {f.N}.accepted_pins SET catalog_manifest_sha256={f.literal(current)};")
            self.refuse(self.query())

    def test_no_extra_roots_overloads_or_B2_B9_capability(self):
        with self.mutate(f"CREATE TABLE {f.N}.extra(x int);", f"DROP TABLE {f.N}.extra;"):
            self.refuse(self.query())
        with self.mutate(f"CREATE FUNCTION {f.N}.verify_scoped_actor(text) RETURNS text LANGUAGE sql AS 'SELECT $1';", f"DROP FUNCTION {f.N}.verify_scoped_actor(text);"):
            self.refuse(self.query())
        self.assertEqual(self.db.scalar(f"SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN({f.literal(f.N)},{f.literal(f.A)});"), "8")
        self.assertEqual(self.evidence()["limits"], LIMITS)
        self.assertFalse(self.receipt["native_source_or_runtime_authority"])

    def test_z_role_recreation_cannot_reuse_original_OID_binding(self):
        # Last mutation is intentionally terminal for this owned fixture. No
        # new OID is relabeled as the previously accepted scoped binding.
        role = f.ACTORS[-1]
        old_oid = self.db.scalar("SELECT oid::text FROM pg_catalog.pg_roles WHERE rolname=" + f.literal(role) + ";")
        self.db.sql(f"DROP OWNED BY {role}; DROP ROLE {role}; CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; GRANT USAGE ON SCHEMA {f.N} TO {role}; GRANT EXECUTE ON FUNCTION {f.N}.verify_scoped_actor(text,text,text,text),{f.N}.get_scoped_binding(text,text,text,text) TO {role};", timeout=30)
        self.assertNotEqual(self.db.scalar("SELECT oid::text FROM pg_catalog.pg_roles WHERE rolname=" + f.literal(role) + ";"), old_oid)
        self.refuse(self.query(7), role=role)
