# Legacy evidence and non-destructive archive rehearsal

DB-03A2D3B2D1, 2026-10-07. This closes the **offline evidence component** of
B2. B2/D3/A3 remain open. No production schema, credential, grant, migration,
worker selection, Railway service or trade is changed by this component.

The deterministic [package and manifest](db-contract/legacy-evidence/manifest.json)
are outside `supabase/migrations`. Only the explicit owned, network-none
PostgreSQL fixture imports them. The builder has no connection option or cloud
application path. The caller-settable rehearsal marker prevents accidental
application; it is not authorization. Do not strip the marker or copy this
component into a migration to bypass complete-package review.

## Why this is needed

The retained production inventory includes stopped colony rows and seventeen
unclosed trade records. Neither proves an external process has exited or proves
current on-chain holdings. The earlier B1 classifier intentionally leaves every
legacy run archive-ineligible. A new workflow must retain the exact evidence
used for a decision, distinguish historical rows from actual exposure, and make
stale approvals unusable without rewriting the old economic history.

This component records a **trusted operator attestation** of external evidence.
It does not independently contact Railway, enumerate processes, inspect wallets,
verify a signature, or fetch the files represented by document hashes. Hashes
bind supplied evidence; they do not prove its truth. The managed attestor
credential, evidence collection/authenticity/retention procedures and actual
operator/browser flow are separate open acceptance gates.

## Capabilities and preserved authority

| Caller | Allowed operations |
|---|---|
| Separate nonprivileged attestor login, with exactly one SET-only `vn_legacy_attestor` membership | Capture a bounded owner/run snapshot; record a review under its original UUID; append an explicit review invalidation. |
| Authenticated owner derived by the existing installer-owned `auth.uid()` bridge | Read current eligibility/archive validity, append a presentation archive with an exact review ID, and page that owner's archive receipts. |
| Anonymous, service-role and authenticator sessions | No evidence API or raw-table/helper permission. Shared API logins cannot act as an attestor even if a capability is mistakenly delegated. |
| Economic and relay capability roles | No new evidence RPC, raw table, DML or maintenance permission. |
| Private NOLOGIN owner | Owns the five private evidence tables and narrowly granted functions; remains nonprivileged and receives no managed Auth grants. |

The attestor capability is NOLOGIN, NOINHERIT, NOSUPERUSER, NOBYPASSRLS,
NOCREATEROLE/NOCREATEDB/NOREPLICATION. The synthetic client is a real independent
non-admin login with one SET-only, non-ADMIN, noninherited membership. A changed
client OID/name, removed membership, NOLOGIN state or privileged client attributes
invalidates its review at subsequent checks. No usable managed attestor login or
password is issued. The review capability is deliberately an operator-wide
aggregate-review permission, not an authenticated user's arbitrary SQL claim.
The real credential's scope, finite lifetime, injection, revocation and audit
must be reviewed before any production grant.

Two installer-owned helpers are required because PostgreSQL does not let a
SELECT-only role take SHARE locks, and preserved public RLS policies directly
call managed `auth.uid()`. `vn_identity.lock_legacy_evidence()` takes exactly the
five fixed table locks; `vn_identity.legacy_rows(owner,run)` returns bounded
owner/run aggregates and row digests with explicit predicates. It accepts no
SQL, table name or role. Neither helper is exposed to API or attestor roles.
The classifier is created under existing limited-installer authority using its
existing Auth access, with unchanged owner/run filters and bounded response. Its
schema's temporary CREATE/USAGE grant is removed. Trigger installation likewise
uses temporary schema/function permissions that are revoked before commit.
Managed Auth ACLs remain unchanged. This proves composition under a distinct
actual non-superuser `postgres` login; managed provider hooks remain untested.
[PostgreSQL LOCK privileges](https://www.postgresql.org/docs/17/sql-lock.html),
[Supabase managed role limitations](https://supabase.com/docs/guides/database/postgres/roles-superuser).

## Exact evidence identity and finite documents

A captured snapshot binds version 1, provenance `legacy`, original owner and
non-null run IDs, a monotonically increasing global revision, all five retained
table row counts and SHA-256 digests, exact open trade IDs and unresolved-link
counts. Rows are sorted by immutable row ID, hashed individually, then aggregated
in that order. UTC, ISO dates and full float output are fixed in the aggregate
reader so caller display settings cannot change a row digest. This preserves
legacy float evidence without converting it into v5 decimal accounting.

Snapshot limits are 50,000 rows, 32 MiB of serialized retained evidence,
128 KiB per row and 200 open trade records. Digests do not return raw genomes,
metrics, trades or another owner's rows. A genuinely unbound legacy group stays
unavailable to this archive workflow; no synthetic run ID is assigned. Orphan
groups with real run IDs can be reviewed but retain their relationship warning.

Review documents have exact keys, version/provenance/owner/run binding, at most
64 KiB, 1–32 distinct writer identities and at most 200 exposures. They require:

1. A hashed writer inventory, external drain evidence, observation time and each
   writer's release identity, drain-receipt digest and reviewed drained state.
2. Hashed reconciliation evidence, an observation at or after drain, and an
   explicitly declared review of legacy records **and external exposure**.
3. Exactly one disposition for every retained unclosed trade ID. Missing,
   duplicated or foreign IDs fail. Additional external exposure may be listed
   with no legacy trade ID.
4. `resolved`, `retained` or `unknown_retained` dispositions with bounded notes
   and evidence digests. Retained/uncertain exposure remains a visible warning;
   even all-resolved records never set `live_holdings_verified=true` or assert
   v5 cash, currency, sampling, ancestry or restoration authority.
5. UTC timestamps, no future observations, at most 24 hours since drain and an
   expiry strictly in the future but no later than 24 hours after drain.

An empty object, stopped status, no open rows, missing lease or caller boolean
cannot substitute for the document. A document's valid shape is only the
database contract; the separately trusted attestor remains responsible for the
actual inventory completeness and evidence authenticity.

## Durable invalidation, locks and acknowledgment

Five AFTER STATEMENT triggers, enabled ALWAYS, increment one private revision
and append an audit record for INSERT, UPDATE, DELETE or TRUNCATE. Zero-row and
other-owner statements invalidate conservatively. A write followed by a write
restoring the same values does not revive the original evidence. A rolled-back
write rolls back its revision/audit record too. ALWAYS covers replica-mode DML;
it cannot stop an administrator disabling triggers or altering private objects.
[PostgreSQL trigger semantics](https://www.postgresql.org/docs/17/sql-createtrigger.html).

Evidence operations lock the five legacy tables in fixed order, then serialize
on the private revision row. This prevents row mutation between snapshot
validation and archive commit. A held old writer fails within the 500 ms lock
bound; no partial archive is stored. A successful archive holds the writer until
commit, and a later write invalidates that archive's current visibility. Calls
require read-committed transactions and an already-set nonzero statement timeout
of at most eight seconds. A function-local timeout is not used as a claim that
the current statement is bounded. The owned client also has a finite outer
deadline. Repeatable-read snapshots established before the lock are refused.
[PostgreSQL snapshot and lock ordering](https://www.postgresql.org/docs/17/sql-lock.html),
[transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html).

The hash-pinned B1 catalog oracle plus a new private-contract inventory check
roles, API ancestor memberships, table/column grants, RLS/policies, defaults,
triggers, dependencies, helper bodies/ACLs, evidence table constraints/indexes,
schema ownership and capability OIDs. Relevant drift fails closed. The fixture
captures this baseline only after independently reviewed B1 retirement and
known-source installation; automatic capture is not human approval of an unknown
production catalog. This does **not** detect every unobserved administrator
change that is later reverted, indirect dynamic-SQL path or external credential.
Review invalidations must accompany operational evidence withdrawal, credential
retirement and administrative authority changes. Durable DDL/grant audit and
unobserved change/regrant semantics require deeper acceptance before production.

Reviews, explicit invalidations and archive acknowledgments are append-only
through their exposed capabilities. A request UUID is immutable within its
operation kind; owner/run/document/attestor identity conflicts fail. The same
committed request returns the identical original receipt after a lost reply,
expiry or data change. That receipt is **not renewed eligibility**. Current
status separately reports `archive_recorded`, `archived` and
`archive_invalidated`; only current valid evidence permits hiding a run. A
catalog error/unavailable status must leave the run visible with an uncertainty
warning in the future browser integration. New reviewed evidence can append a
new archive while preserving all earlier receipts and warnings.

Three explicit indexes support owner/run review discovery, review invalidation
lookup and monotonically sequenced owner/run archive pages. Pages accept 1–100
rows and a nonnegative sequence cursor. Global sequence gaps can belong to other
owners; returned rows remain owner/run filtered. Raw review documents and global
change/invalidations tables are private. There is no delete, liquidation,
balance rewrite, generation backfill or automatic restore operation.

## Acceptance, rollback and remaining work

The real PostgreSQL fixture reconstructs the captured public legacy catalog,
installs the unchanged canonical v5 component as limited `postgres`, and composes
retirement/evidence in one transaction. Bootstrap alone uses a disposable test
administrator. There are no real application env files, passwords, CA files,
provider requests, exposed ports or external network.

Thirty-four focused cases cover managed Auth/least-privilege preservation,
two owners/anonymous/shared API/attestor denial, non-destructive archive/history,
original-ID replay, malformed/stale/oversized evidence, complete open-record
coverage, external retained exposure, stable hashes, unbound/orphan treatment,
row/replica/TRUNCATE/zero-row/other-owner invalidation, rollback, private/helper/
policy/grant/capability drift, finite pages and actual writer/archive lock races.
The previous 25 retirement and 31 canonical-v5 cases run as dependencies. The
full ordinary worker regression and immutable release evidence are recorded in
the preflight/PR. No frontend or selected service behavior changes here.

Code rollback for this inert release is a reviewed revert. A failed combined
installation rolls back its legacy revocations, trigger additions, new role and
schema together. After future acknowledged v5 economics, rollback must preserve
journals, projections, legacy rows and evidence receipts, close admission/drain
and keep legacy writes denied. Dropping evidence or granting old writers back is
not the eventual additive rollback plan.

**Next B2D2:** compose all fresh/native/legacy components into a reviewed complete
forward candidate and manifest; independently check migration history, catalog,
locks and committed postconditions; rehearse old/new overlap and additive
rollback after acknowledged v5 commands. Keep it outside production until D3C
and A3 acceptance. Actual managed issuer/CA/IPv6/native-session acceptance and
private credential injection remain B2C3B, with Railway service/budget decisions
separately scoped. No account action is needed for this local evidence proof.

**Deep substantial research remains:** external writer inventory and receipt
authenticity (including restart/redeploy/credential access), wallet/transaction
reconciliation without guessed legacy accounting, permanent administrative
grant/DDL-change audit, managed attestor scope/revocation/lifetime, evidence and
unclosed-history retention, complete catalog/indirect dependency closure,
bounded snapshot/query/lock/transaction/storage costs, multi-owner contention,
and integration behavior on invalid or unavailable archive status. Local bounds
and synthetic receipts are not measurements or proof of hosted operations.
