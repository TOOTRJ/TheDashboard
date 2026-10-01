"""Real database checks for the isolation and connection contract itself."""

import os
import unittest

from .harness import BOOTSTRAP, CONTRACT, IsolatedPostgres, OPT_IN


@unittest.skipUnless(os.environ.get(OPT_IN) == "1", "Explicit isolated PostgreSQL opt-in required")
class HarnessSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = IsolatedPostgres()
        cls.addClassCleanup(cls.db.close)
        cls.db.start()

    def test_server_and_client_roles(self):
        self.assertEqual(self.db.scalar("SHOW server_version_num;"), "170006")
        self.assertEqual(self.db.scalar("SHOW fsync;"), "on")
        self.assertEqual(self.db.identity["network"], "none")
        self.assertTrue(self.db.identity["image_id"].startswith("sha256:"))
        for role in ("anon", "authenticated", "service_role"):
            self.assertEqual(self.db.scalar("SELECT current_user;", role=role), role)
            self.assertEqual(self.db.scalar(
                "SELECT rolsuper FROM pg_roles WHERE rolname = current_user;", role=role), "f")
        self.assertEqual(self.db.scalar(
            "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user;", role="service_role"), "t")
        self.assertEqual(self.db.scalar(
            "SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
            "WHERE r.rolname IN ('anon', 'authenticated', 'service_role', 'vn_contract_owner');"), "0")

    def test_independent_connections_observe_only_committed_state(self):
        self.db.sql("CREATE TABLE public.harness_smoke (value integer NOT NULL); "
                    "CREATE TABLE public.harness_gate (released boolean NOT NULL); "
                    "INSERT INTO public.harness_gate VALUES (false);")
        held = self.db.begin_sql(
            "BEGIN; INSERT INTO public.harness_smoke VALUES (1); "
            "SELECT pg_advisory_lock(824973); "
            "DO $$ BEGIN LOOP EXIT WHEN (SELECT released FROM public.harness_gate); "
            "PERFORM pg_sleep(.025); END LOOP; END $$; COMMIT;", timeout=5)
        try:
            self.db.wait_until(
                "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND objid = 824973 AND granted);", timeout=3)
            self.assertEqual(self.db.scalar("SELECT count(*) FROM public.harness_smoke;"), "0")
        finally:
            self.db.sql("UPDATE public.harness_gate SET released = true;")
        held.wait(timeout=5)
        self.assertEqual(self.db.scalar("SELECT count(*) FROM public.harness_smoke;"), "1")

    def test_errors_stop_the_script_and_rollback(self):
        result = self.db.sql("BEGIN; CREATE TABLE public.must_rollback (id integer); "
                             "SELECT 1 / 0; COMMIT;", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("22012", result.stderr)
        self.assertEqual(self.db.scalar("SELECT to_regclass('public.must_rollback') IS NULL;"), "t")

    def test_bootstrap_failure_removes_only_its_owned_container(self):
        class BrokenBootstrap(IsolatedPostgres):
            def sql(self, source, **kwargs):
                if source == BOOTSTRAP:
                    raise RuntimeError("Deliberate fixture bootstrap failure")
                return super().sql(source, **kwargs)

        broken = BrokenBootstrap()
        try:
            with self.assertRaisesRegex(RuntimeError, "Deliberate fixture bootstrap failure"):
                broken.start()
            removed = broken._command(["inspect", broken.name], check=False)
            self.assertNotEqual(removed.returncode, 0)
            self.assertIn("no such", removed.stderr.lower())
            self.assertEqual(self.db.scalar("SELECT 1;"), "1")
        finally:
            broken.close()

    def test_server_statement_timeout_ends_a_blocked_connection(self):
        result = self.db.sql("SELECT pg_sleep(10);", timeout=1, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("57014", result.stderr)
        self.assertIn("statement timeout", result.stderr)
        self.assertEqual(self.db.scalar("SELECT 1;"), "1")

    def test_contract_rejects_missing_or_incorrect_rehearsal_marker(self):
        for prefix in ("", "SET dashboard.contract_rehearsal = 'incorrect';\n"):
            result = self.db.sql(prefix + CONTRACT.read_text(), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("isolated_contract_runner_required", result.stderr)
            self.assertEqual(self.db.scalar(
                "SELECT count(*) FROM pg_namespace WHERE nspname = 'vn_durability';"), "0")
