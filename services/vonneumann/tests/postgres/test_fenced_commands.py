"""Independent database acceptance tests for the nondeployable DB-03A rehearsal.

Every RPC is sent through an actual service_role connection. Administrative SQL
is only fixture setup, independent observation, fault injection and lock control.
These tests exercise neither the application repository nor any cloud database.
"""

from __future__ import annotations

import json
import uuid

from tests.postgres.harness import PostgresContractTestCase


def identity() -> str:
    return str(uuid.uuid4())


def literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def document(value: object) -> str:
    return literal(json.dumps(value, separators=(",", ":"), allow_nan=False)) + "::jsonb"


class FencedCommandsTests(PostgresContractTestCase):
    def setUp(self) -> None:
        self.owner, self.other_owner = identity(), identity()
        self.run, self.worker, self.creation = identity(), identity(), identity()
        self.configuration = {"strategy": "ema", "nested": {"retained": [1, 2, 3]}}
        self.db.sql(
            f"INSERT INTO auth.users(id) VALUES ({literal(self.owner)}), ({literal(self.other_owner)});"
        )

    def create_sql(self, *, owner=None, run=None, worker=None, command=None,
                   cash="1000", lease=30, configuration=None) -> str:
        return "SELECT vn_durability.create_run(" + ",".join([
            literal(owner or self.owner), literal(run or self.run),
            literal(worker or self.worker), literal(command or self.creation),
            document(self.configuration if configuration is None else configuration),
            literal(cash), literal(lease),
        ]) + ");"

    def create(self, **kwargs) -> dict:
        return json.loads(self.db.scalar(self.create_sql(**kwargs), role="service_role"))

    def command_sql(self, operations, *, revision=1, command=None, owner=None,
                    run=None, worker=None, fence=1) -> str:
        return self.payload_sql({"version": 1, "operations": operations},
                                revision=revision, command=command, owner=owner,
                                run=run, worker=worker, fence=fence)

    def payload_sql(self, payload, *, revision=1, command=None, owner=None,
                    run=None, worker=None, fence=1) -> str:
        return "SELECT vn_durability.commit_command(" + ",".join([
            literal(owner or self.owner), literal(run or self.run),
            literal(worker or self.worker), literal(fence), literal(revision),
            literal(command or identity()), document(payload),
        ]) + ");"

    def commit(self, operations, **kwargs) -> dict:
        return json.loads(self.db.scalar(self.command_sql(operations, **kwargs), role="service_role"))

    def resolve_sql(self, command, *, owner=None, run=None) -> str:
        return ("SELECT vn_durability.get_command("
                f"{literal(owner or self.owner)},{literal(run or self.run)},{literal(command)});")

    def heartbeat_sql(self, *, worker=None, fence=1, lease=30, owner=None) -> str:
        return ("SELECT vn_durability.heartbeat("
                f"{literal(owner or self.owner)},{literal(self.run)},"
                f"{literal(worker or self.worker)},{literal(fence)},{literal(lease)});")

    def interrupt_sql(self, *, revision=1, command=None, owner=None) -> str:
        return ("SELECT vn_durability.interrupt_expired("
                f"{literal(owner or self.owner)},{literal(self.run)},"
                f"{literal(revision)},{literal(command or identity())});")

    def reject(self, source: str, reason: str, *, role="service_role"):
        result = self.db.sql(source, role=role, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(reason, result.stderr)
        return result

    def run_scalar(self, expression: str) -> str:
        return self.db.scalar(
            f"SELECT {expression} FROM vn_durability.runs WHERE id={literal(self.run)};"
        )

    def expire(self) -> None:
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()-interval '1 second' "
                    f"WHERE id={literal(self.run)};")

    @staticmethod
    def birth(account, cash="100", parents=None):
        return {"kind": "birth", "id": account, "cash": cash, "parent_ids": parents or []}

    @staticmethod
    def opened(position, account, *, quantity="1.25", notional="20", fee="0.5"):
        return {"kind": "open", "id": position, "account_id": account, "asset": "SOL/USDC",
                "quantity": quantity, "notional": notional, "fee": fee}

    def funded_position(self):
        self.create()
        account, position = identity(), identity()
        self.commit([self.birth(account), {"kind": "lifecycle", "status": "running"},
                     self.opened(position, account)])
        return account, position

    def snapshot(self) -> dict:
        result = {}
        for table in ("runs", "accounts", "account_parents", "positions", "commands"):
            key = "id" if table == "runs" else "run_id"
            result[table] = json.loads(self.db.scalar(
                f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text), '[]'::jsonb) "
                f"FROM vn_durability.{table} t WHERE {key}={literal(self.run)};"
            ))
        return result

    def named(self, name: str, source: str) -> str:
        return f"SET application_name={literal(name)}; {source}"

    def wait_for_lock(self, name: str) -> None:
        self.db.wait_until("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE "
                           f"application_name={literal(name)} AND wait_event_type='Lock');")

    def lock_run(self, *, seconds=2):
        name = "hold_" + uuid.uuid4().hex
        holder = self.db.begin_sql(self.named(name,
            f"BEGIN; SELECT id FROM vn_durability.runs WHERE id={literal(self.run)} FOR UPDATE; "
            f"SELECT pg_sleep({seconds}); COMMIT;"))
        self.db.wait_until("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE "
                           f"application_name={literal(name)} AND wait_event='PgSleep');")
        return holder

    def test_creation_is_atomic_immutable_and_idempotent(self):
        first = self.create(cash="1000.125")
        original = self.snapshot()
        second = self.create(cash="1000.125")
        self.assertEqual(first, second)
        self.assertEqual(original, self.snapshot())
        self.assertEqual(first, {"run_id": self.run, "revision": 1, "fence": 1, "status": "starting"})
        self.assertEqual(self.run_scalar("reserve::text"), "1000.125")
        self.reject(self.create_sql(cash="1001"), "command_conflict")
        self.reject(self.create_sql(command=identity()), "command_conflict")
        self.reject(self.create_sql(owner=self.other_owner), "run_unavailable")
        self.assertEqual(original, self.snapshot())

    def test_concurrent_creators_return_one_committed_identity(self):
        name = "creator_" + uuid.uuid4().hex
        first = self.db.begin_sql(self.named(name,
            "BEGIN; " + self.create_sql() + " SELECT pg_sleep(2); COMMIT;"), role="service_role")
        self.db.wait_until("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE "
                           f"application_name={literal(name)} AND wait_event='PgSleep');")
        second_name = "creator_" + uuid.uuid4().hex
        second = self.db.begin_sql(self.named(second_name, self.create_sql()), role="service_role")
        self.wait_for_lock(second_name)
        a = json.loads(first.wait().stdout.strip())
        b = json.loads(second.wait().stdout.strip())
        self.assertEqual(a, b)
        self.assertEqual(len(self.snapshot()["commands"]), 1)
        self.assertEqual(self.run_scalar("reserve::text"), "1000")

    def test_competing_worker_cannot_reuse_run_creation(self):
        self.create()
        original = self.snapshot()
        self.reject(self.create_sql(worker=identity()), "command_conflict")
        self.assertEqual(original, self.snapshot())

    def test_atomic_economic_batch_and_exact_fractional_accounting(self):
        self.create(cash="1000.123456789012345678901234567890123456")
        account, position = identity(), identity()
        self.commit([self.birth(account, "100.123"), {"kind": "lifecycle", "status": "running"},
                     self.opened(position, account, notional="20.012", fee="0.003"),
                     {"kind": "close", "id": position, "proceeds": "25.019", "fee": "0.007"},
                     {"kind": "retire", "id": account}])
        self.assertEqual(self.run_scalar("reserve::text"), "1005.120456789012345678901234567890123456")
        state = self.snapshot()
        self.assertTrue(state["accounts"][0]["retired"])
        self.assertEqual(state["accounts"][0]["cash"], 0)
        self.assertTrue(state["positions"][0]["closed"])
        self.assertEqual(sorted(row["revision"] for row in state["commands"]), [1, 2])
        self.assertEqual(self.run_scalar("revision::text"), "2")

    def test_late_invalid_operation_rolls_back_entire_replacement(self):
        account, position = self.funded_position()
        before = self.snapshot()
        invalid_child = identity()
        source = self.command_sql([
            {"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"},
            {"kind": "retire", "id": account},
            self.birth(identity(), "100", parents=[account]),
            self.birth(invalid_child, "100000000"),
        ], revision=2)
        self.reject(source, "invalid_birth")
        self.assertEqual(before, self.snapshot())

    def test_active_positions_cannot_be_retired_or_closed_twice(self):
        account, position = self.funded_position()
        before = self.snapshot()
        self.reject(self.command_sql([{"kind": "retire", "id": account}], revision=2), "invalid_retirement")
        self.assertEqual(before, self.snapshot())
        self.commit([{"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"}], revision=2)
        closed = self.snapshot()
        self.reject(self.command_sql([{"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"}], revision=3), "invalid_close")
        self.assertEqual(closed, self.snapshot())

    def test_duplicate_asset_open_rolls_back_and_closed_asset_can_be_reopened(self):
        account, position = self.funded_position()
        before = self.snapshot()
        # A preceding valid allocation must roll back together with the conflict.
        self.reject(self.command_sql([self.birth(identity()), self.opened(identity(), account)], revision=2),
                    "one_open_position_per_asset")
        self.assertEqual(before, self.snapshot())
        replacement = identity()
        self.commit([{"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"},
                     self.opened(replacement, account)], revision=2)
        rows = self.snapshot()["positions"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(next(row for row in rows if row["id"] == position)["closed"])
        self.assertFalse(next(row for row in rows if row["id"] == replacement)["closed"])
        self.assertEqual(self.db.scalar(
            f"SELECT cash::text FROM vn_durability.accounts WHERE run_id={literal(self.run)} "
            f"AND id={literal(account)};"), "83.5")

    def test_replay_returns_original_response_and_never_double_debits(self):
        self.create()
        command = identity()
        source = self.command_sql([self.birth(identity())], command=command)
        first = json.loads(self.db.scalar(source, role="service_role"))
        after = self.snapshot()
        second = json.loads(self.db.scalar(source, role="service_role"))
        self.assertEqual(first, second)
        self.assertEqual(after, self.snapshot())
        resolved = json.loads(self.db.scalar(self.resolve_sql(command), role="service_role"))
        self.assertEqual(resolved["response"], first)
        self.assertEqual(len(resolved["request_hash"]), 64)
        self.assertEqual(resolved["request"]["expected_revision"], 1)
        self.assertEqual(self.db.scalar(
            f"SELECT bool_and(request_hash=sha256(convert_to(request::text,'UTF8'))) "
            f"FROM vn_durability.commands WHERE run_id={literal(self.run)};"), "t")

    def test_changed_command_payload_revision_or_kind_is_not_replay(self):
        self.create()
        command, account = identity(), identity()
        operations = [self.birth(account)]
        self.commit(operations, command=command)
        after = self.snapshot()
        self.reject(self.command_sql([self.birth(account, "101")], command=command), "command_conflict")
        self.reject(self.command_sql(operations, revision=2, command=command), "command_conflict")
        self.reject(self.command_sql(operations, revision=2, command=self.creation), "command_conflict")
        self.assertEqual(after, self.snapshot())

    def test_concurrent_same_command_has_one_revision_and_result(self):
        self.create()
        source = self.command_sql([self.birth(identity())], command=identity())
        holder = self.lock_run()
        names = ["same_" + uuid.uuid4().hex for _ in range(2)]
        sessions = [self.db.begin_sql(self.named(name, source), role="service_role") for name in names]
        for name in names:
            self.wait_for_lock(name)
        holder.wait()
        results = [json.loads(session.wait().stdout.strip()) for session in sessions]
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.run_scalar("revision::text || ':' || reserve::text"), "2:900")
        self.assertEqual(len(self.snapshot()["accounts"]), 1)

    def test_concurrent_different_commands_cannot_share_expected_revision(self):
        self.create()
        holder = self.lock_run()
        names = ["revision_" + uuid.uuid4().hex for _ in range(2)]
        sessions = [self.db.begin_sql(self.named(name, self.command_sql([self.birth(identity())])),
                                      role="service_role") for name in names]
        for name in names:
            self.wait_for_lock(name)
        holder.wait()
        results = [session.wait(check=False) for session in sessions]
        self.assertEqual(sum(result.returncode == 0 for result in results), 1)
        self.assertIn("revision_conflict", next(result.stderr for result in results if result.returncode))
        self.assertEqual(self.run_scalar("revision::text || ':' || reserve::text"), "2:900")

    def test_worker_fence_owner_and_revision_checks_leave_no_partial_state(self):
        self.create()
        before = self.snapshot()
        for kwargs, reason in [({"worker": identity()}, "lease_lost"),
                               ({"fence": 2}, "lease_lost"),
                               ({"owner": self.other_owner}, "run_unavailable"),
                               ({"revision": 2}, "revision_conflict")]:
            with self.subTest(kwargs=kwargs):
                self.reject(self.command_sql([self.birth(identity())], **kwargs), reason)
                self.assertEqual(before, self.snapshot())
        self.reject(self.heartbeat_sql(worker=identity()), "lease_lost")
        self.reject(self.heartbeat_sql(fence=2), "lease_lost")
        self.reject(self.heartbeat_sql(owner=self.other_owner), "run_unavailable")

    def test_heartbeat_changes_only_expiry_and_cannot_revive_expired_owner(self):
        self.create(lease=5)
        before = self.snapshot()
        response = json.loads(self.db.scalar(self.heartbeat_sql(lease=30), role="service_role"))
        after = self.snapshot()
        self.assertEqual(response, {"run_id": self.run, "revision": 1, "fence": 1})
        self.assertGreater(after["runs"][0]["lease_until"], before["runs"][0]["lease_until"])
        before["runs"][0]["lease_until"] = after["runs"][0]["lease_until"]
        self.assertEqual(before, after)
        self.expire()
        expired = self.snapshot()
        self.reject(self.heartbeat_sql(), "lease_lost")
        self.reject(self.command_sql([self.birth(identity())]), "lease_lost")
        self.assertEqual(expired, self.snapshot())

    def test_expiry_is_checked_after_lock_wait_not_transaction_start(self):
        self.create(lease=2)
        holder = self.lock_run(seconds=3)
        names = ["expiry_" + uuid.uuid4().hex for _ in range(2)]
        sources = [self.heartbeat_sql(), self.command_sql([self.birth(identity())])]
        sessions = [self.db.begin_sql(self.named(name, "BEGIN; " + source + " COMMIT;"),
                                      role="service_role") for name, source in zip(names, sources)]
        for name in names:
            self.wait_for_lock(name)
            self.assertEqual(self.db.scalar(
                "SELECT a.xact_start < r.lease_until FROM pg_stat_activity a CROSS JOIN vn_durability.runs r "
                f"WHERE a.application_name={literal(name)} AND r.id={literal(self.run)};"), "t")
        holder.wait()
        for session in sessions:
            result = session.wait(check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lease_lost", result.stderr)
        self.assertEqual(self.run_scalar("revision::text"), "1")

    def test_expiry_during_projection_write_rolls_back_work_and_journal(self):
        self.create()
        account = identity()
        self.commit([self.birth(account), {"kind": "lifecycle", "status": "running"}])
        function = "delay_" + uuid.uuid4().hex
        self.db.sql(
            f"CREATE FUNCTION vn_durability.{function}() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN PERFORM pg_sleep(2); RETURN NEW; END $$; "
            f"CREATE TRIGGER {function} BEFORE INSERT ON vn_durability.positions "
            f"FOR EACH ROW WHEN (NEW.run_id={literal(self.run)}::uuid) "
            f"EXECUTE FUNCTION vn_durability.{function}();"
        )
        self.addCleanup(self.db.sql,
                        f"DROP TRIGGER {function} ON vn_durability.positions; "
                        f"DROP FUNCTION vn_durability.{function}();")
        self.db.sql(f"UPDATE vn_durability.runs SET lease_until=clock_timestamp()+interval '1 second' "
                    f"WHERE id={literal(self.run)};")
        before = self.snapshot()
        name = "inside_" + uuid.uuid4().hex
        session = self.db.begin_sql(self.named(name, self.command_sql(
            [self.opened(identity(), account)], revision=2)), role="service_role")
        self.db.wait_until("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE "
                           f"application_name={literal(name)} AND wait_event='PgSleep');")
        result = session.wait(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lease_lost", result.stderr)
        self.assertEqual(before, self.snapshot())

    def test_lost_ack_resolution_remains_available_after_lease_expiry(self):
        self.create()
        command = identity()
        source = self.command_sql([self.birth(identity())], command=command)
        self.db.sql(source, role="service_role")  # Deliberately discard the successful response.
        self.expire()
        before = self.snapshot()
        self.reject(source, "lease_lost")
        result = json.loads(self.db.scalar(self.resolve_sql(command), role="service_role"))
        self.assertEqual(result["response"]["revision"], 2)
        self.assertEqual(result["request"]["payload"]["operations"][0]["cash"], "100")
        self.assertEqual(before, self.snapshot())
        self.reject(self.resolve_sql(command, owner=self.other_owner), "run_unavailable")

    def test_absent_command_while_write_in_flight_is_not_rollback_evidence(self):
        self.create()
        command = identity()
        holder = self.lock_run()
        name = "pending_" + uuid.uuid4().hex
        session = self.db.begin_sql(self.named(name, self.command_sql([self.birth(identity())], command=command)),
                                    role="service_role")
        self.wait_for_lock(name)
        self.assertEqual(self.db.scalar(self.resolve_sql(command), role="service_role"), "")
        holder.wait()
        result = json.loads(session.wait().stdout.strip())
        self.assertEqual(json.loads(self.db.scalar(self.resolve_sql(command), role="service_role"))["response"], result)

    def test_interruption_preserves_economic_history_and_permanently_fences_writer(self):
        self.funded_position()
        self.expire()
        before = self.snapshot()
        command = identity()
        source = self.interrupt_sql(revision=2, command=command)
        result = json.loads(self.db.scalar(source, role="service_role"))
        self.assertEqual(result["revision"], 3)
        self.assertEqual(result["fence"], 2)
        self.assertEqual(result["code"], "worker_interrupted")
        self.assertTrue(result["requires_reconciliation"])
        after = self.snapshot()
        for table in ("accounts", "account_parents", "positions"):
            self.assertEqual(before[table], after[table])
        for column in ("config", "reserve", "initial_cash", "worker_id"):
            self.assertEqual(before["runs"][0][column], after["runs"][0][column])
        self.assertEqual(json.loads(self.db.scalar(source, role="service_role")), result)
        self.assertEqual(after, self.snapshot())
        self.reject(self.heartbeat_sql(fence=2), "lease_lost")
        self.reject(self.command_sql([{"kind": "lifecycle", "status": "running"}],
                                     revision=3, fence=2), "lease_lost")
        self.reject(self.interrupt_sql(revision=3), "not_interruptible")

    def test_interruption_requires_expiry_and_current_revision(self):
        self.create()
        self.reject(self.interrupt_sql(), "not_interruptible")
        self.expire()
        self.reject(self.interrupt_sql(revision=2), "revision_conflict")
        self.reject(self.interrupt_sql(owner=self.other_owner), "run_unavailable")

    def test_concurrent_interruption_creates_one_event(self):
        self.create()
        self.expire()
        holder = self.lock_run()
        names = ["interrupt_" + uuid.uuid4().hex for _ in range(2)]
        sessions = [self.db.begin_sql(self.named(name, self.interrupt_sql()), role="service_role")
                    for name in names]
        for name in names:
            self.wait_for_lock(name)
        holder.wait()
        results = [session.wait(check=False) for session in sessions]
        self.assertEqual(sum(result.returncode == 0 for result in results), 1)
        self.assertIn("revision_conflict", next(result.stderr for result in results if result.returncode))
        self.assertEqual(self.run_scalar("revision::text || ':' || fence::text"), "2:2")
        self.assertEqual(len(self.snapshot()["commands"]), 2)

    def test_cross_owner_and_run_relationships_are_rejected_atomically(self):
        self.create()
        other_run, other_worker, parent, position = identity(), identity(), identity(), identity()
        self.create(run=other_run, worker=other_worker, command=identity(), owner=self.other_owner)
        self.commit([self.birth(parent), {"kind": "lifecycle", "status": "running"},
                     self.opened(position, parent)], run=other_run, worker=other_worker, owner=self.other_owner)
        before = self.snapshot()
        self.reject(self.command_sql([self.birth(identity(), parents=[parent])]), "23503")
        self.reject(self.command_sql([{"kind": "lifecycle", "status": "running"},
                                     self.opened(identity(), parent)]), "invalid_open")
        self.reject(self.command_sql([{"kind": "close", "id": position, "proceeds": "25", "fee": "0"}]), "invalid_close")
        self.assertEqual(before, self.snapshot())
        # The run boundary is mandatory even for two runs owned by the same user.
        same_owner_run, same_parent = identity(), identity()
        self.create(run=same_owner_run, command=identity())
        self.commit([self.birth(same_parent)], run=same_owner_run)
        self.reject(self.command_sql([self.birth(identity(), parents=[same_parent])]), "23503")

    def test_lineage_requires_distinct_existing_same_run_parents(self):
        self.create()
        parent, second_parent, child = identity(), identity(), identity()
        self.commit([self.birth(parent), self.birth(second_parent), self.birth(child, parents=[parent, second_parent])])
        self.assertEqual(len(self.snapshot()["account_parents"]), 2)
        before = self.snapshot()
        self.reject(self.command_sql([self.birth(identity(), parents=[parent, parent])], revision=2), "23505")
        self_parent = identity()
        self.reject(self.command_sql([self.birth(self_parent, parents=[self_parent])], revision=2), "23514")
        self.reject(self.command_sql([self.birth(identity(), parents=[parent, second_parent, child])], revision=2), "invalid_birth")
        self.assertEqual(before, self.snapshot())

    def test_browser_and_service_role_cannot_directly_mutate_or_truncate(self):
        self.funded_position()
        before = self.snapshot()
        self.assertEqual(self.db.scalar("SELECT rolbypassrls FROM pg_roles WHERE rolname='service_role';"), "t")
        for role in ("anon", "authenticated", "service_role"):
            for table in ("runs", "accounts", "account_parents", "positions", "commands"):
                column = "reserve" if table == "runs" else "run_id"
                for mutation in (
                    f"INSERT INTO vn_durability.{table} SELECT * FROM vn_durability.{table} LIMIT 0;",
                    f"UPDATE vn_durability.{table} SET {column}={column} WHERE false;",
                    f"DELETE FROM vn_durability.{table} WHERE false;",
                    f"TRUNCATE vn_durability.{table} CASCADE;",
                ):
                    with self.subTest(role=role, table=table, mutation=mutation.split()[0]):
                        self.reject(mutation, "permission denied", role=role)
        self.assertEqual(before, self.snapshot())

    def test_only_authenticated_owner_can_select_projection_and_journal_rows(self):
        parent, _position = self.funded_position()
        self.commit([self.birth(identity(), parents=[parent])], revision=2)
        for table in ("runs", "accounts", "account_parents", "positions", "commands"):
            key = "id" if table == "runs" else "run_id"
            query = f"SELECT count(*) FROM vn_durability.{table} WHERE {key}={literal(self.run)};"
            with self.subTest(table=table):
                own = self.db.scalar(f"SET request.jwt.claim.sub={literal(self.owner)}; " + query, role="authenticated")
                other = self.db.scalar(f"SET request.jwt.claim.sub={literal(self.other_owner)}; " + query, role="authenticated")
                empty = self.db.scalar(query, role="authenticated")
                self.assertGreater(int(own), 0)
                self.assertEqual(other, "0")
                self.assertEqual(empty, "0")
                self.reject(query, "permission denied", role="anon")
                self.reject(query, "permission denied", role="service_role")

    def test_rpc_permissions_and_private_helpers_are_not_bypassable(self):
        self.create()
        for source in (self.create_sql(), self.command_sql([self.birth(identity())]),
                       self.heartbeat_sql(), self.resolve_sql(self.creation), self.interrupt_sql()):
            for role in ("anon", "authenticated"):
                with self.subTest(role=role, rpc=source.split("(")[0]):
                    self.reject(source, "permission denied", role=role)
        for source in ("SELECT vn_durability.money('\"5\"'::jsonb);",
                       "SELECT vn_durability.exact_keys('{}'::jsonb,ARRAY[]::text[]);",
                       "SET ROLE vn_contract_owner;"):
            self.reject(source, "permission denied", role="service_role")
        self.reject("SET vn_durability.trusted_rpc='true'; UPDATE vn_durability.runs SET reserve=0;",
                    "permission denied")

    def test_future_owner_helper_has_no_default_public_execution(self):
        self.db.sql("SET ROLE vn_contract_owner; "
                    "CREATE FUNCTION vn_durability.later_helper() RETURNS integer "
                    "LANGUAGE sql AS 'SELECT 1'; RESET ROLE;")
        self.addCleanup(self.db.sql, "DROP FUNCTION vn_durability.later_helper();")
        for role in ("anon", "authenticated", "service_role"):
            with self.subTest(role=role):
                self.reject("SELECT vn_durability.later_helper();", "permission denied", role=role)
                self.assertEqual(self.db.scalar(
                    f"SELECT has_function_privilege({literal(role)},'vn_durability.later_helper()','EXECUTE');"), "f")
        self.assertEqual(self.db.scalar(
            "SELECT NOT EXISTS(SELECT 1 FROM pg_proc p CROSS JOIN LATERAL "
            "aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x "
            "WHERE p.oid='vn_durability.later_helper()'::regprocedure AND x.grantee=0 "
            "AND x.privilege_type='EXECUTE');"), "t")

    def test_caller_search_path_and_temp_objects_cannot_replace_trusted_objects(self):
        self.create()
        response = self.db.scalar(
            "CREATE TEMP TABLE runs (id uuid, reserve numeric); "
            "CREATE FUNCTION pg_temp.clock_timestamp() RETURNS timestamptz "
            "LANGUAGE sql AS $$ SELECT '2099-01-01'::timestamptz $$; "
            "SET search_path=pg_temp,public; " + self.heartbeat_sql(), role="service_role")
        self.assertEqual(json.loads(response)["revision"], 1)
        self.assertEqual(self.run_scalar("lease_until < '2099-01-01'::timestamptz"), "t")

    def test_malformed_payloads_and_null_arguments_fail_without_writes(self):
        self.create()
        before = self.snapshot()
        bad_payloads = [None, [], {}, {"version": 2, "operations": [self.birth(identity())]},
                        {"version": "1", "operations": [self.birth(identity())]},
                        {"version": 1, "operations": None}, {"version": 1, "operations": []},
                        {"version": 1, "operations": [None]},
                        {"version": 1, "operations": [{"kind": "unknown"}]},
                        {"version": 1, "operations": [self.birth(identity())], "extra": 1},
                        {"version": 1, "operations": [self.birth(identity())] * 257}]
        for payload in bad_payloads:
            with self.subTest(payload=str(payload)[:80]):
                result = self.db.sql(self.payload_sql(payload), role="service_role", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, self.snapshot())
        signatures = [
            ("create_run", [literal(self.owner), literal(identity()), literal(self.worker), literal(identity()), "'{}'::jsonb", "'100'", "30"]),
            ("heartbeat", [literal(self.owner), literal(self.run), literal(self.worker), "1", "30"]),
            ("commit_command", [literal(self.owner), literal(self.run), literal(self.worker), "1", "1", literal(identity()), document({"version": 1, "operations": [self.birth(identity())]})]),
            ("get_command", [literal(self.owner), literal(self.run), literal(self.creation)]),
            ("interrupt_expired", [literal(self.owner), literal(self.run), "1", literal(identity())]),
        ]
        for function, arguments in signatures:
            for index in range(len(arguments)):
                with self.subTest(function=function, null_argument=index):
                    invalid = list(arguments)
                    invalid[index] = "NULL"
                    result = self.db.sql(f"SELECT vn_durability.{function}({','.join(invalid)});",
                                         role="service_role", check=False)
                    self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(before, self.snapshot())

    def test_decimal_validation_rejects_noncanonical_and_nonfinite_amounts(self):
        self.create()
        before = self.snapshot()
        invalid = [None, True, 1, -1, "NaN", "Infinity", "-Infinity", "-0", "-1", "+1",
                   "1e2", " 1", "1 ", "01", ".5", "1.", "0.0000000000000000000000000000000000001",
                   "1000000000000000000000000000000000001", "9" * 76]
        for amount in invalid:
            with self.subTest(amount=amount):
                self.reject(self.command_sql([self.birth(identity(), amount)]), "invalid_amount")
                self.assertEqual(before, self.snapshot())
        self.reject(self.command_sql([self.birth(identity(), "0")]), "invalid_birth")

    def test_payload_size_and_lease_bounds_fail_closed(self):
        for lease in (0, -1, 121):
            self.reject(self.create_sql(lease=lease), "invalid_payload")
        self.reject(self.create_sql(configuration={"oversized": "x" * 65536}), "invalid_payload")
        self.create()
        for lease in (0, -1, 121):
            self.reject(self.heartbeat_sql(lease=lease), "invalid_payload")
        self.reject(self.payload_sql({"version": 1, "operations": [{"padding": "x" * 262144}]}), "invalid_payload")
        self.assertEqual(self.run_scalar("revision::text"), "1")

    def test_terminal_and_risk_states_restrict_future_economic_commands(self):
        account, position = self.funded_position()
        self.commit([{"kind": "lifecycle", "status": "risk_halted"}], revision=2)
        self.reject(self.command_sql([self.birth(identity())], revision=3), "invalid_birth")
        self.reject(self.command_sql([self.opened(identity(), account)], revision=3), "invalid_open")
        self.commit([{"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"},
                     {"kind": "lifecycle", "status": "stopped"}], revision=3)
        before = self.snapshot()
        self.reject(self.command_sql([{"kind": "lifecycle", "status": "running"}], revision=4), "run_terminal")
        self.reject(self.heartbeat_sql(), "lease_lost")
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.run_scalar("requires_reconciliation::text"), "true")

    def test_risk_halt_cannot_resume_or_pause_around_missing_recovery_contract(self):
        _account, position = self.funded_position()
        self.commit([{"kind": "lifecycle", "status": "risk_halted"}], revision=2)
        halted = self.snapshot()
        for status in ("running", "paused"):
            with self.subTest(status=status):
                # Even an otherwise valid protective close is rolled back if
                # the same command tries to bypass recovery afterward.
                self.reject(self.command_sql([
                    {"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"},
                    {"kind": "lifecycle", "status": status},
                ], revision=3), "risk_recovery_unavailable")
                self.assertEqual(halted, self.snapshot())
        self.reject(self.command_sql([
            {"kind": "lifecycle", "status": "paused"},
            {"kind": "lifecycle", "status": "running"},
        ], revision=3), "risk_recovery_unavailable")
        self.assertEqual(halted, self.snapshot())
        # Idempotent status retention is permitted; exiting the halt is not.
        self.commit([{"kind": "lifecycle", "status": "risk_halted"}], revision=3)
        self.assertEqual(self.run_scalar("status"), "risk_halted")

    def test_risk_trip_and_same_batch_resume_attempt_roll_back_every_projection(self):
        _account, position = self.funded_position()
        before = self.snapshot()
        self.reject(self.command_sql([
            {"kind": "close", "id": position, "proceeds": "25", "fee": "0.5"},
            {"kind": "lifecycle", "status": "risk_halted"},
            {"kind": "lifecycle", "status": "running"},
        ], revision=2), "risk_recovery_unavailable")
        self.assertEqual(before, self.snapshot())

    def test_terminated_database_session_rolls_back_unacknowledged_transaction(self):
        self.create()
        command, account = identity(), identity()
        source = self.command_sql([self.birth(account)], command=command)
        name = "terminate_" + uuid.uuid4().hex
        session = self.db.begin_sql(self.named(name, "BEGIN; " + source + " SELECT pg_sleep(10); COMMIT;"),
                                    role="service_role", timeout=15)
        self.db.wait_until("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE "
                           f"application_name={literal(name)} AND wait_event='PgSleep');")
        # The RPC completed inside the transaction, but nothing is committed.
        self.assertEqual(self.db.scalar(self.resolve_sql(command), role="service_role"), "")
        self.assertEqual(self.run_scalar("reserve::text || ':' || revision::text"), "1000:1")
        self.assertEqual(self.db.scalar(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name={literal(name)};"), "t")
        result = session.wait(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.snapshot()["accounts"]), 0)
        self.assertEqual(len(self.snapshot()["commands"]), 1)
        # This fault injection proved rollback; stable-ID retry is now safe.
        self.db.sql(source, role="service_role")
        self.assertEqual(self.run_scalar("reserve::text || ':' || revision::text"), "900:2")

    def test_revision_overflow_rolls_back_economic_changes(self):
        self.create()
        maximum = 9223372036854775807
        self.db.sql(f"UPDATE vn_durability.runs SET revision={maximum} WHERE id={literal(self.run)};")
        before = self.snapshot()
        self.reject(self.command_sql([self.birth(identity())], revision=maximum), "22003")
        self.assertEqual(before, self.snapshot())
