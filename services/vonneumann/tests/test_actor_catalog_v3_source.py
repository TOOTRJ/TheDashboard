"""Offline source grammar tests; no native installation or database authority."""
import hashlib
import json
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "db-contract/research/jupiter_actor_catalog_v3.sql"
LOADER = runpy.run_path(str(ROOT / "db-contract/research/actor_catalog_v3_source.py"))
SOURCE_SHA256 = "84b3167c6626911fd231f2eeb337e1df4ab645a89c723017ecb169cdabf93cad"
POLICY_SHA256 = "2618f8f4239460112df4b7b21138f103f265353233d35e779e874431057a7c06"


def extract(raw=None, *, digest=SOURCE_SHA256, policy=POLICY_SHA256):
    return LOADER["extract_source"](SQL.read_bytes() if raw is None else raw,
                                    expected_package_sha256=digest,
                                    expected_policy_sha256=policy)


class ActorCatalogV3SourceTests(unittest.TestCase):
    def refuse_rehashed(self, raw):
        with self.assertRaises(LOADER["SourceRefusal"]) as caught:
            extract(raw, digest=hashlib.sha256(raw).hexdigest())
        self.assertEqual(str(caught.exception), "b1_source_refused")

    def test_source_first_exact_full_body_and_table_inventory(self):
        result = extract()
        self.assertEqual(result.package_sha256, SOURCE_SHA256)
        self.assertEqual(result.policy_sha256, POLICY_SHA256)
        functions = result.functions()
        self.assertEqual(len(functions), 8)
        self.assertEqual(len(result.tables()), 4)
        self.assertEqual(len({r["signature"] for r in functions}), 8)
        self.assertEqual(sum(r["spec"]["security_definer"] for r in functions), 2)
        for row in functions:
            spec = row["spec"]
            self.assertIs(spec["strict"], False)
            self.assertEqual(spec["source_package_sha256"], SOURCE_SHA256)
            self.assertEqual(spec["owner_role_name"], LOADER["OWNER"])
            self.assertEqual(spec["local_settings"], list(LOADER["LOCAL_SETTINGS"]))
            self.assertNotIn("catalog_manifest_sha256", spec)
        self.assertNotIn("CREATE ROLE", result.installer_sql)
        self.assertNotIn("CREATE ROLE", result.anchor_sql)
        self.assertTrue(result.installer_sql.startswith("CREATE TABLE " + LOADER["NAMESPACE"] + ".actor_bindings"))
        self.assertTrue(result.anchor_sql.startswith("CREATE TABLE " + LOADER["ANCHOR"] + ".installer_reference"))

    def test_self_rehashed_strict_security_type_and_guc_changes_refuse(self):
        raw = SQL.read_bytes()
        for old, new in ((b"CALLED ON NULL INPUT", b"STRICT"),
                         (b"SECURITY DEFINER", b"SECURITY INVOKER"),
                         (b"verify_scoped_actor(owner_id pg_catalog.text", b"verify_scoped_actor(owner_id pg_catalog.uuid"),
                         (b"SET TimeZone = 'UTC'", b"SET TimeZone = 'Europe/Paris'")):
            with self.subTest(replacement=new):
                if old.startswith(b"verify_scoped_actor("):
                    self.assertEqual(raw.count(old), 1)
                changed = raw.replace(old, new, 1)
                self.assertNotEqual(changed, raw)
                if old.startswith(b"verify_scoped_actor("):
                    self.assertEqual(changed.split(b"-- FUNCTION _c14n", 1)[0],
                                     raw.split(b"-- FUNCTION _c14n", 1)[0])
                self.refuse_rehashed(changed)

    def test_self_rehashed_unknown_outer_ddl_overload_and_comment_refuse(self):
        raw = SQL.read_bytes()
        for addition in (b"CREATE ROLE unrelated LOGIN;\n", b"-- unreviewed outer comment\n",
                         b"CREATE FUNCTION x(text) RETURNS text LANGUAGE sql AS 'select $1';\n"):
            self.refuse_rehashed(raw + addition)
        self.refuse_rehashed(raw.replace(b"-- FUNCTION _binding_core", b"-- FUNCTION _c14n", 1))

    def test_constructor_statement_and_missing_function_cannot_be_smuggled(self):
        raw = SQL.read_bytes()
        self.refuse_rehashed(raw.replace(b"fixture_id pg_catalog.text NOT NULL,",
                            b"fixture_id pg_catalog.text NOT NULL; CREATE ROLE other;", 1))
        self.refuse_rehashed(raw.replace(b"$b1$;\n\n-- FUNCTION _binding_core",
                                        b"$b1$;\n\n-- FUNCTION missing", 1))

    def test_wrong_held_package_policy_and_actual_bytes_type_refuse(self):
        for kwargs in ({"digest": "0" * 64}, {"policy": "0" * 64}):
            with self.assertRaises(LOADER["SourceRefusal"]):
                extract(**kwargs)
        for raw in (SQL.read_text(), bytearray(SQL.read_bytes()), b"", b"x" * 262145,
                    b"\xff", SQL.read_bytes().replace(b"\n", b"\r\n", 1)):
            with self.assertRaises(LOADER["SourceRefusal"]):
                extract(raw)

    def test_expected_scalar_types_and_returned_metadata_detached(self):
        result = extract()
        original = result.functions_json
        rows = result.functions()
        rows[0]["spec"]["strict"] = True
        rows.clear()
        self.assertEqual(result.functions_json, original)
        self.assertEqual(len(result.functions()), 8)
        for digest, policy in ((True, POLICY_SHA256), (SOURCE_SHA256, None),
                               (SOURCE_SHA256.upper(), POLICY_SHA256)):
            with self.assertRaises(LOADER["SourceRefusal"]):
                extract(digest=digest, policy=policy)

    def test_native_or_runtime_authority_not_in_source_projection(self):
        result = extract()
        self.assertEqual(set(result.__dataclass_fields__), {
            "package_sha256", "policy_sha256", "functions_json", "tables_json",
            "installer_sql", "anchor_sql",
        })
        self.assertNotIn("clock", json.dumps(result.functions()))
        self.assertFalse(hasattr(result, "install"))
        self.assertFalse(hasattr(result, "native_admission"))
