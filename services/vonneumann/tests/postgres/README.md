# Isolated PostgreSQL contract tests

These tests exercise real PostgreSQL roles, transactions, row locks and independent
connections. They are an opt-in contract laboratory, **not a Supabase migration or
proof that the worker is ready for hosting**. They never read an application env
file, use an existing database, or contact Supabase.

From `services/vonneumann`, run with an existing Python 3.12+ environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
  python -m tests.postgres.run --allow-isolated-postgres
```

The runner requires an already running local Docker daemon reachable through a
Unix socket, and the already installed image
`public.ecr.aws/supabase/postgres:17.6.1.095`. It neither starts Docker nor pulls or
installs an image. If either prerequisite is unavailable it fails with a setup
error. It resolves the tag to an immutable local image ID before creating the
container and records that ID and the server version in `db.identity`. Ordinary
worker unittest discovery skips these tests without the explicit
`DASHBOARD_ISOLATED_POSTGRES_TESTS=1` marker. The command above sets that marker only
inside its own process.

Each test class receives its own UUID-named, ownership-labeled container. The
harness pins the resolved local Docker socket, bypasses the image entrypoint,
initializes a new PostgreSQL 17.6 cluster on a bounded temporary filesystem, and
uses `--network none`, no published ports, no host mounts, a read-only image and
the unprivileged `postgres` OS user. There are no credentials to copy. PostgreSQL
listens only on an internal Unix socket. `docker exec psql` opens a separate
connection for every call. Startup, SQL sessions and removal have bounded waits.
Cleanup verifies the unique ownership label and removes only that exact container;
it never enumerates, stops, prunes or changes other projects' resources.

The minimal fixture provides `auth.users`, `auth.uid()` and real non-superuser
login roles `anon`, `authenticated`, `service_role` (with BYPASSRLS). Giving these
fixture roles LOGIN allows genuine independent connections without a superuser
session or `SET ROLE`; their production login configuration is not modeled.
`vn_contract_owner` has NOLOGIN, NOBYPASSRLS, and no client role memberships. This
models the privileges under test, not the entire Supabase platform. The HTTP
fixture described below additionally tests local PostgREST/JWT behavior; hosted
gateway authentication, realtime and managed settings still need acceptance.
PostgreSQL retains its default `fsync=on`; a temporary filesystem still cannot
model power loss, so this is not a crash-durability test.

`PostgresContractTestCase` applies exactly
`services/vonneumann/db-contract/001_fenced_commands.sql`. It does not discover or
apply the application's migrations. The harness explicitly sets the SQL file's
`dashboard.contract_rehearsal` marker to `db03a1-isolated`; the file rejects missing
opt-in to reduce accidental manual application. That caller-settable marker is
not a privilege boundary and does not authorize database writes. Subclasses reset
their own fixture rows.

```python
from tests.postgres.harness import PostgresContractTestCase

class ContractTests(PostgresContractTestCase):
    def test_example(self):
        self.assertEqual(self.db.scalar("SELECT current_user;", role="service_role"), "service_role")
```

Useful APIs:

- `db.sql(sql, role="postgres", check=True, timeout=10)` returns a
  `subprocess.CompletedProcess` with stdout/stderr; `check=False` exposes expected
  database failures. Verbose psql errors include SQLSTATE.
- `db.scalar(sql, role="postgres")` returns trimmed stdout.
- `db.begin_sql(sql, role="postgres", timeout=10)` starts an independent tracked
  session. `session.wait(timeout=15, check=True)` returns its completed result;
  `session.done` reports completion.
- `db.wait_until(sql, expected="t", timeout=5)` polls a database-visible barrier
  such as `pg_locks`; prefer it over assuming a competing connection started.

Supply fixture SQL only. `ON_ERROR_STOP` ensures an SQL error terminates the
session, rolling back an open transaction. Every connection gets a server-side
statement timeout in addition to its client deadline. An abruptly killed Python
runner may leave its uniquely named container; recover only that exact labeled
container after checking that no current test process owns it. Do not use a broad
Docker cleanup command.

The HTTP-specific `IsolatedPostgREST` fixture additionally requires the installed
`public.ecr.aws/supabase/postgrest:v14.5` image. It pins the image ID and matches the
hosted version observed on 2026-10-05. It uses a separate labeled private bridge
with IP masquerading disabled (Docker 29 suppresses published ports on internal
networks), no PostgreSQL host port, a subnet-limited fake authenticator, and one
exclusive loopback HTTP port. This is not a general egress firewall. Fake JWTs
and a test-only opaque-key gateway connector exercise PostgREST role/schema/commit
behavior without application keys. Nine HTTP/database tests include the actual
v5 provider controller with fabricated literal provider responses, independent
commit observation and original-ID recovery after a lost reply. See
[the HTTP contract](../../COMMAND-HTTP-CONTRACT.md). Hosted gateway authentication,
transaction-end policy, managed settings and production role defaults remain
separate activation gates.

`test_legacy_retirement.py` creates a separate legacy fixture from the reviewed
catalog snapshot, not historical migration scripts. It reproduces the measured
93 columns, 19 constraints, 25 indexes, 18 policies, two triggers, six default
ACL entries and authenticator membership options with synthetic two-owner rows.
Twenty-five cases validate exact-object/column/maintenance denial, inherited and
SET ROLE paths, preserved defaults/unrelated objects/rows/owner reads, catalog
drift, late rollback and old-writer overlap. A coexistence case runs actual v5
bootstrap/projections after legacy writes are retired. The current fixture's
administrative bootstrap remains broader than hosted `postgres`; fresh read-only
capability metadata exposes missing auth dependency grant options. No cloud
mutation or production-ready owner creation is implied.
See [the legacy retirement contract](../../LEGACY-WRITE-RETIREMENT.md).

`test_installer_boundary.py` creates a distinct NOSUPERUSER postgres login after
renaming initdb's mandatory-superuser bootstrap role. The installation connects
as the actual limited login, with measured non-grantable Auth dependencies;
separate fixture administration seeds and observes the experiment. Seventeen
cases verify a fixed installer-owned identity bridge, Auth FK ownership transfer,
private/API denial, four v5 bootstraps and owner history, unchanged managed Auth/
API/default/unrelated permissions, late rollback and FK lock timeout. Source
hashes and composition anchors are pinned. This is not a production compiler,
custom-role credential provisioner or complete managed-platform emulator.
See [the installer boundary](../../INSTALLER-BOUNDARY.md).
