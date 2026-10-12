# Secret-free Dashboard verification

Prepared 2026-10-12 for QA-01A. The repository now has three independent GitHub
Actions jobs in [.github/workflows/verification.yml](.github/workflows/verification.yml).
They run on pull requests, main pushes and explicit dispatch, with only
`contents:read`, no application secrets, no cloud environment, no deploy step and
no artifact upload. Checkout does not persist its read-only repository credential.
Fork pull requests use the ordinary `pull_request` context; this workflow never
uses `pull_request_target` or `workflow_run` to execute fork code. Feature pushes
do not duplicate PR jobs. Concurrency cancels a superseded run for the same PR/ref.

This is verification infrastructure, not a completed hosted or live acceptance
gate. The first actual GitHub-hosted amd64 run must pass before QA-01A closes; local
helper tests do not prove image pulling, runner installation or Linux execution.
No production credential or Vercel/Supabase/Railway login is required.

Publication is currently blocked by GitHub's rejection of the dedicated Dashboard
token's workflow-file push. The user must add `Workflows: Read and write` to that
existing token, retaining its selection of only `TOOTRJ/TheDashboard` and the
existing organization approval policy. GitHub documents this separate [workflow
write capability](https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens#repository-permissions-for-workflows). No shared login or token has been changed,
and the CI branch has not been published or merged. Workflow results can be read
through the existing authorized Dashboard browser; additional token permissions
for unrelated checks are not required for this setup step.

PR/manual triggers have no path/type/branch filters, and main pushes have only
the main-branch filter. The capability validator requires every advertised Node,
type, lint, advisory, build, lock/hash installation, dependency-consistency and
image/integration command; removing one or adding a bypass/filter fails its tests.

## Independent gates

| Job | Runtime / limit | Work and truthful scope |
| --- | --- | --- |
| Frontend | Node 24.19.0; Ubuntu 24.04; 20 minutes | Clean lock install with lifecycle scripts disabled; all current `tests/*.test.mjs`, `tests/probes/*.test.mjs` and helper Node files; TypeScript, lint, advisory policy and a second fresh fake-configuration production build. Existing lint warnings are reported; errors fail. |
| Ordinary worker | CPython 3.12.14 x64; Ubuntu 24.04; 30 minutes | Fresh virtual environment, hash-required binary-only dev/runtime wheels, `pip check`, complete worker discovery plus repository/helper Python tests. SQL opt-in skips and optional measurement skips are explicitly categorized and printed; no SQL acceptance is claimed. Unexpected skips, empty/all-skipped results and errors fail. |
| Required PostgreSQL | Same Python; Ubuntu 24.04; 50 minutes | Reviewed immutable amd64 PostgreSQL 17.6/PostgREST 14.5 fixtures, followed by full actual PostgreSQL discovery with explicit opt-in. Missing Docker/image/setup, foreign daemon, zero execution or any opt-in skip fails. Six allowlisted non-gating timing-method definitions may be skipped; every reported skip retains its test ID and exact reason. |

The chosen patch versions match the current reviewed source/software contract.
They are deliberate pins, not a claim to be the newest security patches. A later
runtime or action update requires source/lock/advisory and compatibility review;
do not silently switch to `latest`. The frontend advisory gate belongs to the
separate security slice: zero production findings and only its exact expiring
development exception are permitted. It must not be replaced with global audit
suppression or a blanket `continue-on-error`.

The owned child deadlines are 1500 seconds for ordinary discovery and 2400 seconds
for required PostgreSQL discovery, leaving 300/600 seconds within the 30/50 minute
job ceilings for setup and cleanup. The prior ordinary run took 1163 seconds;
that observation motivates the bound but does not guarantee GitHub runner tails.
The wrapper requires CPython 3.12.14 explicitly and gives a virtual-environment
setup error for an unsupported default interpreter.

## Build and environment isolation

[scripts/check-build.mjs](scripts/check-build.mjs) reads the local Git index's
frontend/build filename list with hooks/fsmonitor disabled, then copies only
those current working-tree files into a new owned temporary directory. Stage new
frontend source before running this check; an untracked file is intentionally
excluded. It does not copy `.git`, `.env*`, `ssl`, existing `node_modules`/`.next`,
agent/cloud configuration, worker source or unrelated drafts. Private/generated
reviewed paths, symlinks in any input ancestor and nonregular files are rejected.
The marker-protected directory is removed by its owner even if install/build fails.
Fixture tests can supply an explicit reviewed path list without constructing Git.

The build does its own locked install with
`npm ci --include=dev --ignore-scripts --no-audit --no-fund` and invokes Next directly
in that directory. The explicit dev inclusion retains Tailwind/PostCSS and other
build tools even though the isolated child uses `NODE_ENV=production`; omitting it
reproduced a missing build dependency in the first actual clean build.
Its child receives only minimal runtime/locale paths, fixed fake Supabase public
and server keys, and the reserved `https://dashboard-ci.invalid` URL. These fake
values grant no authority and cannot point at Dashboard services. Shared npm
user/global configuration and caches are excluded through separate empty config
files and an owned cache. The workflow's initial install also uses distinct empty
configs and a runner-temporary cache. No build bundle is uploaded. This is a
clean build check; it does not perform authenticated application requests or
prove provider/browser integration.

[scripts/check-worker.py](scripts/check-worker.py) reexecutes only its own Python
process with allowlisted paths/locale, disabled dotenv/bytecode, fixed thread
bounds and the repository worker import path. It drops application credentials,
proxy/token settings, arbitrary Python import/startup settings, inherited opt-in
and measurement flags. The internal child flag cannot bypass this environment
check. The required SQL child admits only an explicit local Unix Docker socket.
No existing Supabase database is selected.
Locale is fixed to C with Python UTF-8 mode enabled and locale coercion disabled.
On macOS, the child also fixes the benign per-UID text-encoding key added during
Python imports and checks its exact value; arbitrary extra environment keys are
still rejected. The reproduced pre-discovery failure came from that implicit
macOS key, not an application credential or a broad allowance needed by tests.

## Fixture identity and owned integration

[Reviewed registry metadata](scripts/check-ci-images-evidence.json) was captured
from public ECR on 2026-10-12 with response-digest verification. It distinguishes
the multi-platform index, platform manifest and image config; the earlier
`965e…` observed identity is the PostgreSQL index, not an amd64 config digest.

| Image | Linux amd64 manifest | Config digest |
| --- | --- | --- |
| `public.ecr.aws/supabase/postgres:17.6.1.095` | `sha256:4c087262afbfbb47da86e2863a52d7e424eb21ab589f732d77eeaab51be8e521` | `sha256:972aabc75779f6e535f87e1669f36edbab02cdf8bf3f47d13579963c119adefb` |
| `public.ecr.aws/supabase/postgrest:v14.5` | `sha256:bb289d00570b569525e1e22fb77c49cd17c17ca3f41da9ee2b4351a35027551b` | `sha256:af0a6dad76305650c215449d905a124ae5ad3bcd0f04c01845a0cea17d4e0960` |

[scripts/check-ci-images.py](scripts/check-ci-images.py) pulls those exact leaf
references, checks Linux/amd64, repository `RepoDigests` and the reviewed immutable
manifest/config identity, then supplies the exact existing harness tags only in
the new disposable GitHub-hosted Dashboard runner. Its explicit preparation action
checks the documented [runner and repository variables](https://docs.github.com/en/actions/reference/workflows-and-actions/variables) and refuses local/self-hosted and wrong-repository contexts; it never retags a shared
local daemon. Registry failures fail setup rather than selecting a different image.

The existing [owned harness](services/vonneumann/tests/postgres/README.md) creates
UUID-labeled bounded containers and verifies ownership before cleanup. Ordinary
PostgreSQL has no network/host mounts/ports and uses socket-only SQL. The
PostgREST fixture uses its documented private bridge and exclusive loopback HTTP
port with fake identities; this is not a general egress firewall. Tests cover real
role/transaction/lock/HTTP behavior; they do not authenticate hosted Supabase or
establish native version 2 admission, restoration, profitability or live readiness.
No broad Docker stop/prune is used. Cancellation may prevent normal test cleanup;
the disposable hosted runner bounds the lifetime of any remaining fixture.

## Reviewed action pins and local verification

The release pages and pinned action manifests were reviewed on 2026-10-12. All
three run on the action's Node 24 runtime:

- [checkout 7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1): `3d3c42e5aac5ba805825da76410c181273ba90b1`; [pinned inputs/runtime](https://raw.githubusercontent.com/actions/checkout/3d3c42e5aac5ba805825da76410c181273ba90b1/action.yml).
- [setup-node 7.1.0](https://github.com/actions/setup-node/releases/tag/v7.1.0): `949feb2413d6458794dcd2491c4babbbce0c15c1`; [pinned cache/runtime inputs](https://raw.githubusercontent.com/actions/setup-node/949feb2413d6458794dcd2491c4babbbce0c15c1/action.yml).
- [setup-python 6.3.0](https://github.com/actions/setup-python/releases/tag/v6.3.0): `ece7cb06caefa5fff74198d8649806c4678c61a1`; [pinned Python/runtime inputs](https://raw.githubusercontent.com/actions/setup-python/ece7cb06caefa5fff74198d8649806c4678c61a1/action.yml).

Local checks use the existing project Node/Python runtimes. The helper regressions
exercise real snapshot exclusions and symlink rejection, fake child configuration,
failure/owned cleanup, skip accounting and mandatory-SQL denial, registry/platform
identity, and workflow privilege/trigger/bypass changes. Full hosted CI remains
pending until GitHub executes all three required jobs. The workflow capability
check is part of ordinary helper test discovery.

The complete sanitized local run reported 2,088 cases in 1,287.086 seconds. All
1,630 executed worker cases passed; it separately reported 414 SQL opt-in skip
records (399 methods and 15 class setup skips). Its only error was an older
repository export fixture missing the already required controller canary. The
positive fixture and a missing-canary refusal regression repair that test; the
production exporter is unchanged. After the associated portability repair, all
66 repository/helper cases pass again with zero skips. This is the full worker
result plus a complete rerun of the changed helper scope, not a second clean
monolithic run or actual Linux/PostgreSQL acceptance.

Older operator tests assumed macOS import and staging paths. Their bounded
[test-only loader](scripts/tests/operator_fixture.py) admits six reviewed public
source paths, checks and substitutes only the exact pinned ROOT assignment in
memory, and scopes nested imports and pure artifact reads to the fixture checkout.
It denies real subprocess/urllib activity and repository-private file reads and
restores its patches. The relocated-checkout case copies only an explicit public
source/artifact list. Railway export fixtures inject only their owned temporary
staging comparison; default invalid-destination refusal remains unpatched. No
production operator source, target, credential handling or staging constant is
changed. These fixtures test the current admitted helpers, not a general Python
sandbox or real cloud behavior.

```sh
node --test scripts/tests/check-build.test.mjs
PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s scripts/tests -p test_ci_verification.py -v
node scripts/check-build.mjs --prepare-only
```

`--prepare-only` resolves/copies/removes the reviewed snapshot without installing
dependencies or executing a build. Full build installation and fixture pulls are
explicit CI work; they were not performed by the helper unit-test review. All
production deployments, migration/rollback evidence, reader compatibility and
operational budgets remain separately verified release gates.
