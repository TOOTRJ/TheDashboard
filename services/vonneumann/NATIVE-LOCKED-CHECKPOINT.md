# Locked checkpoint dependency resolution — offline proof, 2026-10-11

PAPER-COMPACT-03B2 independently resolves the thirteen-slot research checkpoint
in PostgreSQL. It binds the exact prior under the owner/run lock, validates
canonical component bytes and typed references, and expands primitive evidence.
Complete economic/source/history admission remains PAPER-COMPACT-03.

## Scope and installation

The guarded artifact requires an explicit offline fixture marker and the03B1
numeric boundary. A real limited synthetic installer owns two private fixture
tables and seven functions. Only resolve_request is a definer function; all
functions fix search_path to pg_catalog and use explicit schema references.
PUBLIC receives no table/function/schema privileges. The synthetic auditor
receives only schema usage and resolver execution, without direct table/helper
access. Browser, service-role and relay calls are denied.

Privileged test code seeds the current checkpoint and retained components.
The resolver writes no checkpoint, component, journal, receipt, projection or
dependency pin. Its result is evidence, never a command ACK, lease, source
authenticity proof, executable state or permission to trade. The offline marker
prevents accidental installation; it is not authentication. No hosted/native
package/catalog/grant change, decoder or worker activation is included.

## Independent binding sequence

1. Audit the complete original tagged UTF-8 request before JSONB conversion.
   Bind format, canonical command UUID and owner/run. Apply the192KiB ordinary
   ceiling; a consistent control/Stop/status shape permits the256KiB research
   ceiling without establishing Stop authority.
2. Lock the exact owner/run row with FOR UPDATE. Read current revision and
   original manifest bytes only after the lock returns. Bootstrap requires
   revision one with no prior. Later requests supply the exact current revision
   and independently computed canonical manifest SHA256.
3. Validate supplied blocks and fetch only the bounded union of prior/following
   references, at most26 digests, in deterministic order. Retained rows use
   FOR SHARE. Charge original bytes separately to each checkpoint's256KiB
   dependency budget before decoding/materializing retained blocks.
4. Audit every component once, including canonical wire, hash policy, format,
   embedded scope, body shape, slot and generation. Reuse private checked entries
   within this call; the auditor cannot invoke helpers with invented entry maps.
   Same-digest supplied/retained blocks require identical bytes. Supplied blocks
   cannot repair a missing prior dependency; every supplied block must be used
   by the following checkpoint.
5. Expand both checkpoints independently. Require13 unique references:
   configuration, optimizer, cohort, source bars, EMA and all eight member genomes.
   Stable/configuration slots use generation zero; other slots match the engine
   generation. Bind the model version, GA class, ordered cohort membership,
   iteration identity, exact count and genome generations.
6. Require one next revision, immutable configuration, generation continuity
   and a nonterminal prior. Preserve exact signed-bigint bounds and reserve the
   final revision for the Stop shape. Bound every manifest, component, dependency
   aggregate and fully expanded canonical state. Return original command hash
   and prior/following evidence without any durable state change.

At Read Committed, a waiting row lock can return a newer row, so prior comparison
must follow lock acquisition. Repeatable Read can instead raise a serialization
failure for a concurrently changed row. Neither case permits using a stale cache
or replacing an uncertain command with a new identity.
[PostgreSQL row locking](https://www.postgresql.org/docs/17/explicit-locking.html),
[transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html).

Row locks protect retained dependencies through this transaction only. Durable
pins, original-command recovery and archival retention remain separate gates.

## Actual acceptance and measurements

Seventeen actual PostgreSQL cases and17 unchanged format/package cases pass.
Independent expansion matches Python's complete canonical state for35 commands
across two dense windows and two replacements. Tests cover component reuse,
foreign scope, stale prior, malformed slots/types/generations, missing/duplicate/
unreferenced dependencies, retained byte exhaustion, immutable configuration,
limited installer/client denial and Stop with all eight holdings. Stop preserves
positions and unscored aborted assessments without inventing exits.

Real concurrent sessions prove stale-prior rejection after a lock wait,
Repeatable Read serialization failure and run/component protection through
transaction end. The owned network-none PostgreSQL17.6 fixtures expose no ports,
mounts or application credentials and are removed after acceptance.

Thirty warm full-resolver samples use a PL/pgSQL wire variable and generic plans.
The artifact pins both SQL hashes and the immutable image identity, along with
request/resolved sizes, timing method and exclusions:
[locked-checkpoint-measurements.json](research/locked-checkpoint-measurements.json).
Final warm measurements for the source-hash-bound artifact are:

| Request | Original bytes | Following resolved bytes | p50 ms | p95 ms | Maximum ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bootstrap |128,635 |60,749 |167.954 |174.045 |176.390 |
| Quote |9,192 |61,655 |147.858 |154.497 |168.817 |
| Replacement |149,024 |65,208 |262.949 |275.025 |276.985 |

These include uncontended run/component locking and both checkpoint expansions.
They exclude contended waiting, full semantic admission, journal/pin/projection
writes, final source/lease checks, COMMIT/WAL, TLS/relay and hosted tails. The
measurement keeps its synthetic prior unchanged and establishes no accepted
command cadence or freshness margin.

A small quote wire still requires retained prior/following state resolution.
Choose cadence and hosting budgets only after complete-contract measurements.
Keep full optimizer/RNG evidence until exact restoration is proven.

## Next contract and substantial research

03B3 must independently validate balances, holdings, risk, lifecycle, source
clocks/epochs/watermarks, source/EMA equality, finalized/withheld assessments,
optimizer/cohort continuation, complete history and durable identity/lineage
uniqueness. The new model needs a reviewed semantic contract; presenting it as
an old v5 command would misrepresent its policy.

A deliberate test changes money, source/evidence and history while preserving
valid wire/slots. Resolution returns evidence and installs nothing. This
documents the boundary: hashes and slots do not authorize economic effects.
The native wrapper must reject such a transition before effects, preserve
original-ID replay/readback after advancement, store each original request once
with all components/pins/history/projections atomically, and recheck freshness/
lease after effects. Native Stop row/byte/WAL/lock reserves, the limited installer/
catalog, reader compatibility and rollback rehearsal still gate migration.

**Deep substantial research:** complete retained validation/lock/COMMIT/WAL/TOAST
tails; bounded reuse of independently validated immutable components without
skipping transition checks; serialization/deleted-run/unknown-commit recovery;
pin/resource/archival original-ID ordering; hosted many-window/restart/held-position
costs. This resolver establishes no continuous operation or retention entitlement.

Rollback is a reviewed code/docs revert; no hosted research objects exist.
Reproduce with the isolated locked worker environment from the repository root:

    DASHBOARD_ISOLATED_POSTGRES_TESTS=1 DASHBOARD_LOCKED_CHECKPOINT_MEASURE=1 PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.postgres.test_locked_checkpoint -v
    PYTHONPATH=services/vonneumann PYTHON_DOTENV_DISABLED=1 PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_partitioned_checkpoint tests.test_canonical_v5_package tests.test_forward_package -v
